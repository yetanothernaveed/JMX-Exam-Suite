from controller.startController import start_controller
from controller.endController import end_controller
from controller.getQuestionsController import get_questions_controller

def router(message_json, user_args=None):
    action = message_json.get("action")

    if action == "start":
        return start_controller(message_json.get("payload"), user_args)
    elif action == "end":
        return end_controller(message_json.get("payload"), user_args)
    elif action == "get_questions":
        return get_questions_controller(message_json.get("payload"), user_args)
    # ToDo submit, get_stats, get_best,

    
