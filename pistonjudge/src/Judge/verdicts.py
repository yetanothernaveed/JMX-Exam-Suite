"""Canonical verdict labels and scoring helpers shared by all judges."""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class CaseResult:
    """The scored outcome of one test case."""

    number: int
    verdict: str
    score: float
    max_score: float


def format_case_scores(results: list[CaseResult], total_cases: int) -> str:
    """Format per-case scores as a compact, aligned table."""
    if not results:
        return "Test case scores: no cases were scored."

    rows: list[tuple[str, str, str]] = []
    for result in results:
        outcome = "PASS" if result.verdict == Verdict.ACCEPTED else result.verdict
        rows.append(
            (
                str(result.number),
                outcome,
                f"{result.score:.2f} / {result.max_score:.2f}",
            )
        )

    unscored = total_cases - len(results)
    if unscored == 1:
        rows.append((str(total_cases), "NOT SCORED", "-"))
    elif unscored > 1:
        rows.append((f"{len(results) + 1}-{total_cases}", "NOT SCORED", "-"))

    header = ("Case", "Verdict", "Points")
    widths = [max(len(row[column]) for row in (header, *rows)) for column in range(3)]
    lines = [
        "Test case scores:",
        f"  {header[0]:<{widths[0]}}  {header[1]:<{widths[1]}}  {header[2]}",
        f"  {'-' * widths[0]}  {'-' * widths[1]}  {'-' * widths[2]}",
    ]
    lines.extend(
        f"  {number:<{widths[0]}}  {outcome:<{widths[1]}}  {points}"
        for number, outcome, points in rows
    )
    return "\n".join(lines)


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
