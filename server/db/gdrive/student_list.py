import gspread

from .connect_to_gdrive import CLIENT

class StudentDataSingleton:
    _student_list = None
    _id_to_name = {}
    _section = None

    def __new__(cls, section):
        if cls._student_list is None:
            cls._student_list = StudentDataSingleton.get_student_list(section - 1)
        return cls

    @classmethod
    def get_student_list(cls, section):
        if not cls._student_list:
            print(f"--- Fetching data for Section {section} from Google Sheets ---")
            # Open the sheet and fetch records
            sheet = CLIENT.open("all_sections_student_list").get_worksheet(section - 1) 
            
            try:
                cls._student_list = sheet.get_all_records()
                cls._section = section
            except gspread.exceptions.WorksheetNotFound:
                raise Exception(f"Error: Section {section} does not exist in this file.")
            except Exception as e:
                raise Exception(f"Unknown Error.", e)
                

            for item in cls._student_list:
                cls._id_to_name[item["student_id"]] = item["student_name"]
            
        return cls._id_to_name
    
    @classmethod
    def get_all_student_ids(cls, section):
        if cls._student_list is None:
            cls.get_student_list(section=section)
        return list(cls._id_to_name.keys())
    
    @classmethod
    def find_student_from_id(cls, section, student_id):
        if not cls._student_list:
            cls.get_student_list(section=section)

        if student_id in cls._id_to_name:
            return cls._id_to_name[student_id]
        
        raise Exception(f"No student with found with ID {student_id} in section {cls._section}")
    

# def search_student_by_id(student_id):
    # This function assumes the student ID is in the first column of the sheet
    # students = StudentDataSingleton.get_instance();

if __name__ == "__main__":
    data = StudentDataSingleton.get_student_list(section=1) # Example usage, you can change the section number as needed
    # print("All student data:", data)
    print(data)
