from __future__ import annotations
import json
import logging
import random
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.protocol import Task, Response, send_json, LineBuffer, BUFFER_SIZE

# ──────────────────────────────────────────────────────────────
# Configuração via variáveis de ambiente
# ──────────────────────────────────────────────────────────────
MASTER_UUID = os.environ.get("MASTER_UUID", "Master_4")

# HOST = "0.0.0.0" → aceita conexões de qualquer interface da rede local.
# NUNCA coloque um IP fixo aqui — isso causava o WinError 10061.
HOST = "0.0.0.0"
PORT = int(os.environ.get("MASTER_PORT", 9000))

# MASTER_PEERS: lista de peers no formato "IP:PORTA,IP:PORTA"
# Ex: MASTER_PEERS=192.168.1.10:9001
# Cada Master precisa conhecer apenas o IP:porta dos outros Masters.
_PEERS_ENV = os.environ.get("MASTER_PEERS", "")
PEER_ADDRESSES: list[tuple[str, int]] = [
    (p.split(":")[0], int(p.split(":")[1]))
    for p in _PEERS_ENV.split(",") if p.strip()
]

# IP público/LAN deste Master, usado ao informar Workers onde se conectar.
# Configure com o IP real desta máquina na rede local.
# Ex: MASTER_PUBLIC_IP=192.168.1.10
MASTER_PUBLIC_IP = os.environ.get("MASTER_PUBLIC_IP", "127.0.0.1")

OVERLOAD_THRESHOLD   = int(os.environ.get("OVERLOAD_THRESHOLD", 5))
TASK_GEN_INTERVAL    = float(os.environ.get("TASK_GEN_INTERVAL", 2))
LOAD_REPORT_INTERVAL = float(os.environ.get("LOAD_REPORT_INTERVAL", 10))
HEARTBEAT_CHECK_INTERVAL = float(os.environ.get("HEARTBEAT_CHECK_INTERVAL", 5))
HEARTBEAT_TIMEOUT = float(os.environ.get("HEARTBEAT_TIMEOUT", 15))

# ──────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-12s %(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(MASTER_UUID)


# ──────────────────────────────────────────────────────────────
# Estruturas de dados
# ──────────────────────────────────────────────────────────────
@dataclass
class WorkerInfo:
    worker_id:  str
    conn:       socket.socket
    addr:       tuple
    busy:       bool = False
    borrowed:   bool = False
    owner:      str  = ""
    tasks_done: int  = 0
    last_heartbeat: float = field(default_factory=time.time)
    current_task_id: Optional[str] = None


@dataclass
class SimTask:
    task_id:     str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    payload:     dict = field(default_factory=dict)
    assigned_to: Optional[str] = None


_lock           = threading.Lock()
workers:         dict[str, WorkerInfo] = {}
task_queue:      list[SimTask]         = []
completed_tasks: int                   = 0
assigned_tasks:  dict[str, SimTask]    = {}


def _remove_worker_and_requeue_locked(worker_id: str) -> None:
    worker = workers.pop(worker_id, None)
    if not worker:
        return

    if worker.current_task_id:
        task = assigned_tasks.pop(worker.current_task_id, None)
        if task:
            task.assigned_to = None
            task_queue.insert(0, task)
            log.warning(
                "Tarefa '%s' reencaminhada para fila após falha de '%s'.",
                task.task_id,
                worker_id,
            )


# ──────────────────────────────────────────────────────────────
# Handlers de mensagens
# ──────────────────────────────────────────────────────────────
def handle_heartbeat(payload: dict, worker_id: str) -> dict:
    sender = payload.get("SERVER_UUID", "?")
    with _lock:
        tracked_worker = workers.get(worker_id) or workers.get(sender)
        if tracked_worker:
            tracked_worker.last_heartbeat = time.time()
    log.info("HEARTBEAT de '%s'", sender)
    return {
        "SERVER_UUID": MASTER_UUID,
        "TASK":        Task.HEARTBEAT,
        "RESPONSE":    Response.ALIVE,
    }


