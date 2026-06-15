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
import logging
import os
import json
import ssl
import psutil
import shutil
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver

# Configure structured logging
logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)
logger = logging.getLogger("master")
OUTBOX_DIR = os.path.join(os.path.dirname(__file__), "outbox")
OUTBOX_DLQ = os.path.join(OUTBOX_DIR, "dlq")
# Outbox policies
OUTBOX_MAX_ATTEMPTS = 5
OUTBOX_TTL_SECONDS = 60 * 60 * 24  # 24 hours
METRICS_PORT = 8000
# Time-to-live for a pending offer made in response to request_help
REQUEST_OFFER_TTL = 30  # seconds

# Dashboard reporting configuration (PAYLOAD 4.1 targets)
TCP_SOCKET_HOST = "nuted-ia.dev"
TCP_SOCKET_PORT = 443
TCP_SOCKET_TLS = True
TCP_SOCKET_SNI = "nuted-ia.dev"
FARM_REPORT_INTERVAL = 5  # seconds


def collect_metrics() -> dict:
    with workers_lock:
        local_workers = len(workers_info)
        borrowed = len(borrowed_workers)
        pending = task_queue.qsize()
        assigned = len(assigned_tasks)
    # outbox sizes
    try:
        outbox_files = [f for f in os.listdir(OUTBOX_DIR) if f.endswith('.json')]
        outbox_size = len(outbox_files)
    except Exception:
        outbox_size = 0
    try:
        dlq_files = [f for f in os.listdir(OUTBOX_DLQ) if f.endswith('.json')]
        dlq_size = len(dlq_files)
    except Exception:
        dlq_size = 0
    return {
        'local_workers': local_workers,
        'borrowed_workers': borrowed,
        'pending_tasks': pending,
        'assigned_tasks': assigned,
        'outbox_size': outbox_size,
        'dlq_size': dlq_size,
    }


def build_dashboard_payload() -> dict:
    """Build the PAYLOAD 4.1 JSON structure with system and farm metrics."""
    # system metrics
    uptime_seconds = int(time.time() - psutil.boot_time())
    try:
        la1, la5, _la15 = os.getloadavg()
    except Exception:
        la1 = la5 = 0.0
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_count_logical = psutil.cpu_count()
    cpu_count_physical = psutil.cpu_count(logical=False) or cpu_count_logical
    vm = psutil.virtual_memory()
    du = psutil.disk_usage('/')

    # farm state metrics
    with workers_lock:
        total_registered = len(workers_info)
        workers_alive = len(workers_info)
        workers_idle = max(0, len(workers_info) - len(worker_current_task))
        workers_borrowed = len(borrowed_workers)
        workers_home = total_registered - workers_borrowed
    tasks_pending = task_queue.qsize()
    tasks_running = len(assigned_tasks)
    tasks_completed = 0
    tasks_failed = 0
    oldest_task_age = 0
    # approximate utilization
    try:
        workers_utilization = (tasks_running / max(1, total_registered)) if total_registered > 0 else 0
    except Exception:
        workers_utilization = 0

    borrowed_list = []
    for wid, orig in borrowed_workers.items():
        borrowed_list.append({"direction": "in", "peer_uuid": orig})

    neighbors_list = []
    for nb in NEIGHBORS:
        nb_id, nb_addr = nb
        neighbors_list.append({"server_uuid": nb_id, "status": "available", "last_heartbeat": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})

    payload = {
        "server_uuid": SERVER_UUID,
        "hostname": socket.gethostname(),
        "role": "master",
        "task": "performance_report",
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "payload_version": "sprint4-monitor",
        "performance": {
            "system": {
                "uptime_seconds": uptime_seconds,
                "load_average_1m": la1,
                "load_average_5m": la5,
                "cpu": {
                    "usage_percent": cpu_percent,
                    "count_logical": cpu_count_logical,
                    "count_physical": cpu_count_physical,
                },
                "memory": {
                    "total_mb": int(vm.total / 1024 / 1024),
                    "available_mb": int(vm.available / 1024 / 1024),
                    "percent_used": vm.percent,
                    "memory_used": int(vm.used / 1024 / 1024),
                },
                "disk": {
                    "total_gb": round(du.total / 1024 / 1024 / 1024, 2),
                    "free_gb": round(du.free / 1024 / 1024 / 1024, 2),
                    "percent_used": du.percent,
                }
            },
            "farm_state": {
                "workers": {
                    "total_registered": total_registered,
                    "workers_utilization": workers_utilization,
                    "workers_alive": workers_alive,
                    "workers_idle": workers_idle,
                    "workers_borrowed": workers_borrowed,
                    "workers_recieved": 0,
                    "workers_failed": 0,
                    "workers_home": workers_home,
                    "workers_available_capacity": max(0, CAPACITY - get_current_load()),
                    "borrowed_workers": borrowed_list,
                },
                "tasks": {
                    "tasks_pending": tasks_pending,
                    "tasks_running": tasks_running,
                    "tasks_completed": tasks_completed,
                    "tasks_failed": tasks_failed,
                    "oldest_task_age_s": oldest_task_age,
                }
            },
            "config_thresholds": {
                "max_task": CAPACITY,
                "warn_cpu_percent": 90,
                "warn_memory_percent": 90,
                "release_task": int(CAPACITY * RELEASE_THRESHOLD),
            },
            "neighbors": neighbors_list,
        }
    }
    return payload


