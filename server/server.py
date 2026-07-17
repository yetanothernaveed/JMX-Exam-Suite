import socket

from router import router
from salp import send, receive

def start_server(host='0.0.0.0', port=8080):
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
                print(f"Received Message: {message_json}\n")

                server_response = router(message_json)
                send.send_json(conn, server_response)
                
            except Exception as e:
                print(f"Error handling data: {e}")
            finally:
                conn.close()
                print(f"Connection with {addr} closed.")
                
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        server_socket.close()

if __name__ == "__main__":
    from startFlow import args, folderStructure
    from db.connectToDB import connect_to_mysql_database
    
    # user_args = args.take_args()
    # folderStructure.validate(user_args["questions_folder"], user_args["responses_folder"])
    
    # database_name = f"{user_args['course_name']}_"
    # database_name += f"{user_args['semester']}{user_args['year']}_"
    # database_name += f"section{user_args['section']}_"
    # database_name += f"{user_args['quiz number']}"
    
    DB_CONN_POOL = connect_to_mysql_database(section=1, database_name="testdb")
    start_server()
