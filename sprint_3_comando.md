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
    - Master -> Master - Comunicações Master-to-Master enviadas pelo Socket deverão seguir esta estrutura:
        - O campo "type" substitui a URL da API REST e identifica a operação requisitada:
        - O campo "request_id" é um UUID único;
        -  PAYLOAD 3.1:
            ```
                {
                    "type":"TIPO_DE_REQUISIÇÃO",
                    "request_id":"UUID_ÚNICO_PARA_RASTREIO",
                    "payload":{
                        // ... dados específicos da mensagem
                    }
                }
            ```
    - Master_4 -> Master - Pedido de ajuda (request_help):
        - PAYLOAD 3.2:
            ```
                {
                    "type":"request_help",
                    "request_id":"REQUEST_UUID",
                    "payload":{
                        "master_id":"4",
                        "current_load":150,
                        "capacity": 100,
                        "workers_needed": 2
                    }
                }
            ```
    - Master_7 -> Master_4 - Resposta ao Pedido:
        - PAYLOAD 3.3:
            ```
                {
                    "type":"response_accepted",
                    "resquest_id":"REQUEST_UUID",
                    "payload":{
                        "workers_offered": 2,
                        "worker_details": [
                            {"id":"WORKER1_UUID", "address":"ip:port_worker1},
                            {"id":"WORKER2_UUID", "address":"ip:port_worker2},
                        ]
                    }
                }
            ```
        - PAYLOAD 3.4:
            ```
                {
                    "type":"response_rejected",
                    "resquest_id":"REQUEST_UUID",
                    "payload":{
                        "reason":"high_load"
                    }
                }
            ```
    - MASTER_7 -> Worker - Mensagem de Redirecionamento:
        - PAYLOAD 3.5:
            ```
                {
                    "type": "command_redirect",
                    "request_id": "REQUEST_UUID",
                    "payload":{
                        "new_master_address":"ip_master_4:port"
                    }
                }
            ```
    - Worker1 -> Master_4 - Registro temporário:
        - PAYLOAD 3.6:
            ```
                {
                    "type": "register_temporary_worker",
                    "request_id":"REQUEST_UUID",
                    "payload":{
                        "worker_id":"WORKER1_UUID",
                        "original_master_address": "ip_master_7:port"
                    }
                }
            ```
    - Master_4 -> Worker1 - Comando para retornar (command_release):
        - PAYLOAD 3.7:
            ```
                {
                    "type": "command_release",
                    "request_id": "REQUEST_UUID",
                    "payload":{
                        "original_master_address": "ip_master_7:port"
                    }
                }
            ```
    - Master_4 -> Master_7 - Notificação de devolução (notify_worker_returned):
        - PAYLOAD 3.8:
            ```
                {
                    "type": "notify_worker_returned",
                    "request_id": "REQUEST_UUID",
                    "payload": {
                        "worker_id": "WORKER1_UUID"
                    }
                }
            ```

           

## Explicações para  Implementar camada de comunicação P2P entre Masters (Master -> Master):
- Para permitir que um Master Saturado negocie e receba, de forma autônoma e consensual, Workers emprestados de um Master Vizinho
- Estrutura de Comunicação Mater-to-Master: PAYLOAD 3.1;
- O que deve ser implementado:
    - Pedido de ajuda:
        - Master_4 ao detectar saturação (requisições pendentes acima do threshold definido), abre uma conexão socket com o Master B, uma vez conectado ele envia a mensagem JSON - PAYLOAD 3.2;
    - Análise/Resposta:
        - Ao Receber a mensagem do Master_4 o Master destino (Master_7 por exemplo) pode negar ou aceitar ao pedido:
            - Caso Negue: PAYLOAD 3.3;
            - Caso Aceite: PAYLOAD 3.4;
    - Comando de Redirecionamento:
        - Após enviar response_Accepted, o Master_7 comunica-se com cada um dos workers ofertados, pela conexão socket pré-existente, e ordena o redirecionamento para o Master_4 -> PAYLOAD 3.5;
    - Registro temporário do Worker no Master saturado:
        - Ao receber o command_redirect o Worker1 encerra sua conexão com o Master_7, finalizando primeiramente qualquer tarefa em execuçãao, e abre uma nova conexão socket com o Master_4 -> PAYLOAD 3.6; 
    - Devolução do Worker ao Master de origem quando a carga normalizar:
        - Quando a carga do Master_4 normalizar (requisições pendentes abaixo de um threshold de liberação) o processo de devolução começa em duas etapas:
            - Master_4 instrui o Worker1 para encerrar a conexão e retornar a seu Master original - PAYLOAD 3.7;
            - Assincronamente Master_4 notifica o Master_7 que o Worker foi retornado - PAYLOAD 3.8;

