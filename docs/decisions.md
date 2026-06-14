# Decisions Summary (Jump‑Start for Agents)

This file gives a short, agent‑friendly overview of the most important architectural choices in the **P2P Load Balancing** project. Use it as a quick reference before extending or modifying the system.

## Core Decisions

1. **Worker Registry**
	- Global variable `workers_info: Dict[Tuple[str, int], Dict[str, Any]]` stores each worker’s **UUID**, last heartbeat timestamp and optional metadata.
	- Access is synchronized with a `threading.Lock` (`workers_lock`).
	- Workers now register themselves with a presentation payload (PAYLOAD 2.1) containing `WORKER_UUID`.
	- Master acknowledges registration with an ACK (PAYLOAD 2.5).

2. **Heartbeat Monitoring**
	- Existing HEARTBEAT handling retained; workers send HEARTBEAT payloads and master replies with official response.
	- Registration also updates the heartbeat timestamp.

3. **Connection Lifecycle**
	- On receiving PAYLOAD 2.1 (`ALIVE`) the master registers the worker and sends ACK.
	- HEARTBEAT messages continue to update `last_hb`.
	- Master can now respond to task queries (`QUERY`) with either a task payload (PAYLOAD 2.2) or a no‑task payload (PAYLOAD 2.3).
	- Workers report task completion via PAYLOAD 2.4; master logs the result and replies with ACK.

4. **Logging**
	- Added logs for worker registration, task assignment, status reports and ACK exchanges.

## Rationale
* **Observability** – Consistent logging gives agents immediate insight into system state.
* **Thread‑Safety** – `workers_lock` guarantees safe concurrent access.

## Extension Points for Agents
* **Dynamic Configuration** – Make `interval` and `timeout` configurable via a file or CLI args.

---

Agents should read this summary before making any changes to the master‑worker coordination logic.
