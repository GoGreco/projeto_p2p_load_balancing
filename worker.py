import socket
import json
import time
import logging

WORKER_UUID        = "Worker_A1"
MASTER_HOST        = "127.0.0.1"  
MASTER_PORT        = 9000
HEARTBEAT_INTERVAL = 3            
RECONNECT_DELAY    = 5            
SOCKET_TIMEOUT     = 5             
BUFFER_SIZE        = 4096

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WORKER %(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("Worker")


def send_json(sock: socket.socket, payload: dict) -> None:
    data = json.dumps(payload) + "\n"
    sock.sendall(data.encode("utf-8"))


def recv_json(sock: socket.socket) -> dict:
    raw = b""
    while b"\n" not in raw:
        chunk = sock.recv(BUFFER_SIZE)
        if not chunk:
            raise RuntimeError("Conexao encerrada pelo Master.")
        raw += chunk

    line, _ = raw.split(b"\n", 1)
    return json.loads(line.decode("utf-8"))


def heartbeat_payload() -> dict:
    return {
        "SERVER_UUID": WORKER_UUID,
        "TASK":        "HEARTBEAT",
    }


def send_heartbeat(sock: socket.socket) -> bool:
    payload = heartbeat_payload()
    log.info("Enviando HEARTBEAT -> Master (%s:%s) ...", MASTER_HOST, MASTER_PORT)
    send_json(sock, payload)

    response = recv_json(sock)
    status = response.get("RESPONSE", "???").upper()

    if status == "ALIVE":
        log.info("Status: ALIVE  ✓  (Master '%s' esta ativo)", response.get("SERVER_UUID"))
        return True
    else:
        log.warning("Status inesperado recebido: '%s'", status)
        return False



def run_worker() -> None:
    log.info("Worker '%s' iniciado. Alvo: %s:%s", WORKER_UUID, MASTER_HOST, MASTER_PORT)

    while True:
        sock = None
        try:
            log.info("Conectando ao Master em %s:%s ...", MASTER_HOST, MASTER_PORT)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(SOCKET_TIMEOUT)
            sock.connect((MASTER_HOST, MASTER_PORT))
            log.info("Conexao estabelecida com sucesso.")

            while True:
                send_heartbeat(sock)
                time.sleep(HEARTBEAT_INTERVAL)

        except (ConnectionRefusedError, TimeoutError, OSError) as exc:
            log.error("Status: OFFLINE — %s", exc)
            log.info("Tentando reconectar em %s segundos ...", RECONNECT_DELAY)

        except RuntimeError as exc:
            log.error("Status: OFFLINE — %s", exc)
            log.info("Tentando reconectar em %s segundos ...", RECONNECT_DELAY)

        except json.JSONDecodeError as exc:
            log.error("Resposta invalida do Master — %s", exc)

        except KeyboardInterrupt:
            log.info("Worker encerrado pelo operador.")
            break

        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

        time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    run_worker()