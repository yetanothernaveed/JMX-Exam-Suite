def get_stats_controller(payload, DB_CONN_POOL):
    student_id = payload.get("student_id")
    if not student_id:
        return {"status": "ERROR", "message": "Missing student_id in payload."}

    if DB_CONN_POOL is None:
        return {"status": "ERROR", "message": "Database connection is not available."}

    try:
        conn = DB_CONN_POOL.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch student stats from the database
        cursor.execute("""
            SELECT question_id, COUNT(*) as total_submissions, MAX(score) as best_score
            FROM submissions
            WHERE student_id = %s
            GROUP BY student_id,question_id
        """, (student_id,))
        student_stats = cursor.fetchall()

        if not student_stats:
            return {"status": "ERROR", "message": f"Student with id {student_id} not found."}

        stats = "-------------------\n"
        total_score = 0
        for idx, stat in enumerate(student_stats):
            stats += f"({idx + 1}) Question ID: {stat['question_id']}, Total Submissions: {stat['total_submissions']}, Best Score: {stat['best_score']}\n"
            total_score += stat['best_score'] if stat['best_score'] is not None else 0
        stats += "-------------------\n"
        stats += f"Total score for student {student_id}: {total_score}\n"

    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

    return {
        "status": "SUCCESS", 
        "message": f"Stats retrieved for student {student_id}.",
        "payload": {
            "stats": stats
        }

    }
