from .enums import SemesterEnum
from .findCurrentSlot import currentSlot 


def take_args():
    course = input("Enter the course code: ").lower()
    print()
    
    semester = input("Enter the semester (fall, spring, summer): ").lower()
    print()

    if semester not in [semester.value for semester in SemesterEnum]:
        print("Invalid semester. Please enter a valid semester.")
        return take_args()
    
    year = input("Enter the year (e.g., 2026): ")
    print()

    if len(year) != 4 or not year.isdigit():
        print("Invalid year. Please enter the full four digit year.")
        print("Example: 2026")
        print("Unless of course, you're from the future, in which case, hi!")
        print("JMX was written in the year 2026 (bad time to be alive btw) by YetAnotherNaveed and rated for use until the year 9999.")
        print("He didn't foresee Earth or BracU making it that far into the future, sorry.")
        print()

        return take_args()
    
    try:
        section = int(input("Enter the section: "))
    except ValueError:
        print("Invalid section. Please enter a valid integer.")
        return take_args()

    quiz_number = input("Enter the quiz number [0-infinity]: ")
    print()

    if not quiz_number.isdigit() or int(quiz_number) < 0:
        print("Invalid quiz number. Please enter a non-negative integer.")
        return take_args()
    
    slot = currentSlot()
    print(f"Current Slot: {slot}")
    slot_number_confirm = input(f"Confirm the slot ID is correct: (y/n): ")
    print()

    if (slot_number_confirm.lower() != 'y'):
        slot = input("Enter the correct slot ID (e.g., 'SPECIAL', 'MON_8', 'TUE_11', etc.): ")
        print()

    questions_folder_root = f"~/questions"
    print(f"Question folder root path: {questions_folder_root}")
    
    question_folder_confirm = input(f"Confirm the question folder path is correct: (y/n): ")
    print()
    if (question_folder_confirm.lower() != 'y'):
        questions_folder = input("Enter the correct absolute path: ")
        print()

    reponses_folder_root = f"~/responses/"
    print(f"Quiz responses folder root path: {reponses_folder_root}")

    quiz_reponses_folder_confirm = input(f"Confirm the quiz responses folder path is correct: (y/n): ")
    print()
    if (quiz_reponses_folder_confirm.lower() != 'y'):
        reponses_folder = input("Enter the correct absolute path: ")
        print()

    total_time = int(input("Enter the total time for the quiz in minutes: "))
    print()

    

    
    return {
        "course": course,
        "semester": semester,
        "section": section,
        "year": year,
        "quiz_number": quiz_number,
        "slot": slot,
        "questions_folder_root": questions_folder_root,
        "responses_folder_root": reponses_folder_root,
        "total_time": total_time
    }
