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
PISTON_REQUEST_TIMEOUT_SECONDS = 10

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
    """The parts of Piston's ``run`` response that the judge needs."""

    stdout: str
    stderr: str
    exit_code: int
    signal: str
    cpu_time_ms: float
    wall_time_ms: float
    memory_bytes: int

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
        )


def execute_submission(
    submission_code: str,
    wrapper_file: str,
    input_data: str,
    language: str,
    limits: RunLimits,
) -> RunResult:
    """Compile and run ``submission_code`` inside its wrapper on Piston.

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
    payload = {
        "language": language,
        "version": "*",
        "files": [
            {"name": "Main", "content": code},
            {"name": "input.in", "content": input_data},
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

    compile_result = piston_response.get("compile")
    if isinstance(compile_result, dict) and (compile_result.get("code") or 0) != 0:
        message = (compile_result.get("stderr") or compile_result.get("stdout") or "").strip()
        raise CompilationError(message)

    run = piston_response.get("run")
    if not isinstance(run, dict):
        raise PistonError("The Piston API response did not contain a run result.")

    return RunResult.from_piston(run)
