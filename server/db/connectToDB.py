from .createAndPopulate import create_and_populate_database
from .connectToDBServer import connect_to_mysql_server, close_connection_to_mysql_server

import mysql.connector.pooling
from mysql.connector import Error
import os
import threading
from dotenv import load_dotenv
load_dotenv()

# MySQL Connector/Python refuses to create a pool larger than 32.
MAX_DB_POOL_SIZE = 32


def _configured_pool_size():
    try:
        requested = int(os.getenv("DB_POOL_SIZE", str(MAX_DB_POOL_SIZE)))
    except ValueError:
        requested = MAX_DB_POOL_SIZE

    return max(1, min(requested, MAX_DB_POOL_SIZE))


DB_POOL_SIZE = _configured_pool_size()

# Global Variable
DB_CONN_POOL = None


class _PooledConnection:
    """Proxy that releases its pool slot exactly once when closed."""

    def __init__(self, connection, release_slot):
        self._connection = connection
        self._release_slot = release_slot
        self._closed = False
        self._close_lock = threading.Lock()

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        with self._close_lock:
            if self._closed:
                return

            self._closed = True
            connection = self._connection
            self._connection = None

        try:
            connection.close()
        finally:
            self._release_slot()


class BlockingConnectionPool:
    """Waits for a free connection instead of failing when the pool is busy.

    The connector's pool is capped at 32 connections, but the server may
    receive more simultaneous requests. This wrapper lets the extra requests
    queue for a connection rather than raising ``PoolError``.
    """

    def __init__(self, pool, size):
        self._pool = pool
        self._slots = threading.BoundedSemaphore(size)

    def __getattr__(self, name):
        return getattr(self._pool, name)

    def get_connection(self):
        self._slots.acquire()
        try:
            connection = self._pool.get_connection()
        except BaseException:
            self._slots.release()
            raise

        return _PooledConnection(connection, self._slots.release)


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
        pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="db_conn_pool",
            pool_size=DB_POOL_SIZE,
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=database_name,
            autocommit=True
        )
        DB_CONN_POOL = BlockingConnectionPool(pool, DB_POOL_SIZE)

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
