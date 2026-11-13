from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from server.pistonjudge.src.Judge.base_judge import BaseJudge
from server.pistonjudge.src.Judge.piston import (
    LANGUAGE_PROFILES,
    CompilationError,
    LanguageProfile,
    PistonError,
    RunLimits,
    RunResult,
    execute_submission,
    language_limits,
)
from server.pistonjudge.src.Judge.testcases import (
    TestcaseError,
    load_testcases,
    parse_int_row,
)
from server.pistonjudge.src.Judge.verdicts import (
    MAX_SCORE,
    CaseResult,
    Verdict,
    format_case_scores,
    format_mismatch,
)


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

    def test_unparseable_cut_off_line_after_a_crash_is_a_runtime_error(self):
        result = self.judge.evaluate(
            _run(stdout="1 2\nnot an integer", exit_code=1, stderr="boom"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.RUNTIME_ERROR)
        self.assertEqual(result["score"], 5.0)
        self.assertIn("boom", result["details"])
        self.assertNotIn("Could not parse", result["details"])

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

    def test_partial_output_then_timeout_is_tle_not_wrong_answer(self):
        result = self.judge.evaluate(
            _run(
                stdout="1 2\n3",
                exit_code=-1,
                signal="SIGKILL",
                status="TO",
                message="Time limit exceeded (wall clock)",
                cpu_time_ms=1_500.0,
                wall_time_ms=2_100.0,
            ),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.TIME_LIMIT_EXCEEDED)
        self.assertEqual(result["score"], 5.0)
        self.assertIn("Time limit exceeded", result["details"])

    def test_a_cut_off_line_cannot_be_graded_as_wrong_answer(self):
        result = self.judge.evaluate(
            _run(
                stdout="1 2\n3 4\n5",
                exit_code=-1,
                signal="SIGKILL",
                status="TO",
                message="Time limit exceeded (cpu)",
                cpu_time_ms=1_001.0,
                wall_time_ms=1_200.0,
            ),
            _expected([[1, 2], [3, 4], [5, 6]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.TIME_LIMIT_EXCEEDED)
        self.assertAlmostEqual(result["score"], 10.0 * 2 / 3, places=2)
        self.assertNotIn("WRONG ANSWER", result["details"])

    def test_an_unparseable_cut_off_line_under_timeout_is_tle(self):
        result = self.judge.evaluate(
            _run(
                stdout="1 2\n3 x",
                exit_code=-1,
                signal="SIGKILL",
                status="TO",
                message="Time limit exceeded (cpu)",
                cpu_time_ms=1_001.0,
                wall_time_ms=1_200.0,
            ),
            _expected([[1, 2], [3, 4], [5, 6]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.TIME_LIMIT_EXCEEDED)
        self.assertNotIn("Could not parse", result["details"])

    def test_timeout_before_any_output_is_tle(self):
        result = self.judge.evaluate(
            _run(
                stdout="",
                exit_code=-1,
                signal="SIGKILL",
                status="TO",
                message="Time limit exceeded (wall clock)",
                wall_time_ms=2_100.0,
            ),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.TIME_LIMIT_EXCEEDED)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("test case 1", result["details"])

    def test_a_wrong_prefix_does_not_override_a_timeout(self):
        result = self.judge.evaluate(
            _run(
                stdout="0 2\n3 4\n",
                exit_code=-1,
                signal="SIGKILL",
                status="TO",
                message="Time limit exceeded (wall clock)",
                wall_time_ms=2_100.0,
            ),
            _expected([[1, 2], [3, 4], [5, 6]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.TIME_LIMIT_EXCEEDED)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("TIME LIMIT EXCEEDED", result["details"])

    def test_clean_exit_with_incomplete_output_at_the_limit_is_tle(self):
        result = self.judge.evaluate(
            _run(stdout="1 2\n", cpu_time_ms=1_000.0),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.TIME_LIMIT_EXCEEDED)
        self.assertEqual(result["score"], 5.0)

    def test_piston_timeout_status_is_tle_even_with_all_answers(self):
        result = self.judge.evaluate(
            _run(
                stdout="1 2\n3 4\n",
                exit_code=-1,
                signal="SIGKILL",
                status="TO",
                message="Time limit exceeded (wall clock)",
                wall_time_ms=2_100.0,
            ),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.TIME_LIMIT_EXCEEDED)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("discarded", result["details"])

    def test_exit_137_with_empty_signal_at_the_memory_limit_is_mle(self):
        result = self.judge.evaluate(
            _run(
                stdout="1 2\n",
                exit_code=137,
                signal="",
                status="RE",
                message="Exited with error status 137",
                memory_bytes=100 * 10**6,
                stderr="/piston/packages/java/run: line 7: 4 Killed java $filename \"$@\"\n",
            ),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.MEMORY_LIMIT_EXCEEDED)
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

    def test_python_syntax_error_without_a_compile_stage_is_a_runtime_error(self):
        result = self.judge.evaluate(
            _run(
                stdout="",
                exit_code=1,
                stderr=(
                    '  File "/box/submission/Main", line 1\n'
                    "    def f(:\n"
                    "          ^\n"
                    "SyntaxError: invalid syntax\n"
                ),
            ),
            _expected([[1, 2]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.RUNTIME_ERROR)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("SyntaxError", result["details"])

    def test_wrong_answer_before_a_crash_is_still_a_wrong_answer(self):
        result = self.judge.evaluate(
            _run(stdout="0 2\n", exit_code=1, stderr="boom"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.WRONG_ANSWER)
        self.assertEqual(result["score"], 0.0)

    def test_custom_case_scores_are_used_for_partial_credit(self):
        self.judge.case_scores = [1.5, 2.5, 6.0]

        result = self.judge.evaluate(
            _run(stdout="1 2\n3 4\n5 7\n"),
            _expected([[1, 2], [3, 4], [5, 6]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.WRONG_ANSWER)
        self.assertEqual(result["score"], 4.0)
        self.assertIn("1.50 / 1.50", result["details"])
        self.assertIn("2.50 / 2.50", result["details"])
        self.assertIn("0.00 / 6.00", result["details"])
        self.assertIn("WRONG ANSWER", result["details"])

    def test_first_wrong_answer_marks_later_cases_as_not_scored(self):
        self.judge.case_scores = [2.0, 3.0, 5.0]

        result = self.judge.evaluate(
            _run(stdout="0 2\n3 4\n5 6\n"),
            _expected([[1, 2], [3, 4], [5, 6]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.WRONG_ANSWER)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("0.00 / 2.00", result["details"])
        self.assertIn("2-3", result["details"])
        self.assertIn("NOT SCORED", result["details"])
        self.assertNotIn("3.00 / 5.00", result["details"])

    def test_time_limit_before_all_cases_scores_only_the_passing_prefix(self):
        self.judge.case_scores = [1.0, 2.0, 3.0, 4.0]

        result = self.judge.evaluate(
            _run(stdout="1 2\n3 4\n", exit_code=-9, signal="SIGKILL"),
            _expected([[1, 2], [3, 4], [5, 6], [7, 8]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.TIME_LIMIT_EXCEEDED)
        self.assertEqual(result["score"], 3.0)
        self.assertIn("1.00 / 1.00", result["details"])
        self.assertIn("2.00 / 2.00", result["details"])
        self.assertIn("0.00 / 3.00", result["details"])
        self.assertIn("NOT SCORED", result["details"])

    def test_all_answers_but_a_batch_timeout_receives_zero(self):
        self.judge.case_scores = [4.0, 6.0]

        result = self.judge.evaluate(
            _run(stdout="1 2\n3 4\n", cpu_time_ms=1_500.0),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.TIME_LIMIT_EXCEEDED)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("discarded", result["details"])

    def test_all_passing_details_show_every_case_score(self):
        self.judge.case_scores = [4.0, 6.0]

        result = self.judge.evaluate(
            _run(stdout="1 2\n3 4\n"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.ACCEPTED)
        self.assertEqual(result["score"], 10.0)
        self.assertIn("4.00 / 4.00", result["details"])
        self.assertIn("6.00 / 6.00", result["details"])
        self.assertIn("PASS", result["details"])

    def test_wrong_number_of_case_scores_is_a_system_error(self):
        self.judge.case_scores = [5.0, 5.0, 5.0]

        result = self.judge.evaluate(
            _run(stdout="1 2\n3 4\n"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.SYSTEM_ERROR)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("case_scores", result["details"])

    def test_case_scores_must_sum_to_the_maximum_score(self):
        self.judge.case_scores = [2.0, 2.0]

        result = self.judge.evaluate(
            _run(stdout="1 2\n3 4\n"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.SYSTEM_ERROR)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("sum to 10", result["details"])

    def test_negative_case_scores_are_rejected(self):
        self.judge.case_scores = [-1.0, 11.0]

        result = self.judge.evaluate(
            _run(stdout="1 2\n3 4\n"),
            _expected([[1, 2], [3, 4]]),
            LIMITS,
        )

        self.assertEqual(result["verdict"], Verdict.SYSTEM_ERROR)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("negative", result["details"])


class TestSubmit(unittest.TestCase):
    def test_compilation_error_is_reported_as_a_compilation_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path, output_path = _write_cases(
                directory,
                "@@CASE-1\n1\n",
                "@@CASE-1\n1\n",
            )
            judge = _ListJudge()

            with patch(
                "server.pistonjudge.src.Judge.base_judge.execute_submission",
                side_effect=CompilationError("Main.java:1: error: bad code"),
            ):
                result = judge.submit(
                    "bad",
                    "Main.java",
                    input_path,
                    output_path,
                    "java",
                )

        self.assertEqual(result["verdict"], Verdict.COMPILATION_ERROR)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("bad code", result["details"])


class _KeywordJudge(_ListJudge):
    banned_keywords = ("sort",)


class TestBannedKeywords(unittest.TestCase):
    def _submit(self, judge, code):
        with tempfile.TemporaryDirectory() as directory:
            input_path, output_path = _write_cases(
                directory,
                "@@CASE-1\n1\n",
                "@@CASE-1\n1\n",
            )
            with patch(
                "server.pistonjudge.src.Judge.base_judge.execute_submission"
            ) as execute:
                result = judge.submit(
                    code,
                    "Main.py",
                    input_path,
                    output_path,
                    "python",
                )
        return result, execute

    def test_judges_without_banned_keywords_are_unrestricted(self):
        judge = _ListJudge()

        self.assertIsNone(judge._find_banned_keyword("def mergeSort(): pass"))

    def test_banned_keyword_rejects_before_execution(self):
        judge = _ListJudge(banned_keywords=["sort"])

        result, execute = self._submit(judge, "def mergeSort(): pass\n")

        self.assertEqual(result["verdict"], Verdict.FORBIDDEN_KEYWORD_ERROR)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("'sort'", result["details"])
        execute.assert_not_called()

    def test_matching_is_case_insensitive_and_any_substring(self):
        judge = _ListJudge(banned_keywords=["sort"])

        for code in ("Sort", "SORT", "mergeSort", "ffajffjsortskjfls"):
            with self.subTest(code=code):
                result, execute = self._submit(judge, f"value = {code}\n")

                self.assertEqual(result["verdict"], Verdict.FORBIDDEN_KEYWORD_ERROR)
                execute.assert_not_called()

    def test_keyword_configuration_is_case_insensitive(self):
        judge = _ListJudge(banned_keywords=["SORT"])

        self.assertEqual(judge._find_banned_keyword("mergeSort"), ("SORT", 1))

    def test_first_matching_keyword_is_reported_with_its_line(self):
        judge = _ListJudge(banned_keywords=["merge", "sort"])

        self.assertEqual(
            judge._find_banned_keyword("x = 1\ny = mergeSort\n"),
            ("merge", 2),
        )

    def test_class_attribute_configures_keywords_without_arguments(self):
        judge = _KeywordJudge()

        self.assertEqual(judge.banned_keywords, ("sort",))
        self.assertEqual(judge._find_banned_keyword("mergeSort"), ("sort", 1))

    def test_constructor_overrides_class_attribute(self):
        judge = _KeywordJudge(banned_keywords=["merge"])

        self.assertEqual(judge.banned_keywords, ("merge",))
        self.assertIsNone(judge._find_banned_keyword("def sort(): pass"))

    def test_empty_keywords_are_ignored(self):
        judge = _ListJudge(banned_keywords=["", "   "])

        self.assertEqual(judge.banned_keywords, ())
        self.assertIsNone(judge._find_banned_keyword("anything goes"))


class TestCaseScores(unittest.TestCase):
    def setUp(self):
        self.judge = _ListJudge()

    def test_default_scores_split_the_maximum_evenly(self):
        self.assertEqual(self.judge.get_case_scores(4), [2.5, 2.5, 2.5, 2.5])

    def test_default_scores_are_not_rounded(self):
        scores = self.judge.get_case_scores(3)

        self.assertEqual(len(scores), 3)
        self.assertAlmostEqual(sum(scores), MAX_SCORE)
        self.assertAlmostEqual(scores[0], MAX_SCORE / 3)

    def test_custom_scores_are_returned_in_case_order(self):
        self.judge.case_scores = [1.5, 1.5, 7.0]

        self.assertEqual(self.judge.get_case_scores(3), [1.5, 1.5, 7.0])

    def test_table_groups_later_cases_and_aligns_columns(self):
        results = [
            CaseResult(1, Verdict.ACCEPTED, 1.5, 1.5),
            CaseResult(2, Verdict.WRONG_ANSWER, 0.0, 1.5),
        ]

        lines = format_case_scores(results, 5).splitlines()

        self.assertEqual(lines[0], "Test case scores:")
        self.assertEqual(lines[1].index("Case"), lines[3].index("1"))
        self.assertEqual(lines[1].index("Verdict"), lines[3].index("PASS"))
        self.assertIn("3-5", lines[5])
        self.assertIn("NOT SCORED", lines[5])

    def test_empty_table_explains_that_nothing_was_scored(self):
        self.assertEqual(
            format_case_scores([], 5),
            "Test case scores: no cases were scored.",
        )

    def test_no_test_cases_is_a_configuration_error(self):
        with self.assertRaises(ValueError):
            self.judge.get_case_scores(0)


class TestHelpers(unittest.TestCase):
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
                    "status": "AC",
                    "message": "",
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
            self.assertEqual(result.status, "AC")
            self.assertEqual(result.message, "")
            self.assertEqual(result.cpu_time_ms, 12.5)
            self.assertEqual(result.memory_bytes, 1234)
            sent_payload = post.call_args.kwargs["json"]
            self.assertIn("class Q102 {}", sent_payload["files"][0]["content"])
            self.assertEqual(sent_payload["files"][1]["name"], "input.in")
            self.assertNotIn("stdin", sent_payload)
            self.assertEqual(sent_payload["run_memory_limit"], LIMITS.memory_limit_bytes)

    def test_source_file_name_follows_wrapper_name(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = Path(directory) / "Q111.java"
            wrapper.write_text(
                "public class Q111 {}\n/*SUBMISSION_CODE*/\n",
                encoding="utf-8",
            )
            payload = {
                "compile": {"code": 0},
                "run": {"stdout": "", "stderr": "", "code": 0, "status": "AC"},
            }

            with patch("Judge.piston.requests.post") as post:
                post.return_value = _FakeResponse(payload)
                execute_submission(
                    "code",
                    str(wrapper),
                    "1\n",
                    "java",
                    LIMITS,
                    input_file_name="input.txt",
                )

            sent_payload = post.call_args.kwargs["json"]
            self.assertEqual(sent_payload["files"][0]["name"], "Q111")
            self.assertEqual(sent_payload["files"][1]["name"], "input.txt")
            self.assertEqual(sent_payload["files"][1]["content"], "1\n")
            self.assertNotIn("stdin", sent_payload)

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

    def test_compilation_failure_with_copied_run_result_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = self._wrapper(directory)
            # Piston v2 copies the compile result into ``run`` when compilation
            # fails, so the compile check must win over the run result.
            payload = {
                "compile": {
                    "code": 1,
                    "stderr": "Main.java:1: error: bad code",
                    "signal": None,
                    "status": "RE",
                },
                "run": {
                    "stdout": "",
                    "stderr": "Main.java:1: error: bad code",
                    "code": 1,
                    "signal": None,
                    "status": "RE",
                },
            }

            with patch("Judge.piston.requests.post") as post:
                post.return_value = _FakeResponse(payload)
                with self.assertRaises(CompilationError) as raised:
                    execute_submission("bad", wrapper, "1\n", "java", LIMITS)

            self.assertIn("bad code", raised.exception.details)

    def test_successful_compile_with_runtime_failure_returns_a_run_result(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = self._wrapper(directory)
            payload = {
                "compile": {"code": 0, "stderr": "", "signal": None, "status": None},
                "run": {
                    "stdout": "",
                    "stderr": "Exception in thread \"main\" java.lang.ArithmeticException",
                    "code": 1,
                    "signal": None,
                    "status": "RE",
                },
            }

            with patch("Judge.piston.requests.post") as post:
                post.return_value = _FakeResponse(payload)
                result = execute_submission("code", wrapper, "1\n", "java", LIMITS)

            self.assertEqual(result.exit_code, 1)
            self.assertIn("ArithmeticException", result.stderr)

    def test_compile_warnings_are_not_a_compilation_error(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = self._wrapper(directory)
            payload = {
                "compile": {
                    "code": 0,
                    "stderr": "Main.java:1: warning: unchecked operation",
                    "signal": None,
                    "status": None,
                },
                "run": {
                    "stdout": "1 2\n",
                    "stderr": "",
                    "code": 0,
                    "signal": None,
                    "status": "AC",
                },
            }

            with patch("Judge.piston.requests.post") as post:
                post.return_value = _FakeResponse(payload)
                result = execute_submission("code", wrapper, "1\n", "java", LIMITS)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stdout, "1 2\n")

    def test_missing_compile_exit_code_is_a_compilation_error(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = self._wrapper(directory)
            payload = {
                "compile": {
                    "code": None,
                    "stderr": "",
                    "signal": None,
                    "status": "TO",
                },
            }

            with patch("Judge.piston.requests.post") as post:
                post.return_value = _FakeResponse(payload)
                with self.assertRaises(CompilationError) as raised:
                    execute_submission("code", wrapper, "1\n", "java", LIMITS)

            self.assertIn("timed out", raised.exception.details.lower())

    def test_python_failure_without_a_compile_key_is_a_run_result(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = Path(directory) / "Main.py"
            wrapper.write_text("/*SUBMISSION_CODE*/\n", encoding="utf-8")
            payload = {
                "run": {
                    "stdout": "",
                    "stderr": "SyntaxError: invalid syntax",
                    "code": 1,
                    "signal": None,
                    "status": "RE",
                },
            }

            with patch("Judge.piston.requests.post") as post:
                post.return_value = _FakeResponse(payload)
                result = execute_submission("bad", str(wrapper), "", "python", LIMITS)

            self.assertEqual(result.exit_code, 1)
            self.assertIn("SyntaxError", result.stderr)

    def test_malformed_compile_result_is_a_piston_error(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = self._wrapper(directory)

            with patch("Judge.piston.requests.post") as post:
                post.return_value = _FakeResponse({"compile": []})
                with self.assertRaises(PistonError):
                    execute_submission("code", wrapper, "1\n", "java", LIMITS)

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
