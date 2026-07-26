import pistonjudge
import pistonjudge.judge

from mysql.connector import Error
import socket
import os
from datetime import datetime

LANGUAGE_MULTIPLIERS = {
    "c++": {"cpu": 1.0, "wall": 2.0, "memory": 1.0, "memory_pad": 0},
    "java": {"cpu": 2.0, "wall": 3.0, "memory": 1.5, "memory_pad": 32},
    "python": {"cpu": 3.0, "wall": 4.0, "memory": 1.2, "memory_pad": 128}
}

def  get_judgement(
        payload, user_args,
        base_cpu_timeout,
        base_wall_timeout,
        base_memory_limit
    ):
    """
    Submits the code to the PistonJudge API for execution and returns the result.
    Args:
        payload (dict): A dictionary containing the submission details, including:
            - student_id (str): The ID of the student submitting the code.
            - qid (str): The question ID for which the code is being submitted.
            - code (str): The code to be executed.
        user_args (dict): A dictionary containing user arguments, including:
            - responses_folder (str): The path to the folder where student responses are stored.
            - questions_folder (str): The path to the folder where question files are stored.
            - exam_id (str): The ID of the exam for which the code is being submitted.

    """
    qid = payload.get("qid")
    questions_folder = user_args.get("questions_folder")
    language = None

    file_extension = payload.get("filename").split(".")[-1].lower()  # Get the file extension in lowercase

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

    cpu_timeout = int(base_cpu_timeout * LANGUAGE_MULTIPLIERS[language]["cpu"])
    wall_timeout = int(base_wall_timeout * LANGUAGE_MULTIPLIERS[language]["wall"])
    memory_limit = int(base_memory_limit * LANGUAGE_MULTIPLIERS[language]["memory"]) + LANGUAGE_MULTIPLIERS[language]["memory_pad"]

    try:
        judge_output = pistonjudge.judge.judge_submission(
            payload["code"],
            f"{questions_folder}/{qid.upper()}/~wrapper/Main.{file_extension}",
            f"{questions_folder}/{qid.upper()}/~testcases/tc.in",
            f"{questions_folder}/{qid.upper()}/~testcases/tc.out",
            wall_timeout,
            cpu_timeout,
            memory_limit,
            language
        )

    except Exception as e:
        print(f"Error during code submission: {e}")
        raise Exception("No file corresponding to the question ID found. Please check the question ID and try again.")

    return judge_output

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

def write_to_files(payload, user_args, score, DB_CONN_POOL):
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

    submission_file_name = f"{qid}_{socket.gethostname()}_{datetime.now().time()}.java"

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
    try:
        judge_output = get_judgement(
            payload, 
            user_args,
            base_cpu_timeout=1000,  
            base_wall_timeout=3000,
            base_memory_limit=128 * 10**6
        )
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"An error occurred while submitting the code:\n {str(e)}"
        }

    
    
    if judge_output.get("verdict") == "SYSTEM_ERROR":
        return judge_output

    score = judge_output.get("score", 0)
    update_results(payload, score, DB_CONN_POOL)
    write_to_files(payload, user_args, score, DB_CONN_POOL)

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
        "questions_folder": "/home/naveed/Work/CSE221/questions",
        "responses_folder": "/home/naveed/Work/CSE221/responses",
        "exam_id": "cse221_summer2026_section1_quiz0"
    }

    with open("/home/naveed/Projects/CSE221/server/controller/A.java", "r") as f:
        code = f.read()

    payload = {
        "student_id": "CSYR",
        "qid": "Q101",
        "pc_id": "pc1",
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
