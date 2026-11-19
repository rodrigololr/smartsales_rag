# Implementation Plan — Issue #5: [M01] Gateway FastAPI, Contratos OpenAPI 3.1 e Segurança Base (EAP 3.1, 3.2, 3.3, 4.5)

## Identificação e Metadados
- **Número da Issue**: #5
- **Código do Pacote EAP**: `M01`
- **Marco (*Milestone*)**: M1
- **Sprint**: sprint:1 (22/09–02/10)
- **Branch de Trabalho**: `feat/M01-gateway-rate-limiting-openapi`
- **URL da Issue**: https://github.com/rodrigololr/smartsales_rag/issues/5
- **Governança RACI**:
  - **Aprovador (`A`)**: **Pablo (Mid / API)**
  - **Executores (`R`)**: Well (Mid / SSE), Pablo (Mid / API)

---

## 1. Objetivo e Escopo
- **Meta do Pacote**: Implementar as entregas vinculadas à issue #5 respeitando o SDD e TDD.
- **Entregáveis da EAP**:
- [x] **EAP 3.3 — Especificar contratos de API (OpenAPI 3.1)**: Publicação e validação do `openapi.yaml` para `/sessions`, `/chat/stream`, `/products`, `/feedback`, `/checkout/mock`, `/metrics/summary`, `/health` e `/internal/rag/stream` (`A`: Pablo | `R`: Well).
- [ ] **EAP 4.5 (Parte 1) — Setup do API Gateway FastAPI (`UC07`)**: Estrutura do serviço `middleend/`, middlewares de CORS, Rate Limiting (`20 req/min` por IP/sessão), validação Pydantic v2 e rota `/api/v1/health` (`A`: Pablo | `R`: Well).

---

## 2. Especificações de Referência (`specs/`)
- [`specs/architecture/03_openapi_and_sse_contracts.md`](file:////home/antonio/Documentos/gerencia_projeto/smartsales_rag/specs/architecture/03_openapi_and_sse_contracts.md)
- [`specs/components/02_middleend_gateway_sse_redis_spec.md`](file:////home/antonio/Documentos/gerencia_projeto/smartsales_rag/specs/components/02_middleend_gateway_sse_redis_spec.md)

---

## 3. Testes Automatizados Obrigatórios (TDD)
- **Casos de Teste Mapeados**: `UT-M01-01`
- **Meta de Cobertura**: >= 70% com zero defeitos críticos.

---

## 4. Lista de Tarefas Atômicas (1 Commit por Task)

> [!IMPORTANT]
> Cada tarefa abaixo deve ser executada individualmente, testada e comitada separadamente.

- [x] **Task 1: Setup e Definição de Tipos/Contratos de Rate Limiting**
  - **Arquivos**: `middleend/app/config.py`, `middleend/.env.example`, `middleend/app/ratelimit/__init__.py`, `middleend/app/ratelimit/limiter.py`
  - **Mensagem do Commit**: `feat(M01): add rate limit settings and RateLimiter protocol`

- [x] **Task 2: Testes TDD Red (`UT-M01-01` e `CT-M01-01`)**
  - **Arquivos**: `middleend/tests/unit/test_rate_limit_and_openapi.py`
  - **Mensagem do Commit**: `test(M01): add UT-M01-01 rate limit and CT-M01-01 OpenAPI contract tests`

- [x] **Task 3: Implementação TDD Green (RateLimitMiddleware, Redis/InMemory RateLimiter e Validação 422 no Envelope)**
  - **Arquivos**: `middleend/app/ratelimit/limiter.py`, `middleend/app/main.py`
  - **Mensagem do Commit**: `feat(M01): enforce 30 req/min rate limiting and standard 422 error envelope`

- [ ] **Task 4: Documentação Técnica e Cobertura (Gate)**
  - **Arquivos**: `docs/DEVELOPMENT.md`, `README.md`, `.gemini/plans/5-M01-gateway-rate-limiting-openapi.md`
  - **Mensagem do Commit**: `docs(M01): document rate limiting settings and ratelimit:ip Redis key`

---

## 5. Critérios de Aceite e Comandos de Validação
```bash
# Executar suíte de validação antes de abrir PR:
# Backend/Specs:
uv run --with-requirements tests/requirements-specs.txt python -m unittest discover -s tests -v

# Frontend (quando aplicável):
pnpm -C frontend run test:unit
```
