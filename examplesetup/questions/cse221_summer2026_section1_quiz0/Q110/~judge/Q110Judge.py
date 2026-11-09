"""Judge for Q110: subtract two integer arrays element by element."""

from pathlib import Path

from pistonjudge.src.Judge.base_judge import BaseJudge
from pistonjudge.src.Judge.local_harness import run_local
from pistonjudge.src.Judge.piston import LANGUAGE_PROFILES as DEFAULT_LANGUAGE_PROFILES
from pistonjudge.src.Judge.piston import LanguageProfile
from pistonjudge.src.Judge.testcases import parse_int_row


class Judge(BaseJudge):
    # Q110 materializes two input arrays and one result array of up to 10^6
    # integers, so it extends the shared per-language limits.
    #
    # The effective limits are:
    #   C++    : 3000 ms CPU, 7500 ms wall, 192 MB
    #   Java   : 6000 ms CPU, 12000 ms wall, 320 MB
    #   Python : 12000 ms CPU, 22500 ms wall, 576 MB
    #
    # ``**DEFAULT_LANGUAGE_PROFILES`` keeps the shared profile for any language
    # that is not overridden here.
    language_profiles = {
        **DEFAULT_LANGUAGE_PROFILES,
        "c++": LanguageProfile(
            cpu_factor=1.5,
            wall_factor=2.5,
            memory_factor=1.5,
            memory_pad_mb=0,
        ),
        "java": LanguageProfile(
            cpu_factor=3.0,
            wall_factor=4.0,
            memory_factor=2.0,
            memory_pad_mb=64,
        ),
        "python": LanguageProfile(
            cpu_factor=6,
            wall_factor=7.5,
            memory_factor=3.5,
            memory_pad_mb=128,
        ),
    }

    # The first two cases are small correctness checks; the larger cases are
    # where the per-language limits matter. The values sum to MAX_SCORE (10).
    case_scores = [1.5, 1.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.5, 0.5]

    def parse_result(self, text: str) -> list[int]:
        return parse_int_row(text)

    def compare_output(self, actual: list[int], expected: list[int]) -> bool:
        return actual == expected


if __name__ == "__main__":
    run_local(
        Judge,
        Path(__file__).resolve().parents[1],
        default_language="python",
    )
