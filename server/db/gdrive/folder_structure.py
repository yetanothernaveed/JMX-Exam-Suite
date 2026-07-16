import os
from db.gdrive.student_list import StudentDataSingleton

COURSE_CODE = input("Enter the course code: ").upper() # GLOBAL
SECTION_NUM = int(input("Enter the section number: ")) # GLOBAL 
QUIZ_NUM = int(input("Enter the quiz number: ")) # GLOBAL

if SECTION_NUM < 1:
    raise ValueError("Section number be greater than one.")

ROOT_DIR = os.path.join(f"~/{COURSE_CODE}QuizFiles", f"section_{SECTION_NUM}", f"quiz_{QUIZ_NUM}") # GlOBAL
print(f"Quiz Root directory: {ROOT_DIR}")

if not os.path.exists(ROOT_DIR):
    # os.makedirs(ROOT_DIR) # comment up for testing
    print(f"Directory {ROOT_DIR} created successfully.")
else:        
    print(f"Directory {ROOT_DIR} already exists.")

new_count = 0
existing_count = 0
for student_id in StudentDataSingleton.get_all_student_ids(section=SECTION_NUM):
    student_dir = os.path.join(ROOT_DIR, f"{student_id}")
    
    if not os.path.exists(student_dir):
        # os.makedirs(student_dir) # comment up for testing
        new_count += 1
    else:
        existing_count += 1
    
print(f"Total new directories created: {new_count}")
print(f"Total existing directories: {existing_count}")
