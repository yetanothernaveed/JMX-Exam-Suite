import db.connectToDB
from db.createAndPopulate import DatabaseError
from controller.getQuestionsController import get_questions_controller
from utils.promptWindow import request_approval_dialog

import os

def start_controller(payload, user_args=None):
    if not user_args or not isinstance(user_args, dict):
        raise ValueError("Start Controller: User arguments must be provided")
    
    student_id = payload.get("student_id")
    hostname = payload.get("hostname")

    if db.connectToDB.DB_CONN_POOL:
        conn = db.connectToDB.DB_CONN_POOL.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
        found = cursor.fetchone()

        if found and type(found) is tuple and len(found) >= 2:
            print(f"Student {student_id} found in the database.")

            student_folder_path = os.path.join(user_args["responses_folder"], student_id, "best")
            if not os.path.exists(student_folder_path):
                os.makedirs(student_folder_path)
                print(f"Student folder did not exist so it was created: {student_folder_path}")

            # Check if an active session exists for this hostname and a different student_id
            cursor.execute("SELECT * FROM sessions WHERE hostname = %s AND student_id != %s", (hostname, student_id))
            active_session = cursor.fetchone()

            if active_session:
                prompt_msg = (
                    f"An active session already exists for hostname '{hostname}' "
                    f"belonging to Student ID: '{active_session[1]}'.\n"
                    f"Student ID '{student_id}' is requesting to overwrite this session.\n"
                    f"If a student knowingly did this without a valid reason, consider this an academic integrity violation.\n"
                    f"Would you like to approve the session override?"
                )

                # Spawn the external terminal window and wait for approval
                approved = request_approval_dialog("Session Override Request", prompt_msg)
                
                if not approved:
                    print(f"Approval denied or timed out for hostname {hostname}.")
                    return {
                        "status": "ERROR",
                        "message": f"An active session already exists for hostname {hostname} with a different student ID ({active_session[1]}). Session override approval was denied."
                    }
            
            # Insert or update the session for this hostname and student_id
            cursor.execute("REPLACE INTO sessions (hostname, student_id) VALUES (%s, %s)", (hostname, student_id))
            conn.commit()
            print(f"Session started for student {student_id} on hostname {hostname}.")
            
            return {
                "status": "SUCCESS", 
                "message": f"Student {student_id} found.", 
                "payload": {
                    "student_id": found[0],
                    "student_name": found[1],
                    "exam_id": user_args.get("exam_id") if user_args else None,
                    "questions": get_questions_controller(payload, user_args)["payload"]["questions"]
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
    # For each folder in questions folder, look for files with extensions .md, .java and .py
    # Don't look at the questions folder itself, only look at the subfolders
    questions = []
    for root, dirs, _ in os.walk(questions_folder):
        for dir in dirs:
            dir_path = os.path.join(root, dir)
            for file in os.listdir(dir_path):
                if file.endswith(".md") or file.endswith(".java") or file.endswith(".py") or file.endswith(".cpp"):
                    questions.append({
                        "qid": dir,
                        "path": os.path.join(dir_path, file),
                        "extension": os.path.splitext(file)[1]
                    })
           
    return questions
