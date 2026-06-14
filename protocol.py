"""protocol.py
Utility functions for sending and receiving JSON messages over a TCP socket.
Each message is a JSON object terminated by a newline character ("\n").
"""
import json
import socket
from typing import Optional

# Simple per-socket receive buffer stored in a dict keyed by socket object id.
_recv_buffers = {}


def _get_buffer(sock: socket.socket) -> str:
    """Retrieve the buffer string for a socket, creating it if missing."""
    return _recv_buffers.setdefault(id(sock), "")


def _set_buffer(sock: socket.socket, value: str) -> None:
    _recv_buffers[id(sock)] = value


def send_msg(sock: socket.socket, payload: dict) -> None:
    """Serialize *payload* to JSON, append a newline, and send it.

    The function uses ``sock.sendall`` to guarantee the whole message is transmitted.
    """
    data = json.dumps(payload) + "\n"
    # Encode as UTF‑8 bytes and send.
    sock.sendall(data.encode("utf-8"))


def recv_msg(sock: socket.socket) -> Optional[dict]:
    """Read from *sock* until a full JSON line (ending with ``\n``) is available.

    Returns the parsed JSON object, or ``None`` if the connection is closed
    before a complete message is received.
    """
    buffer = _get_buffer(sock)
    while "\n" not in buffer:
        try:
            chunk = sock.recv(4096)
        except ConnectionResetError:
            return None
        if not chunk:
            # Connection closed.
            return None
        buffer += chunk.decode("utf-8")
    # Split at the first newline.
    line, rest = buffer.split("\n", 1)
    _set_buffer(sock, rest)
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        # Malformed JSON – treat as None.
        return None
