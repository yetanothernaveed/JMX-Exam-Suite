import db.connectToDB
from db.createAndPopulate import DatabaseError
from controller.getQuestionsController import get_questions_controller
from utils.promptWindow import request_approval_dialog

import os
import threading

# Starting a session is a read-then-write operation. Serialize starts per
# hostname so two requests for the same PC cannot both pass the attendance
# check, while requests for other PCs proceed independently.
_session_locks_guard = threading.Lock()
_session_locks = {}


def _get_session_lock(hostname):
    with _session_locks_guard:
        lock = _session_locks.get(hostname)
        if lock is None:
            lock = threading.Lock()
            _session_locks[hostname] = lock
        return lock


def _format_session_time(value):
    try:
        return value.strftime("%Y-%m-%d %H:%M:%S")
    except AttributeError:
        return str(value)


def _build_session_approval_request(hostname, student_id, previous_sessions):
    """Build a clear approval prompt from the PC's attendance history."""
    # Caller orders these newest-first, so the first row is the last user.
    last_student_id, last_time = previous_sessions[0]
    other_students = sorted({sid for sid, _ in previous_sessions if sid != student_id})
    is_restart = any(sid == student_id for sid, _ in previous_sessions)

    if other_students and is_restart:
        title = "Session Restart / Override Request"
    elif other_students:
        title = "Session Override Request"
    else:
        title = "Session Restart Request"

    lines = [
        f"Session approval required for hostname '{hostname}'.",
        "",
        f"Last person to use this PC: Student ID '{last_student_id}' "
        f"at {_format_session_time(last_time)}.",
    ]

    # The last user is already shown above; only list the others.
    additional_other_students = [
        sid for sid in other_students if sid != last_student_id
    ]
    if additional_other_students:
        lines.append(
            "Other student ID(s) who have used this PC: "
            + ", ".join(additional_other_students) + "."
        )
    if is_restart:
        lines.append(
            f"Student ID '{student_id}' has already started this exam on this PC."
        )

    lines.extend([
        "",
        f"Student ID '{student_id}' is requesting to start this exam on this PC.",
        "Approve only for a legitimate restart or a valid reason for reassigning the PC.",
        "Otherwise, treat this as a possible academic integrity violation.",
        "",
        "Would you like to approve this session start?",
    ])

    return title, "\n".join(lines)


def start_controller(payload, user_args=None):
    if not user_args or not isinstance(user_args, dict):
        raise ValueError("Start Controller: User arguments must be provided")
    
    student_id = payload.get("student_id")
    hostname = payload.get("hostname")

    if (
        not isinstance(student_id, str)
        or not isinstance(hostname, str)
        or not student_id
        or not hostname
    ):
        return {
            "status": "ERROR",
            "message": "Both student_id and hostname are required to start a session."
        }

    if db.connectToDB.DB_CONN_POOL:
        conn = db.connectToDB.DB_CONN_POOL.get_connection()
        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
            found = cursor.fetchone()

            if not (found and type(found) is tuple and len(found) >= 2):
                print(f"Student {student_id} not found in the database.")
                return {
                    "status": "ERROR",
                    "message": f"Student with id {student_id} was not found in student list."
                }

            print(f"Student {student_id} found in the database.")

            with _get_session_lock(hostname):
                # The sessions table is the PC attendance history for this exam.
                # Fetch every student who has used this PC so we can detect both
                # an override (another student) and a restart (same student).
                cursor.execute(
                    "SELECT student_id, time FROM sessions WHERE hostname = %s "
                    "ORDER BY time DESC, student_id ASC",
                    (hostname,),
                )
                previous_sessions = cursor.fetchall()

                if previous_sessions:
                    title, prompt_msg = _build_session_approval_request(
                        hostname, student_id, previous_sessions
                    )

                    # Spawn the external terminal window and wait for approval
                    approved = request_approval_dialog(title, prompt_msg)

                    if not approved:
                        last_student_id = previous_sessions[0][0]
                        print(f"Approval denied for hostname {hostname}.")
                        return {
                            "status": "ERROR",
                            "message": (
                                f"Session approval was denied for hostname {hostname}. "
                                f"The last person to use this PC was Student ID "
                                f"{last_student_id}."
                            )
                        }

                # Insert or update the session for this hostname and student_id.
                # Other students' rows are kept as attendance history.
                cursor.execute(
                    "REPLACE INTO sessions (hostname, student_id) VALUES (%s, %s)",
                    (hostname, student_id),
                )
                print(f"Session started for student {student_id} on hostname {hostname}.")

            student_folder_path = os.path.join(user_args["responses_folder"], student_id, "best")
            os.makedirs(student_folder_path, exist_ok=True)
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                conn.close()

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
        raise DatabaseError("Database connection is not established. Please connect to the database first.")

