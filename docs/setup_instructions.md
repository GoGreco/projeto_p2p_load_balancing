# Setup e Instruções de Execução

Este documento descreve como preparar o ambiente local para executar o projeto e como configurar a conexão com o dashboard de avaliação (PAYLOAD 4.1).

## Requisitos

- Python 3.9+ recomendado
- `pip` e um ambiente virtual (`venv`) opcional
- Dependências listadas em `requirements.txt` (recomenda-se instalar em um virtualenv)

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Variáveis de configuração esperadas

- `TCP_SOCKET_HOST` (default: `nuted-ia.dev`)
- `TCP_SOCKET_PORT` (default: `443`)
- `TCP_SOCKET_TLS` (default: `True`) — se `True` cria contexto TLS para a conexão
- `TCP_SOCKET_SNI` (default: `nuted-ia.dev`) — nome para SNI
- `CA_BUNDLE_PATH` (opcional) — caminho para CA customizada se necessário

Exemplo de export (Linux/macOS):

```bash
export TCP_SOCKET_HOST="nuted-ia.dev"
export TCP_SOCKET_PORT=443
export TCP_SOCKET_TLS=true
export TCP_SOCKET_SNI="nuted-ia.dev"
# export CA_BUNDLE_PATH=/path/to/ca-bundle.pem
```

## Notas sobre TLS e SNI

- Ao conectar via socket TLS para `nuted-ia.dev:443`, use um `ssl.SSLContext` com `server_hostname=TCP_SOCKET_SNI` (SNI).
- Para ambientes de avaliação com CA customizada, carregue o `CA_BUNDLE_PATH` no contexto TLS (`context.load_verify_locations(CA_BUNDLE_PATH)`).
- Se o sistema não possuir certificado válido para `nuted-ia.dev`, forneça a CA do avaliador em `CA_BUNDLE_PATH`.

## Como executar

- Iniciar Master (exemplo usando `scripts`):

```bash
source .venv/bin/activate
# assegure variáveis de ambiente definidas antes
python scripts/run_master_instance.py
```

- Iniciar Worker (em outro terminal):

```bash
source .venv/bin/activate
python scripts/run_worker_instance.py
```

Observações:
- O Master, quando configurado com `TCP_SOCKET_HOST`/`PORT` para o dashboard, enviará o PAYLOAD 4.1 conforme especificado em `sprint_4_comando.md`.
- O campo `farm_state` será atualizado e enviado a cada 5 segundos pelo loop principal do Master.

## Verificação rápida

- Para validar que o Master está tentando conectar ao dashboard (logs): verifique saídas/logs do processo — mensagens de tentativa de conexão e envio de PAYLOAD 4.1 devem aparecer.
- Para testes locais sem o dashboard real, é possível apontar `TCP_SOCKET_HOST` para um listener TLS local (ex.: `openssl s_server`) e inspecionar os JSONs enviados.

## Debug

- Habilite logs em nível DEBUG no Master para ver payloads e eventos de conexão.
- Para debugar problemas TLS, use `openssl s_client -connect nuted-ia.dev:443 -servername nuted-ia.dev` (ajuste host se usar redirecionamento local).
