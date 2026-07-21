from controller.startController import start_controller
from controller.endController import end_controller

def router(message_json, user_args=None):
    action = message_json.get("action")

    if action == "start":
        return start_controller(message_json.get("payload"), user_args)
    elif action == "end":
        return end_controller(message_json.get("payload"), user_args)

    
