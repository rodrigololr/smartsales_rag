# Plano de Implementação — Pacote P2: Consultor Unificado (Backend Consultant)

## 1. Identificação
- **Pacote**: `P2` (Backend Consultant — Critical Path)
- **Branch**: `feat/consultor-p2`
- **Worktree**: `/home/antonio/Documentos/gerencia_projeto/smartsales_p2`
- **Spec de Referência**: `specs/components/04_consultor_unificado_spec.md` (§1–§5, §9, §11 Adendo Congelado)
- **Interfaces Congeladas**: `I1` (ConsultantRequest / ChatTurn.recommended_skus), `I2` (OPTION card role & KB citations), `I4` (dados e knowledge_facts), `I5` (ConsultantCatalog protocol com `knowledge_doc(doc_id)`)

## 2. Objetivo e Escopo
Implementar o orquestrador consultivo unificado (`ConsultantOrchestrator`) que envolve o `RAGOrchestrator` legado sem alterá-lo, adicionando:
- Modelo de conversação multi-turno com extração de estado (`shown_skus`, `mentioned_skus`) e slots com fusão reversa interrompida em mudança de categoria;
- Roteador determinístico puro (`Route`: `BLOCKED`, `GREETING`, `DIMENSION_FIT`, `STREAM_FIT`, `GAME_FIT`, `SET_VOLTAGE`, `PRICE_RANK`, `OPINION_BRAND`, `COMPARE`, `DISCOVERY`, `TECHNICAL`, `KB_QA`) com guarda de categorias legadas (`D3`);
- Extratores determinísticos de evidência (`parse_game_rows`, `kb_measure`, `kb_sentence` fail-closed, `webcam_capability`) e constantes literais da base curada (`knowledge_facts.py`);
- Builders determinísticos puros com templates em português do Brasil e cards `OPTION` ancorados exclusivamente no SQL (`R01`, `R03`, `R09`);
- Extensões opt-in no G-OUT (`SentenceVerifier(None, ...)`, `ConsultativeVerifier` com `allow_general_information` e `user_message`, `general_information()`, `length_measures_cm()`, `CATALOG_MISSING_NOTICE`);
- Repositório `PostgresConsultantCatalog` (`products`, `search`, `categories_in_stock`, `game_tables`, `knowledge_doc`, `knowledge_page`, `search_knowledge`);
- Suíte completa de testes unitários, diálogo multi-turno com fakes (`tests/conversational/dialogs.json`), integração com pgvector e suíte live (`tests/live/test_consultor_dialogs.py`).

Fora de escopo: alterações em `middleend/` (P3), `frontend/` (P4) ou no corpus homologado do RAGAS (`data/catalog.json`, `golden_set.json`, `RAGOrchestrator`).

## 3. Arquivos Afetados
- `backend/app/models/schemas.py`
- `backend/app/config.py`
- `backend/app/recommendation/models.py`
- `backend/app/recommendation/cards.py`
- `backend/app/recommendation/intent.py`
- `backend/app/guardrails/output.py`
- `backend/app/guardrails/publication.py`
- `backend/app/generation/prompt.py`
- `backend/app/consultant/__init__.py`
- `backend/app/consultant/knowledge_facts.py`
- `backend/app/consultant/slots.py`
- `backend/app/consultant/conversation.py`
- `backend/app/consultant/router.py`
- `backend/app/consultant/evidence.py`
- `backend/app/consultant/builders.py`
- `backend/app/consultant/service.py`
- `backend/app/db/consultant_repository.py`
- `backend/app/main.py`
- `backend/tests/unit/test_consultant_slots.py`
- `backend/tests/unit/test_consultant_router.py`
- `backend/tests/unit/test_consultant_evidence.py`
- `backend/tests/unit/test_consultant_builders.py`
- `backend/tests/unit/test_publication_consultant.py`
- `backend/tests/unit/test_consultant_orchestrator.py`
- `backend/tests/integration/test_consultant_repository.py`
- `tests/conversational/dialogs.json`
- `tests/live/test_consultor_dialogs.py`

