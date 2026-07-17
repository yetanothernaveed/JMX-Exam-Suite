from .createAndPopulate import create_and_populate_database
from .connectToDBServer import connect_to_mysql_server, close_connection_to_mysql_server

import mysql.connector.pooling
from mysql.connector import Error
import os
from dotenv import load_dotenv
load_dotenv()

# Global Variable
DB_CONN_POOL = None

def connect_to_mysql_database(section, database_name):
    """
    Establish a connection to the specified MySQL/MariaDB database.
    If the database does not exist, it will be created and populated with initial data from google sheets.

    Args:
        section (int): The section for which to create the database.
        database_name (str): The name of the database to connect to.

    Returns:
        connectionPool: Thread safe connection pool.
    """
    if not database_exists(database_name):
        print(f"Database with name {database_name} does not exist")
        print(f"----------------- Creating and Populating database from Google Sheets -----------------")
        create_and_populate_database(section, database_name)
    else:
        print(f"Database with name {database_name} already exists. Connecting to it...")
    
    try:
        global DB_CONN_POOL
        DB_CONN_POOL = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="db_conn_pool",
            pool_size=10,
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=database_name,
            autocommit=True
        )

        return DB_CONN_POOL
    except Error as e:
        raise Error(f"Error while connecting to MySQL database '{database_name}': {e}")
    

def database_exists(database_name):
    conn = None
    cursor = None
    try:
        conn = connect_to_mysql_server()
        
        if conn and conn.is_connected():
            cursor = conn.cursor()
            
            query = "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s"
            cursor.execute(query, (database_name,))
            
            result = cursor.fetchone()
            return result is not None

    except Error as e:
        raise Error(f"Error while connecting to MySQL: {e}")

    finally:
        close_connection_to_mysql_server(conn)
