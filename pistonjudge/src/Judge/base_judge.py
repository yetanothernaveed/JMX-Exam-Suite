"""Shared judging pipeline.

A question judge only needs to decide how two output values are compared.
Everything else -- loading testcases, executing on Piston, parsing output,
scoring, and mapping failures to verdicts -- lives here.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, TypedDict

from .piston import (
    LANGUAGE_PROFILES,
    CompilationError,
    PistonError,
    RunLimits,
    RunResult,
    execute_submission,
    language_limits,
)
from .testcases import TestcaseError, load_testcases
from .verdicts import (
    MAX_SCORE,
    Verdict,
    format_mismatch,
    score_for_passed,
)

logger = logging.getLogger(__name__)

KILL_SIGNALS = frozenset({"SIGKILL", "SIGTERM"})
MEMORY_ERROR_MARKERS = (
    "OutOfMemoryError",
    "java.lang.OutOfMemoryError",
    "MemoryError",
    "std::bad_alloc",
    "bad_alloc",
    "Out of memory",
    "out of memory",
    "memory limit exceeded",
)


class JudgeResult(TypedDict):
    verdict: str
    score: float
    details: str


class BaseJudge(ABC):
    """Template for all question judges."""

    # Questions may override this dict when a language needs different limits.
    language_profiles = LANGUAGE_PROFILES

    def submit(
        self,
        submission_code: str,
        wrapper_file_path: str,
        input_file_path: str,
        output_file_path: str,
        language: str,
    ) -> JudgeResult:
        """Run and judge one submission.

        Infrastructure problems are returned as ``SYSTEM_ERROR`` results rather
        than raised, so the server always receives a complete verdict.
        """
        try:
            limits = self.get_limits(language)
            testcases = load_testcases(input_file_path, output_file_path)
        except (TestcaseError, ValueError, OSError) as exc:
            logger.exception("Judge infrastructure error")
            return self._result(
                Verdict.SYSTEM_ERROR,
                0.0,
                f"Judge system error: {exc}",
            )

        expected_results: list[Any] = []
        for case in testcases.cases:
            try:
                expected_results.append(self.parse_result(case.expected_text))
            except (ValueError, TypeError) as exc:
                return self._result(
                    Verdict.SYSTEM_ERROR,
                    0.0,
                    f"Could not parse expected output for test case "
                    f"{case.number}: {exc}",
                )

        try:
            run = execute_submission(
                submission_code=submission_code,
                wrapper_file=wrapper_file_path,
                input_data=testcases.piston_input,
                language=language,
                limits=limits,
            )
        except CompilationError as exc:
            return self._result(Verdict.COMPILATION_ERROR, 0.0, exc.details)
        except (PistonError, ValueError, OSError, KeyError, TypeError) as exc:
            logger.exception("Judge infrastructure error")
            return self._result(
                Verdict.SYSTEM_ERROR,
                0.0,
                f"Judge system error: {exc}",
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            logger.exception("Unexpected judge error")
            return self._result(
                Verdict.SYSTEM_ERROR,
                0.0,
                f"Unexpected judge error: {exc}",
            )

        return self.evaluate(run, expected_results, limits)

    def evaluate(
        self,
        run: RunResult,
        expected_results: list[Any],
        limits: RunLimits,
    ) -> JudgeResult:
        """Compare output and classify a completed or failed run."""
        total_cases = len(expected_results)
        actual_lines = run.stdout.splitlines()

        if len(actual_lines) > total_cases:
            return self._result(
                Verdict.WRONG_ANSWER,
                0.0,
                f"The program produced {len(actual_lines)} output lines for "
                f"{total_cases} test cases.",
            )

        actual_results: list[Any] = []
        for index, line in enumerate(actual_lines):
            try:
                actual_results.append(self.parse_result(line))
            except (ValueError, TypeError) as exc:
                return self._result(
                    Verdict.WRONG_ANSWER,
                    score_for_passed(index, total_cases),
                    f"Could not parse the program output for test case "
                    f"{index + 1}: {exc}",
                )

        completed_cases = len(actual_results)

        # A cleanly exited program that exceeded a resource limit is a TLE even
        # if it managed to print every answer.
        if run.exit_code == 0 and not run.signal:
            if run.cpu_time_ms >= limits.cpu_timeout_ms:
                return self._result(
                    Verdict.TIME_LIMIT_EXCEEDED,
                    0.0,
                    self._time_limit_details(run, limits, "after the final test case"),
                )
            if run.wall_time_ms >= limits.wall_timeout_ms:
                return self._result(
                    Verdict.TIME_LIMIT_EXCEEDED,
                    0.0,
                    self._time_limit_details(run, limits, "after the final test case"),
                )

        # Check the output that was produced before deciding why the program
        # stopped. A wrong answer before a crash is still a wrong answer.
        for index, (actual, expected) in enumerate(
            zip(actual_results, expected_results)
        ):
            if not self.compare_output(actual, expected):
                return self._result(
                    Verdict.WRONG_ANSWER,
                    score_for_passed(index, total_cases),
                    format_mismatch(actual, expected, index + 1),
                )

        if run.signal or run.exit_code != 0:
            return self._classify_failure(run, completed_cases, total_cases, limits)

        if completed_cases < total_cases:
            return self._result(
                Verdict.WRONG_ANSWER,
                score_for_passed(completed_cases, total_cases),
                f"The program exited before producing output for test case "
                f"{completed_cases + 1} of {total_cases}.",
            )

        return self._result(
            Verdict.ACCEPTED,
            MAX_SCORE,
            f"Passed all {total_cases} test cases in {run.cpu_time_ms:.1f} ms "
            f"CPU time, {run.wall_time_ms:.1f} ms wall time, using "
            f"{run.memory_bytes / 10**6:.1f} MB of memory.",
        )

    def parse_result(self, text: str) -> Any:
        """Parse one testcase result.

        The same parser is used for expected output and for the corresponding
        line of wrapper stdout. Override it for non-string output types.
        """
        return text

    @abstractmethod
    def compare_output(self, actual: Any, expected: Any) -> bool:
        """Return True when one testcase's output is correct."""

    def get_limits(self, language: str) -> RunLimits:
        """Return the execution limits for ``language``.

        Override ``language_profiles`` or this method to give a specific
        question different limits.
        """
        return language_limits(language, self.language_profiles)

    def _classify_failure(
        self,
        run: RunResult,
        completed_cases: int,
        total_cases: int,
        limits: RunLimits,
    ) -> JudgeResult:
        if completed_cases < total_cases:
            location = f"test case {completed_cases + 1}"
            score = score_for_passed(completed_cases, total_cases)
        else:
            location = "after the final test case"
            score = 0.0

        stderr = run.stderr.strip()

        if self._is_memory_limit_exceeded(run, limits):
            details = (
                f"Memory limit exceeded on {location}. Used "
                f"{run.memory_bytes / 10**6:.1f} MB of the "
                f"{limits.memory_limit_bytes / 10**6:.1f} MB limit."
            )
            if stderr:
                details = f"{details} {_truncate(stderr)}"
            return self._result(Verdict.MEMORY_LIMIT_EXCEEDED, score, details)

        if run.signal in KILL_SIGNALS:
            return self._result(
                Verdict.TIME_LIMIT_EXCEEDED,
                score,
                self._time_limit_details(run, limits, location),
            )

        if run.signal:
            details = f"Runtime error on {location}: process terminated by {run.signal}."
            if stderr:
                details = f"{details} {_truncate(stderr)}"
            return self._result(Verdict.RUNTIME_ERROR, score, details)

        if run.exit_code != 0:
            details = stderr or f"Process exited with code {run.exit_code}."
            return self._result(
                Verdict.RUNTIME_ERROR,
                score,
                f"Runtime error on {location}: {_truncate(details)}",
            )

        return self._result(
            Verdict.SYSTEM_ERROR,
            score,
            f"The program stopped unexpectedly on {location}.",
        )

    @staticmethod
    def _is_memory_limit_exceeded(run: RunResult, limits: RunLimits) -> bool:
        if any(marker in run.stderr for marker in MEMORY_ERROR_MARKERS):
            return True
        return (
            run.signal in KILL_SIGNALS
            and run.memory_bytes >= limits.memory_limit_bytes
        )

    @staticmethod
    def _time_limit_details(
        run: RunResult,
        limits: RunLimits,
        location: str,
    ) -> str:
        return (
            f"Time limit exceeded on {location} "
            f"({run.cpu_time_ms:.1f} ms CPU, {run.wall_time_ms:.1f} ms wall; "
            f"limits are {limits.cpu_timeout_ms} ms CPU and "
            f"{limits.wall_timeout_ms} ms wall)."
        )

    @staticmethod
    def _result(verdict: str, score: float, details: str) -> JudgeResult:
        return {
            "verdict": verdict,
            "score": score,
            "details": details,
        }


def _truncate(text: str, limit: int = 2_000) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... (truncated)"
