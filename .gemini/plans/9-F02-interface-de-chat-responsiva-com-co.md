# Implementation Plan — Issue #9: [F02] Interface de Chat Responsiva com Consumo SSE em Tempo Real (EAP 4.9)

## Identificação e Metadados
- **Número da Issue**: #9
- **Código do Pacote EAP**: `F02`
- **Marco (*Milestone*)**: M2
- **Sprint**: sprint:2 (05/10–16/10)
- **Branch de Trabalho**: `feat/F02-interface-de-chat-responsiva-com-co`
- **Base Branch**: `feat/F01-prototipos-figma-e-setup-do-projeto`
- **URL da Issue**: https://github.com/rodrigololr/smartsales_rag/issues/9
- **Governança RACI**:
  - **Aprovador (`A`)**: Eduardo (Front-end)
  - **Executores (`R`)**: Victor Hugo (UX/Front), Eduardo (Front-end)

---

## 1. Objetivo e Escopo
- **Meta do Pacote**: Construir a interface conversacional com consumo de Server-Sent Events (`POST /api/v1/chat/stream`), implementando o hook `useSSEChatStream`, renderização progressiva token a token, auto-scroll, indicador de digitação com *skeleton* pulsante (*"Consultando manuais oficiais e estoque..."*), suporte a `correction` e `error` com fallback seguro, persistência de `client_request_id` UUID v4 e botão de reiniciar conversa (`ResetSessionButton`).
- **Entregáveis da EAP**:
  - [ ] **EAP 4.9 — Construir interface de chat (`UC01`, `UC07`)**: Hook `useSSEChatStream`, componentes `MessageList`, `AssistantMessageBubble`, `ResetSessionButton`, `StoreHeader` isolado e integração no `ContextualChatDrawer`.

---

## 2. Especificações de Referência (`specs/`)
- [`specs/components/03_frontend_chat_and_cards_spec.md`](file:///c:/Users/Victo/Desktop/Ufal/smartsales_rag/specs/components/03_frontend_chat_and_cards_spec.md)
- [`specs/architecture/03_openapi_and_sse_contracts.md`](file:///c:/Users/Victo/Desktop/Ufal/smartsales_rag/specs/architecture/03_openapi_and_sse_contracts.md)
- [`specs/tdd_and_quality/02_test_cases_unit_int_e2e.md`](file:///c:/Users/Victo/Desktop/Ufal/smartsales_rag/specs/tdd_and_quality/02_test_cases_unit_int_e2e.md)

---

## 3. Testes Automatizados Obrigatórios (TDD)
- **Casos TDD Obrigatórios**: `UT-F02-01`, `UT-F02-02`
- **Requisitos Atendidos**: `RF10`, `RNF01`, `RNF08`
- **Cenários**:
  - `UT-F02-01`: Atualização token a token via SSE, desativação do botão de envio durante streaming e reativação no evento `done`.
  - `UT-F02-02`: Substituição atômica pelo evento `correction` (`STREAM_INTERRUPTED`) com `wasCorrected == true`.
  - Validação de descarte em caso de `error` e persistência de `client_request_id`.

---

## 4. Lista de Tarefas Atômicas (1 Commit por Task)

- [x] **Task 1: Hook useSSEChatStream e Parser de Eventos SSE**
  - **Arquivos**: `frontend/src/hooks/useSSEChatStream.ts`, `frontend/src/utils/sseParser.ts`
  - **Commit**: `feat(F02): implement useSSEChatStream hook with resilient SSE parser`

- [x] **Task 2: Testes TDD Red (UT-F02-01 e UT-F02-02)**
  - **Arquivos**: `frontend/tests/unit/useSSEChatStream.test.tsx`
  - **Commit**: `test(F02): add unit tests UT-F02-01 and UT-F02-02 for SSE stream hook`

- [ ] **Task 3: Componentes de Chat (MessageList, AssistantMessageBubble, ResetSessionButton, StoreHeader)**
  - **Arquivos**: `frontend/src/components/chat/MessageList.tsx`, `frontend/src/components/chat/AssistantMessageBubble.tsx`, `frontend/src/components/chat/ResetSessionButton.tsx`, `frontend/src/components/layout/StoreHeader.tsx`
  - **Commit**: `feat(F02): implement MessageList, AssistantMessageBubble and ResetSessionButton`

- [ ] **Task 4: Integração do Streaming no ContextualChatDrawer e Vitrine**
  - **Arquivos**: `frontend/src/components/chat/ContextualChatDrawer.tsx`, `frontend/src/app/page.tsx`, `frontend/tests/unit/ContextualChatDrawer.test.tsx`
  - **Commit**: `feat(F02): integrate SSE chat streaming and skeleton in ContextualChatDrawer`

- [ ] **Task 5: Refactor, Linters e Gates de Qualidade**
  - **Arquivos**: Módulos alterados, `frontend/README.md`
  - **Commit**: `refactor(F02): refine streaming error handling and validate quality gates`

---

## 5. Critérios de Aceite e Comandos de Validação
```bash
npm --prefix frontend run test:unit
npm --prefix frontend run lint
uv run --with-requirements tests/requirements-specs.txt python -m unittest discover -s tests -v
```
