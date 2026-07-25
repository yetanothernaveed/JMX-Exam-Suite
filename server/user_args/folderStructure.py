def validate(questions_folder_root, responses_folder_root, exam_id):
    """
    Creates the folder structure for questions and responses if they don't exist.
    
    Args:
        questions_folder_root (str): The path to the questions folder root.
        responses_folder_root (str): The path to the responses folder root.
        exam_id (str): The ID of the exam for which to create folders.
    """
    import os

    # Create questions folder if it doesn't exist
    if not os.path.exists(questions_folder_root):
        # raise error
        raise FileNotFoundError(f"Questions folder root does not exist: {questions_folder_root}")

    if not os.path.exists(questions_folder_root / exam_id):
        os.makedirs(questions_folder_root / exam_id)
        raise FileNotFoundError(f"Questions folder with exam id does not exist: {questions_folder_root / exam_id}")

    number_of_questions_files_found = 0 
    for root, dirs, _ in os.walk(questions_folder_root / exam_id):
            for dir in dirs:
                dir_path = os.path.join(root, dir)
                for file in os.listdir(dir_path):
                    if file.endswith(".md"):
                        number_of_questions_files_found += 1

    if number_of_questions_files_found == 0:
        raise FileNotFoundError(f"No markdown question files found in the questions folder: {questions_folder_root / exam_id}")

    # Create responses folder if it doesn't exist
    if not os.path.exists(responses_folder_root):
        os.makedirs(responses_folder_root)
        print(f"Responses folder did not exist so it was created: {responses_folder_root}")
    

    # Create exam folder inside responses folder if it doesn't exist
    exam_folder = os.path.join(responses_folder_root, exam_id)
    if not os.path.exists(exam_folder):
        os.makedirs(exam_folder)
        print(f"Exam folder did not exist so it was created: {exam_folder}")

    return (questions_folder_root / exam_id, exam_folder)
    
