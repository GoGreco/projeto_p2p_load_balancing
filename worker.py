"""worker.py
TCP client that connects to a master, presents itself, sends HEARTBEATs,
requests tasks, executes them (simulated sleep) and reports status.
"""
import socket
import threading
import time
import uuid
from typing import Optional
from protocol import send_msg, recv_msg

MASTER_HOST = "127.0.0.1"
MASTER_PORT = 5000
# Keep SERVER_UUID for tests that use it to craft heartbeat responses
SERVER_UUID = "Master_4"
HEARTBEAT_INTERVAL = 10  # seconds

# Redirect state shared across functions (mutable to avoid global declaration issues)
redirect_state = {"pending_redirect": None, "pending_original_master": None}
# When borrowed, this holds the original master's identifier/address to include as SERVER_UUID
current_origin: Optional[str] = None


def heartbeat_loop(sock: socket.socket, sock_lock: threading.Lock):
    """Continuously send HEARTBEAT payloads every HEARTBEAT_INTERVAL seconds.

    Uses `sock_lock` so it doesn't race with the task/request thread on recv.
    """
    while True:
        payload = {"SERVER_UUID": (current_origin if current_origin else SERVER_UUID), "TASK": "HEARTBEAT"}
        try:
            with sock_lock:
                send_msg(sock, payload)
                resp = recv_msg(sock)
            if resp is None:
                print("[WORKER] Heartbeat connection closed")
                break
            # Handle command_redirect received from master
            if resp.get("type") == "command_redirect":
                new_addr = resp.get("payload", {}).get("new_master_address")
                if new_addr:
                    redirect_state["pending_redirect"] = new_addr
                    # original master is the current connected master
                    redirect_state["pending_original_master"] = f"{MASTER_HOST}:{MASTER_PORT}"
                    print(f"[WORKER] Received redirect to {new_addr}; will reconnect")
                    break
            if resp.get("type") == "command_release":
                # instruct to return to original master
                orig = resp.get("payload", {}).get("original_master_address")
                if orig:
                    redirect_state["pending_redirect"] = orig
                    redirect_state["pending_original_master"] = None
                    print(f"[WORKER] Received release to return to {orig}; will reconnect")
                    break
            print("[WORKER] Received heartbeat response:", resp)
        except Exception as e:
            print("[WORKER] Error during heartbeat communication:", e)
            break
        time.sleep(HEARTBEAT_INTERVAL)


def task_loop(sock: socket.socket, sock_lock: threading.Lock, worker_uuid: str):
    """Continuously ask for tasks, execute them, and report results.

    Protocol:
    - Send: {"TASK":"REQUEST","WORKER_UUID":...}
    - Receive: {"TASK":"QUERY","USER":...,"TASK_ID":...} or {"TASK":"NO_TASK"}
    - If QUERY: simulate work (sleep 10s), then send {"STATUS":"OK","TASK":...,"WORKER_UUID":...}
      and wait for ACK {"STATUS":"ACK"}.
    """
    while True:
        try:
            with sock_lock:
                # include SERVER_UUID for borrowed workers for observability
                req_payload = {"TASK": "REQUEST", "WORKER_UUID": worker_uuid}
                if current_origin:
                    req_payload["SERVER_UUID"] = current_origin
                send_msg(sock, req_payload)
                resp = recv_msg(sock)
            if resp is None:
                print("[WORKER] Connection closed by master while requesting task")
                break
            # Handle command_redirect that may arrive here as well
            if resp.get("type") == "command_redirect":
                new_addr = resp.get("payload", {}).get("new_master_address")
                if new_addr:
                    redirect_state["pending_redirect"] = new_addr
                    redirect_state["pending_original_master"] = f"{MASTER_HOST}:{MASTER_PORT}"
                    print(f"[WORKER] Received redirect to {new_addr}; will reconnect after finishing current work")
                    break
            if resp.get("type") == "command_release":
                orig = resp.get("payload", {}).get("original_master_address")
                if orig:
                    redirect_state["pending_redirect"] = orig
                    redirect_state["pending_original_master"] = None
                    print(f"[WORKER] Received release to return to {orig}; will reconnect after finishing current work")
                    break
            if resp.get("TASK") == "NO_TASK":
                print("[WORKER] No task assigned; will retry shortly")
                time.sleep(2)
                continue
            if resp.get("TASK") == "QUERY":
                task_id = resp.get("TASK_ID")
                user = resp.get("USER")
                print(f"[WORKER] Received task {task_id} for user {user} — executing...")
                # Simulate processing
                time.sleep(10)
                # Send result
                result = {"STATUS": "OK", "TASK": resp.get("TASK"), "WORKER_UUID": worker_uuid}
                if current_origin:
                    result["SERVER_UUID"] = current_origin
                with sock_lock:
                    send_msg(sock, result)
                    ack = recv_msg(sock)
                print(f"[WORKER] Sent result for task {task_id}, received ack: {ack}")
                continue
            # Unknown response
            print(f"[WORKER] Unknown response from master: {resp}")
            time.sleep(1)
        except Exception as e:
            print("[WORKER] Error in task loop:", e)
            break


