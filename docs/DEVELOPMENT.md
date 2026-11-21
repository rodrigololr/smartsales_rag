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
| middleend | `BACKEND_TIMEOUT_SECONDS`, `BACKEND_FIRST_EVENT_TIMEOUT_SECONDS` | `30.0`, `3.0` | Timeout de leitura do stream do backend e prazo máximo até o primeiro evento (com 1 nova tentativa automática antes de publicar tokens). |
| middleend | `REDIS_URL` | não definida | Com ela (e `DATABASE_URL`), sessões têm projeção/lease no Redis e cache semântico ativo. Sem ela, as sessões ficam na memória do processo e o cache fica desligado. |
| middleend | `REDIS_SOCKET_TIMEOUT_SECONDS`, `REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS` | `2.0`, `2.0` | Limite de cada chamada e da conexão ao Redis. |
| middleend | `DATABASE_URL` | não definida | Persistência durável de sessões/turnos (`chat_sessions`, `chat_messages`, `chat_turn_requests`, requer `REDIS_URL`) e leitura de `products` para revalidar o cache e o *replay*. |
| middleend | `DATABASE_CONNECT_TIMEOUT_SECONDS` | `2` | Limite para conectar ao PostgreSQL na revalidação do cache (inteiro, mínimo 2). |
| middleend | `SESSION_DB_CONNECT_TIMEOUT_SECONDS`, `SESSION_DB_QUERY_TIMEOUT_MS` | `2`, `2000` | Limite de conexão e `statement_timeout` (ms) do repositório SQL de sessões. |
| middleend | `CHECKOUT_DECREMENT_STOCK` | `true` | O *mock checkout* confirmado desconta `products.stock_quantity`. Com `false`, só registra a conversão em `checkout_events`. |
| middleend | `ADMIN_TOKEN` | não definida | Valor exigido no cabeçalho `X-Admin-Token` de `GET /api/v1/metrics/summary`. Sem ele (ou vazio), a rota responde sempre `401`. |
| middleend | `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Origens aceitas, separadas por vírgula. |
| middleend | `SESSION_TTL_SECONDS`, `SESSION_HISTORY_MAX_MESSAGES`, `SESSION_LOCK_TTL_SECONDS` | `1800`, `10`, `60` | TTL da sessão, janela do histórico (número par, mínimo 2) e validade do lease/lock de turno. |
| middleend | `SESSION_HEARTBEAT_SECONDS`, `SESSION_MAINTENANCE_SECONDS`, `TURN_RETRY_AFTER_SECONDS` | `10.0`, `60.0`, `1` | Intervalo de renovação do lease durante o stream, intervalo de limpeza SQL de sessões/turnos expirados e cabeçalho `Retry-After` em `409 TURN_IN_PROGRESS`. |
| middleend | `RATE_LIMIT_PER_MINUTE` | `30` | Limite de requisições por minuto, em janela fixa de 60 s (`429 RATE_LIMITED` com cabeçalho `Retry-After`): por sessão em `POST /chat/stream` (`ratelimit:session:{session_id}`, com um teto grosso de 10× por IP em `ratelimit:ip-chat:{client_ip}` que barra `session_id` inventados antes da consulta ao banco) e por IP nas demais rotas (`ratelimit:ip:{client_ip}`). Se o Redis cair, o limitador deixa as requisições passarem (*fail-open*, decisão de disponibilidade coberta por teste). |
| middleend | `RATE_LIMIT_TRUSTED_PROXY_HOPS` | `0` | Quantos proxies reversos confiáveis ficam na frente do gateway. Com `0`, o `X-Forwarded-For` é ignorado e o IP é o da conexão; com `N`, usa o endereço anexado pelo proxy mais externo (o cliente não consegue forjar o próprio IP). |
| middleend | `CACHE_TTL_SECONDS`, `CACHE_POLICY_VERSION` | `3600`, `p1` | TTL das respostas em cache; mude a versão ao alterar prompts, guardrails, ranking ou modelo. |

## Arquitetura implementada

### Backend (`backend/app/`)

| Módulo | Pacote | O que faz |
| --- | --- | --- |
| `ingestion/` | `B01`, `B03` | CLI `python -m app.ingestion.run`: adquire *advisory lock* de sessão no PostgreSQL (rejeitando execuções concorrentes com código 1), valida o catálogo, faz *upsert* em `products`, substitui `product_relations` sob lock de tabela quando `--relations` é informado (sem a flag a tabela não é tocada; arquivo inexistente é erro), e indexa a ficha técnica e o manual de cada produto em chunks de 500 tokens (sobreposição de 50) a partir de um *snapshot* único de bytes e de um *fingerprint* de configuração (contexto, título, modelo/provedor, dimensão e chunking). Cada fonte roda sob `ingestion_jobs` (`RUNNING` → `INDEXED`), com até 3 tentativas e *backoff* apenas para falhas transitórias (`LLMUnavailableError`, `psycopg.OperationalError`); esgotadas, ou em erro permanente (PDF corrompido/vazio, erro de leitura, `IntegrityError`), fica `NEEDS_INTERVENTION`, preserva a versão anterior sob `lock_product`, segue para a próxima fonte e a CLI termina com código 1. Troca de extensão aposenta a fonte antiga do SKU. O `INCR catalog:version` roda ao final em `finally`; se o Redis falhar, o relatório traz `catalog_version_error` e a CLI termina com código 1. |
| `db/` | `B01`, `B03`, `B04` | `schema.sql` (idempotente) com `products`, `manual_chunks` (HNSW), `product_relations` e `ingestion_jobs`; `repository.py` com as consultas e snapshot `REPEATABLE READ READ ONLY` para recomendações. |
| `clients/` | `B02`, `B03` | Cliente compatível com a API da OpenAI e `RedisCatalogVersion` (`INCR catalog:version`). |
| `rag/orchestrator.py` | `B02`, `B03`, `B04` | Turno de um produto: G-IN, busca dos 5 chunks do SKU, limiar, seleção SQL pré-prompt de recomendações, geração com G-OUT por sentença (`SentenceVerifier` / `ConsultativeVerifier`), releitura SQL dos cards e citações. |
| `guardrails/` | `B03`, `B04` | Bloqueio de *prompt injection* (`input.py`) e verificação por sentença (`output.py`, `publication.py`): valida preço, voltagem, potência e capacidade contra o SQL do SKU (com normalização de `mL`/`L` e `kW`/`W`), exige trecho literal verificado e página real para fatos de manual, permite fatos SQL de alternativas em `<RECOMENDACOES_SQL>` quando prefixadas por `SKU <codigo>:`, e só emite o aviso *"não consta no manual"* quando a sentença bloqueada contém afirmação técnica (descartando saudações/paráfrases sem número silenciosamente). |
| `recommendation/` | `B04` | `engine.py` (regras `RN01`, `RN04`, `RN05` em `Decimal`), `service.py` (snapshot SQL `REPEATABLE READ` → filtros de compra → motor → cards), `cards.py` (textos montados só com valores do SQL) e `intent.py` (intenção de upgrade com tratamento de negação e restrição `only_consulted_product`). |

Contrato interno: o middle-end chama `POST /internal/rag/stream` com
`{sku, question, history, preferred_voltage?, budget_max?, capacity_min?, category?}`
e recebe NDJSON com `token` (só sentenças aprovadas pelo G-OUT), `citations`,
`recommendations`, `error` e `end`.

Quando o evento `recommendations` é emitido:

| Situação do turno | Cards |
| --- | --- |
| Resposta com evidência | Produto consultado (se em estoque e compatível com os filtros de compra) e cross-sell. O upsell entra se a pergunta indica necessidade maior ou comparação (sem negação de upgrade), ou se o produto consultado está esgotado, tem voltagem incompatível ou capacidade abaixo de `capacity_min`. Se o usuário pedir explicitamente apenas o produto consultado (`only_consulted_product`), `UPSELL` e `CROSS_SELL` são suprimidos. |
| `LOW_SIMILARITY_FALLBACK` ou `LLM_UNAVAILABLE` | Produto consultado, upsell e cross-sell, como alternativas em estoque (respeitando `only_consulted_product` e os filtros de compra). |
| `GUARDRAIL_BLOCKED` ou produto fora do catálogo ativo | Nenhum. |

As opções elegíveis são lidas em snapshot `REPEATABLE READ READ ONLY` antes do prompt
(entrando em `<RECOMENDACOES_SQL>` para comparação consultiva verificada por SKU) e
relidas novamente antes de emitir o evento `recommendations`. Se qualquer etapa das
recomendações falhar, o turno segue sem cards.

### Gateway (`middleend/app/`)

| Módulo | Pacote | O que faz |
| --- | --- | --- |
| `routes/chat.py` | `M01`, `M02`, `M03` | `POST /api/v1/sessions` (201 para sessão nova, 200 com o histórico quando o `session_id` enviado ainda está ativo), `DELETE /api/v1/sessions/{id}`, `POST /api/v1/chat/stream` e `GET /api/v1/health` (`backend`, `redis`, `postgres`). Indisponibilidade de Redis ou PostgreSQL responde 503 `SERVICE_UNAVAILABLE` no envelope de erro, e falhas de validação Pydantic respondem 422 `VALIDATION_ERROR` no mesmo envelope. |
| `ratelimit/` | `M01` | `RedisRateLimiter` (contador atômico Lua em `ratelimit:ip:{client_ip}` ou, no chat, `ratelimit:session:{session_id}`, TTL de 60 s, 30 req/min por padrão) e `InMemoryRateLimiter` (quando `REDIS_URL` não está definida), retornando `429 RATE_LIMITED` com cabeçalho `Retry-After`. |
| `sessions/` e `db/` | `M02` | `PostgresSessionStore` (autoridade durável em `chat_sessions`, `chat_messages` e `chat_turn_requests`, migradas sob *advisory lock* em `middleend/app/db/schema.sql`), `SessionCache` (projeção e máquina de estados no Redis), `LeaseStream` (renovação de lease por *heartbeat* a cada 10 s e bloqueio de entrega caso a posse seja perdida), `replay.py` (revalidação SQL dos cards antes de entregar um *replay* idempotente) e `SessionStreamingResponse`, além dos adaptadores auxiliares `RedisSessionStore` e `InMemorySessionStore`. |
| `cache/` | `M03` | `build_cache_key` (identidade canônica), `SemanticCacheService` e `RedisCacheStorage`. |
| `routes/commerce.py`, `repositories/commerce.py` | `M04`, `M05` | `GET /api/v1/products` (busca, filtros e paginação só com itens ativos em estoque), `GET /api/v1/products/{sku}`, `POST /api/v1/feedback` (um like/dislike por mensagem do assistente) e `POST /api/v1/checkout/mock` (`SELECT ... FOR UPDATE` em `products`, `409` para `OUT_OF_STOCK`/`PRICE_CHANGED`, `INCR catalog:version` quando o preço muda ou o estoque zera). Feedback e checkout usam o `session_id` e o `message_id` do evento SSE `metadata`; sessão encerrada responde `410`. Tabelas `feedback_logs` e `checkout_events` em `repositories/commerce.sql`, criadas após o schema de sessões (exige `products` já criada pelo backend). |
| `routes/commerce.py` (`metrics_summary`), `metrics.py`, `telemetry/http_errors.py` | `M04` | `GET /api/v1/metrics/summary` (`UC09`), protegido por `X-Admin-Token`. Janela `[from, to)`; padrão: últimos 7 dias até agora. Definições: `turns` = respostas do assistente em `chat_messages` (inclui turnos com falha); `ttft_p50_ms`, `ttft_p95_ms` e `total_latency_p95_ms` = `percentile_cont` sobre essas respostas; `cache_hit_ratio` = fração com `cache_hit`; `like_ratio` = likes / (likes + dislikes) em `feedback_logs`; `card_ctr` = respostas com cards que receberam ao menos um clique no *mock checkout* (qualquer status) / respostas com cards; `confirmed_checkouts` = `checkout_events` com `CONFIRMED`; `top_questions` = 5 perguntas do usuário mais frequentes (minúsculas, sem espaços nas pontas); `error_5xx_rate` = respostas HTTP `>= 500` / todas as respostas do gateway, contadas por um *middleware* em buckets horários no Redis (granularidade de 1 h, retenção de 31 dias; sem Redis vale 0). Sem dados, tudo é 0. |
| `repositories/products.py` | `M03` | Leitura de preço, estoque e status em `products` (ADR-06). |
| `sse/` | `M02` | `sse_chat_generator`: protocolo público, transições de estado, ordem dos eventos, falhas e liberação do turno. |
| `clients/backend.py` | `M02`, `B04` | Adaptador NDJSON do backend (encaminhando filtros de compra, com timeout de 3 s até o primeiro evento e 1 retry antes de publicar tokens) e `ReplayStream` para turnos concluídos ou vindos do cache. |

Chaves no Redis:

| Chave | Tipo | TTL | Conteúdo |
| --- | --- | --- | --- |
| `session:{id}:state` | HASH | 1800 s | `state` (`IDLE`, `VALIDATING_CACHE`, `STREAMING_TOKENS`, `EMITTING_CARDS_AND_CITATIONS`, `ERROR_CONTINGENCY`), `active_sku`, `updated_at`. |
| `session:{id}:history` | LIST | 1800 s | Últimas 10 mensagens (`LPUSH` + `LTRIM 0 9`). |
| `session:{id}:lock` | STRING | 60 s | Token `uuid4` do dono do turno em andamento (`SET NX EX`), renovado a cada 10 s por *heartbeat*. Só o dono transita estado, libera o lock ou conclui o turno. |
| `session:{id}:turn:{client_request_id}` | STRING | 1800 s | Registro de idempotência usado apenas no modo auxiliar Redis-only (sem `DATABASE_URL`); em produção a autoridade é `chat_turn_requests` no PostgreSQL (retenção de 24 h; `410 TURN_EXPIRED` após expirar). |
| `session:{id}:turns` | SET | 1800 s | Ids dos turnos no modo auxiliar Redis-only, para o `DELETE` remover tudo. |
| `cache:sem:v{versão}:{sha256}` | STRING | 3600 s | Texto, citações e cards de um turno respondido, mais `consulted` (SKU, preço e disponibilidade do produto consultado). |
| `catalog:version` | STRING | sem expiração | Contador incrementado pela ingestão. |
| `metrics:http:{AAAAMMDDHH}` | HASH | 31 dias | `total` e `5xx`: respostas HTTP do gateway naquela hora UTC (fonte de `error_5xx_rate`, `M04`). |
| `ratelimit:ip:{client_ip}` | STRING | 60 s | Contador de requisições por minuto por IP (`INCR` + `EXPIRE 60`, limite padrão de 30 req/min). |

Regras do cache:

- A chave inclui a versão do catálogo, a consulta normalizada (NFC e espaços), os
  filtros resolvidos, o histórico da sessão (obtido sob a reserva do turno) e a versão
  de política. Com histórico, a resposta só é reaproveitada por uma sessão com o mesmo
  histórico.
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
- Em relação à seção 4 de `specs/architecture/02_database_pgvector_and_redis_schema.md`:
  o HASH `session:{id}:state` não persiste `voltage_pref` separado (a preferência de
  voltagem vem em `context_filters` por turno).
- `error_5xx_rate` não registra respostas enquanto o próprio Redis está fora, e um turno
  SSE que falha depois do `200` termina em `done: error`, não em `5xx`.
- Quando o backend está inacessível, a contingência do gateway não publica cards.
- Os testes unitários não medem RAGAS com provedor externo, latência de rede real nem
  *cache hit ratio* de produção. Essas medições pertencem à homologação viva do `B05` e
  ao `F05`.
