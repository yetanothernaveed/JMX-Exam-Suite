import socket
import struct
import json

def receive_exact(conn, length):
    """
    Helper function to ensure we read exactly 'length' bytes.
    TCP streams can fragment, so a single recv() might not return 
    the full amount requested.
    """
    data = b''
    while len(data) < length:
        packet = conn.recv(length - len(data))
        if not packet:
            # The client closed the connection unexpectedly
            return None
        data += packet
    return data

def send_msg(conn, message_str):
    """
    Helper function to send a length-prefixed message to the client.
    """
    # 1. Encode the string to raw bytes (UTF-8)
    message_bytes = message_str.encode('utf-8')
    
    # 2. Get the length of the message
    msg_len = len(message_bytes)
    
    # 3. Pack the length into a 4-byte big-endian integer ('!I')
    header = struct.pack('!I', msg_len)
    
    # 4. Send the header followed by the actual message body
    # sendall() guarantees that the entire buffer is transmitted or an error is raised
    conn.sendall(header + message_bytes)
    print(f"Sent response of {msg_len} bytes back to client.")

def start_server(host='0.0.0.0', port=8080):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Allow immediate reuse of the port after stopping the server
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    server_socket.bind((host, port))
    server_socket.listen(1)
    print(f"Server listening on {host}:{port}...")

    try:
        while True:
            conn, addr = server_socket.accept()
            print(f"Connected by {addr}")
            
            try:
                # 1. Read the 4-byte uint32_t header containing the message length
                header = receive_exact(conn, 4)
                if not header:
                    print("Client disconnected before sending header.")
                    continue
                
                # 2. Unpack the 4 bytes into a Python integer
                # '<I' means Standard Little-Endian, 32-bit unsigned int (common for C++)
                # '!I' or '>I' means Network Byte Order (Big-Endian)
                # Change to '!I' if your C++ client converts to network byte order using htonl()
                message_length = struct.unpack('!I', header)[0]
                print(f"Expecting a message of size: {message_length} bytes")
                
                # 3. Read the actual message based on the size we just unpacked
                message_bytes = receive_exact(conn, message_length)
                if not message_bytes:
                    print("Client disconnected before sending full message.")
                    continue
                
                # 4. Decode the text data
                message = message_bytes.decode('utf-8')
                message_json = json.loads(message)  # Assuming the message is in JSON format
                print(f"Received Message: {message_json}\n")

                server_response = f"Server received your exam start request.\n"
                server_response += f"It will now verify your student ID against the student list\n"
                server_response += f"and then send you the exam questions if you are verified.\n"
                send_msg(conn, server_response)

                
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
    start_server()
