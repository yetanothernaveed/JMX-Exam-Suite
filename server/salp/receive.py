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
            return None
        data += packet
    return data

def receive_json(conn):
    """
    Receive a message according to the protocol:
    1. Read the 4-byte header to determine the length of the incoming message.
    2. Read the message of the specified length.
    """
    # Read the 4-byte header
    header = receive_exact(conn, 4)
    if not header:
        return None
    
    # Unpack the length (network byte order)
    message_length = struct.unpack('!I', header)[0]
    
    # Read the actual message
    message_bytes = receive_exact(conn, message_length)
    if not message_bytes:
        print("Client disconnected before sending full message.")
        return None
    
    message = message_bytes.decode('utf-8')
    message_json = json.loads(message)  # Message is in JSON format
    
    return message_json
    
