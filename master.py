"""master.py
Threaded TCP server that accepts connections from workers and responds to HEARTBEAT payloads.
"""
import socket
import threading
import queue
import time
import random
import uuid
from typing import Tuple, Dict, Any
from protocol import send_msg, recv_msg

HOST = "0.0.0.0"
PORT = 5000
SERVER_UUID = "Master_4"

# Number of initial tasks to populate on startup (configurable)
INITIAL_TASK_COUNT = 60

# Registry of workers: key = WORKER_UUID, value = info dict
workers_info: Dict[str, Dict[str, Any]] = {}
workers_lock = threading.Lock()

# Task queue (simple FIFO of dicts with at least 'USER' key)
task_queue: "queue.Queue[Dict[str, str]]" = queue.Queue()
    # Map of task_id -> assignment info {'worker_uuid':..., 'task': {...}}
assigned_tasks: Dict[str, Dict[str, Any]] = {}
# Map worker_uuid -> current task_id
worker_current_task: Dict[str, str] = {}
# Map connection id -> worker_uuid (to detect worker on disconnect)
conn_to_worker: Dict[int, str] = {}


def register_worker(worker_uuid: str, conn_info: Tuple[str, int]):
    with workers_lock:
        workers_info[worker_uuid] = {
            "addr": conn_info,
            "last_hb": time.time(),
        }
    print(f"[MASTER] Registered worker {worker_uuid} from {conn_info}")


def update_heartbeat(worker_uuid: str):
    with workers_lock:
        if worker_uuid in workers_info:
            workers_info[worker_uuid]["last_hb"] = time.time()
        else:
            workers_info[worker_uuid] = {"addr": None, "last_hb": time.time()}
    print(f"[MASTER] Heartbeat from worker {worker_uuid}")


def handle_client(conn: socket.socket, addr: Tuple[str, int]):
    """Handle a single worker connection.

    Supports:
    - PAYLOAD 2.1: Worker presents itself: {"WORKER":"ALIVE","WORKER_UUID":"..."}
    - HEARTBEAT: {"SERVER_UUID":..., "TASK":"HEARTBEAT"}
    - REQUEST: worker asks for task: {"TASK":"REQUEST","WORKER_UUID":"..."}
    - STATUS report: PAYLOAD 2.4 {"STATUS":"OK|NOK","TASK":"...","WORKER_UUID":"..."}
    """
    conn_id = id(conn)
    try:
        with conn:
            while True:
                msg = recv_msg(conn)
                if msg is None:
                    # Connection closed or error.
                    break

                # Worker presentation
                if msg.get("WORKER") == "ALIVE":
                    worker_uuid = msg.get("WORKER_UUID")
                    register_worker(worker_uuid, addr)
                    # map connection id to worker
                    conn_to_worker[conn_id] = worker_uuid
                    # Acknowledge registration
                    send_msg(conn, {"STATUS": "ACK"})
                    continue

                # Heartbeat handling (legacy support)
                if msg.get("TASK") == "HEARTBEAT":
                    resp = {
                        "SERVER_UUID": SERVER_UUID,
                        "TASK": "HEARTBEAT",
                        "RESPONSE": "ALIVE",
                    }
                    # If the worker supplied its id, update heartbeat
                    if msg.get("WORKER_UUID"):
                        update_heartbeat(msg.get("WORKER_UUID"))
                    send_msg(conn, resp)
                    continue

                # Worker requesting a task
                if msg.get("TASK") == "REQUEST":
                    worker_uuid = msg.get("WORKER_UUID")
                    # ensure connection mapping exists
                    conn_to_worker.setdefault(conn_id, worker_uuid)
                    print(f"[MASTER] Task request received from worker {worker_uuid}")
                    try:
                        task = task_queue.get_nowait()
                    except queue.Empty:
                        send_msg(conn, {"TASK": "NO_TASK"})
                        print(f"[MASTER] No tasks for worker {worker_uuid}")
                    else:
                        # Send task payload (PAYLOAD 2.2 style)
                        payload = {"TASK": "QUERY", "USER": task.get("USER"), "TASK_ID": task.get("TASK_ID")}
                        send_msg(conn, payload)
                        # record assignment
                        with workers_lock:
                            assigned_tasks[task.get("TASK_ID")] = {"worker_uuid": worker_uuid, "task": task}
                            worker_current_task[worker_uuid] = task.get("TASK_ID")
                        print(f"[MASTER] Assigned task {task.get('TASK_ID')} to worker {worker_uuid}")
                    continue

                # Worker reporting status/result (PAYLOAD 2.4)
                if msg.get("STATUS") in ("OK", "NOK"):
                    worker_uuid = msg.get("WORKER_UUID")
                    task = msg.get("TASK")
                    status = msg.get("STATUS")
                    print(f"[MASTER] Received status {status} for task {task} from worker {worker_uuid}")
                    # Acknowledge to release worker
                    send_msg(conn, {"STATUS": "ACK"})
                    # Remove assignment records if present
                    with workers_lock:
                        task_id = worker_current_task.pop(worker_uuid, None)
                        if task_id and task_id in assigned_tasks:
                            assigned_tasks.pop(task_id, None)
                    # Log completion (here we just print)
                    print(f"[MASTER] Logged completion: worker={worker_uuid} task={task} status={status}")
                    continue

                # Unknown message – ignore but log
                print(f"[MASTER] Unknown message from {addr}: {msg}")
        # end with conn
    finally:
        # Connection cleanup: if this connection was associated with a worker, mark disconnect
        worker_uuid = conn_to_worker.pop(conn_id, None)
        if worker_uuid:
            print(f"[MASTER] Worker disconnected: {worker_uuid} (addr={addr})")
            # If worker had an in-progress task, requeue it
            with workers_lock:
                task_id = worker_current_task.pop(worker_uuid, None)
                if task_id:
                    info = assigned_tasks.pop(task_id, None)
                    if info and info.get("task"):
                        task_queue.put(info.get("task"))
                        print(f"[MASTER] Requeued task {task_id} from disconnected worker {worker_uuid}")


def start_server(host: str = HOST, port: int = PORT):
    """Start the master TCP server.

    The server runs forever, accepting new connections and spawning a thread for each.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((host, port))
        server_sock.listen()
        print(f"Master listening on {host}:{port}")
        while True:
            conn, addr = server_sock.accept()
            print(f"Accepted connection from {addr}")
            thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            thread.start()


def enqueue_task(user: str, task_id: str):
    task_queue.put({"USER": user, "TASK_ID": task_id})
    print(f"[MASTER] Enqueued task {task_id} for user {user}")


def populate_initial_tasks(count: int = INITIAL_TASK_COUNT):
    """Populate the task queue with `count` random tasks for testing/demo."""
    for i in range(count):
        user = random.choice(["alice", "bob", "carol", "dan", "eve"]) 
        task_id = f"{int(time.time())}-{uuid.uuid4().hex[:6]}-{i}"
        enqueue_task(user, task_id)



if __name__ == "__main__":
    # Start server in background and populate initial tasks
    threading.Thread(target=start_server, daemon=True).start()
    print(f"[MASTER] Populating {INITIAL_TASK_COUNT} initial tasks...")
    populate_initial_tasks(INITIAL_TASK_COUNT)
    # Keep main thread alive; periodically add a demo task
    tid = 0
    while True:
        time.sleep(30)
        tid += 1
        enqueue_task("demo_user", f"task-{tid}")
