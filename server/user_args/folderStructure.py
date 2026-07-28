from pathlib import Path

def validate_questions_folder(questions_folder_root, exam_id):
    """
    Validates the questions folder structure for a given exam.
    """
    questions_root = Path(questions_folder_root)
    exam_folder = questions_root / exam_id

    # 1. Check if the exam_id folder exists
    if not exam_folder.exists() or not exam_folder.is_dir():
        raise FileNotFoundError(f"Questions folder with exam ID does not exist: {exam_folder}")

    # 2. Find and print subfolders
    subfolders = [f for f in exam_folder.iterdir() if f.is_dir()]
    
    print(f"Found {len(subfolders)} folder(s) inside '{exam_folder}':")
    for folder in subfolders:
        print(f" - {folder.name}")

    # 3. Ensure each subfolder has the required inner folders
    required_inner_folders = {"~judge", "~testcases", "~wrapper"}
    
    for folder in subfolders:
        existing_inner_folders = {child.name for child in folder.iterdir() if child.is_dir()}
        missing_folders = required_inner_folders - existing_inner_folders
        
        if missing_folders:
            raise FileNotFoundError(
                f"Folder '{folder.name}' is missing the following required subfolder(s): "
                f"{', '.join(missing_folders)}"
            )

    return exam_folder


def validate_responses_folder(responses_folder_root, exam_id):
    """
    Validates and creates the responses folder structure for a given exam if necessary.
    """
    responses_root = Path(responses_folder_root)
    exam_folder = responses_root / exam_id

    # 1 & 2. Check if the folder exists, create if it doesn't
    if exam_folder.exists() and exam_folder.is_dir():
        print(f"Response folder with exam ID already exists at: {exam_folder}. Moving on.")
    else:
        # parents=True acts like os.makedirs, ensuring root folders are created if missing
        exam_folder.mkdir(parents=True, exist_ok=True)
        print(f"Response folder did not exist, so it was created at: {exam_folder}")

    return exam_folder


def validate(questions_folder_root, responses_folder_root, exam_id):
    """
    Main orchestration function to validate both questions and responses folders.
    
    Args:
        questions_folder_root (str or Path): The path to the questions folder root.
        responses_folder_root (str or Path): The path to the responses folder root.
        exam_id (str): The ID of the exam.
        
    Returns:
        tuple: (validated_questions_path, validated_responses_path)
    """
    # Cast exam_id to string to ensure safe path joining
    exam_id = str(exam_id)
    
    print("--- Validating Questions Folder ---")
    questions_path = validate_questions_folder(questions_folder_root, exam_id)
    
    print("\n--- Validating Responses Folder ---")
    responses_path = validate_responses_folder(responses_folder_root, exam_id)
    
    print("\nFolder Validations Complete.")
    
    return questions_path, responses_path