def dashboard_reporter_loop():
    """Loop that sends PAYLOAD 4.1 periodically to the configured dashboard over TLS/TCP.

    Each JSON object is sent followed by a newline as delimiter.
    """
    while True:
        try:
            payload = build_dashboard_payload()
            j = json.dumps(payload) + "\n"
            # establish connection
            host = TCP_SOCKET_HOST
            port = TCP_SOCKET_PORT
            if TCP_SOCKET_TLS:
                ctx = ssl.create_default_context()
                try:
                    with socket.create_connection((host, port), timeout=5) as sock:
                        with ctx.wrap_socket(sock, server_hostname=TCP_SOCKET_SNI) as ssock:
                            ssock.sendall(j.encode('utf-8'))
                            logger.info("Dashboard payload sent to %s:%d (TLS)", host, port)
                except Exception as e:
                    logger.debug("Dashboard TLS send failed: %s", e)
            else:
                try:
                    with socket.create_connection((host, port), timeout=5) as sock:
                        sock.sendall(j.encode('utf-8'))
                        logger.info("Dashboard payload sent to %s:%d (plain)", host, port)
                except Exception as e:
                    logger.debug("Dashboard plain send failed: %s", e)
        except Exception as e:
            logger.debug("Error building/sending dashboard payload: %s", e)
        # send farm_state in real-time every FARM_REPORT_INTERVAL seconds
        time.sleep(FARM_REPORT_INTERVAL)


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/metrics':
            self.send_response(404)
            self.end_headers()
            return
        metrics = collect_metrics()
        body_lines = []
        # simple Prometheus-style exposition
        body_lines.append(f"p2p_local_workers {metrics['local_workers']}")
        body_lines.append(f"p2p_borrowed_workers {metrics['borrowed_workers']}")
        body_lines.append(f"p2p_pending_tasks {metrics['pending_tasks']}")
        body_lines.append(f"p2p_assigned_tasks {metrics['assigned_tasks']}")
        body_lines.append(f"p2p_outbox_size {metrics['outbox_size']}")
        body_lines.append(f"p2p_dlq_size {metrics['dlq_size']}")
        body = '\n'.join(body_lines) + '\n'
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; version=0.0.4')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))


def start_metrics_server(port: int = METRICS_PORT):
    try:
        httpd = HTTPServer(('0.0.0.0', port), MetricsHandler)
        logger.info('Metrics server listening on 0.0.0.0:%d', port)
        httpd.serve_forever()
    except Exception as e:
        logger.warning('Metrics server failed to start: %s', e)


def ensure_outbox_dir():
    try:
        os.makedirs(OUTBOX_DIR, exist_ok=True)
    except Exception:
        logger.warning("Could not create outbox dir %s", OUTBOX_DIR)


