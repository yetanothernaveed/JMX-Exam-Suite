import db.connectToDB
from db.createAndPopulate import DatabaseError

def start_controller(payload):
    student_id = payload.get("student_id")

    if db.connectToDB.DB_CONN_POOL:
        conn = db.connectToDB.DB_CONN_POOL.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
        found = cursor.fetchone()

        if found and type(found) is tuple and len(found) >= 2:
            print(f"Student {student_id} found in the database.")
            return {
                "status": "success", 
                "message": f"Student {student_id} found.", 
                "payload": {
                    "student_id": found[0],
                    "name": found[1]
                }
            }
        else:
            print(f"Student {student_id} not found in the database.")
            return {"status": "error", "message": f"Student {student_id} not found."}
    else:
        raise DatabaseError("Database connection is not established. Please connect to the database first.")

