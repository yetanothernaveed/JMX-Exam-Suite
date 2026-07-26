import os

def get_questions_controller(payload, user_args):
    if not user_args or not isinstance(user_args, dict):
        raise ValueError("Get Questions Controller: User arguments must be provided")
    
    questions_folder = user_args.get("questions_folder")
    if not questions_folder:
        raise ValueError("Get Questions Controller: 'questions_folder' must be provided in user arguments")

    questions = get_questions(questions_folder)

    # Read the files and add them to the payload labeled with their file names
    questions_payload = []
    for question in questions:
        qid = question["qid"]
        path = question["path"]
        extension = question["extension"]
        with open(path, 'r') as file:
            questions_payload.append({
                "qid": qid,
                "content": file.read(),
                "extension": extension
            })

    return {
        "status": "SUCCESS", 
        "message": f"Questions retrieved successfully.", 
        "payload": {
            "questions": questions_payload
        }
    }

def get_questions(questions_folder):
    # For each folder in questions folder, look for files with extensions .md, .java and .py
    # Don't look at the questions folder itself, only look at the subfolders
    questions = []
    for root, dirs, _ in os.walk(questions_folder):
        for dir in dirs:
            if dir.startswith('~'):
                continue  # Skip directory whose name starts with ~
            dir_path = os.path.join(root, dir)
            for file in os.listdir(dir_path):
                if file.endswith(".md") or file.endswith(".java") or file.endswith(".py"):
                    questions.append({
                        "qid": dir,
                        "path": os.path.join(dir_path, file),
                        "extension": os.path.splitext(file)[1]
                    })
           
    return questions