def enqueue_outbox(target_addr: str, message: dict) -> str:
    """Persist a message to outbox for reliable delivery. Returns filepath."""
    ensure_outbox_dir()
    msg = {
        "target": target_addr,
        "message": message,
        "created_at": time.time(),
        "attempts": 0,
    }
    fname = f"{int(time.time())}-{uuid.uuid4().hex}.json"
    path = os.path.join(OUTBOX_DIR, fname)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(msg, f)
        logger.info("Enqueued outbox message %s -> %s", fname, target_addr)
        return path
    except Exception as e:
        logger.warning("Failed to enqueue outbox message: %s", e)
        return ""


def ensure_dlq_dir():
    try:
        os.makedirs(OUTBOX_DLQ, exist_ok=True)
    except Exception:
        logger.warning("Could not create DLQ dir %s", OUTBOX_DLQ)


def move_to_dlq(path: str):
    ensure_dlq_dir()
    try:
        base = os.path.basename(path)
        dest = os.path.join(OUTBOX_DLQ, base)
        os.replace(path, dest)
        logger.info("Moved outbox file %s to DLQ", base)
    except Exception as e:
        logger.warning("Failed to move outbox file to DLQ: %s", e)


def outbox_worker_loop():
    """Background loop that scans the outbox directory and attempts delivery."""
    ensure_outbox_dir()
    while True:
        try:
            files = [f for f in os.listdir(OUTBOX_DIR) if f.endswith('.json')]
            for fn in files:
                path = os.path.join(OUTBOX_DIR, fn)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        payload = json.load(f)
                except Exception as e:
                    logger.debug("Failed to read outbox file %s: %s", fn, e)
                    # corrupt file -> remove
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                    continue
                target = payload.get('target')
                message = payload.get('message')
                attempts = payload.get('attempts', 0)
                # TTL check
                created_at = payload.get('created_at', 0)
                age = time.time() - created_at
                if attempts >= OUTBOX_MAX_ATTEMPTS or age > OUTBOX_TTL_SECONDS:
                    logger.info("Outbox file %s exceeded attempts (%d) or TTL (age=%.0f), moving to DLQ", fn, attempts, age)
                    try:
                        move_to_dlq(path)
                    except Exception:
                        pass
                    continue
                # attempt delivery
                host, port_s = target.split(":")
                port = int(port_s)
                success = False
                try:
                    with socket.create_connection((host, port), timeout=5) as s:
                        send_msg(s, message)
                        # expect an ack reply
                        resp = recv_msg(s)
                        if resp and resp.get('type') == 'ack' and resp.get('request_id') == message.get('request_id'):
                            success = True
                except Exception as e:
                    logger.debug("Outbox delivery attempt to %s failed: %s", target, e)
                if success:
                    try:
                        os.remove(path)
                        logger.info("Outbox message %s delivered and removed", fn)
                    except Exception as e:
                        logger.debug("Could not remove outbox file %s: %s", fn, e)
                else:
                    # update attempts and leave for retry later
                    payload['attempts'] = attempts + 1
                    try:
                        with open(path, 'w', encoding='utf-8') as f:
                            json.dump(payload, f)
                    except Exception:
                        pass
            time.sleep(2)
        except Exception as e:
            logger.debug("Outbox worker error: %s", e)
            time.sleep(2)

HOST = "0.0.0.0"
PORT = 5000
SERVER_UUID = "Master_4"

# Capacity and thresholds
CAPACITY = 100
# When load drops below RELEASE_THRESHOLD * CAPACITY, borrowed workers can be released
RELEASE_THRESHOLD = 0.6

# Neighbors directory (master_id, "ip:port").
# Populate with known peers for negotiation. Example entries can be adjusted.
NEIGHBORS = [
    ("Master_7", "127.0.0.1:6000"),
]

# Number of initial tasks to populate on startup (configurable)
INITIAL_TASK_COUNT = 60

# Registry of workers: key = WORKER_UUID, value = info dict
workers_info: Dict[str, Dict[str, Any]] = {}
workers_lock = threading.Lock()
# Active worker sockets (to send commands directly): worker_uuid -> socket
worker_sockets: Dict[str, socket.socket] = {}
# Per-worker send locks
worker_send_locks: Dict[str, threading.Lock] = {}
# Workers reserved for redirect (worker_uuid -> reserved boolean)
reserved_workers: Dict[str, bool] = {}