def handle_join(payload: dict, _worker_id: str) -> dict:
    sender = payload.get("SERVER_UUID", "?")
    log.info("JOIN de '%s'", sender)
    return {
        "SERVER_UUID": MASTER_UUID,
        "TASK":        Task.JOIN,
        "RESPONSE":    Response.ACK,
    }


def handle_task_result(payload: dict, worker_id: str) -> dict:
    global completed_tasks
    task_id = payload.get("TASK_ID", "?")
    result  = payload.get("RESULT")
    with _lock:
        assigned_tasks.pop(task_id, None)
        completed_tasks += 1
        if worker_id in workers:
            workers[worker_id].busy = False
            workers[worker_id].current_task_id = None
    log.info("Tarefa '%s' concluída por '%s'. Resultado: %s", task_id, worker_id, result)
    return {"SERVER_UUID": MASTER_UUID, "TASK": Task.TASK_RESULT, "RESPONSE": Response.ACK}


def handle_worker_status(payload: dict, worker_id: str) -> dict:
    status = payload.get("STATUS", "unknown")
    log.debug("Status de '%s': %s", worker_id, status)
    return {"SERVER_UUID": MASTER_UUID, "TASK": Task.WORKER_STATUS, "RESPONSE": Response.OK}


def handle_borrow_worker(payload: dict, _: str) -> dict:
    """
    Outro Master (sobrecarregado) pede emprestado um Worker livre.
    Envia ao Worker escolhido a instrução WORKER_MIGRATE com o IP/porta
    do Master solicitante, para que ele reconecte via TCP.
    """
    requesting_master = payload.get("SERVER_UUID", "?")
    target_host = payload.get("REDIRECT_HOST", "")
    target_port = int(payload.get("REDIRECT_PORT", 0))

    with _lock:
        candidate = next(
            (w for w in workers.values() if not w.busy and not w.borrowed),
            None,
        )
        if candidate:
            candidate.borrowed = True
            candidate.owner    = MASTER_UUID
            wid = candidate.worker_id
            log.info("↗  Emprestando Worker '%s' para Master '%s'", wid, requesting_master)
            try:
                send_json(candidate.conn, {
                    "SERVER_UUID": MASTER_UUID,
                    "TASK":        Task.WORKER_MIGRATE,
                    "NEW_HOST":    target_host,
                    "NEW_PORT":    target_port,
                    "OWNER":       MASTER_UUID,
                })
            except Exception as exc:
                log.warning("Falha ao notificar Worker para migrar: %s", exc)
            return {
                "SERVER_UUID": MASTER_UUID,
                "TASK":        Task.BORROW_ACK,
                "RESPONSE":    Response.OK,
                "WORKER_ID":   wid,
            }
        else:
            log.info("↘  Nenhum Worker disponível para emprestar a '%s'", requesting_master)
            return {
                "SERVER_UUID": MASTER_UUID,
                "TASK":        Task.BORROW_ACK,
                "RESPONSE":    Response.DENIED,
            }


def handle_peer_hello(payload: dict, _: str) -> dict:
    peer_id = payload.get("SERVER_UUID", "?")
    log.info("Peer '%s' se apresentou.", peer_id)
    return {
        "SERVER_UUID": MASTER_UUID,
        "TASK":        Task.PEER_HELLO,
        "RESPONSE":    Response.ACK,
        "LOAD":        len(task_queue),
        "WORKERS":     len(workers),
    }


def handle_load_report(payload: dict, _: str) -> dict:
    peer_id = payload.get("SERVER_UUID", "?")
    load    = payload.get("LOAD", 0)
    log.info("Carga reportada por '%s': %s tarefas", peer_id, load)
    return {"SERVER_UUID": MASTER_UUID, "TASK": Task.LOAD_REPORT, "RESPONSE": Response.ACK}


TASK_HANDLERS = {
    Task.JOIN:          handle_join,
    Task.HEARTBEAT:     handle_heartbeat,
    Task.TASK_RESULT:   handle_task_result,
    Task.WORKER_STATUS: handle_worker_status,
    Task.BORROW_WORKER: handle_borrow_worker,
    Task.PEER_HELLO:    handle_peer_hello,
    Task.LOAD_REPORT:   handle_load_report,
}


