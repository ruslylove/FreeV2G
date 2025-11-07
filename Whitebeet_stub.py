import socket
import threading
import time
import struct

EV_PORT = 6000
EVSE_PORT = 6001
HOST = '127.0.0.1'

ev_client_socket = None
evse_client_socket = None

def calculate_checksum(data):
    """Calculates the checksum for the given data."""
    return (~sum(data)) & 0xFF

def frame_message(mod_id, sub_id, req_id, payload=b''):
    """Creates a framed message."""
    payload_len = len(payload)
    header = struct.pack('>BBBH', 0xC0, mod_id, sub_id, req_id, payload_len)
    
    frame_without_checksum = header + payload
    
    # Checksum is calculated over the whole frame, with checksum byte as 0
    temp_frame_for_checksum = bytearray(frame_without_checksum)
    temp_frame_for_checksum.append(0) # Placeholder for checksum
    
    checksum_val = 0
    for byte in temp_frame_for_checksum:
        checksum_val = (checksum_val + byte) & 0xFFFF
    
    while checksum_val > 0xFF:
        checksum_val = (checksum_val & 0xFF) + (checksum_val >> 8)

    checksum = (~checksum_val) & 0xFF
    
    return frame_without_checksum + struct.pack('B', checksum) + b'\xC1'

def handle_client(client_socket, client_address, target_socket_getter, client_name, target_name):
    """Handles communication for a connected client."""
    print(f"Accepted connection from {client_name} at {client_address}")
    
    try:
        while True:
            target_socket = target_socket_getter()
            if not target_socket:
                print(f"Waiting for {target_name} to connect...")
                time.sleep(1)
                continue

            data = client_socket.recv(4096)
            if not data:
                print(f"{client_name} disconnected.")
                break

            print(f"Received from {client_name}: {data.hex()}")

            # Simple relay logic
            try:
                target_socket.sendall(data)
                print(f"Relayed message from {client_name} to {target_name}.")
            except socket.error as e:
                print(f"Error sending to {target_name}: {e}")
                # Potentially the other client disconnected
                break

    except ConnectionResetError:
        print(f"{client_name} connection reset.")
    except Exception as e:
        print(f"An error occurred with {client_name}: {e}")
    finally:
        client_socket.close()
        if client_name == "EV":
            global ev_client_socket
            ev_client_socket = None
        else:
            global evse_client_socket
            evse_client_socket = None
        print(f"{client_name} connection closed.")

def ev_listener():
    """Listens for a connection from the EV simulator."""
    global ev_client_socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, EV_PORT))
    server.listen(1)
    print(f"Whitebeet Stub: Listening for EV on {HOST}:{EV_PORT}")

    while True:
        if ev_client_socket is None:
            try:
                client, addr = server.accept()
                ev_client_socket = client
                client_handler = threading.Thread(target=handle_client, args=(client, addr, lambda: evse_client_socket, "EV", "EVSE"))
                client_handler.daemon = True
                client_handler.start()
            except Exception as e:
                print(f"Error accepting EV connection: {e}")
                break
        time.sleep(0.1)

def evse_listener():
    """Listens for a connection from the EVSE simulator."""
    global evse_client_socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, EVSE_PORT))
    server.listen(1)
    print(f"Whitebeet Stub: Listening for EVSE on {HOST}:{EVSE_PORT}")

    while True:
        if evse_client_socket is None:
            try:
                client, addr = server.accept()
                evse_client_socket = client
                client_handler = threading.Thread(target=handle_client, args=(client, addr, lambda: ev_client_socket, "EVSE", "EV"))
                client_handler.daemon = True
                client_handler.start()
            except Exception as e:
                print(f"Error accepting EVSE connection: {e}")
                break
        time.sleep(0.1)

def main():
    """Main function to start the listeners."""
    ev_thread = threading.Thread(target=ev_listener)
    ev_thread.daemon = True
    ev_thread.start()

    evse_thread = threading.Thread(target=evse_listener)
    evse_thread.daemon = True
    evse_thread.start()

    print("Whitebeet Stub started. Waiting for EV and EVSE connections.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down Whitebeet Stub.")

if __name__ == "__main__":
    main()