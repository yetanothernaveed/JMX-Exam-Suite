import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

def check_if_database_exists(connection, database_name):
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
    if database_name not in databases:
        raise ValueError(f"Database '{database_name}' does not exist. Please create and populate it first.")
    
    print(f"Database '{database_name}' exists. Proceeding with the connection.")


def connect_to_mysql_server():
    """
    Establish a connection to the specified MySQL/MariaDB database.
    If the database does not exist, it will be created.

    Args:
        database_name (str): The name of the database to connect to.

    Returns:
        connection: A database connection object.
    """
    connection = None
    
    try:
        load_dotenv()
        # 1. Establish connection to local MySQL
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST'),          # Use IP to avoid socket issues
            user=os.getenv('DB_USER'),      # Your MySQL username (e.g., 'root')
            password=os.getenv('DB_PASSWORD'),  # Your MySQL password 
            autocommit=True  # Automatically commit changes to the database
        )

        if connection.is_connected():
            print("Successfully connected to the MySQL database!")
            
            # 2. Get server info
            db_info = connection.server_info
            print(f"MySQL Server version: {db_info}")

            return connection
        
    except Error as e:
        print(f"Error while connecting to MySQL: {e}")


if __name__ == "__main__":
    connect_to_mysql_server()
