import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
load_dotenv()

def connect_to_mysql_server():
    conn = None
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            autocommit=True
        )
        
        if conn.is_connected():
            return conn

    except Error as e:
        raise Error(f"Error while connecting to MySQL: {e}")
    
def close_connection_to_mysql_server(conn):
    try:
        if conn and conn.is_connected():
            conn.close()
    except Error as e:
        raise Error("Error closing mysql server connection object")
