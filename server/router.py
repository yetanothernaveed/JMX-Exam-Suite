from controller.startController import start_controller
from controller.endController import end_controller
from controller.getQuestionsController import get_questions_controller
from controller.submissionController import submit
from controller.getStatsController import get_stats_controller
from controller.getSubmissionsController import (
    get_best_submission_controller,
    get_recent_submissions_controller,
)

def router(message_json, user_args, DB_CONN_POOL):
    action = message_json.get("action")

    if action == "hello":
        return {"status": "SUCCESS", "message": "Hi! I am server :P."}
    elif action == "start":
        return start_controller(message_json.get("payload"), user_args)
    elif action == "end":
        return end_controller(message_json.get("payload"), user_args)
    elif action == "get_questions":
        return get_questions_controller(message_json.get("payload"), user_args)
    elif action == "submit":
        return submit(message_json.get("payload"), user_args, DB_CONN_POOL)
    elif action == "get_stats":
        return get_stats_controller(message_json.get("payload"), DB_CONN_POOL)
    elif action == "get_recent_submissions":
        return get_recent_submissions_controller(message_json.get("payload"), user_args)
    elif action == "get_best_submission":
        return get_best_submission_controller(message_json.get("payload"), user_args)
    else:
        return {"status": "ERROR", "message": f"Unknown action: {action}"}
    
