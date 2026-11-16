# Desenvolvimento local

Guia para rodar cada camada fora do Docker, executar os testes e entender o que
está implementado no backend (`B01`–`B04`) e no gateway (`M02`, `M03`). O passo a
passo com Docker Compose está no [README](../README.md#como-rodar-docker-compose).

## Preparação (uv + Python 3.12)

Use o [uv](https://docs.astral.sh/uv/) para o ambiente Python. Na raiz:

```bash
uv venv --python 3.12
uv pip install -r requirements-dev.txt
```

`requirements-dev.txt` inclui as dependências de `backend/requirements.txt`,
`middleend/requirements.txt` e dos testes documentais. Execute cada serviço em um
processo separado: ambos possuem seu próprio pacote `app`, como previsto na
arquitetura.

## Verificação

Na raiz, valide os contratos e exemplos documentais (inclui o `openapi.yaml`):

```bash
uv run --no-project python -m unittest discover -s tests -v
```

Entre em `backend/` (e depois em `middleend/`) e execute:

```bash
uv run --no-project python -m pytest tests -v --cov=app --cov-branch --cov-fail-under=70
uv run --no-project python -m ruff check app tests
uv run --no-project python -m mypy app
```

Sem serviços externos rodam só os testes unitários. Os testes que usam PostgreSQL
com pgvector e Redis reais são pulados enquanto `TEST_DATABASE_URL` e
`TEST_REDIS_URL` não estiverem definidas. Para rodá-los, suba dois containers
descartáveis:

```bash
docker run -d --name smartsales-pgvector-test -p 127.0.0.1:5544:5432 -e POSTGRES_USER=smartsales \
  -e POSTGRES_PASSWORD=smartsales -e POSTGRES_DB=smartsales pgvector/pgvector:pg16
docker run -d --name smartsales-redis-test -p 127.0.0.1:6390:6379 redis:7-alpine
export TEST_DATABASE_URL=postgresql://smartsales:smartsales@127.0.0.1:5544/smartsales
export TEST_REDIS_URL=redis://127.0.0.1:6390/0
```

Use `127.0.0.1`, não `localhost`: no Windows `localhost` pode resolver para IPv6 e
a conexão fica pendurada. Os testes de integração apagam e recriam as tabelas do
backend e gravam em `catalog:version`; nunca aponte essas variáveis para um banco
ou Redis com dados que importam.

O workflow `Python domain modules` sobe os dois serviços e executa as verificações
das duas camadas com uv. `Specs and reference contracts` continua validando a
documentação e o OpenAPI.

## Rodar sem Docker (três terminais)

Precisa de um PostgreSQL com pgvector e de um Redis acessíveis.

```bash
# 1. backend (:8001) — DATABASE_URL, REDIS_URL e LLM_API_KEY (veja backend/.env.example)
cd backend && uv run --no-project python -m app.ingestion.run --catalog ../data/catalog.json \
  --manuals ../data/manuals/ --relations ../data/product_relations.json
cd backend && uv run --no-project uvicorn app.main:app --port 8001
# 2. middleend (:8000) — REDIS_URL e DATABASE_URL (veja middleend/.env.example)
cd middleend && uv run --no-project uvicorn app.main:app --port 8000
# 3. frontend (:3000) apontando para o gateway
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 pnpm -C frontend dev
```

O gateway publica o Swagger UI em `http://localhost:8000/docs` e o backend interno
em `http://localhost:8001/docs`.

### Variáveis de ambiente

| Serviço | Variável | Padrão | Efeito |
| --- | --- | --- | --- |
| backend | `DATABASE_URL` | `postgresql://smartsales:smartsales@localhost:5432/smartsales` | PostgreSQL com pgvector. |
| backend | `REDIS_URL` | não definida | Com ela, a ingestão executa `INCR catalog:version`. Sem ela, a CLI avisa e não invalida o cache. |
| backend | `REDIS_CONNECT_TIMEOUT_SECONDS` | `5.0` | Limite para conectar ao Redis no `INCR catalog:version`. |
| backend | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `EMBEDDING_MODEL` | OpenAI, `gpt-4o-mini`, `text-embedding-3-small` | Provedor compatível com a API da OpenAI. |
| backend | `SIMILARITY_THRESHOLD` | `0.72` | Abaixo dele o turno vira `LOW_SIMILARITY_FALLBACK`. |
| backend | `INGESTION_MAX_ATTEMPTS`, `INGESTION_BACKOFF_SECONDS` | `3`, `1.0` | Tentativas por fonte (mínimo 1) e espera inicial (dobra a cada falha). |
| backend | `HISTORY_MAX_MESSAGES` | `6` | Mensagens do histórico que entram no prompt. A janela de 10 é a que o gateway guarda e envia; o backend usa as 6 mais recentes. |
| middleend | `BACKEND_INTERNAL_URL` | `http://localhost:8001` | Endereço do backend. |
| middleend | `REDIS_URL` | não definida | Com ela, sessões e cache ficam no Redis. Sem ela, as sessões ficam na memória do processo e o cache fica desligado. |
| middleend | `REDIS_SOCKET_TIMEOUT_SECONDS`, `REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS` | `2.0`, `2.0` | Limite de cada chamada e da conexão ao Redis. |
| middleend | `DATABASE_URL` | não definida | Leitura de `products` para revalidar o cache. O cache só liga com `REDIS_URL` e `DATABASE_URL`. |
| middleend | `DATABASE_CONNECT_TIMEOUT_SECONDS` | `2` | Limite para conectar ao PostgreSQL na revalidação (inteiro, mínimo 2). |
| middleend | `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Origens aceitas, separadas por vírgula. |
| middleend | `SESSION_TTL_SECONDS`, `SESSION_HISTORY_MAX_MESSAGES`, `SESSION_LOCK_TTL_SECONDS` | `1800`, `10`, `60` | TTL da sessão, janela do histórico (número par, mínimo 2) e validade do lock de turno. |
| middleend | `CACHE_TTL_SECONDS`, `CACHE_POLICY_VERSION` | `3600`, `p1` | TTL das respostas em cache; mude a versão ao alterar prompts, guardrails, ranking ou modelo. |

## Arquitetura implementada

### Backend (`backend/app/`)

| Módulo | Pacote | O que faz |
| --- | --- | --- |
| `ingestion/` | `B01`, `B03` | CLI `python -m app.ingestion.run`: valida o catálogo, faz *upsert* em `products`, substitui `product_relations` pelo seed quando `--relations` é informado (sem a flag a tabela não é tocada; arquivo inexistente é erro), indexa a ficha técnica e o manual de cada produto em chunks de 500 tokens (sobreposição de 50). Cada fonte roda sob um registro em `ingestion_jobs` (`RUNNING` → `INDEXED`), com até 3 tentativas e *backoff* (`attempts` conta as tentativas da execução atual); esgotadas, ou em erro que repetir não resolve (PDF corrompido), fica `NEEDS_INTERVENTION`, a carga segue para a próxima fonte e a CLI termina com código 1. Os chunks novos e o `INDEXED` são gravados na mesma transação, então a versão anterior dos chunks é preservada em caso de falha; ao indexar, jobs não concluídos de versões antigas da mesma fonte são removidos. O `INCR catalog:version` roda ao final mesmo que a carga pare no meio; se o Redis falhar, o relatório traz `catalog_version_error` e a CLI termina com código 1. |
| `db/` | `B01` | `schema.sql` (idempotente) com `products`, `manual_chunks` (HNSW), `product_relations` e `ingestion_jobs`; `repository.py` com as consultas. |
| `clients/` | `B02`, `B03` | Cliente compatível com a API da OpenAI e `RedisCatalogVersion` (`INCR catalog:version`). |
| `rag/orchestrator.py` | `B02`, `B03`, `B04` | Turno de um produto: G-IN, busca dos 5 chunks do SKU, limiar, geração com G-OUT por sentença, citações e cards. |
| `guardrails/` | `B03` | Bloqueio de *prompt injection* e conferência de voltagem, potência, capacidade e preço antes de publicar cada sentença. |
| `recommendation/` | `B04` | `engine.py` (regras `RN01`, `RN04`, `RN05` em `Decimal`), `service.py` (candidatos do SQL → motor → cards), `cards.py` (textos montados só com valores do SQL) e `intent.py` (palavras-chave que abrem o ramo de upsell). |

Contrato interno: o middle-end chama `POST /internal/rag/stream` com
`{sku, question, history, preferred_voltage?}` e recebe NDJSON com `token` (só
sentenças aprovadas pelo G-OUT), `citations`, `recommendations`, `error` e `end`.

Quando o evento `recommendations` é emitido:

| Situação do turno | Cards |
| --- | --- |
| Resposta com evidência | Produto consultado (se em estoque) e cross-sell. O upsell entra se a pergunta indica necessidade maior ou comparação, ou se o produto consultado está esgotado. |
| `LOW_SIMILARITY_FALLBACK` ou `LLM_UNAVAILABLE` | Produto consultado, upsell e cross-sell, como alternativas em estoque. |
| `GUARDRAIL_BLOCKED` ou produto fora do catálogo ativo | Nenhum. |

O produto consultado é relido do SQL na hora de montar os cards (card `PRIMARY` e
teto de +35% do upsell). Se qualquer etapa das recomendações falhar, o turno segue
sem cards. O prompt continua
restrito ao produto consultado: os cards não entram no texto gerado.

### Gateway (`middleend/app/`)

| Módulo | Pacote | O que faz |
| --- | --- | --- |
| `routes/chat.py` | `M02`, `M03` | `POST /api/v1/sessions` (201 para sessão nova, 200 com o histórico quando o `session_id` enviado ainda está ativo), `DELETE /api/v1/sessions/{id}`, `POST /api/v1/chat/stream` e `GET /api/v1/health`. Redis indisponível nas rotas de sessão e chat responde 503 `SERVICE_UNAVAILABLE` no envelope de erro. |
| `sessions/` | `M02` | `SessionStore` com dois adaptadores: `RedisSessionStore` e `InMemorySessionStore`. |
| `cache/` | `M03` | `build_cache_key` (identidade canônica), `SemanticCacheService` e `RedisCacheStorage`. |
| `repositories/products.py` | `M03` | Leitura de preço, estoque e status em `products` (ADR-06). |
| `sse/` | `M02` | `sse_chat_generator`: protocolo público, ordem dos eventos, falhas e liberação do turno. |
| `clients/backend.py` | `M02` | Adaptador NDJSON do backend e *replay* de turnos concluídos ou vindos do cache. |

Chaves no Redis:

| Chave | Tipo | TTL | Conteúdo |
| --- | --- | --- | --- |
| `session:{id}:state` | HASH | 1800 s | `state`, `active_sku`, `updated_at`. |
| `session:{id}:history` | LIST | 1800 s | Últimas 10 mensagens (`LPUSH` + `LTRIM 0 9`). |
| `session:{id}:lock` | STRING | 60 s | Token do dono do turno em andamento, um por aquisição (`SET NX EX`). Só o dono libera o lock ou grava o turno. |
| `session:{id}:turn:{client_request_id}` | STRING | 1800 s | Registro de idempotência do turno. |
| `session:{id}:turns` | SET | 1800 s | Ids dos turnos, para o `DELETE` remover tudo. |
| `cache:sem:v{versão}:{sha256}` | STRING | 3600 s | Texto, citações e cards de um turno respondido, mais `consulted` (SKU, preço e disponibilidade do produto consultado). |
| `catalog:version` | STRING | sem expiração | Contador incrementado pela ingestão. |

Regras do cache:

- A chave inclui a versão do catálogo, a consulta normalizada (NFC e espaços), os
  filtros resolvidos, o histórico da sessão e a versão de política. Com histórico,
  a resposta só é reaproveitada por uma sessão com o mesmo histórico.
- Só entram no cache turnos concluídos com `finish_reason = "stop"` cujo produto
  consultado está ativo em `products`.
- Antes de servir um *hit*, o gateway lê preço, estoque e status do produto
  consultado e dos cards no PostgreSQL. Produto consultado inativo, com preço
  diferente ou que mudou entre disponível e esgotado, ou card esgotado, inativo ou
  com preço diferente, descarta a entrada e o turno é gerado de novo. Se só a
  quantidade em estoque mudou, o card sai com a quantidade atual.
- Entrada ilegível (outro formato ou corrompida) é apagada e conta como *miss*.
- Falha do Redis ou do PostgreSQL em uma operação do cache conta como *miss*; o chat
  continua pelo backend.

## Limites conhecidos

- `GET /api/v1/sessions/{id}`, citado na issue do `M02`, não foi criado: o
  `openapi.yaml` define a restauração pelo `POST /api/v1/sessions` com `session_id`.
- O histórico e a idempotência ficam no Redis; as tabelas `chat_sessions`,
  `chat_messages` e `chat_turn_requests` das specs ainda não existem.
- Em relação à seção 4 de `specs/architecture/02_database_pgvector_and_redis_schema.md`:
  o HASH `session:{id}:state` não tem `voltage_pref`; `state` é gravado como `IDLE` na
  criação e nunca muda (a máquina de estados da sessão não foi implementada); as
  chaves `session:{id}:lock`, `session:{id}:turn:{client_request_id}` e
  `session:{id}:turns` não constam na spec, que prevê a idempotência em
  `chat_turn_requests`; `ratelimit:ip:{client_ip}` não existe (`M01`).
- Um turno que dura mais que o TTL do lock (60 s) perde o lock: a resposta chega ao
  cliente, mas não entra no histórico nem no registro de idempotência.
- Quando o backend está inacessível, a contingência do gateway não publica cards.
- Os testes unitários não medem RAGAS, latência de rede nem *cache hit ratio*.
  Essas medições pertencem ao `B05` e ao `F05`.
