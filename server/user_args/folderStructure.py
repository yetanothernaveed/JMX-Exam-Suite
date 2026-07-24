def validate(questions_folder, responses_folder, exam_id):
    """
    Creates the folder structure for questions and responses if they don't exist.
    
    Args:
        questions_folder (str): The path to the questions folder.
        responses_folder (str): The path to the responses folder.
    """
    import os

    # Create questions folder if it doesn't exist
    if not os.path.exists(questions_folder):
        # raise error
        raise FileNotFoundError(f"Questions folder does not exist: {questions_folder}")

    number_of_questions_files_found = 0 
    for root, dirs, _ in os.walk(questions_folder):
            for dir in dirs:
                dir_path = os.path.join(root, dir)
                for file in os.listdir(dir_path):
                    if file.endswith(".md") or file.endswith(".java") or file.endswith(".py"):
                        number_of_questions_files_found += 1

    if number_of_questions_files_found == 0:
        raise FileNotFoundError(f"No markdown question files found in the questions folder: {questions_folder}")

    # Create responses folder if it doesn't exist
    if not os.path.exists(responses_folder):
        os.makedirs(responses_folder)
        print(f"Responses folder did not exist so it was created: {responses_folder}")

    # Create exam folder inside responses folder if it doesn't exist
    exam_folder = os.path.join(responses_folder, exam_id)
    if not os.path.exists(exam_folder):
        os.makedirs(exam_folder)
        print(f"Exam folder did not exist so it was created: {exam_folder}")
    
