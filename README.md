# Projeto P2P Load Balancing

## Descrição
Este repositório contém uma implementação simples de balanceamento de carga ponto‑a‑ponto (P2P) usando sockets TCP em Python. Um **master** aceita conexões de múltiplos **workers**, mantém um registro dos workers ativos e monitora *heartbeats* para detectar falhas de conexão.

## Estrutura do Projeto
```
.
├── master.py          # Servidor master que aceita workers, registra UUIDs e monitora heartbeats
├── worker.py          # Cliente que se conecta ao master e envia HEARTBEAT periodicamente
├── protocol.py        # Funções auxiliares para enviar/receber mensagens JSON terminadas por '\n'
├── docs/
│   ├── decisions.md   # Documentação das decisões de projeto
│   └── ...            # Outros documentos
├── tests/
│   ├── test_master.py
│   ├── test_worker.py
│   └── test_protocol.py
└── README.md          # Este arquivo
```

## Como Executar
1. **Instalar dependências** (pytest para testes):
   ```bash
    python -m pip install -r requirements.txt  # ou apenas pytest se já houver um venv
   ```
2. **Iniciar o master**:
   ```bash
   python master.py
   ```
   O master escuta em `0.0.0.0:5000` por padrão.
3. **Iniciar um worker** (em outra janela/terminal):
   ```bash
   python worker.py
   ```
   O worker se conecta ao master e envia um *heartbeat* a cada 10 s.

### Envio do PAYLOAD 4.1 para Dashboard de Avaliação

Para avaliação, o Master pode enviar o `PAYLOAD 4.1` (relatório de performance) para o dashboard remoto. As configurações esperadas são:

- `TCP_SOCKET_HOST = "nuted-ia.dev"`
- `TCP_SOCKET_PORT = 443`
- `TCP_SOCKET_TLS = True`
- `TCP_SOCKET_SNI = "nuted-ia.dev"`

Defina essas variáveis de ambiente antes de iniciar o Master ou ajuste a configuração no código. Veja `docs/setup_instructions.md` para detalhes sobre certificação TLS/SNI e verificação local.

O Master envia o `farm_state` em tempo real a cada 5 segundos enquanto estiver rodando.

### Enfileirar tarefas manualmente
Você pode enfileirar tarefas diretamente no processo do master (útil para testes):

```python
# em um REPL ou script executando no mesmo ambiente do projeto
from master import enqueue_task
enqueue_task('alice', 'task-1')
```

### Executando testes (venv)
Se estiver usando o ambiente virtual do projeto, execute:

```bash
./.venv/bin/python -m pytest -q
```

## Protocolo (resumo de payloads suportados)
- Worker -> Master (apresentação):
   - PAYLOAD 2.1
      ```json
      {"WORKER":"ALIVE","WORKER_UUID":"<uuid>"}
      ```
- Master -> Worker (atribuição de tarefa):
   - PAYLOAD 2.2
      ```json
      {"TASK":"QUERY","USER":"<user>","TASK_ID":"<id>"}
      ```
   - PAYLOAD 2.3 (sem tarefa)
      ```json
      {"TASK":"NO_TASK"}
      ```
- Worker -> Master (resultado):
   - PAYLOAD 2.4
      ```json
      {"STATUS":"OK|NOK","TASK":"QUERY","WORKER_UUID":"<uuid>"}
      ```
- Master -> Worker (ACK):
   - PAYLOAD 2.5
      ```json
      {"STATUS":"ACK"}
      ```

## Funcionalidades Principais
- **Rastreamento de workers** com UUID único para cada conexão.
- **Monitoramento de heartbeat**: se o master não receber um heartbeat dentro de 15 s, o worker é considerado desconectado e removido da lista..

## Documentação de Decisões
Veja `docs/decisions.md` para entender as escolhas de design, razões e próximos passos.

## Setup e Configuração
Consulte `docs/setup_instructions.md` para passos de preparação do ambiente, variáveis necessárias e exemplos de execução.

## Contribuindo
1. Fork o repositório.
2. Crie uma branch para sua feature ou correção.
3. Execute os testes (`pytest -q`) para garantir que tudo continua funcionando.
4. Abra um Pull Request descrevendo as mudanças.

## Licença
Este projeto está licenciado sob a licença MIT. Consulte o arquivo `LICENSE` para mais detalhes.
