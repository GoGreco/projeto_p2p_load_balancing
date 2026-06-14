# Sprint 1 Load Balancing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a reliable TCP-based concurrent server (Master) and client (Worker) exchanging JSON heartbeat messages delimited by `\n` using the standard library `threading` package in Python.

**Architecture:** A communication helper module (`protocol.py`) handles TCP message framing by appending/searching for the newline delimiter (`\n`). `master.py` listens for TCP connections and spawns a thread per connection to non-blockingly handle workers. `worker.py` connects to the master and maintains a persistent connection, sending periodic `HEARTBEAT` payloads every 10 seconds.

**Tech Stack:** Python 3 (standard libraries `socket`, `json`, `threading`, `time`), pytest for testing.

---

### File Structure
- `protocol.py`: Low-level TCP message sending and buffered reading.
- `master.py`: Threaded TCP server accepting worker connections and responding to heartbeats.
- `worker.py`: Client connection and regular heartbeat sender loop.
- `tests/test_protocol.py`: Unit tests for TCP message framing.

---

### Task 1: Protocol Helper Functions (`protocol.py`)

**Files:**
- Create: `protocol.py`
- Create: `tests/test_protocol.py`

- [ ] **Step 1.1: Create basic protocol file and test stub**
  Create a basic `protocol.py` file defining `send_msg` and `recv_msg`.
  Create a `tests/test_protocol.py` file.

- [ ] **Step 1.2: Write failing unit test for `send_msg`**
  Write a test in `tests/test_protocol.py` that verifies `send_msg` correctly converts dict to JSON, appends `\n`, and sends it to a mock socket.

- [ ] **Step 1.3: Run the test to verify it fails**
  Run `pytest tests/test_protocol.py` to ensure it fails or shows import/implementation errors.

- [ ] **Step 1.4: Implement `send_msg`**
  Implement `send_msg(sock, payload)` in `protocol.py`.

- [ ] **Step 1.5: Verify `send_msg` test passes**
  Run `pytest tests/test_protocol.py` and ensure the test passes.

- [ ] **Step 1.6: Write failing unit test for `recv_msg`**
  Write a test that mocks `sock.recv` returning a stream of data (including partial messages and multiple messages separated by `\n`) and verifies `recv_msg` extracts them one by one correctly.

- [ ] **Step 1.7: Run the test to verify it fails**
  Run `pytest tests/test_protocol.py` and ensure it fails.

- [ ] **Step 1.8: Implement `recv_msg`**
  Implement `recv_msg(sock)` in `protocol.py` with an internal thread-safe or connection-scoped read buffer.

- [ ] **Step 1.9: Verify `recv_msg` test passes**
  Run `pytest tests/test_protocol.py` and ensure all tests pass.

- [ ] **Step 1.10: Commit**
  Commit `protocol.py` and `tests/test_protocol.py`.

---

### Task 2: Master Node (`master.py`)

**Files:**
- Create: `master.py`
- Create: `tests/test_master.py`

- [ ] **Step 2.1: Write integration test for Master's heartbeat handler**
  Write an integration test in `tests/test_master.py` that spins up a Master on a local random port, connects to it, sends a heartbeat payload, and asserts the correct response payload.

- [ ] **Step 2.2: Run test to verify it fails**
  Run `pytest tests/test_master.py` and verify it fails (since `master.py` does not exist or isn't running).

- [ ] **Step 2.3: Implement threaded Master TCP server**
  Implement the listening socket, connection-accepting loop, and connection-handling thread inside `master.py`.
  If `"TASK": "HEARTBEAT"` is received, reply with:
  ```json
  {
    "SERVER_UUID": "Master_4",
    "TASK": "HEARTBEAT",
    "RESPONSE": "ALIVE"
  }
  ```

- [ ] **Step 2.4: Verify Master test passes**
  Run `pytest tests/test_master.py` and ensure the test passes.

- [ ] **Step 2.5: Commit**
  Commit `master.py` and `tests/test_master.py`.

---

### Task 3: Worker Node (`worker.py`)

**Files:**
- Create: `worker.py`
- Create: `tests/test_worker.py`

- [ ] **Step 3.1: Write test for Worker's connection and heartbeat execution**
  Write an integration test that runs a mock TCP server, starts a Worker client, and verifies that the Worker connects, sends the official `HEARTBEAT` payload, and handles the server's reply.

- [ ] **Step 3.2: Run test to verify it fails**
  Run `pytest tests/test_worker.py` and verify it fails.

- [ ] **Step 3.3: Implement Worker client**
  Implement `worker.py` containing the TCP client socket connection, the background thread to handle sending heartbeats every 10 seconds, and exception handling for reconnection.

- [ ] **Step 3.4: Verify Worker test passes**
  Run `pytest tests/test_worker.py` and ensure the test passes.

- [ ] **Step 3.5: Commit**
  Commit `worker.py` and `tests/test_worker.py`.

---

### Task 4: Complete Integration & Validation

- [ ] **Step 4.1: Manual verification**
  Run `master.py` in one terminal and `worker.py` in another. Verify from the standard outputs that heartbeats are sent, acknowledged, and logged successfully every 10 seconds.
- [ ] **Step 4.2: Resilience check**
  Stop the Master process, observe the Worker attempt to reconnect gracefully, then start Master again and observe successful reconnection and heartbeat resumption.