def connect_and_run(host: str = MASTER_HOST, port: int = MASTER_PORT):
    """Connect to the master and run heartbeat + task threads.

    If the connection fails, it retries every 5 seconds.
    """
    worker_uuid = str(uuid.uuid4())
    backoff = 1
    while True:
        try:
            with socket.create_connection((host, port)) as sock:
                print(f"[WORKER] Connected to master at {host}:{port}")
                sock_lock = threading.Lock()
                # Send presentation payload (PAYLOAD 2.1)
                try:
                    # If we are reconnecting due to a redirect to a new master (temporary registration)
                    if redirect_state.get("pending_redirect") and redirect_state.get("pending_original_master") and redirect_state.get("pending_redirect") == f"{host}:{port}":
                        # Register temporary worker with original master's address
                        orig = redirect_state.get("pending_original_master")
                        with sock_lock:
                            send_msg(sock, {"type": "register_temporary_worker", "request_id": str(uuid.uuid4()), "payload": {"worker_id": worker_uuid, "original_master_address": orig}})
                            reg_ack = recv_msg(sock)
                        # mark that we are now operating as a borrowed worker (SERVER_UUID = original master address)
                        current_origin = orig
                        # clear redirect flags
                        redirect_state["pending_redirect"] = None
                        redirect_state["pending_original_master"] = None
                    elif redirect_state.get("pending_redirect") and not redirect_state.get("pending_original_master") and redirect_state.get("pending_redirect") == f"{host}:{port}":
                        # Reconnecting to original master (return). Clear borrowed state.
                        redirect_state["pending_redirect"] = None
                        redirect_state["pending_original_master"] = None
                        current_origin = None
                        with sock_lock:
                            send_msg(sock, {"WORKER": "ALIVE", "WORKER_UUID": worker_uuid})
                            reg_ack = recv_msg(sock)
                    else:
                        with sock_lock:
                            send_msg(sock, {"WORKER": "ALIVE", "WORKER_UUID": worker_uuid})
                            reg_ack = recv_msg(sock)
                    print(f"[WORKER] Presentation ACK: {reg_ack}")
                except Exception as e:
                    print("[WORKER] Presentation failed:", e)
                    # let reconnect loop handle it
                    continue

                # Start heartbeat and task threads
                hb_thread = threading.Thread(target=heartbeat_loop, args=(sock, sock_lock), daemon=True)
                task_thread = threading.Thread(target=task_loop, args=(sock, sock_lock, worker_uuid), daemon=True)
                hb_thread.start()
                task_thread.start()
                # Keep main thread alive while threads run; if either exits, reconnect
                while hb_thread.is_alive() and task_thread.is_alive():
                    time.sleep(0.5)
                print("[WORKER] Connection threads ended, will reconnect")
                backoff = 1
        except (ConnectionRefusedError, OSError) as e:
            print(f"[WORKER] Connection failed: {e}. Retrying in {backoff} seconds...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    connect_and_run()
