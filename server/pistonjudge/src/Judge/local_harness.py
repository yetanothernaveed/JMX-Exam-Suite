"""Small local runner used by the ``if __name__ == "__main__"`` blocks."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Type

from .base_judge import BaseJudge, JudgeResult
from .verdicts import MAX_SCORE

EXTENSIONS = {
    "python": "py",
    "java": "java",
    "c++": "cpp",
}


def run_local(
    judge_class: Type[BaseJudge],
    question_dir: Path | str,
    default_language: str = "python",
) -> JudgeResult:
    """Judge a question's sample submission from the command line.

    Paths are derived from the question folder, so no developer-specific
    absolute paths are needed.
    """
    parser = argparse.ArgumentParser(description="Run a question judge locally.")
    parser.add_argument(
        "--language",
        choices=sorted(EXTENSIONS),
        default=default_language,
        help=f"Submission language (default: {default_language}).",
    )
    parser.add_argument(
        "--submission",
        type=Path,
        help="Optional path to the submission file.",
    )
    args = parser.parse_args()

    question_dir = Path(question_dir)
    extension = EXTENSIONS[args.language]
    submission_path = args.submission or question_dir / f"{question_dir.name}.{extension}"

    wrapper_folder = question_dir / "~wrapper"
    preferred_wrapper = wrapper_folder / f"{question_dir.name}.{extension}"
    if not preferred_wrapper.exists():
        preferred_wrapper = wrapper_folder / f"Main.{extension}"

    result = judge_class().submit(
        submission_code=submission_path.read_text(encoding="utf-8"),
        wrapper_file_path=str(preferred_wrapper),
        input_file_path=str(question_dir / "~testcases" / "tc.in"),
        output_file_path=str(question_dir / "~testcases" / "tc.out"),
        language=args.language,
    )
    print(f"Verdict: {result['verdict']}")
    print(f"Score:   {result['score']:.2f} / {MAX_SCORE:.2f}")
    print(result["details"])
    return result
