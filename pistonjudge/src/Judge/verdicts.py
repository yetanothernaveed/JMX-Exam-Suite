"""Canonical verdict labels and scoring helpers shared by all judges."""

from typing import Any

MAX_SCORE = 10.0


class Verdict:
    """String labels returned to the server.

    The labels intentionally keep the existing public values so the server and
    frontend continue to work without changes. The controller currently treats
    ``ERROR``/``UNKNOWN_ERROR`` as non-scoring infrastructure failures, so
    ``SYSTEM_ERROR`` maps to ``ERROR`` until the controller is migrated.
    """

    ACCEPTED = "ACCEPTED"
    WRONG_ANSWER = "WRONG ANSWER"
    TIME_LIMIT_EXCEEDED = "TIME LIMIT EXCEEDED"
    MEMORY_LIMIT_EXCEEDED = "MEMORY LIMIT EXCEEDED"
    RUNTIME_ERROR = "RUNTIME ERROR"
    COMPILATION_ERROR = "COMPILATION ERROR"
    SYSTEM_ERROR = "ERROR"


def score_for_passed(passed_cases: int, total_cases: int) -> float:
    """Return the score for ``passed_cases`` out of ``total_cases``."""
    if total_cases <= 0:
        return 0.0
    passed_cases = max(0, min(passed_cases, total_cases))
    return round(passed_cases * MAX_SCORE / total_cases, 2)


def format_mismatch(
    actual: Any,
    expected: Any,
    case_number: int,
    window: int = 3,
) -> str:
    """Build a small, human-readable description of the first difference.

    Large outputs must not be copied into ``details``. For lists, only a short
    window around the first differing element is shown.
    """
    if not isinstance(actual, (list, tuple)) or not isinstance(expected, (list, tuple)):
        return (
            f"Test case {case_number} failed. "
            f"Expected: {_truncate(repr(expected))}, got: {_truncate(repr(actual))}."
        )

    if len(actual) != len(expected):
        return (
            f"Test case {case_number} failed: expected {len(expected)} values, "
            f"got {len(actual)}."
        )

    for index, (actual_value, expected_value) in enumerate(zip(actual, expected)):
        if actual_value != expected_value:
            start = max(0, index - window)
            end = min(len(actual), index + window + 1)
            return (
                f"Test case {case_number} failed at index {index}: "
                f"expected {expected_value}, got {actual_value}. "
                f"Expected[{start}:{end}]={list(expected[start:end])}, "
                f"Actual[{start}:{end}]={list(actual[start:end])}."
            )

    return f"Test case {case_number} failed."


def _truncate(text: str, limit: int = 120) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... (truncated)"
