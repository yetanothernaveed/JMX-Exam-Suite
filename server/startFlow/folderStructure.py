def validate(questions_folder, responses_folder):
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
        
    questions = [
        f for f in os.listdir(questions_folder) 
        if os.path.isfile(os.path.join(questions_folder, f)) and f.lower().endswith(('.md', '.markdown'))
    ]

    if not questions:
        raise FileNotFoundError(f"No markdown question files found in the questions folder: {questions_folder}")

    # Create responses folder if it doesn't exist
    if not os.path.exists(responses_folder):
        os.makedirs(responses_folder)
        print(f"Responses folder did not exist so it was created: {responses_folder}")
    
