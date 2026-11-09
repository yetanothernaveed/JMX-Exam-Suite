import random
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def generate(t: int, n: int) -> None:
    """Generate marker-framed testcases for Q110.

    Each case in ``tc.in`` contains the array length followed by arrays A and B.
    Each case in ``tc.out`` contains the element-wise difference A[i] - B[i].
    """
    input_path = BASE_DIR / "tc.in"
    output_path = BASE_DIR / "tc.out"

    with input_path.open("w", encoding="utf-8") as input_file, \
            output_path.open("w", encoding="utf-8") as output_file:
        length = 3
        for case_number in range(1, t + 1):
            arr1 = [random.randint(1, 100) for _ in range(length)]
            arr2 = [random.randint(1, 100) for _ in range(length)]
            result = [a - b for a, b in zip(arr1, arr2)]

            input_file.write(f"@@CASE-{case_number}\n")
            input_file.write(f"{length}\n")
            input_file.write(" ".join(map(str, arr1)) + "\n")
            input_file.write(" ".join(map(str, arr2)) + "\n")

            output_file.write(f"@@CASE-{case_number}\n")
            output_file.write(" ".join(map(str, result)) + "\n")

            length = min(n, length * 10)


if __name__ == "__main__":
    generate(t=10, n=1_000_000)
