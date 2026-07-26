import requests
import json

PISTON_URL = "http://localhost:2000/api/v2/execute"  # Change to your Piston endpoint
RUN_TIMEOUT_MS = 3000     # 2 seconds max total execution
MEMORY_LIMIT_BYTES = 128 * 1024 * 1024  # 128 MB RAM limit

def execute_and_judge():
    with open("Main.java", "r") as f:
        wrapper_code = f.read()

    with open("questions/prob_101/tc.in", "r") as f:
        input_data = f.read()

    with open("questions/prob_101/tc.out", "r") as f:
        expected_output = f.read()

    payload = {
        "language": "java",
        "version": "*",
        "files": [
            {"name": "Main", "content": wrapper_code},
            {"name": "input.in", "content": input_data},  # <-- Pass input as a file
            {"name": "expected.out", "content": expected_output}  # <-- Pass expected output as a file
        ],
        "run_timeout": RUN_TIMEOUT_MS,
        "run_memory_limit": MEMORY_LIMIT_BYTES
    }

    try:
        response = requests.post(PISTON_URL, json=payload, timeout=10)
        piston_res = response.json()
    except Exception as e:
        return {"verdict": "SYSTEM_ERROR", "details": f"Piston API request failed: {str(e)}"}

    print(piston_res["run"]["stdout"])
    print(piston_res["run"]["stderr"])


print(execute_and_judge())