# Task queue (simple FIFO of dicts with at least 'USER' key)
task_queue: "queue.Queue[Dict[str, str]]" = queue.Queue()
    # Map of task_id -> assignment info {'worker_uuid':..., 'task': {...}}
assigned_tasks: Dict[str, Dict[str, Any]] = {}
# Map worker_uuid -> current task_id
worker_current_task: Dict[str, str] = {}
# Map connection id -> worker_uuid (to detect worker on disconnect)
conn_to_worker: Dict[int, str] = {}
# Track borrowed workers: worker_uuid -> original_master_address
borrowed_workers: Dict[str, str] = {}
# Pending offers made in response to request_help: request_id -> {"workers": [ids], "timer": threading.Timer}
pending_offers: Dict[str, Dict[str, Any]] = {}


def cancel_reservation_for_worker(wid: str, reason: str = "manual"):
    """Clear reservation for a worker and update any pending offers that referenced it."""
    with workers_lock:
        removed = False
        if reserved_workers.pop(wid, None) is not None:
            logger.info("Cancelled reservation for worker %s (%s)", wid, reason)
            removed = True
        # remove worker from any pending_offers lists; if offer becomes empty, cancel timer
        for rid, entry in list(pending_offers.items()):
            wlist = entry.get("workers", [])
            if wid in wlist:
                wlist.remove(wid)
                logger.info("Removed worker %s from pending offer %s due to %s", wid, rid, reason)
                if not wlist:
                    t = entry.get("timer")
                    try:
                        t.cancel()
                    except Exception:
                        pass
                    pending_offers.pop(rid, None)
                    logger.info("Pending offer %s cancelled because no workers remain", rid)
        return removed


def register_worker(worker_uuid: str, conn_info: Tuple[str, int], conn_sock: socket.socket = None):
    with workers_lock:
        workers_info[worker_uuid] = {
            "addr": conn_info,
            "last_hb": time.time(),
        }
        if conn_sock is not None:
            worker_sockets[worker_uuid] = conn_sock
            worker_send_locks.setdefault(worker_uuid, threading.Lock())
    logger.info("Registered worker %s from %s", worker_uuid, conn_info)
    log_state()


