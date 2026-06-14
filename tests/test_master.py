import socket
import threading
import time
import json
from protocol import send_msg, recv_msg
from master import start_server, SERVER_UUID

# Helper to run master in background thread on a random port

def run_master(port, ready_event):
    def target():
        # Override globals for test
        start_server(host='127.0.0.1', port=port)
    threading.Thread(target=target, daemon=True).start()
    # Give it a moment to start
    time.sleep(0.2)
    ready_event.set()

def test_master_heartbeat_response():
    port = 6100
    ready = threading.Event()
    threading.Thread(target=lambda: start_server(host='127.0.0.1', port=port), daemon=True).start()
    time.sleep(0.2)  # wait for server to listen
    with socket.create_connection(("127.0.0.1", port)) as sock:
        # send heartbeat payload
        payload = {"SERVER_UUID": SERVER_UUID, "TASK": "HEARTBEAT"}
        send_msg(sock, payload)
        resp = recv_msg(sock)
        assert resp["SERVER_UUID"] == SERVER_UUID
        assert resp["TASK"] == "HEARTBEAT"
        assert resp["RESPONSE"] == "ALIVE"
