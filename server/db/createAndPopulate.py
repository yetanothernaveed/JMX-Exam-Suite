from .gdrive import student_list
from .connectToDBServer import connect_to_mysql_server, close_connection_to_mysql_server

class DatabaseError(Exception):
    """Raised when the database setup or creation fails."""
    pass

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
    except DatabaseError as e:
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

    try:
        cursor = connection.cursor()
        cursor.execute(f"USE {database_name}")

        cursor.execute(f"CREATE TABLE IF NOT EXISTS students (id VARCHAR(15) PRIMARY KEY, name TEXT)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id CHAR(100) PRIMARY KEY DEFAULT (UUID()),
                student_id VARCHAR(15),
                pc_id TEXT,
                question_id TEXT,
                time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                score INT,
                
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                hostname VARCHAR(255),
                student_id VARCHAR(15),
                time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (hostname, student_id),
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        """)

        data = student_list.StudentDataSingleton.get_student_list(section=section)

        print(f"Found a total of {len(data)} students in section {section}. Populating the database...")

        for student_id, student_name in data.items():
            cursor.execute("INSERT INTO students (id, name) VALUES (%s, %s)", (student_id, student_name))

        print(f"Database '{database_name}' populated successfully with student data for section {section}.")
    except DatabaseError as e:
        raise DatabaseError(f"Error populating database '{database_name}': {e}")

def create_and_populate_database(section, database_name):
    conn = None
    try:
        conn = connect_to_mysql_server()
        if conn and conn.is_connected():
            create_database(conn, database_name)
            populate_database(conn, section, database_name=database_name)
    except DatabaseError as e:
        raise DatabaseError(f"Error in create_and_populate_database:\n {e}")
    finally:
        close_connection_to_mysql_server(conn)
    