def update_heartbeat(worker_uuid: str):
    with workers_lock:
        if worker_uuid in workers_info:
            workers_info[worker_uuid]["last_hb"] = time.time()
        else:
            workers_info[worker_uuid] = {"addr": None, "last_hb": time.time()}
    logger.debug("Heartbeat from worker %s", worker_uuid)


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
                    register_worker(worker_uuid, addr, conn_sock=conn)
                    # map connection id to worker
                    conn_to_worker[conn_id] = worker_uuid
                    # Acknowledge registration
                    send_msg(conn, {"STATUS": "ACK"})
                    continue

                # Temporary registration when a worker was redirected here
                if msg.get("type") == "register_temporary_worker":
                    payload = msg.get("payload", {})
                    worker_id = payload.get("worker_id")
                    original_master = payload.get("original_master_address")
                    if worker_id:
                        register_worker(worker_id, addr, conn_sock=conn)
                        borrowed_workers[worker_id] = original_master
                        conn_to_worker[conn_id] = worker_id
                        send_msg(conn, {"STATUS": "ACK"})
                        logger.info("Registered temporary worker %s from %s", worker_id, original_master)
                        log_state()
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
                    # If this worker was reserved for an outgoing offer, avoid assigning it locally
                    if reserved_workers.get(worker_uuid):
                        send_msg(conn, {"TASK": "NO_TASK"})
                        logger.info("Declined to assign task to reserved worker %s", worker_uuid)
                        continue
                    # ensure connection mapping exists
                    conn_to_worker.setdefault(conn_id, worker_uuid)
                    logger.debug("Task request received from worker %s", worker_uuid)
                    try:
                        task = task_queue.get_nowait()
                    except queue.Empty:
                        send_msg(conn, {"TASK": "NO_TASK"})
                        logger.debug("No tasks for worker %s", worker_uuid)
                    else:
                        # Send task payload (PAYLOAD 2.2 style)
                        payload = {"TASK": "QUERY", "USER": task.get("USER"), "TASK_ID": task.get("TASK_ID")}
                        send_msg(conn, payload)
                        # record assignment
                        assigned_id = task.get("TASK_ID")
                        with workers_lock:
                            assigned_tasks[assigned_id] = {"worker_uuid": worker_uuid, "task": task}
                            worker_current_task[worker_uuid] = assigned_id
                        # If this worker had a reservation, cancel it now (we assigned it locally)
                        cancel_reservation_for_worker(worker_uuid, reason="assigned_locally")
                        logger.info("Assigned task %s to worker %s", task.get('TASK_ID'), worker_uuid)
                    continue

                # Worker reporting status/result (PAYLOAD 2.4)
                if msg.get("STATUS") in ("OK", "NOK"):
                    worker_uuid = msg.get("WORKER_UUID")
                    task = msg.get("TASK")
                    status = msg.get("STATUS")
                    logger.info("Received status %s for task %s from worker %s", status, task, worker_uuid)
                    # Acknowledge to release worker
                    send_msg(conn, {"STATUS": "ACK"})
                    # Remove assignment records if present
                    with workers_lock:
                        task_id = worker_current_task.pop(worker_uuid, None)
                        if task_id and task_id in assigned_tasks:
                            assigned_tasks.pop(task_id, None)
                    # Log completion (here we just print)
                    logger.info("Logged completion: worker=%s task=%s status=%s", worker_uuid, task, status)
                    continue

                # Unknown message – ignore but log
                # Master-to-Master messages
                if msg.get("type") == "request_help":
                    # Evaluate current load and respond
                    req_id = msg.get("request_id")
                    payload = msg.get("payload", {})
                    their_load = payload.get("current_load", 0)
                    # Decide based on available idle workers
                    with workers_lock:
                        idle_workers = [w for w in workers_info.keys() if w not in worker_current_task]
                    if len(idle_workers) >= 1:
                        # Offer up to requested workers, but not more than we have idle
                        need = payload.get("workers_needed", 1)
                        offer = min(len(idle_workers), need)
                        offered = []
                        # Create worker details with placeholder addresses from registry
                        with workers_lock:
                            for w in idle_workers[:offer]:
                                info = workers_info.get(w, {})
                                addr_info = info.get("addr")
                                if addr_info:
                                    offered.append({"id": w, "address": f"{addr_info[0]}:{addr_info[1]}"})
                        # Mark offered workers as reserved to avoid assigning them
                        with workers_lock:
                            for w in offered:
                                reserved_workers[w["id"]] = True
                        # start a TTL timer to auto-cancel this offer if nothing happens
                        def _cancel_offer(rid):
                            with workers_lock:
                                entry = pending_offers.pop(rid, None)
                                if not entry:
                                    return
                                wlist = entry.get("workers", [])
                                for wid in wlist:
                                    if reserved_workers.get(wid):
                                        reserved_workers.pop(wid, None)
                                        logger.info("Auto-cancelled reservation for worker %s from request %s due to TTL", wid, rid)

                        timer = threading.Timer(REQUEST_OFFER_TTL, _cancel_offer, args=(req_id,))
                        pending_offers[req_id] = {"workers": [w["id"] for w in offered], "timer": timer}
                        timer.daemon = True
                        timer.start()
                        resp = {
                            "type": "response_accepted",
                            "request_id": req_id,
                            "payload": {"workers_offered": len(offered), "worker_details": offered},
                        }
                        send_msg(conn, resp)
                        logger.info("Responded ACCEPT to request %s offering %d workers", req_id, len(offered))
                    else:
                        resp = {"type": "response_rejected", "request_id": req_id, "payload": {"reason": "high_load"}}
                        send_msg(conn, resp)
                        logger.info("Responded REJECT to request %s", req_id)
                    continue

                if msg.get("type") == "notify_worker_returned":
                    req_id = msg.get("request_id")
                    payload = msg.get("payload", {})
                    wid = payload.get("worker_id")
                    logger.info("Received notify_worker_returned for worker %s (request_id=%s)", wid, req_id)
                    # If we had reserved this worker, clear reservation
                    with workers_lock:
                        if wid in reserved_workers:
                            reserved_workers.pop(wid, None)
                            logger.info("Cleared reservation for worker %s due to notify", wid)
                    # send ack back to notifier
                    try:
                        send_msg(conn, {"type": "ack", "request_id": req_id, "payload": {"status": "received"}})
                    except Exception:
                        pass
                    # If this notify corresponds to a pending offer, clear it and cancel timer
                    with workers_lock:
                        # find any pending offer that listed this worker and remove it
                        to_remove = []
                        for rid, entry in list(pending_offers.items()):
                            wlist = entry.get("workers", [])
                            if wid in wlist:
                                # cancel timer and remove reservation
                                t = entry.get("timer")
                                try:
                                    t.cancel()
                                except Exception:
                                    pass
                                pending_offers.pop(rid, None)
                                if reserved_workers.get(wid):
                                    reserved_workers.pop(wid, None)
                                    logger.info("Cleared reservation for worker %s due to notify (request %s)", wid, rid)
                                break
                    continue

                logger.debug("Unknown message from %s: %s", addr, msg)
        # end with conn
    finally:
        # Connection cleanup: if this connection was associated with a worker, mark disconnect
        worker_uuid = conn_to_worker.pop(conn_id, None)
        if worker_uuid:
            logger.info("Worker disconnected: %s (addr=%s)", worker_uuid, addr)
            # If worker was reserved for transfer, cancel reservation to avoid stale lock
            if reserved_workers.get(worker_uuid):
                cancel_reservation_for_worker(worker_uuid, reason="disconnect")
            # If worker had an in-progress task, requeue it
            with workers_lock:
                task_id = worker_current_task.pop(worker_uuid, None)
                if task_id:
                    info = assigned_tasks.pop(task_id, None)
                    if info and info.get("task"):
                        task_queue.put(info.get("task"))
                        logger.info("Requeued task %s from disconnected worker %s", task_id, worker_uuid)


