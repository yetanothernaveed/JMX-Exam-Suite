from unittest import case

import requests
import json
import os

# Configuration
PISTON_URL = "http://localhost:2000/api/v2/execute"  # Change to your Piston endpoint
wall_timeout_ms = 3000     # 3 seconds max wall clock time
cpu_timeout_ms = 1000      # 1 second max CPU time
memory_limit_bytes = 128 * 10**6  # 128 MB RAM limit

def judge_submission(
        submission_code: str, 
        wrapper_file: str,
        input_file: str,
        expected_output_file: str,
        wall_timeout_ms: int,
        cpu_timeout_ms: int,
        memory_limit_bytes: int,
        language: str = "java"
    ) -> dict:
    """
    Main evaluation pipeline following the waterfall deduction model.
    """
    with open(wrapper_file, "r") as f:
            code = f.read()
            # Append submission code to the wrapper code
            code = code.replace("/*SUBMISSION_CODE*/", submission_code)

    if not os.path.exists(input_file) or os.path.getsize(input_file) == 0:
        return {
            "verdict": "SYSTEM_ERROR", 
            "details": "No question with specified ID found",
            "score": 0
        }
    if not os.path.exists(expected_output_file) or os.path.getsize(expected_output_file) == 0:
        return {
            "verdict": "SYSTEM_ERROR", 
            "details": "No expected output file found for the question",
            "score": 0
        }

    with open(input_file, "r") as f:
        input_data = f.read()


    with open(expected_output_file, "r") as f:
        expected_output = f.read()

    if input_data is None or expected_output is None:
        return {
            "verdict": "SYSTEM_ERROR", 
            "details": "Input or expected output file is missing.",
            "score": 0
        }


    payload = {
        "language": language,
        "version": "*",
        "files": [
            {"name": "Main", "content": code},  # <-- Pass the submission code as a file
            {"name": "input.in", "content": input_data},  # <-- Pass input as a file
            {"name": "expected.out", "content": expected_output}  # <-- Pass expected output as a file
        ],
        "run_timeout": wall_timeout_ms,
        "run_cpu_timeout": cpu_timeout_ms,
        "run_memory_limit": memory_limit_bytes
    }

    try:
        response = requests.post(PISTON_URL, json=payload, timeout=10)
        piston_res = response.json()
    except Exception as e:
        return {
            "verdict": "SYSTEM_ERROR", 
            "details": f"Piston API request failed: {str(e)}",
            "score": 0
        }


    number_of_testcases = int(input_data.splitlines()[0]) if input_data else 0
    # free input and expected output files from memory
    del input_data
    del expected_output
    del code
    
    run_details = piston_res.get("run", {})
    exit_code = run_details.get("code", -1)
    stdout = run_details.get("stdout", "")
    stderr = run_details.get("stderr", "")
    signal = run_details.get("signal", "")
    memory_bytes_used = run_details.get("memory", 0)
    cpu_time = run_details.get("cpu_time", 0)
    wall_time = run_details.get("wall_time", 0)

    # Parse stdout to determine how many test cases were run and their results
    completed_cases = [json.loads(line) for line in stdout.strip().split("\n")] if stdout else []
    cases_run = len(completed_cases)
    score_per_case = 10 / number_of_testcases if number_of_testcases > 0 else 0
    
    # Waterfall Verdict Logic
    # CASE A: Normal execution — all test cases completed
    if exit_code == 0 and cases_run == number_of_testcases:
        if cpu_time >= cpu_timeout_ms:
            return {
                "verdict": "TLE", 
                "details": f"Time limit exceeded.",
                "score": 0
            }

        if wall_time >= wall_timeout_ms:
            return {
                "verdict": "TLE", 
                "details": f"Wall clock time limit exceeded.",
                "score": 0
            }

        cases_failed = []
        verdict = "AC"
        for idx, case in enumerate(completed_cases):
            if not bool(case["passed"]):
                verdict = "WA"
                cases_failed.append(idx + 1)
        
        if verdict == "WA": 
            return {
                "verdict": verdict,
                "details": f"Wrong Answer on test case(s): {', '.join(map(str, cases_failed))}.",
                "score": int(number_of_testcases - len(cases_failed)) * score_per_case,
            }
        
        # All passed!
        total_time_ms = sum(float(c["time_ms"]) for c in completed_cases)
        return {
            "verdict": "AC",
            "details": f"""Passed {number_of_testcases} testcases in {cpu_time} ms CPU time and {wall_time} ms wall clock time. Used {memory_bytes_used / 10e6} Megabytes.""",
            "score": 10,
        }

    # CASE B: Crash occurred — determine failing case and cause
    failing_case_index = cases_run + 1  # The index where code stopped executing
    score = int(failing_case_index - 1) * score_per_case # as it ran fine up to (n - 1)th case

    # Memory Limit Exceeded (MLE)
    if "OutOfMemoryError" in stderr or "java.lang.OutOfMemoryError" in stderr:
        return {
            "verdict": "MLE", 
            "details": f"Out of memory error on test case {failing_case_index}.",
            "score": score
        }

    # Time Limit Exceeded (TLE)
    if signal in ["SIGKILL", "SIGTERM"]:
        if memory_bytes_used >= memory_limit_bytes:
            return {
                "verdict": "MLE", 
                "details": f"Process killed due to memory limit on test case {failing_case_index}.",
                "score": score
            }
        
        return {
            "verdict": "TLE", 
            "details": f"Time limit exceeded on test case {failing_case_index}.", 
            "score": score
        }

    # General Runtime Error (RE)
    if exit_code != 0:
        return {
            "verdict": "RE",
            "details": stderr.strip(),
            "score": score
        }

    return {
        "verdict": "UNKNOWN_ERROR", 
        "details": stderr,
        "score": score
    }


if __name__ == "__main__":
    with open("/home/naveed/Projects/PistonJudge/example/A.java" , "r") as f:
        submission_code = f.read()

    result = judge_submission(
        submission_code=submission_code,
        wrapper_file="/home/naveed/Work/CSE221/questions/cse221_summer2026_section1_quiz0/Q101/wrapper/Main.java",
        input_file="/home/naveed/Work/CSE221/questions/cse221_summer2026_section1_quiz0/Q101/testcases/tc.in",
        expected_output_file="/home/naveed/Work/CSE221/questions/cse221_summer2026_section1_quiz0/Q101/testcases/tc.out",
        wall_timeout_ms=3000,
        cpu_timeout_ms=1000,
        memory_limit_bytes=128 * 10**6
    )

    print(result)
