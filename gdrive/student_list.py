import gspread

from connect_to_gdrive import CLIENT

class StudentDataSingleton:
    _student_list = None
    _id_to_name = {}
    _section_num = None

    def __new__(cls):
        if cls._student_list is None:
            cls._student_list = StudentDataSingleton.get_student_list()
        return cls._student_list

    @classmethod
    def get_student_list(cls, section_num):
        if not cls._student_list:
            print(f"--- Fetching data for Section {section_num} from Google Sheets ---")
            # Open the sheet and fetch records
            sheet = CLIENT.open("all_sections_student_list").get_worksheet(section_num - 1) 
            
            try:
                cls._student_list = sheet.get_all_records()
                cls._section_num = section_num
            except gspread.exceptions.WorksheetNotFound:
                raise Exception(f"Error: Section {section_num} does not exist in this file.")
            except Exception as e:
                raise Exception(f"Unknown Error.", e)
                

            for item in cls._student_list:
                cls._id_to_name[item["student_id"]] = item["student_name"]
            
        return cls._student_list
    
    @classmethod
    def get_all_student_ids(cls, section_num):
        if cls._student_list is None:
            cls.get_student_list(section_num=section_num)
        return list(cls._id_to_name.keys())
    
    @classmethod
    def find_student_from_id(cls, section_num, student_id):
        if not cls._student_list:
            cls.get_student_list(section_num=section_num)

        if student_id in cls._id_to_name:
            return cls._id_to_name[student_id]
        
        raise Exception(f"No student with found with ID {student_id} in section {cls._section_num}")
    

# def search_student_by_id(student_id):
    # This function assumes the student ID is in the first column of the sheet
    # students = StudentDataSingleton.get_instance();

if __name__ == "__main__":
    data = StudentDataSingleton.get_student_list(section_num=1) # Example usage, you can change the section number as needed
    # print("All student data:", data)
    for id, full_name in StudentDataSingleton._id_to_name.items():
        last_name = full_name.split(" ")[-1]
        first_name = full_name.split(" ")[:-1]
        print(f"{last_name}, {' '.join(first_name)}")
