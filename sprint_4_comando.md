### Desenvolver a base de um sistema distribuído autônomo;
## Arquitetura do sistema:
    - Nó master:
        - Recebe requisições de clientes (requisições simuladas pelo próprio nó);
        - Mantém uma lista de Workers em sua farm;
        - Monitora constantemente o número de requisições pendentes;
        - Inicia o "Protocolo de Conversa consensual";
        - Gerencia Workers "emprestados" de outros Masters;
    - Nó Worker:
        - Recebe tarefa do seu master atual e a processa (para simular o processamento o worker dormirá por 10 segundos);
        - Deve ser capaz de se desconectar do seu Master original e se conectar a um novo Master quando instruído;
    - Protocolo de Comunicação (Mensageria):
        - Define regras de negociação;
        - Será baseado em troca de mensagens, por exemplo, via API REST, gRPC ou Sockets customizados com formato JSON;
    
## Estrutura do repositório:
-- root
    |
    |-- docs/
    |-- master.py
    |-- worker.py
    |-- protocol.py
    |-- README.md

## CONSIDERAÇÕES DE IMPLEMENTAÇÃO:
    - **Message Delimiter**: \n deverá ser enviado após cada objeto JSON para determinar onde o JSON termina, o receptor deverá ler o socket até encotrar um "\n", e então processa o que recebeu como um JSON completo;
    - **Escuta Contínua**: Cada Master e Worker deve rodar em um loop infinito escutando por novas conexões (se for servidor) ou novas mensagens em conexões existentes;
    - **Threads/AsyncIO**: é fundamental para usar concorrência para que um master possa se comunicar com múltiplos outros Masters e Workers simultaneamente;
    - PROTOCOLOS DE COMUNICAÇÃO DEVERÃO UTILIZAR O QUE ESTÁ ESPECIFICADO EM Payload Oficial:
    
## Payload Oficial:
    - Conexão com Dashboard de avaliação:
        - PAYLOAD 4.1:
            ```
                {
                    "server_uuid": "Master_4",
                    "hostname": "Master_4.farm.local",
                    "role": "master",
                    "task": "performance_report",
                    "timestamp": "AAAA-MM-DDThh:mm:ssZ",
                    "payload_version": "sprint4-monitor",

                    "performance":{
                        "system":{
                            "uptime_seconds": "GET_UPTIME_SECONDS",
                            "load_average_1m": "GET_LOAD_AVERAGE_1M",
                            "load_average_5m": "GET_LOAD_AVERAGE_5M",
                            "cpu":{
                                "usage_percent": "GET_USAGE_PERCENT",
                                "count_logical": "GET_COUNT_LOGICAL",
                                "count_physical": "GET_COUNT_PHYSICAL"
                            },
                            "memory": {
                                "total_mb": TOTAL_MB,
                                "available_mb": AVAILABLE_MB,
                                "percent_used": PERCENT_USED,
                                "memory_used": MEMORY_USED 
                            },
                            "disk": {
                                "total_gb": TOTAL_GB,
                                "free_gb": FREE_GB,
                                "percent_used": PERCENT_USED
                            }
                        },
                        "farm_state": {
                            "workers": {
                                "total_registered": TOTAL_WORKERS_REGISTERED,
                                "workers_utilization": WORKERS_UTILIZATION,
                                "workers_alive": WORKERS_ALIVE,
                                "workers_idle": WORKERS_IDLE,
                                "workers_borrowed": WORKERS_BORROWED,
                                "workers_recieved": WORKERS_RECIEVED,
                                "workers_failed": WORKERS_FAILED,
                                "workers_home": WORKERS_HOME,
                                "workers_available_capacity": WORKERS_AVAILABLE_CAPACITY,
                                "borrowed_workers": {[
                                    {"direction": "out", "peer_uuid": "Master_5"},
                                    {"direction": "in", "peer_uuid": "Master_5"}
                                ]
                            },
                            "tasks": {
                                "tasks_pending": TASKS_PENDING,
                                "tasks_running": TASKS_RUNNING,
                                "tasks_completed": TASKS_COMPLETED,
                                "tasks_failed": TASKS_FAILED,
                                "oldest_task_age_s": OLDEST_TASK_AGE
                            }
                        },

                        "config_thresholds": {
                            "max_task": MAX_TASKS,
                            "warn_cpu_percent": WARN_CPU_PERCENT,
                            "warn_memory_percent": WARN_MEMORY_PERCENT,
                            "release_task": RELEASE_TASK,
                        },
                        "neighbors": [
                            "server_uuid": "Master_5",
                            "status": "available",
                            "last_heartbeat": "AAAA-MM-DDThh:mm:ssZ",
                        ]
                    }
                }
            }
            ```
## Objetivos da sessão:
- Para avaliação do trabalho o JSON especificado como PAYLOAD 4.1 deve ser enviado para um dashboard cuja configuração deve seguir os sseguintes parametros:
    - TCP_SOCKET_HOST = "nuted-ia.dev"
    - TCP_SOCKET_PORT = 443
    - TCP_SOCKET_TLS = True
    - TCP_SOCKET_SNI = "nuted-ia.dev"
- As informações do campo "performance" devem ser extraídas do próprio sistema operacional;
- As informações do campo "farm_state" devem ser enviadas em tempo real a cada 5 segundos pelo main

