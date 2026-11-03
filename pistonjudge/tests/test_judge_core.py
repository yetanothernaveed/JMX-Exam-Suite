from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from Judge.base_judge import BaseJudge
from Judge.piston import (
    LANGUAGE_PROFILES,
    CompilationError,
    LanguageProfile,
    PistonError,
    RunLimits,
    RunResult,
    execute_submission,
    language_limits,
)
from Judge.testcases import (
    TestcaseError,
    load_testcases,
    parse_int_row,
)
from Judge.verdicts import Verdict, format_mismatch, score_for_passed


class _ListJudge(BaseJudge):
    def parse_result(self, text: str) -> list[int]:
        return parse_int_row(text)

    def compare_output(self, actual, expected) -> bool:
        return actual == expected


LIMITS = RunLimits(
    cpu_timeout_ms=1_000,
    wall_timeout_ms=2_000,
    memory_limit_bytes=100 * 10**6,
)


def _expected(rows: list[list[int]]) -> list[list[int]]:
    return rows


def _run(**overrides) -> RunResult:
    values = {
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
        "signal": "",
        "cpu_time_ms": 10.0,
        "wall_time_ms": 20.0,
        "memory_bytes": 10 * 10**6,
    }
    values.update(overrides)
    return RunResult(**values)


def _write_cases(directory: str, input_text: str, output_text: str) -> tuple[str, str]:
    input_path = Path(directory) / "tc.in"
    output_path = Path(directory) / "tc.out"
    input_path.write_text(input_text, encoding="utf-8")
    output_path.write_text(output_text, encoding="utf-8")
    return str(input_path), str(output_path)