def start_server(host: str = HOST, port: int = PORT):
    """Start the master TCP server.

    The server runs forever, accepting new connections and spawning a thread for each.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((host, port))
        server_sock.listen()
        logger.info("Master listening on %s:%d", host, port)
        while True:
            conn, addr = server_sock.accept()
            logger.debug("Accepted connection from %s", addr)
            thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            thread.start()


def enqueue_task(user: str, task_id: str):
    task_queue.put({"USER": user, "TASK_ID": task_id})
    logger.info("Enqueued task %s for user %s", task_id, user)


def populate_initial_tasks(count: int = INITIAL_TASK_COUNT):
    """Populate the task queue with `count` random tasks for testing/demo."""
    for i in range(count):
        user = random.choice(["alice", "bob", "carol", "dan", "eve"]) 
        task_id = f"{int(time.time())}-{uuid.uuid4().hex[:6]}-{i}"
        enqueue_task(user, task_id)


def get_current_load() -> int:
    """Estimate current load as pending + assigned tasks."""
    return task_queue.qsize() + len(assigned_tasks)


def log_state():
    """Log current state: counts of local and borrowed workers and queue lengths."""
    with workers_lock:
        local_workers = len(workers_info)
        borrowed = len(borrowed_workers)
        pending = task_queue.qsize()
        assigned = len(assigned_tasks)
    logger.info("State: local_workers=%d borrowed_workers=%d pending_tasks=%d assigned_tasks=%d", local_workers, borrowed, pending, assigned)



def send_request_help_to_neighbor(neighbor_addr: str, payload: dict, timeout: float = 5.0) -> dict:
    """Connect to neighbor master and send a request_help payload, returning the parsed response or None on timeout/error."""
    host, port_s = neighbor_addr.split(":")
    port = int(port_s)
    # retry with exponential backoff
    attempts = 3
    delay = 0.5
    for i in range(attempts):
        try:
            with socket.create_connection((host, port), timeout=timeout) as s:
                s.settimeout(timeout)
                send_msg(s, payload)
                resp = recv_msg(s)
                return resp
        except Exception as e:
            logger.debug("Attempt %d: error contacting neighbor %s: %s", i + 1, neighbor_addr, e)
            time.sleep(delay)
            delay = min(delay * 2, 5)
    logger.warning("Failed to contact neighbor %s after %d attempts", neighbor_addr, attempts)
    return None


def send_command_redirect_to_worker(worker_id: str, worker_address: str, new_master_address: str, request_id: str) -> bool:
    """Send a command_redirect to a worker. Prefer to send over the existing connection if available.

    Returns True on success.
    """
    # Prefer active socket
    with workers_lock:
        wsock = worker_sockets.get(worker_id)
        wlock = worker_send_locks.get(worker_id)
    payload = {"type": "command_redirect", "request_id": request_id, "payload": {"new_master_address": new_master_address}}
    if wsock and wlock:
        try:
            with wlock:
                send_msg(wsock, payload)
            logger.info("Sent command_redirect to worker %s via existing connection -> %s", worker_id, new_master_address)
            return True
        except Exception as e:
            logger.debug("Failed to send command_redirect over existing socket to %s: %s", worker_id, e)
            # fallthrough to direct connect

    # fallback: try to connect directly to worker address
    attempts = 3
    delay = 0.5
    try:
        host, port_s = worker_address.split(":")
        port = int(port_s)
    except Exception:
        logger.debug("Invalid worker address format: %s", worker_address)
        return False
    for i in range(attempts):
        try:
            with socket.create_connection((host, port), timeout=5) as s:
                send_msg(s, payload)
                logger.info("Sent command_redirect to worker %s via direct connection -> %s", worker_id, new_master_address)
                return True
        except Exception as e:
            logger.debug("Attempt %d: failed to send command_redirect to %s: %s", i + 1, worker_address, e)
            time.sleep(delay)
            delay = min(delay * 2, 5)
    logger.warning("Failed to send command_redirect to %s after %d attempts", worker_address, attempts)
    return False


def send_command_release_to_worker(worker_uuid: str, request_id: str) -> bool:
    """Send a command_release to a worker currently connected to this master.

    Returns True on success, False on failure.
    """
    with workers_lock:
        info = workers_info.get(worker_uuid)
    if not info or not info.get("addr"):
        logger.debug("No connection info for worker %s to send release", worker_uuid)
        return False
    worker_addr = f"{info['addr'][0]}:{info['addr'][1]}"
    attempts = 3
    delay = 0.5
    for i in range(attempts):
        try:
            with socket.create_connection((info['addr'][0], info['addr'][1]), timeout=5) as s:
                payload = {"type": "command_release", "request_id": request_id, "payload": {"original_master_address": borrowed_workers.get(worker_uuid)}}
                send_msg(s, payload)
                logger.info("Sent command_release to worker %s (addr=%s) request_id=%s", worker_uuid, worker_addr, request_id)
                return True
        except Exception as e:
            logger.debug("Attempt %d: failed to send command_release to %s: %s", i + 1, worker_addr, e)
            time.sleep(delay)
            delay = min(delay * 2, 5)
    logger.warning("Failed to send command_release to worker %s after %d attempts", worker_uuid, attempts)
    return False


def notify_origin_worker_returned(origin_addr: str, worker_id: str, request_id: str) -> bool:
    """Notify the origin master that a worker was returned."""
    # enqueue message to outbox for persistent delivery
    msg = {"type": "notify_worker_returned", "request_id": request_id, "payload": {"worker_id": worker_id}}
    p = enqueue_outbox(origin_addr, msg)
    return bool(p)
def monitor_load_loop(host: str = HOST, port: int = PORT):
    """Background loop that monitors load and requests help from neighbors when overloaded."""
    while True:
        try:
            current_load = get_current_load()
            if current_load > CAPACITY:
                excess = current_load - CAPACITY
                # heuristic: 1 worker per 10 excess tasks
                workers_needed = max(1, (excess + 9) // 10)
                req_id = str(uuid.uuid4())
                payload = {
                    "type": "request_help",
                    "request_id": req_id,
                    "payload": {"master_id": SERVER_UUID, "current_load": current_load, "capacity": CAPACITY, "workers_needed": workers_needed},
                }
                logger.info("Overloaded (load=%d), requesting %d workers (request_id=%s)", current_load, workers_needed, req_id)
                for neighbor in NEIGHBORS:
                    nb_id, nb_addr = neighbor
                    resp = send_request_help_to_neighbor(nb_addr, payload)
                    if not resp:
                        logger.debug("No response from neighbor %s for request %s", nb_addr, req_id)
                        continue
                    # Validate response request_id matches
                    if resp.get("request_id") != req_id:
                        logger.warning("Mismatched request_id from neighbor %s: expected %s got %s", nb_addr, req_id, resp.get("request_id"))
                        continue
                    if resp.get("type") == "response_accepted":
                        logger.info("Neighbor %s accepted request %s", nb_addr, req_id)
                        details = resp.get("payload", {}).get("worker_details", [])
                        for wd in details:
                            worker_addr = wd.get("address")
                            wid = wd.get("id")
                            logger.info("Redirecting worker %s to %s (request_id=%s)", wid, f"{host}:{port}", req_id)
                            # instruct worker to redirect to us; prefer existing connection
                            ok = send_command_redirect_to_worker(wid, worker_addr, f"{host}:{port}", req_id)
                            if not ok:
                                with workers_lock:
                                    reserved_workers.pop(wid, None)
                                logger.info("Unreserved worker %s after failed redirect", wid)
                        # stop after first successful neighbor
                        break
                    elif resp.get("type") == "response_rejected":
                        reason = resp.get("payload", {}).get("reason")
                        logger.info("Neighbor %s rejected request %s: %s", nb_addr, req_id, reason)
                        continue
            # Release borrowed workers when under threshold
            if get_current_load() < int(CAPACITY * RELEASE_THRESHOLD):
                # instruct borrowed workers to return
                for w_uuid, orig_addr in list(borrowed_workers.items()):
                    try:
                        # if worker known, send release
                        info = workers_info.get(w_uuid)
                        if info and info.get("addr"):
                            worker_addr = f"{info['addr'][0]}:{info['addr'][1]}"
                            req_id = str(uuid.uuid4())
                            with socket.create_connection((info['addr'][0], info['addr'][1]), timeout=3) as s:
                                send_msg(s, {"type": "command_release", "request_id": req_id, "payload": {"original_master_address": orig_addr}})
                                logger.info("Sent command_release for worker %s (request_id=%s)", w_uuid, req_id)
                            # notify original master that worker returned
                            # attempt to notify origin asynchronously
                            try:
                                host_o, port_o = orig_addr.split(":")
                                with socket.create_connection((host_o, int(port_o)), timeout=3) as mconn:
                                    send_msg(mconn, {"type": "notify_worker_returned", "request_id": req_id, "payload": {"worker_id": w_uuid}})
                                    logger.info("Notified origin %s that worker %s returned (request_id=%s)", orig_addr, w_uuid, req_id)
                            except Exception:
                                logger.debug("Could not notify origin %s for worker %s", orig_addr, w_uuid)
                            borrowed_workers.pop(w_uuid, None)
                            log_state()
                    except Exception:
                        # if sending release fails, ignore for now
                        pass
            time.sleep(2)
        except Exception as e:
            logger.exception("monitor loop error: %s", e)
            time.sleep(2)


# Note: the dashboard reporter is started in __main__ only to avoid
# surprising side-effects when the module is imported by helper scripts.


if __name__ == "__main__":
    # Start server in background and populate initial tasks
    threading.Thread(target=start_server, daemon=True).start()
    logger.info("Populating %d initial tasks...", INITIAL_TASK_COUNT)
    populate_initial_tasks(INITIAL_TASK_COUNT)
    # Start monitoring loop to detect saturation and negotiate with neighbors
    threading.Thread(target=monitor_load_loop, daemon=True).start()
    logger.info("Neighbors: %s", NEIGHBORS)
    # Start outbox worker for reliable Master->Master messaging
    threading.Thread(target=outbox_worker_loop, daemon=True).start()
    # Start metrics server
    threading.Thread(target=start_metrics_server, daemon=True).start()
    # Start dashboard reporter to send PAYLOAD 4.1 every FARM_REPORT_INTERVAL seconds
    threading.Thread(target=dashboard_reporter_loop, daemon=True).start()
    # Keep main thread alive; periodically add a demo task
    tid = 0
    while True:
        time.sleep(30)
        tid += 1
        enqueue_task("demo_user", f"task-{tid}")
