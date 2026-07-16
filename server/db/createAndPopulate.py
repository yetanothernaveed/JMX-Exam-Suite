from .gdrive import student_list

class DatabaseError(Exception):
    """Raised when the database setup or creation fails."""
    pass


def database_exists(connection, database_name):
    """
    Check if the specified database exists.

    Args:
        connection: A database connection object.
        database_name (str): The name of the database to check.
    """

    # Check if the database exists
    cursor = connection.cursor()
    cursor.execute("SHOW DATABASES")
    databases = [db[0] for db in cursor.fetchall()]
    if database_name in databases:
        print(f"Database '{database_name}' exists. Proceeding with the connection.")
        return True
    
    return False

def create_database(connection, database_name):
    """
    Create the specified database.

    Args:
        connection: A database connection object.
        database_name (str): The name of the database to create.
    """
    try:
        cursor = connection.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database_name}")
        print(f"Database '{database_name}' created successfully.")
    except Exception as e:
        print(f"Error creating database '{database_name}'")
        print("Verify the database user has creation privileges.")
        raise DatabaseError(f"Error creating database '{database_name}': {e}")

def populate_database(connection, section, database_name):
    """
    Populate the specified database with initial data.

    Args:
        connection: A database connection object.
        database_name (str): The name of the database to populate.
    """
    if database_exists(connection, database_name):
        print(f"Database '{database_name}' already exists. Skipping creation and population.")
        return

    create_database(connection, database_name)

    try:
        cursor = connection.cursor()
        cursor.execute(f"USE {database_name}")

        cursor.execute(f"CREATE TABLE IF NOT EXISTS students (id VARCHAR(15) PRIMARY KEY, name TEXT)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submission (
                id VARCHAR(100) PRIMARY KEY,
                student_id VARCHAR(15),
                pc_id TEXT,
                question_id TEXT,
                time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                score INT,
                
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        """)

        data = student_list.StudentDataSingleton.get_student_list(section=section)

        print(f"Found a total of {len(data)} students in section {section}. Populating the database...")

        for student_id, student_name in data.items():
            cursor.execute("INSERT INTO students (id, name) VALUES (%s, %s)", (student_id, student_name))

        print(f"Database '{database_name}' populated successfully with student data for section {section}.")
    except Exception as e:
        raise DatabaseError(f"Error populating database '{database_name}': {e}")
