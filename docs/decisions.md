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

## Sprint 4 — Monitoramento e Dashboard

1. **Message Delimiter (confirmado)**
	- Todas as mensagens JSON trocadas entre nós são terminadas com um delimitador de linha `"\n"`.
	- Recebedores devem ler do socket até encontrar um `"\n"` e então desserializar o JSON completo.

2. **Envio de métricas para Dashboard (PAYLOAD 4.1)**
	- O Master enviará periodicamente (ou sob demanda) o JSON conforme especificado em `sprint_4_comando.md` (PAYLOAD 4.1) para um dashboard remoto.
	- Parâmetros de conexão esperados (variáveis de configuração):
	  - `TCP_SOCKET_HOST = "nuted-ia.dev"`
	  - `TCP_SOCKET_PORT = 443`
	  - `TCP_SOCKET_TLS = True`
	  - `TCP_SOCKET_SNI = "nuted-ia.dev"`

3. **Periodicidade e conteúdo do `farm_state`**
	- O campo `farm_state` deve ser atualizado em tempo real e enviado a cada 5 segundos pelo processo principal do Master.
	- Valores obrigatórios em `farm_state` incluem contagens de workers (registrados, vivos, ociosos, emprestados), capacidade disponível e métricas de tasks (pendentes, em execução, concluídas, falhadas, idade da mais antiga).

4. **Coleta de métricas do sistema operacional**
	- Os campos dentro de `performance.system` (uptime, load average, uso de CPU, memória, disco) devem ser obtidos diretamente do SO onde o Master roda.
	- Implementações devem usar bibliotecas portáveis (por exemplo `psutil`) quando possível, e documentar alternativas de fallback se `psutil` não estiver disponível.

5. **Segurança/TLS e SNI**
	- A conexão com o dashboard deve suportar TLS com suporte a SNI usando `TCP_SOCKET_SNI`.
	- Implementações devem permitir a especificação de certificados CA customizados via variável/arquivo de configuração para ambientes de avaliação privados.

### Rationale
* Cumprir o formato oficial do payload garante compatibilidade com o avaliador.
* Enviar `farm_state` a cada 5s fornece visibilidade suficiente sem sobrecarregar a rede.
* Uso de `psutil` (ou equivalente) centraliza coleta de métricas e simplifica testes.

---

_Registro gerado em: 2026-06-15_