## Objetivos da Sessão:
- Tarefa 01 — Conexão TCP entre Masters:
    - Implementar no Master a capacidade de atuar simultaneamente como servidor (escutando
    conexões de Workers e de outros Masters) e como cliente (abrindo conexões com Masters
    vizinhos);
    - Manter um diretório de Masters vizinhos contendo master_id e endereço (ip:porta).
    - Utilizar o delimitador \n  para enquadramento das mensagens JSON;
- Tarefa 02 — Detecção de Saturação:
    - Definir e parametrizar o threshold de saturação (ex.: capacity = 100 requisições pendentes);
    - Definir um threshold de liberação (ex.: 60% da capacidade) para acionar a devolução, evitando oscilações (efeito histerese).
    - Disparar o envio de request_help quando current_load > capacity, calculando workers_needed proporcionalmente ao excedente;
- Tarefa 03 — Protocolo de Negociação (request_help / response):
    - Implementar emissão de request_help com geração de UUID v4 para o request_id;
    - Implementar receptor no Master que avalia carga atual, número de Workers ociosos e responde com response_accepted ou response_rejected;
    - Garantir que o request_id da resposta seja idêntico ao da requisição original;
    - Implementar timeout de 5 segundos no Master solicitante; após o timeout, considerar o pedido como recusado e tentar próximo vizinho;
- Tarefa 04 — Redirecionamento de Workers:
    - Implementar emissão de command_redirect do Master ofertante para cada Worker selecionado;
    - Atualizar o Worker para tratar command_redirect: encerrar a conexão atual graciosamente (sem perder tarefa em execução), conectar ao novo endereço e enviar register_temporary_worker;
    - Atualizar o Master receptor para tratar register_temporary_worker, registrando o Worker como "emprestado" e seu Master de origem;
    - A partir do registro, o Worker emprestado deve operar enviando
    ALIVE com o campo SERVER_UUID preenchido com o Master de origem;
- Tarefa 05 — Devolução do Worker:
    - Implementar lógica que monitora o retorno da carga abaixo do threshold de liberação no Master_4;
    - Implementar emissão de command_release do Master_4 para o Worker emprestado;
    - Implementar emissão de notify_worker_returned do Master_4 para o Master_7 na conexão
    Master-to-Master;
    - Garantir que o Worker se reconecte ao Master original e volte a operar normalmente, sem perda de estado;
- Tarefa 06 — Concorrência e Resiliência:
    - Utilizar Threads ou AsyncIO para que o Master atenda Workers próprios, Workers emprestados, conexões com Masters vizinhos e simulação de carga simultaneamente, sem bloqueio;
    - Tratar desconexões inesperadas: se um Worker emprestado perder conexão com o Master_4, ele deve tentar voltar ao Master_7; se um Master vizinho cair durante a negociação, o solicitante deve liberar o request_id e seguir o fluxo;
    - Toda mensagem recebida com type desconhecido deve ser logada e ignorada, sem derrubar o processo (compatibilidade com extensões futuras);
- Tarefa 07 — Logs e Observabilidade:
    - Registrar em log toda emissão e recebimento de mensagens Master-to-Master com seu
    request_id, type e timestamp;
    - Manter contador de Workers locais e emprestados por Master, exibindo o estado a cada
    mudança;
    - Registrar o ciclo de vida completo de cada Worker emprestado: empréstimo, registro, tarefas executadas e devolução;