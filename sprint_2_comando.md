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
    - Worker -> Master x - Worker A1 se apresenta para um master caso vinculádo a um master diferente do original:
        -  PAYLOAD 2.1:
            ```
                {
                    "WORKER":"ALIVE",
                    "WORKER_UUID":"...",
                }
            ```
    - Master -> Master 4 verificando a fila de tarefas:
        - PAYLOAD 2.2:
            ```
                {
                    "TASK":"QUERY",
                    "USER":"..."
                }
            ``` 
        - PAYLOAD 2.3:
            ```
                {
                    "TASK":"NO_TASK"
                }
            ```
    - Worker -> Worker devolvendo o resultado ao Master:
        - PAYLOAD 2.4:
            ```
                {
                    "STATUS":"OK|NOK",
                    "TASK":"QUERY",
                    "WORKER_UUID":"..."
                }
            ```
    - Master -> Confirmação de resposta:
        - PAYLOAD 2.5:
            ```
                {
                    "STATUS":"ACK"
                }
            ```

## Objetivos dessa sessão:
- ### Tarefa 01 -> Lógica de Apresentação e Identificação (Worker -> Master):
    - Implementar no Worker a capacidade de se apresentar ao Master enviando seu UUID;
    - *Diferencial de origem*: O Worker deve ser capaz de enviar o payload de "Emprestado" caso esteja vinculado a um Master original Diferente;
    - Payoad de Apresentação: PAYLOAD 2.1;
- ### Tarefa 02 -> Distribuição de carga  e Gestão da Fila (Master -> Worker):
    - Configurar o Master para gerenciar uma fila (queue) de tarefas pendentes;
    - Ao receber um pedido de tarefa, o master deve verificar a fila:
    - Payload caso haja tarefas: PAYLOAD 2.2;
    - Payload caso não haja tarefas: PAYLOAD 2.3;
- ### Tarefa 03 -> Simulação de Processamento e Relatório de Status (Worker -> Master):
    - Desenvolver no Worker o "executor": ao receber uma QUERY, ele deve simular um precessamento (ex: sleep de 10 segundos);
    - Após o "trabalho" o Worker deve reportar o resultado;
    - Payload: PAYLOAD 2.4;
- ### Tarefa 04 -> Mecanismo de Confirmação (ACK) e Persistência (Master -> Worker):
    - Implementar no Master o recebimento de status e a resposta de confirmação imediata para liberar o Worker;
    - Payload de recebimento/resposta: PAYLOAD 2.5
    - Garantir que o Master registre (log) qual Worker (local ou emprestado) concluiu qual tarefa;