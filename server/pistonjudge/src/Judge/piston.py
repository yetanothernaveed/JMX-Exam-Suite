"""Piston transport and per-language execution limits.

This module knows how to talk to Piston and how to turn a Piston response into
a small :class:`RunResult`. It does not know how any individual question is
judged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import requests

PISTON_URL = os.getenv(
    "PISTON_URL",
    "http://localhost:2000/api/v2/execute",
)
PISTON_REQUEST_TIMEOUT_SECONDS = 120

BASE_CPU_TIMEOUT_MS = 2_000
BASE_WALL_TIMEOUT_MS = 3_000
BASE_MEMORY_LIMIT_MB = 128


class PistonError(RuntimeError):
    """Raised when Piston cannot be reached or returns an unusable response."""


class CompilationError(PistonError):
    """Raised when the submission does not compile."""

    def __init__(self, details: str):
        self.details = details.strip() or "Compilation failed."
        super().__init__(self.details)


def _compile_error_details(compile_result: dict) -> str:
    """Return the most useful message from a failed Piston compile stage."""
    details = (
        compile_result.get("stderr")
        or compile_result.get("stdout")
        or compile_result.get("message")
        or ""
    ).strip()
    if details:
        return details

    status = (compile_result.get("status") or "").strip().upper()
    signal = (compile_result.get("signal") or "").strip()
    if status == "TO":
        return "Compilation timed out."
    if signal:
        return f"Compilation terminated by {signal}."
    return "Compilation failed."


@dataclass(frozen=True)
class LanguageProfile:
    """Scaling factors applied to the baseline limits for one language."""

    cpu_factor: float
    wall_factor: float
    memory_factor: float
    memory_pad_mb: int


# The same limits are used for every question unless a question judge overrides
# ``BaseJudge.get_limits``.
LANGUAGE_PROFILES = {
    "c++": LanguageProfile(cpu_factor=1.0, wall_factor=2.0, memory_factor=1.0, memory_pad_mb=0),
    "java": LanguageProfile(cpu_factor=2.0, wall_factor=3.0, memory_factor=1.5, memory_pad_mb=32),
    "python": LanguageProfile(cpu_factor=3.5, wall_factor=4.5, memory_factor=3.0, memory_pad_mb=128),
}


@dataclass(frozen=True)
class RunLimits:
    cpu_timeout_ms: int
    wall_timeout_ms: int
    memory_limit_bytes: int


def language_limits(
    language: str,
    profiles: dict[str, LanguageProfile] | None = None,
) -> RunLimits:
    """Return the effective limits for ``language``.

    Raises:
        ValueError: If the language has no configured profile.
    """
    profiles = profiles or LANGUAGE_PROFILES
    try:
        profile = profiles[language]
    except KeyError as exc:
        supported = ", ".join(sorted(profiles))
        raise ValueError(
            f"Unsupported language {language!r}. Supported languages: {supported}."
        ) from exc

    memory_mb = (
        BASE_MEMORY_LIMIT_MB * profile.memory_factor + profile.memory_pad_mb
    )
    return RunLimits(
        cpu_timeout_ms=int(BASE_CPU_TIMEOUT_MS * profile.cpu_factor),
        wall_timeout_ms=int(BASE_WALL_TIMEOUT_MS * profile.wall_factor),
        memory_limit_bytes=int(memory_mb * 10**6),
    )


@dataclass(frozen=True)
class RunResult:
    """The parts of Piston's ``run`` response that the judge needs.

    ``status`` and ``message`` are Piston's own termination report, for example
    ``"TO"`` / ``"Time limit exceeded (wall clock)"`` or ``"RE"`` /
    ``"Exited with error status 137"``. They are kept because they are the most
    reliable evidence that a process was stopped, independent of any partial
    output that happened to be flushed before it was killed.
    """

    stdout: str
    stderr: str
    exit_code: int
    signal: str
    cpu_time_ms: float
    wall_time_ms: float
    memory_bytes: int
    status: str = ""
    message: str = ""

    @classmethod
    def from_piston(cls, run: dict) -> "RunResult":
        exit_code = run.get("code")
        return cls(
            stdout=run.get("stdout") or "",
            stderr=run.get("stderr") or "",
            exit_code=int(exit_code) if exit_code is not None else -1,
            signal=run.get("signal") or "",
            cpu_time_ms=float(run.get("cpu_time") or 0),
            wall_time_ms=float(run.get("wall_time") or 0),
            memory_bytes=int(run.get("memory") or 0),
            status=run.get("status") or "",
            message=run.get("message") or "",
        )


def execute_submission(
    submission_code: str,
    wrapper_file: str,
    input_data: str,
    language: str,
    limits: RunLimits,
    input_file_name: str = "input.in",
) -> RunResult:
    """Compile and run ``submission_code`` inside its wrapper on Piston.

    For compiled languages, Piston reports a separate ``compile`` stage. A
    failed compile stage is authoritative: it is raised as ``CompilationError``
    before the ``run`` result is inspected. Piston v2 copies the compile result
    into ``run`` when compilation fails, so checking ``compile`` first is what
    keeps compile errors from being mistaken for runtime errors.

    Interpreted languages such as Python have no ``compile`` key. Their failures
    are run-stage failures and are returned as a normal :class:`RunResult`.

    Raises:
        CompilationError: If Piston reports a compiler failure.
        PistonError: If the request fails or the response is malformed.
    """
    try:
        wrapper_code = Path(wrapper_file).read_text(encoding="utf-8")
    except OSError as exc:
        raise PistonError(f"Could not read wrapper file {wrapper_file!r}: {exc}") from exc

    if "/*SUBMISSION_CODE*/" not in wrapper_code:
        raise PistonError(
            f"Wrapper file {wrapper_file!r} does not contain the "
            "'/*SUBMISSION_CODE*/' placeholder."
        )

    code = wrapper_code.replace("/*SUBMISSION_CODE*/", submission_code, 1)

    # Name the Piston source file after the wrapper template. Questions that
    # use ``Main.<ext>`` keep the historical ``Main`` source name, while a
    # question that supplies ``Q111.<ext>`` gets a ``Q111`` source file. This
    # matters for Java, where a ``public class Q111`` must live in Q111.java.
    source_name = Path(wrapper_file).stem
    payload = {
        "language": language,
        "version": "*",
        "files": [
            {"name": source_name, "content": code},
            # Question wrappers or submissions open this file explicitly.
            # Piston's stdin field is not used because it truncates large
            # inputs, so test data is always delivered as a file.
            {"name": input_file_name, "content": input_data},
        ],
        "run_timeout": limits.wall_timeout_ms,
        "run_cpu_timeout": limits.cpu_timeout_ms,
        "run_memory_limit": limits.memory_limit_bytes,
    }

    try:
        response = requests.post(
            PISTON_URL,
            json=payload,
            timeout=PISTON_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        piston_response = response.json()
    except requests.RequestException as exc:
        raise PistonError(f"Error while communicating with the Piston API: {exc}") from exc
    except ValueError as exc:
        raise PistonError("The Piston API returned a response that was not valid JSON.") from exc

    if not isinstance(piston_response, dict):
        raise PistonError("The Piston API returned an unexpected response.")

    compile_result = piston_response.get("compile")
    if compile_result is not None and not isinstance(compile_result, dict):
        raise PistonError("The Piston API response contained a malformed compile result.")

    # Piston uses ``compile.code !== 0`` to decide whether compilation failed.
    # A missing/None code means the compile stage did not complete (for example,
    # it timed out or was killed), so it must not be treated as a success.
    if isinstance(compile_result, dict) and compile_result.get("code") != 0:
        raise CompilationError(_compile_error_details(compile_result))

    run = piston_response.get("run")
    if not isinstance(run, dict):
        raise PistonError("The Piston API response did not contain a run result.")

    return RunResult.from_piston(run)
