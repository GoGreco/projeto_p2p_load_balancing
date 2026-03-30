import socket
import threading
import json
import logging
import time

# Definição de conexão
MASTER_UUID = "Master_A"
HOST        = "0.0.0.0"   
PORT        = 9000         
BUFFER_SIZE = 4096

#Registro de atividades

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MASTER %(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("Master")

#Determina a resposta do heartbeaat

def handle_heartbeat(payload: dict) -> dict:
    log.info("HEARTBEAT recebido de '%s'. Enviando ALIVE.", payload.get("SERVER_UUID", "???"))
    return {
        "SERVER_UUID": MASTER_UUID,
        "TASK":        "HEARTBEAT",
        "RESPONSE":    "ALIVE",
    }


TASK_HANDLERS = {
    "HEARTBEAT": handle_heartbeat,
}


# ─── Gerenciamento de Conexao 

def handle_client(conn: socket.socket, addr: tuple) -> None:
    log.info("Nova conexao de %s:%s", *addr)
    buffer = ""

    try:
        while True:
            chunk = conn.recv(BUFFER_SIZE).decode("utf-8")
            if not chunk:
                log.info("Conexao encerrada por %s:%s", *addr)
                break

            buffer += chunk

            while "\n" in buffer:
                raw, buffer = buffer.split("\n", 1)
                raw = raw.strip()
                if not raw:
                    continue

                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError as exc:
                    log.warning("JSON invalido de %s:%s — %s", *addr, exc)
                    continue

                task = payload.get("TASK", "").upper()
                handler = TASK_HANDLERS.get(task)

                if handler:
                    response = handler(payload)
                else:
                    log.warning("Task desconhecida '%s' de %s:%s", task, *addr)
                    response = {
                        "SERVER_UUID": MASTER_UUID,
                        "TASK":        task,
                        "RESPONSE":    "UNKNOWN_TASK",
                    }

                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

    except ConnectionResetError:
        log.warning("Conexao resetada por %s:%s", *addr)
    except Exception as exc:
        log.error("Erro inesperado com %s:%s — %s", *addr, exc)
    finally:
        conn.close()
        log.info("Socket de %s:%s fechado.", *addr)


def start_server() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen()
        log.info("Master '%s' escutando em %s:%s ...", MASTER_UUID, HOST, PORT)

        while True:
            try:
                conn, addr = srv.accept()
                t = threading.Thread(
                    target=handle_client,
                    args=(conn, addr),
                    daemon=True,
                    name=f"Worker-{addr[0]}:{addr[1]}",
                )
                t.start()
                log.info("Thread iniciada: %s (ativas: %s)", t.name, threading.active_count() - 1)
            except KeyboardInterrupt:
                log.info("Servidor encerrado pelo operador.")
                break
            except Exception as exc:
                log.error("Erro ao aceitar conexao: %s", exc)
                time.sleep(1)


if __name__ == "__main__":
    start_server()