"""Testcase loading for the ``@@CASE-n`` file format.

Both ``tc.in`` and ``tc.out`` use the same framing:

    @@CASE-1
    <content for test case 1>
    @@CASE-2
    <content for test case 2>

A case with no content is represented by placing the next marker immediately
after the current marker. Markers must be numbered ``1..N`` in order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CASE_MARKER_PATTERN = re.compile(r"^@@CASE-(\d+)$")


class TestcaseError(ValueError):
    """Raised when a testcase file is missing or malformed."""


@dataclass(frozen=True)
class TestCase:
    number: int
    input_lines: tuple[str, ...]
    expected_text: str


@dataclass(frozen=True)
class TestcaseSet:
    cases: tuple[TestCase, ...]

    @property
    def count(self) -> int:
        return len(self.cases)

    @property
    def piston_input(self) -> str:
        """Return the input stream sent to the wrapper.

        The marker lines are removed and a conventional first-line testcase
        count is prepended. This keeps the existing wrapper implementations
        unchanged: they read ``t`` first and then consume each case's content.
        """
        lines = [str(self.count)]
        for case in self.cases:
            lines.extend(case.input_lines)
        return "\n".join(lines) + "\n"


def parse_int_row(text: str) -> list[int]:
    """Parse one testcase result as a whitespace-separated list of integers."""
    return [int(token) for token in text.split()]


def _read_marked_cases(text: str, path: str) -> list[tuple[int, tuple[str, ...]]]:
    cases: list[tuple[int, tuple[str, ...]]] = []
    current_number: int | None = None
    current_lines: list[str] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        match = CASE_MARKER_PATTERN.match(line.strip())
        if match:
            if current_number is not None:
                cases.append((current_number, tuple(current_lines)))
            current_number = int(match.group(1))
            current_lines = []
            continue

        if current_number is None:
            raise TestcaseError(
                f"{path}:{line_number}: expected a '@@CASE-n' marker before "
                "any testcase content."
            )
        current_lines.append(line)

    if current_number is not None:
        cases.append((current_number, tuple(current_lines)))

    if not cases:
        raise TestcaseError(f"{path}: no '@@CASE-n' markers found.")

    actual_numbers = [number for number, _ in cases]
    expected_numbers = list(range(1, len(cases) + 1))
    if actual_numbers != expected_numbers:
        raise TestcaseError(
            f"{path}: case markers must be numbered 1..{len(cases)} in order; "
            f"got {actual_numbers}."
        )

    return cases


def load_testcases(input_file_path: str, output_file_path: str) -> TestcaseSet:
    """Read and validate marker-framed ``tc.in`` and ``tc.out`` files."""
    try:
        input_text = Path(input_file_path).read_text(encoding="utf-8")
        output_text = Path(output_file_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise TestcaseError(f"Could not read testcase files: {exc}") from exc

    input_cases = _read_marked_cases(input_text, input_file_path)
    output_cases = _read_marked_cases(output_text, output_file_path)

    if len(input_cases) != len(output_cases):
        raise TestcaseError(
            f"Testcase files are inconsistent: {input_file_path} has "
            f"{len(input_cases)} cases, but {output_file_path} has "
            f"{len(output_cases)} cases."
        )

    cases = tuple(
        TestCase(
            number=input_number,
            input_lines=input_lines,
            expected_text="\n".join(expected_lines),
        )
        for (input_number, input_lines), (_, expected_lines) in zip(
            input_cases, output_cases
        )
    )
    return TestcaseSet(cases=cases)