# ──────────────────────────────────────────────────────────────
# Tratamento de conexão (thread por cliente)
# ──────────────────────────────────────────────────────────────
def handle_client(conn: socket.socket, addr: tuple) -> None:
    worker_id = None
    buf = LineBuffer()
    log.info("⬆  Nova conexão de %s:%s", *addr)

    try:
        while True:
            chunk = conn.recv(BUFFER_SIZE)
            if not chunk:
                break
            messages = buf.feed(chunk.decode("utf-8", errors="replace"))

            for payload in messages:
                task_str = payload.get("TASK", "").upper()
                sender   = payload.get("SERVER_UUID", "unknown")

                # Registra Worker no JOIN e mantém fallback por HEARTBEAT
                if worker_id is None and task_str in (Task.JOIN, Task.HEARTBEAT):
                    worker_id = sender
                    with _lock:
                        if worker_id not in workers:
                            workers[worker_id] = WorkerInfo(
                                worker_id=worker_id,
                                conn=conn,
                                addr=addr,
                            )
                        else:
                            workers[worker_id].conn = conn
                            workers[worker_id].addr = addr
                        workers[worker_id].last_heartbeat = time.time()
                    log.info("Worker '%s' registrado. Total: %d", worker_id, len(workers))

                handler = TASK_HANDLERS.get(task_str)
                if handler:
                    response = handler(payload, worker_id or sender)
                else:
                    log.warning("Task desconhecida '%s' de %s", task_str, sender)
                    response = {
                        "SERVER_UUID": MASTER_UUID,
                        "TASK":        task_str,
                        "RESPONSE":    Response.UNKNOWN_TASK,
                    }
                send_json(conn, response)

    except ConnectionResetError:
        log.warning("Conexão resetada por %s:%s", *addr)
    except Exception as exc:
        log.error("Erro com %s:%s — %s", *addr, exc)
    finally:
        conn.close()
        if worker_id:
            with _lock:
                _remove_worker_and_requeue_locked(worker_id)
            log.info("Worker '%s' desconectado. Total: %d", worker_id, len(workers))
        else:
            log.info("Socket %s:%s fechado.", *addr)


# ──────────────────────────────────────────────────────────────
# Threads de suporte
# ──────────────────────────────────────────────────────────────
def task_generator() -> None:
    ops = ["COMPUTE_FIBONACCI", "SORT_ARRAY", "HASH_DATA", "PING_ENDPOINT", "COMPRESS_DATA"]
    while True:
        time.sleep(TASK_GEN_INTERVAL)
        task = SimTask(payload={"OP": random.choice(ops), "N": random.randint(10, 100)})
        with _lock:
            task_queue.append(task)
        log.info("Nova tarefa gerada: %s (%s). Fila: %d",
                 task.task_id, task.payload["OP"], len(task_queue))


def task_dispatcher() -> None:
    while True:
        time.sleep(0.5)
        with _lock:
            if not task_queue:
                continue
            free_workers = [w for w in workers.values() if not w.busy]
            if not free_workers:
                continue
            worker = random.choice(free_workers)
            task   = task_queue.pop(0)
            worker.busy = True
            worker.current_task_id = task.task_id
            task.assigned_to = worker.worker_id
            assigned_tasks[task.task_id] = task

        try:
            send_json(worker.conn, {
                "SERVER_UUID": MASTER_UUID,
                "TASK":        Task.ASSIGN_TASK,
                "TASK_ID":     task.task_id,
                "PAYLOAD":     task.payload,
            })
            log.info("Tarefa '%s' enviada para Worker '%s'", task.task_id, worker.worker_id)
        except Exception as exc:
            log.error("Falha ao enviar tarefa para '%s': %s", worker.worker_id, exc)
            with _lock:
                assigned_tasks.pop(task.task_id, None)
                if worker.worker_id in workers:
                    workers[worker.worker_id].busy = False
                    workers[worker.worker_id].current_task_id = None
                task.assigned_to = None
                task_queue.insert(0, task)


