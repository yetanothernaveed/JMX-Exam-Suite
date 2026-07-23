import db.connectToDB
from db.createAndPopulate import DatabaseError

import os

def start_controller(payload, user_args=None):
    if not user_args or not isinstance(user_args, dict):
        raise ValueError("Start Controller: User arguments must be provided")
    
    student_id = payload.get("student_id")

    if db.connectToDB.DB_CONN_POOL:
        conn = db.connectToDB.DB_CONN_POOL.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
        found = cursor.fetchone()

        if found and type(found) is tuple and len(found) >= 2:
            print(f"Student {student_id} found in the database.")
            questions = get_questions(user_args.get("questions_folder") if user_args else None)

            # Read the files and add them to the payload labeled with their file names
            questions_payload = {}
            for qid, path, extension in questions:
                with open(path, 'r') as file:
                    if extension == ".md":
                        questions_payload[qid]["md"] = file.read()
                    elif extension == ".java":
                        questions_payload[qid]["java"] = file.read()
                    elif extension == ".py":
                        questions_payload[qid]["py"] = file.read()


            return {
                "status": "SUCCESS", 
                "message": f"Student {student_id} found.", 
                "payload": {
                    "student_id": found[0],
                    "student_name": found[1],
                    "exam_id": user_args.get("exam_id") if user_args else None,
                    "questions": questions_payload
                }
            }
        else:
            print(f"Student {student_id} not found in the database.")
            return {
                "status": "ERROR", 
                "message": f"Student with id {student_id} was not found in student list."
            }
    else:
        raise DatabaseError("Database connection is not established. Please connect to the database first.")


def get_questions(questions_folder):
    print("Getting Questions from the questions folder...")

    # For each folder in questions folder, look for files with extensions .md, .java and .py
    # Don't look at the questions folder itself, only look at the subfolders
    questions = []
    for root, dirs, _ in os.walk(questions_folder):
        for dir in dirs:
            dir_path = os.path.join(root, dir)
            for file in os.listdir(dir_path):
                if file.endswith(".md") or file.endswith(".java") or file.endswith(".py"):
                    questions.append({
                        "qid": dir,
                        "path": os.path.join(dir_path, file),
                        "extension": os.path.splitext(file)[1]
                    })
                    
    return questions
