import struct
import json

def send_json(conn, message_str):
    """
    Helper function to send a length-prefixed message to the client.
    """
    message_json_bytes = json.dumps(message_str).encode('utf-8')
    msg_len = len(message_json_bytes)
    header = struct.pack('!I', msg_len)
    
    conn.sendall(header + message_json_bytes)
    print(f"Sent response of {msg_len} bytes back to client.")