def load_monitor() -> None:
    while True:
        time.sleep(LOAD_REPORT_INTERVAL)
        with _lock:
            current_load = len(task_queue)
            worker_count = len(workers)

        log.info("Carga atual: %d tarefas | %d workers ativos | %d concluídas",
                 current_load, worker_count, completed_tasks)

        if current_load >= OVERLOAD_THRESHOLD and PEER_ADDRESSES:
            log.warning("SOBRECARGA DETECTADA (%d >= %d). Iniciando negociação P2P...",
                        current_load, OVERLOAD_THRESHOLD)
            _request_worker_from_peer()


def heartbeat_monitor() -> None:
    while True:
        time.sleep(HEARTBEAT_CHECK_INTERVAL)
        now = time.time()
        stale_workers: list[tuple[str, socket.socket]] = []

        with _lock:
            for wid, info in list(workers.items()):
                if now - info.last_heartbeat > HEARTBEAT_TIMEOUT:
                    stale_workers.append((wid, info.conn))
                    _remove_worker_and_requeue_locked(wid)

        for wid, conn in stale_workers:
            try:
                conn.close()
            except Exception:
                pass
            log.warning("Worker '%s' removido por timeout de heartbeat.", wid)


def _request_worker_from_peer() -> None:
    """
    Contata um Master peer via TCP e solicita empréstimo de Worker.
    O peer responde com BORROW_ACK e instrui o Worker a migrar via TCP
    para MASTER_PUBLIC_IP:PORT deste Master.
    """
    for peer_host, peer_port in PEER_ADDRESSES:
        try:
            log.info("Contactando peer %s:%s para empréstimo de Worker...", peer_host, peer_port)
            with socket.create_connection((peer_host, peer_port), timeout=5) as s:
                send_json(s, {
                    "SERVER_UUID":   MASTER_UUID,
                    "TASK":          Task.BORROW_WORKER,
                    # Informa ao peer o IP e porta REAIS deste Master na LAN,
                    # para que o Worker migrado saiba onde se conectar via TCP.
                    "REDIRECT_HOST": MASTER_PUBLIC_IP,
                    "REDIRECT_PORT": PORT,
                })
                raw = b""
                while b"\n" not in raw:
                    chunk = s.recv(BUFFER_SIZE)
                    if not chunk:
                        break
                    raw += chunk
                if raw:
                    line = raw.split(b"\n")[0]
                    resp = json.loads(line.decode())
                    if resp.get("RESPONSE") == Response.OK:
                        log.info("Empréstimo aceito. Worker '%s' migrando para cá.",
                                 resp.get("WORKER_ID", "?"))
                        return
                    else:
                        log.info("Peer %s:%s negou empréstimo.", peer_host, peer_port)
        except Exception as exc:
            log.warning("Falha ao contatar peer %s:%s — %s", peer_host, peer_port, exc)


# ──────────────────────────────────────────────────────────────
# Entrada principal
# ──────────────────────────────────────────────────────────────
def start_server() -> None:
    log.info("═" * 60)
    log.info("Master '%s'  |  escutando em 0.0.0.0:%s", MASTER_UUID, PORT)
    log.info("IP público/LAN anunciado aos Workers: %s", MASTER_PUBLIC_IP)
    log.info("Threshold de sobrecarga: %d tarefas", OVERLOAD_THRESHOLD)
    log.info("Peers conhecidos: %s", PEER_ADDRESSES or "nenhum")
    log.info("═" * 60)

    for target, name in [
        (task_generator,  "TaskGen"),
        (task_dispatcher, "TaskDispatch"),
        (load_monitor,    "LoadMonitor"),
        (heartbeat_monitor, "HeartbeatMonitor"),
    ]:
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        log.info("Thread '%s' iniciada.", name)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(50)
        log.info("Master escutando em 0.0.0.0:%s ...", PORT)

        while True:
            try:
                conn, addr = srv.accept()
                t = threading.Thread(
                    target=handle_client,
                    args=(conn, addr),
                    daemon=True,
                    name=f"Conn-{addr[0]}:{addr[1]}",
                )
                t.start()
            except KeyboardInterrupt:
                log.info("Servidor encerrado pelo operador.")
                break
            except Exception as exc:
                log.error("Erro ao aceitar conexão: %s", exc)
                time.sleep(1)


if __name__ == "__main__":
    start_server()