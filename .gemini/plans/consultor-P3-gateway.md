# Implementation Plan — Consultor Unificado P3: Gateway / Middle-end

## Identificação e Metadados
- **Pacote**: `P3` (Gateway / Middle-end — `M01`–`M05`)
- **Branch de Trabalho**: `feat/consultor-p3`
- **Especificação de Referência**: [`specs/components/04_consultor_unificado_spec.md`](../../specs/components/04_consultor_unificado_spec.md) (§1, §6, §9, §10, §11)

---

## 1. Objetivo e Escopo
- Permitir turnos em **modo catálogo** (`sku = None`) em `POST /api/v1/chat/stream` sem retornar `422 PRODUCT_CONTEXT_REQUIRED` e sem consultar/gravar cache semântico quando `sku is None`.
- Estender `HistoryItem` com `recommended_skus: tuple[str, ...] = ()` nas 3 implementações de sessão (`InMemorySessionStore`, `RedisSessionStore`, `PostgresSessionStore`), preservando leitura de entradas legadas no Redis sem a chave `"skus"`, e repassar `recommended_skus` (quando não vazio) e `"sku": null` em `BackendClient.open_stream`.
- Adicionar o papel `OPTION` em `ProductCard`, `RecommendationType`, validação SSE (`MAX_CARDS = 5`, `MAX_OPTIONS = 4`, unicidade apenas para `PRIMARY`, `UPSELL`, `CROSS_SELL`), migração DDL idempotente de `checkout_events` e contratos `openapi.yaml` / `specs/architecture/03_openapi_and_sse_contracts.md`.

---

## 2. Arquivos Afetados
- `middleend/app/sessions/store.py`
- `middleend/app/sessions/redis_store.py`
- `middleend/app/sessions/postgres_store.py`
- `middleend/app/clients/backend.py`
- `middleend/app/routes/chat.py`
- `middleend/app/schemas.py`
- `middleend/app/sse/models.py`
- `middleend/app/sse/validation.py`
- `middleend/app/commerce.py`
- `middleend/app/repositories/commerce.sql`
- `openapi.yaml`
- `specs/architecture/03_openapi_and_sse_contracts.md`
- `middleend/tests/unit/test_session_store.py`
- `middleend/tests/unit/test_persistent_sessions.py`
- `middleend/tests/unit/test_chat_routes.py`
- `middleend/tests/unit/test_chat_cache.py`
- `middleend/tests/unit/test_sse_stream.py`
- `middleend/tests/unit/test_rate_limit_and_openapi.py`
- `middleend/tests/integration/test_commerce_contract.py`

---

## 3. Lista de Tarefas Atômicas (1 Commit por Task)

- [x] **Task 1: Testes TDD Red para modo catálogo, `recommended_skus` no histórico, validação SSE `OPTION` e checkout `OPTION`**
  - **Arquivos**: `middleend/tests/unit/test_session_store.py`, `middleend/tests/unit/test_persistent_sessions.py`, `middleend/tests/unit/test_chat_routes.py`, `middleend/tests/unit/test_chat_cache.py`, `middleend/tests/unit/test_sse_stream.py`, `middleend/tests/unit/test_rate_limit_and_openapi.py`, `middleend/tests/integration/test_commerce_contract.py`, `.gemini/plans/consultor-P3-gateway.md`
  - **Commit**: `test(P3): add gateway tests for catalog mode, recommended_skus and OPTION cards`

- [x] **Task 2: Histórico com `recommended_skus`, encaminhamento para o backend e modo catálogo sem cache semântico**
  - **Arquivos**: `middleend/app/sessions/store.py`, `middleend/app/sessions/redis_store.py`, `middleend/app/sessions/postgres_store.py`, `middleend/app/clients/backend.py`, `middleend/app/routes/chat.py`, `middleend/app/schemas.py`
  - **Commit**: `feat(P3): support catalog mode and forward recommended_skus in session history`

- [x] **Task 3: Papel `OPTION` nos cards SSE, migração DDL do checkout e contratos OpenAPI/SSE**
  - **Arquivos**: `middleend/app/sse/models.py`, `middleend/app/sse/validation.py`, `middleend/app/commerce.py`, `middleend/app/repositories/commerce.sql`, `openapi.yaml`, `specs/architecture/03_openapi_and_sse_contracts.md`, `.gemini/plans/consultor-P3-gateway.md`
  - **Commit**: `feat(P3): add OPTION card role to SSE validation, checkout DDL and OpenAPI`

---

## 4. Critérios de Aceite e Comandos de Validação
```bash
cd middleend && /home/antonio/Documentos/gerencia_projeto/smartsales_rag/.venv/bin/python -m pytest tests -q --cov=app --cov-fail-under=70
cd middleend && /home/antonio/Documentos/gerencia_projeto/smartsales_rag/.venv/bin/python -m ruff check app tests
cd middleend && /home/antonio/Documentos/gerencia_projeto/smartsales_rag/.venv/bin/python -m mypy app
```
