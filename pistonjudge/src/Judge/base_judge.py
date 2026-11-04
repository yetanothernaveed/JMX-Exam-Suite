"""Shared judging pipeline.

A question judge only needs to decide how two output values are compared.
Everything else -- loading testcases, executing on Piston, parsing output,
scoring, and mapping failures to verdicts -- lives here.
"""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
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
    CaseResult,
    Verdict,
    format_case_scores,
    format_mismatch,
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

    # Optional per-case points. When None, every case is worth
    # ``MAX_SCORE / total_cases``. A question judge may set a sequence with one
    # value per test case; the values must sum to ``MAX_SCORE``.
    case_scores: Sequence[float] | None = None

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
        """Compare output and score each test case separately.

        The run is a single Piston execution containing every test case. Cases
        are scored in order; the first wrong answer or resource failure stops
        scoring, and later cases receive no points.
        """
        total_cases = len(expected_results)
        try:
            case_scores = self.get_case_scores(total_cases)
        except ValueError as exc:
            return self._result(
                Verdict.SYSTEM_ERROR,
                0.0,
                f"Judge configuration error: {exc}",
            )

        actual_lines = run.stdout.splitlines()

        # Resource failures must be classified before any output is compared.
        # A process that was killed can leave a complete-looking prefix, or even
        # a cut-off final line, on stdout. Grading that partial output would
        # turn a timeout into a wrong answer. Piston's own status/message and
        # the measured resource usage are the authoritative evidence here.
        resource_verdict = self._resource_failure_verdict(run, limits)
        if resource_verdict is not None:
            passed = self._passing_prefix(
                actual_lines, expected_results, case_scores, total_cases
            )
            return self._resource_failure_result(
                run,
                limits,
                resource_verdict,
                passed,
                total_cases,
                case_scores,
            )

        if len(actual_lines) > total_cases:
            return self._result(
                Verdict.WRONG_ANSWER,
                0.0,
                f"The program produced {len(actual_lines)} output lines for "
                f"{total_cases} test cases.",
            )

        passed: list[CaseResult] = []
        for index, line in enumerate(actual_lines):
            try:
                actual = self.parse_result(line)
            except (ValueError, TypeError) as exc:
                # A cut-off line from a process that was terminated is not a
                # wrong answer. Let the termination be classified instead.
                if run.signal or run.exit_code != 0:
                    return self._classify_failure(
                        run, passed, total_cases, limits, case_scores
                    )
                return self._failure_at(
                    passed=passed,
                    index=index,
                    verdict=Verdict.WRONG_ANSWER,
                    details=f"Could not parse the program output for test case "
                    f"{index + 1}: {exc}",
                    case_scores=case_scores,
                    total_cases=total_cases,
                )

            if not self.compare_output(actual, expected_results[index]):
                return self._failure_at(
                    passed=passed,
                    index=index,
                    verdict=Verdict.WRONG_ANSWER,
                    details=format_mismatch(actual, expected_results[index], index + 1),
                    case_scores=case_scores,
                    total_cases=total_cases,
                )

            passed.append(
                CaseResult(
                    number=index + 1,
                    verdict=Verdict.ACCEPTED,
                    score=case_scores[index],
                    max_score=case_scores[index],
                )
            )

        if run.signal or run.exit_code != 0:
            return self._classify_failure(
                run, passed, total_cases, limits, case_scores
            )

        if len(passed) < total_cases:
            return self._failure_at(
                passed=passed,
                index=len(passed),
                verdict=Verdict.WRONG_ANSWER,
                details=f"The program exited before producing output for "
                f"test case {len(passed) + 1} of {total_cases}.",
                case_scores=case_scores,
                total_cases=total_cases,
            )

        return self._result(
            Verdict.ACCEPTED,
            round(sum(case_scores), 2),
            f"Passed all {total_cases} test cases in {run.cpu_time_ms:.1f} ms "
            f"CPU time, {run.wall_time_ms:.1f} ms wall time, using "
            f"{run.memory_bytes / 10**6:.1f} MB of memory.\n"
            f"{format_case_scores(passed, total_cases)}",
        )

    def get_case_scores(self, total_cases: int) -> list[float]:
        """Return the point value of each test case.

        By default, every case is worth ``MAX_SCORE / total_cases``. A question
        judge may set ``case_scores`` to a sequence with one value per test
        case; the values must sum to ``MAX_SCORE``.
        """
        if total_cases <= 0:
            raise ValueError("There must be at least one test case.")

        if self.case_scores is None:
            return [MAX_SCORE / total_cases] * total_cases

        scores = [float(value) for value in self.case_scores]
        if len(scores) != total_cases:
            raise ValueError(
                f"case_scores has {len(scores)} entries, but there are "
                f"{total_cases} test cases."
            )
        if any(score < 0 for score in scores):
            raise ValueError("case_scores cannot contain negative values.")

        total = sum(scores)
        if not math.isclose(total, MAX_SCORE, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                f"case_scores must sum to {MAX_SCORE:g}, got {total:.2f}."
            )
        return scores

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

    def _passing_prefix(
        self,
        actual_lines: list[str],
        expected_results: list[Any],
        case_scores: list[float],
        total_cases: int,
    ) -> list[CaseResult]:
        """Return complete output lines that match, stopping at the first miss.

        Only lines that were fully written before the process was stopped can
        earn credit. A missing or cut-off line is simply the failing case; it is
        never interpreted as a wrong answer.
        """
        passed: list[CaseResult] = []
        for index in range(min(len(actual_lines), total_cases)):
            try:
                actual = self.parse_result(actual_lines[index])
            except (ValueError, TypeError):
                break
            if not self.compare_output(actual, expected_results[index]):
                break
            passed.append(
                CaseResult(
                    number=index + 1,
                    verdict=Verdict.ACCEPTED,
                    score=case_scores[index],
                    max_score=case_scores[index],
                )
            )
        return passed

    def _resource_failure_result(
        self,
        run: RunResult,
        limits: RunLimits,
        verdict: str,
        passed: list[CaseResult],
        total_cases: int,
        case_scores: list[float],
    ) -> JudgeResult:
        """Return a resource-failure result using only the completed prefix."""
        completed_cases = len(passed)
        if completed_cases < total_cases:
            location = f"test case {completed_cases + 1}"
        else:
            location = "the final test case"

        if verdict == Verdict.TIME_LIMIT_EXCEEDED:
            details = self._time_limit_details(run, limits, location)
        else:
            details = (
                f"Memory limit exceeded on {location}. Used "
                f"{run.memory_bytes / 10**6:.1f} MB of the "
                f"{limits.memory_limit_bytes / 10**6:.1f} MB limit."
            )
            stderr = run.stderr.strip()
            if stderr:
                details = f"{details} {_truncate(stderr)}"

        return self._failure_or_discard(
            verdict,
            details,
            passed,
            total_cases,
            case_scores,
        )

    @classmethod
    def _resource_failure_verdict(
        cls,
        run: RunResult,
        limits: RunLimits,
    ) -> str | None:
        """Classify a stopped run from Piston's report before grading output.

        Explicit timeout evidence wins over memory evidence because Piston
        reports ``status == "TO"`` when it stopped the process at a time limit.
        A kill signal with no time evidence and memory at the limit is an
        out-of-memory kill, even when Piston reports it as ``"RE"`` with exit
        code 137 and an empty signal.
        """
        if cls._time_limit_exceeded(run):
            return Verdict.TIME_LIMIT_EXCEEDED
        if any(marker in run.stderr for marker in MEMORY_ERROR_MARKERS):
            return Verdict.MEMORY_LIMIT_EXCEEDED
        if (
            run.cpu_time_ms + 100 >= limits.cpu_timeout_ms # Add 100ms buffer to account for measurement inaccuracies
            or run.wall_time_ms + 100 >= limits.wall_timeout_ms
        ):
            return Verdict.TIME_LIMIT_EXCEEDED
        if cls._is_memory_limit_exceeded(run, limits):
            return Verdict.MEMORY_LIMIT_EXCEEDED
        if run.signal in KILL_SIGNALS:
            return Verdict.TIME_LIMIT_EXCEEDED
        return None

    @staticmethod
    def _time_limit_exceeded(run: RunResult) -> bool:
        """Return True when Piston explicitly reported a timeout."""
        status = run.status.strip().upper()
        message = run.message.strip().lower()
        return (
            status == "TO"
            or "time limit exceeded" in message
            or "timed out" in message
        )

    def _classify_failure(
        self,
        run: RunResult,
        passed: list[CaseResult],
        total_cases: int,
        limits: RunLimits,
        case_scores: list[float],
    ) -> JudgeResult:
        """Classify a failure that happened while the program was running.

        Compile-stage failures never reach this method: ``execute_submission``
        raises ``CompilationError`` and ``submit`` returns a
        ``COMPILATION ERROR`` before any test case is evaluated.
        """
        completed_cases = len(passed)
        if completed_cases < total_cases:
            location = f"test case {completed_cases + 1}"
        else:
            location = "the final test case"

        stderr = run.stderr.strip()

        if self._is_memory_limit_exceeded(run, limits):
            details = (
                f"Memory limit exceeded on {location}. Used "
                f"{run.memory_bytes / 10**6:.1f} MB of the "
                f"{limits.memory_limit_bytes / 10**6:.1f} MB limit."
            )
            if stderr:
                details = f"{details} {_truncate(stderr)}"
            return self._failure_or_discard(
                Verdict.MEMORY_LIMIT_EXCEEDED,
                details,
                passed,
                total_cases,
                case_scores,
            )

        if run.signal in KILL_SIGNALS:
            return self._failure_or_discard(
                Verdict.TIME_LIMIT_EXCEEDED,
                self._time_limit_details(run, limits, location),
                passed,
                total_cases,
                case_scores,
            )

        if run.signal:
            details = f"Runtime error on {location}: process terminated by {run.signal}."
            if stderr:
                details = f"{details} {_truncate(stderr)}"
            return self._failure_or_discard(
                Verdict.RUNTIME_ERROR,
                details,
                passed,
                total_cases,
                case_scores,
            )

        if run.exit_code != 0:
            details = stderr or f"Process exited with code {run.exit_code}."
            return self._failure_or_discard(
                Verdict.RUNTIME_ERROR,
                f"Runtime error on {location}: {_truncate(details)}",
                passed,
                total_cases,
                case_scores,
            )

        return self._failure_or_discard(
            Verdict.SYSTEM_ERROR,
            f"The program stopped unexpectedly on {location}.",
            passed,
            total_cases,
            case_scores,
        )

    def _failure_at(
        self,
        passed: list[CaseResult],
        index: int,
        verdict: str,
        details: str,
        case_scores: list[float],
        total_cases: int,
    ) -> JudgeResult:
        """Return a result for the first failing case at zero-based ``index``."""
        failed = CaseResult(
            number=index + 1,
            verdict=verdict,
            score=0.0,
            max_score=case_scores[index],
        )
        evaluated = passed + [failed]
        score = round(sum(case_scores[: len(passed)]), 2)
        return self._result(
            verdict,
            score,
            f"{details}\n{format_case_scores(evaluated, total_cases)}",
        )

    def _failure_or_discard(
        self,
        verdict: str,
        details: str,
        passed: list[CaseResult],
        total_cases: int,
        case_scores: list[float],
    ) -> JudgeResult:
        """Score the passing prefix, or discard everything if all cases ran."""
        if len(passed) < total_cases:
            return self._failure_at(
                passed,
                len(passed),
                verdict,
                details,
                case_scores,
                total_cases,
            )
        return self._result(
            verdict,
            0.0,
            f"{details} All case scores were discarded.",
        )

    @staticmethod
    def _is_memory_limit_exceeded(run: RunResult, limits: RunLimits) -> bool:
        if any(marker in run.stderr for marker in MEMORY_ERROR_MARKERS):
            return True
        return (
            run.memory_bytes >= limits.memory_limit_bytes
            and (
                run.signal in KILL_SIGNALS
                or run.exit_code in (137, -9)
            )
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
