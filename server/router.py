from controller.startController import start_controller

def router(message_json):
    action = message_json.get("action")

    if action == "start":
        return start_controller(message_json.get("payload"))

    
