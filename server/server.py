import socket
from pathlib import Path

from router import router
from salp import send, receive
from utils import folderStructure

def start_server(host='0.0.0.0', port=8080, user_args=None, DB_CONN_POOL=None):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Free port
    server_socket.bind((host, port))
    server_socket.listen(10)
    print(f"Server listening on {host}:{port}...")

    try:
        while True:
            conn, addr = server_socket.accept()
            print(f"Connected by {addr}")
            
            try:
                message_json = receive.receive_json(conn)
                print(f"\nReceived Message: {message_json}\n")

                server_response = router(message_json, user_args, DB_CONN_POOL)
                send.send_json(conn, server_response)
                
            except Exception as e:
                print(f"Error handling data: {e}")
            finally:
                conn.close()
                print(f"Connection with {addr} closed.\n")
                
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        server_socket.close()

if __name__ == "__main__":
    from utils import args, folderStructure
    from db.connectToDB import connect_to_mysql_database
    
    # user_args = args.take_args()
    # folderStructure.validate(user_args["questions_folder"], user_args["responses_folder"])
    
    # database_name = f"{user_args['course_name']}_"
    # database_name += f"{user_args['semester']}{user_args['year']}_"
    # database_name += f"section{user_args['section']}_"
    # database_name += f"{user_args['quiz number']}"
    
    # for testing only
    user_args = {
        "course": "cse221",
        "semester": "summer",
        "year": "2026",
        "section": "1",
        "quiz_number": "0",
        "slot": "SUN_11",
        "questions_folder_root": Path.home() / "Projects/CSE221/examplesetup/questions",
        "responses_folder_root": Path.home() / "Projects/CSE221/examplesetup/responses",
        "total_time": "60"
    }
    user_args["exam_id"] = f"{user_args['course']}_{user_args['semester']}{user_args['year']}_section{user_args['section']}_quiz{user_args['quiz_number']}"

    user_args["questions_folder"], user_args["responses_folder"] = folderStructure.validate(
        user_args["questions_folder_root"], 
        user_args["responses_folder_root"], 
        user_args["exam_id"]
    )
    
    DB_CONN_POOL = connect_to_mysql_database(section=1, database_name=user_args["exam_id"])
    start_server(user_args = user_args, DB_CONN_POOL=DB_CONN_POOL)
