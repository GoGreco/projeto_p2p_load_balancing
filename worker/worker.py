from __future__ import annotations

import logging
import os
import random
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.protocol import Task, Response, send_json, LineBuffer, BUFFER_SIZE

# ──────────────────────────────────────────────────────────────
# Configuração via variáveis de ambiente
# ──────────────────────────────────────────────────────────────
WORKER_UUID        = os.environ.get("WORKER_UUID",        "Worker_A1")

# MASTER_HOST deve ser o IP LAN da máquina onde o Master está rodando.
# Ex: set MASTER_HOST=192.168.1.10   (Windows)
#     export MASTER_HOST=192.168.1.10 (Linux/Mac)
# Se não for definido, tenta localhost (útil apenas para testes locais).
MASTER_HOST        = os.environ.get("MASTER_HOST",        "10.62.217.41")
MASTER_PORT        = int(os.environ.get("MASTER_PORT",    9000))

HEARTBEAT_INTERVAL = float(os.environ.get("HEARTBEAT_INTERVAL", 6))
RECONNECT_DELAY    = float(os.environ.get("RECONNECT_DELAY",    5))
SOCKET_TIMEOUT     = float(os.environ.get("SOCKET_TIMEOUT",     10))

# ──────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-12s %(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(WORKER_UUID)


# ──────────────────────────────────────────────────────────────
# Execução de tarefas
# ──────────────────────────────────────────────────────────────
def execute_task(payload: dict) -> str:
    op = payload.get("OP", "NOP")
    n  = int(payload.get("N", 10))

    if op == "COMPUTE_FIBONACCI":
        time.sleep(10)
        result = str(42)

    elif op == "SORT_ARRAY":
        time.sleep(10)
        result = str(42)

    elif op == "HASH_DATA":
        time.sleep(10)
        result = str(42)

    elif op == "PING_ENDPOINT":
        time.sleep(10)
        result = str(42)

    elif op == "COMPRESS_DATA":
        time.sleep(10)
        result = str(42)

    else:
        time.sleep(10)
        result = str(42)

    time.sleep(random.uniform(0.2, 1.5))
    return result


# ──────────────────────────────────────────────────────────────
# Processamento de mensagens recebidas do Master
# ──────────────────────────────────────────────────────────────
_pending_migration: dict | None = None


def process_message(payload: dict, sock: socket.socket) -> bool:
    """
    Retorna False quando o Worker deve encerrar esta conexão TCP
    e migrar para um novo Master (WORKER_MIGRATE).
    """
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
            log.info("ALIVE recebido (Master '%s' ativo)", payload.get("SERVER_UUID"))
        else:
            log.warning("Resposta inesperada ao heartbeat: '%s'", status)

    elif task == Task.ASSIGN_TASK:
        task_id = payload.get("TASK_ID", "?")
        tp      = payload.get("PAYLOAD", {})
        log.info("Tarefa recebida: %s  OP=%s  N=%s", task_id, tp.get("OP"), tp.get("N"))
        result  = execute_task(tp)
        log.info("Tarefa %s concluída. Resultado: %s", task_id, result)
        send_json(sock, {
            "SERVER_UUID": WORKER_UUID,
            "TASK":        Task.TASK_RESULT,
            "TASK_ID":     task_id,
            "RESULT":      result,
        })

    elif task == Task.WORKER_MIGRATE:
        new_host = payload.get("NEW_HOST", "127.0.0.1")
        new_port = int(payload.get("NEW_PORT", 9000))
        owner    = payload.get("OWNER", "?")
        log.info("Instrução de migração recebida → %s:%s  (owner: %s)", new_host, new_port, owner)
        # Confirma recebimento e encerra esta conexão TCP
        send_json(sock, {
            "SERVER_UUID": WORKER_UUID,
            "TASK":        Task.MIGRATE_ACK,
            "RESPONSE":    Response.ACK,
        })
        _pending_migration = {"host": new_host, "port": new_port}
        return False  # sinaliza para sair do loop e reconectar no novo Master

    return True


# ──────────────────────────────────────────────────────────────
# Loop de conexão TCP com o Master
# ──────────────────────────────────────────────────────────────
def connection_loop(host: str, port: int) -> dict | None:
    """
    Conecta via TCP ao Master em host:port.
    Retorna dict {"host": ..., "port": ...} se receber instrução de migração,
    ou None se a conexão cair por outro motivo.
    """
    global _pending_migration
    _pending_migration = None

    log.info("Conectando via TCP a %s:%s ...", host, port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(SOCKET_TIMEOUT)

    try:
        sock.connect((host, port))
    except (ConnectionRefusedError, TimeoutError, OSError) as exc:
        log.error("Falha na conexão TCP com %s:%s — %s", host, port, exc)
        log.error("Verifique se o Master está rodando e se o IP/porta estão corretos.")
        sock.close()
        return None

    log.info("Conectado via TCP a %s:%s", host, port)
    send_json(sock, {
        "SERVER_UUID": WORKER_UUID,
        "TASK":        Task.JOIN,
    })
    log.info("JOIN enviado → %s:%s", host, port)

    buf             = LineBuffer()
    last_heartbeat  = 0.0

    try:
        while True:
            now = time.monotonic()

            # Envia heartbeat periodicamente
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                log.info("Enviando HEARTBEAT → %s:%s", host, port)
                send_json(sock, {
                    "SERVER_UUID": WORKER_UUID,
                    "TASK":        Task.HEARTBEAT,
                })
                last_heartbeat = now

            # Leitura não-bloqueante (timeout curto para não travar o heartbeat)
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
                pass  # sem dados no momento, continua o loop

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


# ──────────────────────────────────────────────────────────────
# Entrada principal
# ──────────────────────────────────────────────────────────────
def run_worker() -> None:
    log.info("═" * 60)
    log.info("  Worker '%s'", WORKER_UUID)
    log.info("  Master alvo: %s:%s", MASTER_HOST, MASTER_PORT)
    log.info("  Heartbeat a cada %.0fs | Reconexão em %.0fs",
             HEARTBEAT_INTERVAL, RECONNECT_DELAY)
    log.info("═" * 60)

    current_host = MASTER_HOST
    current_port = MASTER_PORT

    while True:
        try:
            result = connection_loop(current_host, current_port)
            if result:
                # Migração para novo Master via TCP
                log.info("Migrando via TCP para novo Master: %s:%s",
                         result["host"], result["port"])
                current_host = result["host"]
                current_port = result["port"]
            else:
                # Falha ou desconexão — volta ao Master original após delay
                current_host = MASTER_HOST
                current_port = MASTER_PORT
                log.info("Reconectando ao Master original em %.0fs ...", RECONNECT_DELAY)
                time.sleep(RECONNECT_DELAY)

        except KeyboardInterrupt:
            log.info("Saindo.")
            break


if __name__ == "__main__":
    run_worker()