can### Desenvolver a base de um sistema distribuído autônomo;
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
    - Worker A1 -> Master 4 - Worker A1 pergunta ao Servidor se ele está ativo:
        -  PAYLOAD:
            ```
                {
                    "SERVER_UUID":"Master_4",
                    "TASK":"HEARTBEAT"
                }
            ```
    - Master 4 -> Worker A1 - Responde que está ativo:
        - PAYLOAD:
            ```
               {
                "SERVER_UUID":"Master_4",
                "TASK":"HEARTBEAT",
                "RESPONSE":"ALIVE"
               } 
            ```
    
## Objetivos dessa sessão:
    - Estabelescer conexão entre o Master e o Worker garantindo que o Worker consiga verificar se o seu "mestre" está ativo através de troca de mensagens JSON via TCP.
    ### Backlog de Tarefas:
        - **Tarefa 01** - Infraestrutura da Comunicação TCP:
            - Configurar o Master para atuar como Servidor, escutando em uma porta definida;
            - Configurar o Worker para atuar como cliente iniciando a conexão;
            - Padrão de Mensagem: implementar delimitador de nova linha (\n) ao final de cada JSON para garantir que o receptor identifique o fim da mensagem no stream TCP;
        - **Tarefa 02** - Lógica de Requisição (Worker -> Master):
            - Desenvolver a função no Worker para disparar o payload de verificação;
            - Payload de Envio: PAYLOAD OFICIAL;
        - **Tarefa 03** - Lógica de Resposta (Master -> Worker):
            - Implementar no Master a capacidade de interpretar a tarefa "HEARTBEAT" e  devolver a confirmação imediata;
            - Payload de Resposta: PAYLOAD OFICIAL;
        - **Tarefa 04** - Concorrência e Resiliência:
            - Utilizar Threads ou AsyncIO no Master para que o atendimento de um Heartbeat não bloqueie outras operações (como processamento de tarefas "reais");
            - Cirar um loop no Worker para repetir essa verificação em intervalos regulares (a cada 10 segundos); 
        
