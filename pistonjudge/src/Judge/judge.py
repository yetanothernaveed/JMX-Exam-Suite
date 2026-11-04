"""Legacy import surface for ``Judge.judge``.

The judging implementation now lives in :mod:`Judge.base_judge`,
:mod:`Judge.piston`, :mod:`Judge.testcases`, and :mod:`Judge.verdicts`.

This module is kept because the server currently imports ``from Judge import
judge``. Do not add judging logic here; add it to the shared modules so every
question keeps using one implementation.
"""

from .base_judge import BaseJudge, JudgeResult
from .piston import (
    LANGUAGE_PROFILES,
    CompilationError,
    LanguageProfile,
    PistonError,
    RunLimits,
    RunResult,
    execute_submission,
    language_limits,
)
from .testcases import (
    TestCase,
    TestcaseError,
    TestcaseSet,
    load_testcases,
    parse_int_row,
)
from .verdicts import (
    MAX_SCORE,
    CaseResult,
    Verdict,
    format_case_scores,
    format_mismatch,
)

__all__ = [
    "BaseJudge",
    "JudgeResult",
    "LANGUAGE_PROFILES",
    "LanguageProfile",
    "CompilationError",
    "PistonError",
    "RunLimits",
    "RunResult",
    "execute_submission",
    "language_limits",
    "TestcaseError",
    "TestCase",
    "TestcaseSet",
    "load_testcases",
    "parse_int_row",
    "MAX_SCORE",
    "CaseResult",
    "Verdict",
    "format_case_scores",
    "format_mismatch",
]