class TestParsing(unittest.TestCase):
    def test_empty_text_parses_as_an_empty_row(self):
        self.assertEqual(parse_int_row(""), [])

    def test_whitespace_between_values_is_accepted(self):
        self.assertEqual(parse_int_row("1\t2   3"), [1, 2, 3])

    def test_load_testcases_reads_marker_framed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path, output_path = _write_cases(
                directory,
                "@@CASE-1\n2\n1 2\n\n@@CASE-2\n0\n",
                "@@CASE-1\n1 2\n@@CASE-2\n\n",
            )

            testcases = load_testcases(input_path, output_path)

            self.assertEqual(testcases.count, 2)
            self.assertEqual(
                [case.expected_text for case in testcases.cases],
                ["1 2", ""],
            )

    def test_empty_input_case_content_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path, output_path = _write_cases(
                directory,
                "@@CASE-1\n@@CASE-2\n1\n",
                "@@CASE-1\n\n@@CASE-2\n1\n",
            )

            testcases = load_testcases(input_path, output_path)

            self.assertEqual(testcases.cases[0].input_lines, ())
            self.assertEqual(testcases.cases[0].expected_text, "")
            self.assertEqual(testcases.cases[1].input_lines, ("1",))

    def test_empty_expected_case_content_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path, output_path = _write_cases(
                directory,
                "@@CASE-1\n0\n@@CASE-2\n1\n",
                "@@CASE-1\n@@CASE-2\n5\n",
            )

            testcases = load_testcases(input_path, output_path)

            self.assertEqual(testcases.cases[0].expected_text, "")
            self.assertEqual(testcases.cases[1].expected_text, "5")

    def test_piston_input_strips_markers_and_prepends_the_count(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path, output_path = _write_cases(
                directory,
                "@@CASE-1\n3\n1 3 5\n3\n2 4 6\n@@CASE-2\n1\n5\n0\n\n",
                "@@CASE-1\n1 2 3 4 5 6\n@@CASE-2\n5\n",
            )

            testcases = load_testcases(input_path, output_path)

            self.assertEqual(
                testcases.piston_input,
                "2\n3\n1 3 5\n3\n2 4 6\n1\n5\n0\n\n",
            )

    def test_content_before_the_first_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path, output_path = _write_cases(
                directory,
                "1\n@@CASE-1\n2\n",
                "@@CASE-1\n3\n",
            )

            with self.assertRaises(TestcaseError):
                load_testcases(input_path, output_path)

    def test_files_without_markers_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path, output_path = _write_cases(directory, "1\n2\n", "3\n")

            with self.assertRaises(TestcaseError):
                load_testcases(input_path, output_path)

    def test_out_of_order_markers_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path, output_path = _write_cases(
                directory,
                "@@CASE-1\n1\n@@CASE-3\n2\n",
                "@@CASE-1\n1\n@@CASE-2\n2\n",
            )

            with self.assertRaises(TestcaseError):
                load_testcases(input_path, output_path)

    def test_duplicate_markers_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path, output_path = _write_cases(
                directory,
                "@@CASE-1\n1\n@@CASE-1\n2\n",
                "@@CASE-1\n1\n@@CASE-2\n2\n",
            )

            with self.assertRaises(TestcaseError):
                load_testcases(input_path, output_path)

    def test_input_and_output_case_count_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path, output_path = _write_cases(
                directory,
                "@@CASE-1\n1\n@@CASE-2\n2\n",
                "@@CASE-1\n1\n",
            )

            with self.assertRaises(TestcaseError):
                load_testcases(input_path, output_path)


class TestEvaluate(unittest.TestCase):
    def setUp(self):
        self.judge = _ListJudge()

    def test_all_cases_pass(self):
        result = self.judge.evaluate(
            _run(stdout="1 2\n3 4\n"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.ACCEPTED)
        self.assertEqual(result["score"], 10.0)

    def test_first_case_wrong_gets_no_credit(self):
        result = self.judge.evaluate(
            _run(stdout="0 2\n3 4\n"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.WRONG_ANSWER)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("test case 1", result["details"].lower())

    def test_second_case_wrong_gets_partial_credit(self):
        result = self.judge.evaluate(
            _run(stdout="1 2\n3 5\n"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.WRONG_ANSWER)
        self.assertEqual(result["score"], 5.0)

    def test_missing_final_case_is_a_wrong_answer(self):
        result = self.judge.evaluate(
            _run(stdout="1 2\n", exit_code=0),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.WRONG_ANSWER)
        self.assertEqual(result["score"], 5.0)
        self.assertIn("test case 2", result["details"].lower())

    def test_extra_output_is_rejected(self):
        result = self.judge.evaluate(
            _run(stdout="1 2\n3 4\n5 6\n"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.WRONG_ANSWER)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("3 output lines", result["details"])

    def test_an_empty_result_matches_an_empty_expected_row(self):
        result = self.judge.evaluate(
            _run(stdout="1\n\n3\n"),
            _expected([[1], [], [3]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.ACCEPTED)
        self.assertEqual(result["score"], 10.0)

    def test_a_lone_empty_line_matches_a_single_empty_result(self):
        result = self.judge.evaluate(
            _run(stdout="\n"),
            _expected([[]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.ACCEPTED)
        self.assertEqual(result["score"], 10.0)

    def test_no_output_does_not_match_an_expected_empty_result(self):
        result = self.judge.evaluate(
            _run(stdout=""),
            _expected([[]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.WRONG_ANSWER)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("test case 1", result["details"].lower())

    def test_unparseable_output_is_a_wrong_answer(self):
        result = self.judge.evaluate(
            _run(stdout="1 2\nnot an integer\n"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.WRONG_ANSWER)
        self.assertEqual(result["score"], 5.0)
        self.assertIn("Could not parse", result["details"])

    def test_clean_exit_after_exceeding_cpu_limit_is_tle(self):
        result = self.judge.evaluate(
            _run(stdout="1 2\n3 4\n", cpu_time_ms=1_500.0),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.TIME_LIMIT_EXCEEDED)
        self.assertEqual(result["score"], 0.0)

    def test_killed_process_with_low_memory_is_tle(self):
        result = self.judge.evaluate(
            _run(stdout="1 2\n", exit_code=-9, signal="SIGKILL"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.TIME_LIMIT_EXCEEDED)
        self.assertEqual(result["score"], 5.0)

    def test_killed_process_at_memory_limit_is_mle(self):
        result = self.judge.evaluate(
            _run(
                stdout="1 2\n",
                exit_code=-9,
                signal="SIGKILL",
                memory_bytes=100 * 10**6,
            ),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.MEMORY_LIMIT_EXCEEDED)
        self.assertEqual(result["score"], 5.0)

    def test_memory_error_in_stderr_is_mle(self):
        result = self.judge.evaluate(
            _run(
                exit_code=1,
                stderr="java.lang.OutOfMemoryError: Java heap space",
            ),
            _expected([[1, 2]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.MEMORY_LIMIT_EXCEEDED)
        self.assertEqual(result["score"], 0.0)

    def test_runtime_error_keeps_credit_for_completed_cases(self):
        result = self.judge.evaluate(
            _run(stdout="1 2\n", exit_code=1, stderr="boom"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.RUNTIME_ERROR)
        self.assertEqual(result["score"], 5.0)
        self.assertIn("boom", result["details"])

    def test_wrong_answer_before_a_crash_is_still_a_wrong_answer(self):
        result = self.judge.evaluate(
            _run(stdout="0 2\n", exit_code=1, stderr="boom"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.WRONG_ANSWER)
        self.assertEqual(result["score"], 0.0)


class TestHelpers(unittest.TestCase):
    def test_score_for_passed_rounds_to_two_decimals(self):
        self.assertEqual(score_for_passed(1, 3), 3.33)
        self.assertEqual(score_for_passed(2, 3), 6.67)
        self.assertEqual(score_for_passed(99, 3), 10.0)

    def test_language_profiles_can_be_overridden_per_question(self):
        profiles = {
            **LANGUAGE_PROFILES,
            "java": LanguageProfile(
                cpu_factor=2.0,
                wall_factor=3.0,
                memory_factor=3.0,
                memory_pad_mb=32,
            ),
        }

        limits = language_limits("java", profiles)

        self.assertEqual(limits.memory_limit_bytes, int((128 * 3.0 + 32) * 10**6))

    def test_mismatch_details_are_compact(self):
        expected = list(range(1_000))
        actual = list(expected)
        actual[500] = -1

        details = format_mismatch(actual, expected, 1)

        self.assertIn("index 500", details)
        self.assertLess(len(details), 500)


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class TestPistonTransport(unittest.TestCase):
    def _wrapper(self, directory: str) -> str:
        path = Path(directory) / "Main.java"
        path.write_text("class Main {}\n/*SUBMISSION_CODE*/\n", encoding="utf-8")
        return str(path)

    def test_successful_run_is_converted_to_run_result(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = self._wrapper(directory)
            payload = {
                "compile": {"code": 0},
                "run": {
                    "stdout": "1 2\n",
                    "stderr": "",
                    "code": 0,
                    "signal": "",
                    "cpu_time": 12.5,
                    "wall_time": 20.0,
                    "memory": 1234,
                },
            }

            with patch("Judge.piston.requests.post") as post:
                post.return_value = _FakeResponse(payload)
                result = execute_submission(
                    "class Q102 {}",
                    wrapper,
                    "1\n",
                    "java",
                    LIMITS,
                )

            self.assertEqual(result.stdout, "1 2\n")
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.cpu_time_ms, 12.5)
            self.assertEqual(result.memory_bytes, 1234)
            sent_payload = post.call_args.kwargs["json"]
            self.assertIn("class Q102 {}", sent_payload["files"][0]["content"])
            self.assertEqual(sent_payload["run_memory_limit"], LIMITS.memory_limit_bytes)

    def test_compilation_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = self._wrapper(directory)
            payload = {
                "compile": {"code": 1, "stderr": "Main.java:1: error: bad code"},
                "run": {"stdout": "", "stderr": "", "code": 0},
            }

            with patch("Judge.piston.requests.post") as post:
                post.return_value = _FakeResponse(payload)
                with self.assertRaises(CompilationError):
                    execute_submission("bad", wrapper, "1\n", "java", LIMITS)

    def test_missing_run_result_is_a_piston_error(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = self._wrapper(directory)

            with patch("Judge.piston.requests.post") as post:
                post.return_value = _FakeResponse({"compile": {"code": 0}})
                with self.assertRaises(PistonError):
                    execute_submission("code", wrapper, "1\n", "java", LIMITS)

    def test_http_failure_is_a_piston_error(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = self._wrapper(directory)

            with patch("Judge.piston.requests.post") as post:
                post.return_value = _FakeResponse({}, status_code=500)
                with self.assertRaises(PistonError):
                    execute_submission("code", wrapper, "1\n", "java", LIMITS)


if __name__ == "__main__":
    unittest.main()
