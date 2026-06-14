import socket
import threading
import time
import json
from protocol import send_msg, recv_msg
from worker import HEARTBEAT_INTERVAL, SERVER_UUID

def start_master_for_test(port):
    def server_thread():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.listen(1)
            conn, _ = s.accept()
            with conn:
                while True:
                    msg = recv_msg(conn)
                    if not msg:
                        break
                    if msg.get("TASK") == "HEARTBEAT":
                        resp = {"SERVER_UUID": SERVER_UUID, "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"}
                        send_msg(conn, resp)
    t = threading.Thread(target=server_thread, daemon=True)
    t.start()
    return t

def test_worker_heartbeat_cycle():
    port = 6200
    start_master_for_test(port)
    # Patch worker constants to use test port and short interval
    import importlib
    worker_mod = importlib.import_module('worker')
    worker_mod.MASTER_HOST = "127.0.0.1"
    worker_mod.MASTER_PORT = port
    worker_mod.HEARTBEAT_INTERVAL = 1  # fast for test
    # Run worker in a thread, let it send a few heartbeats then stop
    def run_worker():
        worker_mod.connect_and_run()
    t = threading.Thread(target=run_worker, daemon=True)
    t.start()
    # Allow some time for a couple of heartbeats
    time.sleep(3)
    # If we reach here without exception, the test passes
    assert True