## 4. Tarefas Atômicas e Commits (TDD Red -> Green)
- [x] **Task 1 (Red — Slots, Conversação e Medidas)**: Criar `backend/tests/unit/test_consultant_slots.py` cobrindo `UT-CU-01..06` (`CATEGORY_KEYWORDS`, orçamento, voltagem, jogos, `length_measures_cm`, `merge_slots` e `conversation_state`).
  - Commit: `test(P2): add failing unit tests for consultant slots and conversation state`
- [x] **Task 2 (Green — Schemas, Helpers, Slots e Conversação)**: Atualizar `schemas.py`, `config.py`, `recommendation/{models,cards,intent}.py`, `guardrails/output.py` (`length_measures_cm`) e criar `consultant/{__init__,knowledge_facts,slots,conversation}.py`.
  - Commit: `feat(P2): implement consultant schemas, slots parser and conversation state`
- [x] **Task 3 (Red — Router e Comparison Set)**: Criar `backend/tests/unit/test_consultant_router.py` cobrindo `UT-CU-07/08` (tabela de rotas, legacy guard GS-13/14/41/44, `comparison_set`).
  - Commit: `test(P2): add failing unit tests for consultant router and legacy guard`
- [x] **Task 4 (Green — Router e Comparison Set)**: Implementar `backend/app/consultant/router.py`.
  - Commit: `feat(P2): implement pure intent router with legacy category guard`
- [x] **Task 5 (Red — Evidence e Builders)**: Criar `backend/tests/unit/test_consultant_evidence.py` (`UT-CU-17`) e `backend/tests/unit/test_consultant_builders.py` (`UT-CU-09..16`).
  - Commit: `test(P2): add failing unit tests for evidence parsers and deterministic builders`
- [x] **Task 6 (Green — Evidence e Builders)**: Implementar `backend/app/consultant/evidence.py` e `backend/app/consultant/builders.py`.
  - Commit: `feat(P2): implement lexical evidence parsers and deterministic answer builders`
- [x] **Task 7 (Red — G-OUT Opt-in e Catalog Prompt)**: Criar `backend/tests/unit/test_publication_consultant.py` (`UT-CU-18`).
  - Commit: `test(P2): add failing unit tests for opt-in consultative publication guardrails`
- [x] **Task 8 (Green — G-OUT Opt-in e Catalog Prompt)**: Atualizar `backend/app/guardrails/publication.py` e `backend/app/generation/prompt.py`.
  - Commit: `feat(P2): add opt-in general information, user length echo and catalog prompt`
- [x] **Task 9 (Red — Orchestrator, Dialogs e Live Suite)**: Criar `tests/conversational/dialogs.json`, `backend/tests/unit/test_consultant_orchestrator.py` e `tests/live/test_consultor_dialogs.py`.
  - Commit: `test(P2): add failing conversational dialog and consultant orchestrator tests`
- [x] **Task 10 (Green — Repositório, ConsultantOrchestrator e Main Wiring)**: Implementar `backend/app/db/consultant_repository.py`, `backend/app/consultant/service.py` e conectar `backend/app/main.py`.
  - Commit: `feat(P2): implement consultant repository, orchestrator service and fastapi wiring`
- [x] **Task 11 (Red/Green — Integração PostgreSQL/pgvector)**: Criar e validar `backend/tests/integration/test_consultant_repository.py` contra container pgvector na porta `5562`.
  - Commit: `test(P2): add pgvector integration tests for consultant repository`

## 5. Comandos de Validação
- `cd backend && /home/antonio/Documentos/gerencia_projeto/smartsales_rag/.venv/bin/python -m pytest tests/unit -q`
- `cd backend && /home/antonio/Documentos/gerencia_projeto/smartsales_rag/.venv/bin/python -m pytest tests/ragas_eval -q`
- `cd backend && TEST_DATABASE_URL=postgresql://smartsales:smartsales@127.0.0.1:5562/smartsales /home/antonio/Documentos/gerencia_projeto/smartsales_rag/.venv/bin/python -m pytest tests/integration/test_consultant_repository.py -q`
- `cd backend && /home/antonio/Documentos/gerencia_projeto/smartsales_rag/.venv/bin/python -m ruff check app tests`
- `cd backend && /home/antonio/Documentos/gerencia_projeto/smartsales_rag/.venv/bin/python -m mypy app`
