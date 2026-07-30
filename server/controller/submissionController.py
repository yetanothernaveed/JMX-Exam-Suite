from Judge import judge
from utils import dynamic_loader

from mysql.connector import Error
import socket
import os
from datetime import datetime

def update_results(payload, score, DB_CONN_POOL):
    """
    Updates the results of a student's submission in the database.
    Args:
        payload (dict): A dictionary containing the submission details, including:
            - student_id (str): The ID of the student submitting the code.
            - qid (str): The question ID for which the code is being submitted.
        score (float): The score obtained by the student for this submission.

    """
    student_id = payload.get("student_id")
    qid = payload.get("qid")
    pc_id = payload.get("pc_id")
    conn = None
    cursor = None

    try:
        conn = DB_CONN_POOL.get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "INSERT INTO submissions (student_id, pc_id, question_id, score) VALUES (%s, %s, %s, %s)",
            (student_id, pc_id, qid, score)
        )

    except Error as e:
        print("Error while connecting to MySQL using connection pool: ", e)
    finally:
        if conn is not None and conn.is_connected():
            if cursor is not None: 
                cursor.close()
            conn.close()
            print("MySQL connection returned to pool.")

def write_to_files(payload, user_args, score, file_extension, DB_CONN_POOL):
    """
    Writes the student's code submission to a file in the responses folder.
    Args:
        payload (dict): A dictionary containing the submission details, including:
            - student_id (str): The ID of the student submitting the code.
            - qid (str): The question ID for which the code is being submitted.
            - code (str): The code to be executed.
        user_args (dict): A dictionary containing user arguments, including:
            - responses_folder (str): The path to the folder where student responses are stored.
    """
    student_id = payload.get("student_id")
    qid = payload.get("qid")
    code = payload.get("code")
    responses_folder = user_args.get("responses_folder")

    student_folder = f"{responses_folder}/{student_id}"
    if not os.path.exists(student_folder):
        os.makedirs(student_folder)


    # Get current max score for this student and question
    conn = None
    cursor = None
    try:
        conn = DB_CONN_POOL.get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT MAX(score) AS max_score FROM submissions WHERE student_id = %s AND question_id = %s",
            (student_id, qid)
        )
        result = cursor.fetchone()
        max_score = result["max_score"] if result["max_score"] is not None else 0
    except Error:
        raise Error("Unknown error while connecting to MySQL using connection pool. Could not get max score for student and question.")
    finally:
        if conn is not None and conn.is_connected():
            if cursor is not None: 
                cursor.close()
            conn.close()
            print("MySQL connection returned to pool.")

    submission_file_name = f"{qid}_{socket.gethostname()}_{datetime.now().time()}.{file_extension}"

    if score >= max_score:
        best_folder = f"{student_folder}/best/{submission_file_name}"
        with open(best_folder, "w") as f:
            f.write(code)
        print(f"Best submission for {student_id} on question {qid} written to {best_folder}")

    with open(f"{student_folder}/{submission_file_name}", "w") as f:
        f.write(code)
    print(f"Submission for {student_id} on question {qid} written to {student_folder}/{submission_file_name}")
    
def submit(payload, user_args, DB_CONN_POOL):
    """
    Handles the submission of code by a student, including judging the code and updating the results in the database.
    Args:
        payload (dict): A dictionary containing the submission details, including:
            - student_id (str): The ID of the student submitting the code.
            - qid (str): The question ID for which the code is being submitted.
            - code (str): The code to be executed.
        user_args (dict): A dictionary containing user arguments, including:
            - responses_folder (str): The path to the folder where student responses are stored.
            - questions_folder (str): The path to the folder where question files are stored.
            - exam_id (str): The ID of the exam for which the code is being submitted.
        DB_CONN_POOL: A connection pool object for interacting with the database.

    Returns:
        dict: A dictionary containing the result of the submission, including:
            - status (str): The status of the submission ("SUCCESS" or "ERROR").
            - message (str): A message providing additional information about the submission result.
    """
    qid = payload.get("qid").upper()
    questions_folder = user_args.get("questions_folder")
    file_extension = payload.get("filename").split(".")[-1].lower()

    wrapper_file_path = f"{questions_folder}/{qid}/~wrapper/Main.{file_extension}"
    input_file_path = f"{questions_folder}/{qid}/~testcases/tc.in"
    output_file_path = f"{questions_folder}/{qid}/~testcases/tc.out"
    language = None

    if file_extension == "java":
        language = "java"
    elif file_extension == "py":
        language = "python"
    elif file_extension == "cpp":
        language = "c++"
    else:
        return {
            "status": "ERROR",
            "message": "Unsupported file type. Only .java, .py, and .cpp files are currently supported."
        }

    ProblemJudge = None
    try:
        judge_path = f"{questions_folder}/{qid}/~judge/{qid}Judge.py"
        ProblemJudge = dynamic_loader.load_module_from_path(judge_path)
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"An error occurred while submitting the code:\n {str(e)}"
        }

    if not ProblemJudge:
        return {
            "status": "ERROR",
            "message": f"An error occurred while submitting the code:\n ProblemJudge is None. Please check the question ID and try again."
        }

    try:
        judge = ProblemJudge.Judge()
        judge_output = judge.submit(
            submission_code=payload["code"],
            wrapper_file_path=wrapper_file_path,
            input_file_path=input_file_path,
            output_file_path=output_file_path,
            language=language
        )
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"An error occurred while submitting the code:\n {str(e)}"
        }

    
    
    if judge_output.get("verdict") == "UNKNOWN_ERROR" or judge_output.get("verdict") == "ERROR":
        return judge_output

    score = judge_output.get("score", 0)
    update_results(payload, score, DB_CONN_POOL)
    write_to_files(payload, user_args, score, payload.get("filename").split(".")[-1], DB_CONN_POOL)

    return {
        "status": "SUCCESS",
        "message": f"Submission judged successfully.",
        "payload": {
            "verdict": judge_output.get("verdict"),
            "score": score,
            "details": judge_output.get("details", "No submissions detailed provided")
        }
    }


if __name__ == "__main__":
    # Example usage for testing purposes only
    user_args = {
        "questions_folder": "/home/naveed/Projects/CSE221/examplesetup/questions/cse221_summer2026_section1_quiz0",
        "responses_folder": "/home/naveed/Projects/CSE221/examplesetup/responses/cse221_summer2026_section1_quiz0",
        "exam_id": "cse221_summer2026_section1_quiz0"
    }

    with open("/home/naveed/Projects/CSE221/examplesetup/questions/cse221_summer2026_section1_quiz0/Q102/Q102.py", "r") as f:
        code = f.read()

    payload = {
        "student_id": "CSYR",
        "qid": "Q102",
        "pc_id": "pc1",
        "filename": "Q102.py",
        "code": code
    }

    import mysql.connector.pooling

    DB_CONN_POOL = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="db_conn_pool",
        pool_size=10,
        host="localhost",
        user="jmx",
        password="jmx2304",
        database="cse221_summer2026_section1_quiz0",
        autocommit=True
    )

    result = submit(payload, user_args, DB_CONN_POOL)
    print(result)
