# base_judge.py
from abc import ABC, abstractmethod
from typing import TypedDict

class JudgeResult(TypedDict):
    verdict: str      # ACCEPTED, WRONG_ANSWER, TIME_LIMIT_EXCEEDED, MEMORY_LIMIT_EXCEEDED, RUNTIME_ERROR.
    score: float       # Useful for partial scoring (0.0 to 1.0)
    details: str       # Message to display or log

class BaseJudge(ABC):
    @abstractmethod
    def submit(
            self, 
            submission_code: str,
            wrapper_file_path: str,
            input_file_path: str,
            output_file_path: str,
            language: str
        ) -> JudgeResult:
        pass
