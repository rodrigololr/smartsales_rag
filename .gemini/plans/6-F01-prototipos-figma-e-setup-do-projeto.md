# Implementation Plan — Issue #6: [F01] Protótipos Figma e Setup do Projeto Next.js / TailwindCSS (EAP 3.1, 3.4, 3.5)

## Identificação e Metadados
- **Número da Issue**: #6
- **Código do Pacote EAP**: `F01`
- **Marco (*Milestone*)**: M1
- **Sprint**: sprint:1 (22/09–02/10)
- **Branch de Trabalho**: `feat/F01-prototipos-figma-e-setup-do-projeto`
- **URL da Issue**: https://github.com/rodrigololr/smartsales_rag/issues/6
- **Governança RACI**:
  - **Aprovador (`A`)**: Victor Hugo (UX/UI / QA)
  - **Executores (`R`)**: Eduardo (Front-end), Victor Hugo (UX/UI)

---

## 1. Objetivo e Escopo
- **Meta do Pacote**: Entregar o setup inicial da camada `frontend/` com Next.js 14+ (App Router), TypeScript (`strict: true`), Tailwind CSS, tipagem alinhada ao `openapi.yaml`, configuração de testes unitários com Vitest + React Testing Library e o primeiro componente funcional testado (`SmartSalesPage` com `ContextualChatDrawer` atendendo ao teste `UT-F01-01`).
- **Entregáveis da EAP**:
  - [ ] **EAP 3.4 — Prototipar interfaces no Figma**: Documentar a especificação dos protótipos de alta fidelidade e arquitetura de componentes do Figma no frontend.
  - [ ] **EAP 3.5 (Front) — Setup Next.js 14+ (App Router) + TypeScript strict + TailwindCSS**: Configuração de package.json, tsconfig.json, Tailwind, Vitest, tipagem estrita de chat/catálogo e implementação base.

---

## 2. Especificações de Referência (`specs/`)
- [`specs/components/03_frontend_chat_and_cards_spec.md`](file:///c:/Users/Victo/Desktop/Ufal/smartsales_rag/specs/components/03_frontend_chat_and_cards_spec.md)
- [`specs/architecture/03_openapi_and_sse_contracts.md`](file:///c:/Users/Victo/Desktop/Ufal/smartsales_rag/specs/architecture/03_openapi_and_sse_contracts.md)
- [`specs/tdd_and_quality/02_test_cases_unit_int_e2e.md`](file:///c:/Users/Victo/Desktop/Ufal/smartsales_rag/specs/tdd_and_quality/02_test_cases_unit_int_e2e.md)

---

## 3. Testes Automatizados Obrigatórios (TDD)
- **Caso TDD Obrigatório**: `UT-F01-01`
- **Requisitos Atendidos**: `RF10`, `RNF08`, `RNF10`
- **Cenário**: Renderização de `<SmartSalesPage />`, seleção de produto na vitrine e abertura contextual do `<ContextualChatDrawer />` com `current_product_sku`.

---

## 4. Lista de Tarefas Atômicas (1 Commit por Task)

- [x] **Task 1: Setup Next.js 14+, Tailwind CSS e TypeScript Strict**
  - **Arquivos**: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/tailwind.config.ts`, `frontend/postcss.config.js`, `frontend/next.config.js`
  - **Commit**: `feat(F01): setup Next.js 14 project with TailwindCSS and TypeScript strict`

- [x] **Task 2: Tipagem OpenAPI e Setup de Testes Vitest**
  - **Arquivos**: `frontend/src/types/chat.ts`, `frontend/vitest.config.ts`, `frontend/src/test/setup.ts`
  - **Commit**: `feat(F01): configure TypeScript types from OpenAPI and Vitest testing setup`

- [x] **Task 3: Testes TDD Red (UT-F01-01)**
  - **Arquivos**: `frontend/tests/unit/SmartSalesPage.test.tsx`
  - **Commit**: `test(F01): add UT-F01-01 test for SmartSalesPage and ContextualChatDrawer`

- [x] **Task 4: Implementação TDD Green (SmartSalesPage e ContextualChatDrawer)**
  - **Arquivos**: `frontend/src/app/page.tsx`, `frontend/src/app/layout.tsx`, `frontend/src/app/globals.css`, `frontend/src/components/chat/ContextualChatDrawer.tsx`, `frontend/src/components/catalog/CatalogAndProductView.tsx`
  - **Commit**: `feat(F01): implement SmartSalesPage showcase and contextual chat drawer`

- [x] **Task 5: Documentação Figma EAP 3.4 e Gate de Qualidade**
  - **Arquivos**: `frontend/README.md`, `specs/components/03_frontend_chat_and_cards_spec.md`
  - **Commit**: `docs(F01): document Figma prototype spec and validate quality gates`

---

## 5. Critérios de Aceite e Comandos de Validação
```bash
npm --prefix frontend run test:unit
npm --prefix frontend run lint
uv run --with-requirements tests/requirements-specs.txt python -m unittest discover -s tests -v
```
