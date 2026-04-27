from __future__ import annotations
import json
import socket
from enum import Enum
from typing import Any

BUFFER_SIZE = 4096  # tamanho máximo de cada leitura do socket TCP
DELIMITER   = b"\n" # separador de mensagens no stream TCP


class Task(str, Enum):
<<<<<<< HEAD:protocol.py
    JOIN            = "JOIN"
    HEARTBEAT       = "HEARTBEAT"
    ASSIGN_TASK     = "ASSIGN_TASK"
    TASK_RESULT     = "TASK_RESULT"
    WORKER_STATUS   = "WORKER_STATUS"
    LOAD_REPORT     = "LOAD_REPORT"
    BORROW_WORKER   = "BORROW_WORKER"
    BORROW_ACK      = "BORROW_ACK"
    WORKER_MIGRATE  = "WORKER_MIGRATE"
    MIGRATE_ACK     = "MIGRATE_ACK"
    PEER_HELLO      = "PEER_HELLO"
=======
    JOIN           = "JOIN"
    HEARTBEAT      = "HEARTBEAT"
    ASSIGN_TASK    = "ASSIGN_TASK"
    TASK_RESULT    = "TASK_RESULT"
    WORKER_STATUS  = "WORKER_STATUS"
    LOAD_REPORT    = "LOAD_REPORT"
    BORROW_WORKER  = "BORROW_WORKER"
    BORROW_ACK     = "BORROW_ACK"
    WORKER_MIGRATE = "WORKER_MIGRATE"
    MIGRATE_ACK    = "MIGRATE_ACK"
    PEER_HELLO     = "PEER_HELLO"
>>>>>>> 27edec5d774f0d16611f7a299741bdf063923050:shared/protocol.py


class Response(str, Enum):
    ALIVE        = "ALIVE"
    OK           = "OK"
    DENIED       = "DENIED"
    UNKNOWN_TASK = "UNKNOWN_TASK"
    ACK          = "ACK"


def send_json(sock: socket.socket, payload: dict[str, Any]) -> None:
    data = json.dumps(payload) + "\n"
    sock.sendall(data.encode("utf-8"))


class LineBuffer:
    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> list[dict]:
        self._buf += chunk
        messages: list[dict] = []
        while "\n" in self._buf:
            raw, self._buf = self._buf.split("\n", 1)
            raw = raw.strip()
            if raw:
                try:
                    messages.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass
        return messages