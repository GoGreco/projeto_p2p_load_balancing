import socket
import threading
import json
import time
from protocol import send_msg, recv_msg

def start_dummy_server(port, messages_to_send):
    """Start a simple server that accepts one connection and sends given messages."""
    def server_thread():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.listen(1)
            conn, _ = s.accept()
            with conn:
                for msg in messages_to_send:
                    conn.sendall((json.dumps(msg) + "\n").encode())
                # keep connection open for client to read
                time.sleep(0.5)
    t = threading.Thread(target=server_thread, daemon=True)
    t.start()
    return t

def test_send_msg_and_recv_msg():
    port = 6000
    # Server will echo back whatever it receives (simple echo server)
    def echo_server():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.listen(1)
            conn, _ = s.accept()
            with conn:
                while True:
                    data = conn.recv(4096)
                    if not data:
                        break
                    conn.sendall(data)  # echo back exactly what was received
    server = threading.Thread(target=echo_server, daemon=True)
    server.start()
    time.sleep(0.1)  # give server time to start
    with socket.create_connection(("127.0.0.1", port)) as client_sock:
        payload = {"test": 123}
        send_msg(client_sock, payload)
        received = recv_msg(client_sock)
        assert received == payload
