from __future__ import annotations

import logging
import math
import os
import random
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.protocol import Task, Response, send_json, LineBuffer, BUFFER_SIZE

WORKER_UUID        = os.environ.get("WORKER_UUID",   "Worker_A1")
MASTER_HOST        = os.environ.get("MASTER_HOST",   "10.62.217.41")
MASTER_PORT        = int(os.environ.get("MASTER_PORT",  9000))
HEARTBEAT_INTERVAL = float(os.environ.get("HEARTBEAT_INTERVAL", 6))
RECONNECT_DELAY    = float(os.environ.get("RECONNECT_DELAY",    5))
SOCKET_TIMEOUT     = float(os.environ.get("SOCKET_TIMEOUT",     10))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-12s %(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(WORKER_UUID)


def execute_task(payload: dict) -> str:
    op = payload.get("OP", "NOP")
    n  = int(payload.get("N", 10))

    if op == "COMPUTE_FIBONACCI":
        a, b = 0, 1
        for _ in range(n):
            a, b = b, a + b
        result = str(a)

    elif op == "SORT_ARRAY":
        arr = [random.randint(0, 1000) for _ in range(n)]
        result = str(sorted(arr)[:3]) + "..." 

    elif op == "HASH_DATA":
        import hashlib
        data = os.urandom(n * 8)
        result = hashlib.sha256(data).hexdigest()[:16]

    elif op == "PING_ENDPOINT":
        time.sleep(random.uniform(0.1, 0.5))   
        result = f"200 OK ({random.randint(20, 200)}ms)"
        

    elif op == "COMPRESS_DATA":
        import zlib
        data = bytes(range(n % 256)) * (n // 10 + 1)
        compressed = zlib.compress(data)
        ratio = len(data) / max(len(compressed), 1)
        result = f"ratio={ratio:.2f}"

    else:
        time.sleep(0.1)
        result = "NOOP"

    time.sleep(random.uniform(0.2, 1.5))
    return result
_pending_migration: dict | None = None


def process_message(payload: dict, sock: socket.socket) -> bool:
    global _pending_migration
    task = payload.get("TASK", "").upper()

    if task == Task.JOIN:
        status = payload.get("RESPONSE", "").upper()
        if status == Response.ACK:
            log.info("JOIN confirmado por '%s'", payload.get("SERVER_UUID"))
        else:
            log.warning("Resposta inesperada ao JOIN: '%s'", status)

    elif task == Task.HEARTBEAT:
        status = payload.get("RESPONSE", "").upper()
        if status == Response.ALIVE:
            log.info("♥  ALIVE  ✓  (Master '%s' ativo)", payload.get("SERVER_UUID"))
        else:
            log.warning("♥  Resposta inesperada ao heartbeat: '%s'", status)

    elif task == Task.ASSIGN_TASK:
        task_id  = payload.get("TASK_ID", "?")
        tp       = payload.get("PAYLOAD", {})
        log.info("Tarefa recebida: %s  OP=%s  N=%s", task_id, tp.get("OP"), tp.get("N"))
        result   = execute_task(tp)
        log.info("Tarefa %s concluída. Resultado: %s", task_id, result)
        send_json(sock, {
            "SERVER_UUID": WORKER_UUID,
            "TASK":        Task.TASK_RESULT,
            "TASK_ID":     task_id,
            "RESULT":      result,
        })

    elif task == Task.WORKER_MIGRATE:
        new_host  = payload.get("NEW_HOST", "127.0.0.1")
        new_port  = int(payload.get("NEW_PORT", 9000))
        owner     = payload.get("OWNER", "?")
        log.info("Instrução de migração recebida → %s:%s  (owner: %s)", new_host, new_port, owner)
        send_json(sock, {
            "SERVER_UUID": WORKER_UUID,
            "TASK":        Task.MIGRATE_ACK,
            "RESPONSE":    Response.ACK,
        })
        _pending_migration = {"host": new_host, "port": new_port}
        return False   
    return True


def connection_loop(host: str, port: int) -> dict | None:
    global _pending_migration
    _pending_migration = None

    log.info("Conectando a %s:%s ...", host, port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(SOCKET_TIMEOUT)

    try:
        sock.connect((host, port))
    except (ConnectionRefusedError, TimeoutError, OSError) as exc:
        log.error("Falha na conexão: %s", exc)
        sock.close()
        return None

    log.info("Conectado a %s:%s", host, port)
    send_json(sock, {
        "SERVER_UUID": WORKER_UUID,
        "TASK":        Task.JOIN,
    })
    log.info("JOIN enviado → %s:%s", host, port)

    buf = LineBuffer()
    last_heartbeat = 0.0

    try:
        while True:
            now = time.monotonic()

            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                log.info("Enviando HEARTBEAT → %s:%s ...", host, port)
                send_json(sock, {
                    "SERVER_UUID": WORKER_UUID,
                    "TASK":        Task.HEARTBEAT,
                })
                last_heartbeat = now

            sock.settimeout(0.5)
            try:
                chunk = sock.recv(BUFFER_SIZE)
                if not chunk:
                    raise RuntimeError("Conexão encerrada pelo Master.")
                messages = buf.feed(chunk.decode("utf-8", errors="replace"))
                for msg in messages:
                    if not process_message(msg, sock):
                        return _pending_migration   # migração solicitada
            except socket.timeout:
                pass   # sem dados no momento, continua

    except (RuntimeError, ConnectionResetError, OSError) as exc:
        log.error("Conexão perdida: %s", exc)
        return None

    except KeyboardInterrupt:
        log.info("Worker encerrado pelo operador.")
        raise

    finally:
        try:
            sock.close()
        except Exception:
            pass


def run_worker() -> None:
    log.info("═" * 60)
    log.info("  Worker '%s'  |  Alvo inicial: %s:%s", WORKER_UUID, MASTER_HOST, MASTER_PORT)
    log.info("  Heartbeat a cada %.0fs  |  Reconexão em %.0fs", HEARTBEAT_INTERVAL, RECONNECT_DELAY)
    log.info("═" * 60)

    current_host = MASTER_HOST
    current_port = MASTER_PORT

    while True:
        try:
            result = connection_loop(current_host, current_port)
            if result:
                # Migração para novo Master
                log.info("Migrando para novo Master: %s:%s", result["host"], result["port"])
                current_host = result["host"]
                current_port = result["port"]
            else:
                # Falha ou desconexão — volta ao master original após delay
                current_host = MASTER_HOST
                current_port = MASTER_PORT
                log.info("Reconectando em %.0fs ...", RECONNECT_DELAY)
                time.sleep(RECONNECT_DELAY)

        except KeyboardInterrupt:
            log.info("Saindo.")
            break


if __name__ == "__main__":
    run_worker()