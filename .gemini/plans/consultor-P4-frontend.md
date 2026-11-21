# Plano de Implementacao — Pacote P4 (Frontend Consultor Unificado)

## 1. Identificacao
- **Pacote**: P4 (Frontend — Consultor Unificado)
- **Branch**: `feat/consultor-p4`
- **Referencia SDD**: `specs/components/04_consultor_unificado_spec.md` (§6, §7, §9, §10)

## 2. Objetivo e Escopo
Implementar a camada Frontend do Consultor Unificado:
- Suporte ao papel `OPTION` em `RecommendationType` e `ProductRecommendationCarousel` (tom `slate`, selo `"Opção"` e link `"Ver detalhes"` apontando para `/produto/{sku}`).
- Novas unidades em `SPEC_UNITS` (`gb: "GB"`, `polegadas: "″"`, `fps: "fps"`, `ms: "ms"`).
- `ConsultantProvider` montado em `app/layout.tsx` mantendo uma sessao por aba criada com `current_product_sku: null` e enviando o SKU por turno em `context_filters` (omitindo `context_filters` no modo catalogo).
- Modo mock com `product = null` emitindo o token `"O consultor do catálogo exige a API real."` seguido de `done`.
- `ProductAssistant` e `ContextualChatDrawer` aceitando `product: Product | null` com textos de modo catalogo/produto, `CATALOG_SUGGESTIONS` e `suggestionsFor` estendido para Computadores, Webcams, Sofas e Monitores.
- Botao flutuante `"Pergunte ao Consultor IA"` em `CatalogView` (visivel em todas as larguras) abrindo `ContextualChatDrawer` com `product={null}`.
- `ProductPageView` consumindo `useConsultant()` e sincronizando `setContextProduct(product)` na montagem e `null` na desmontagem.
- Testes unitarios (Vitest) e E2E (Playwright com SSE mockado via `page.route`).

## 3. Arquivos Afetados
- `frontend/src/types/chat.ts`
- `frontend/src/lib/format.ts`
- `frontend/src/lib/chat-api.ts`
- `frontend/src/lib/mock-api.ts`
- `frontend/src/hooks/use-chat-session.ts`
- `frontend/src/components/chat/ConsultantProvider.tsx`
- `frontend/src/components/chat/ProductAssistant.tsx`
- `frontend/src/components/chat/ContextualChatDrawer.tsx`
- `frontend/src/components/shop/ProductRecommendationCarousel.tsx`
- `frontend/src/components/shop/ProductPageView.tsx`
- `frontend/src/components/catalog/CatalogView.tsx`
- `frontend/src/app/layout.tsx`
- `frontend/tests/unit/RecommendationCarousel.test.tsx`
- `frontend/tests/unit/ProductPage.test.tsx`
- `frontend/tests/unit/CitationList.test.tsx`
- `frontend/tests/unit/chatApi.test.ts`
- `frontend/tests/unit/useChatSessionApi.test.tsx`
- `frontend/tests/unit/SmartSalesPage.test.tsx`
- `frontend/tests/e2e/consultor.spec.ts`

## 4. Lista de Tarefas Atomicas (TDD — 1 Commit por Task)
- [x] **Task 1 (Red)**: Adicionar testes unitarios para cards `OPTION`, link `"Ver detalhes"`, novas unidades em `SPEC_UNITS` e citacoes `KB-*`.
  - Commit: `test(P4): add unit tests for OPTION cards, Ver detalhes link, SPEC_UNITS and KB citations`
- [x] **Task 2 (Green)**: Implementar `OPTION` em `types/chat.ts` e `ProductRecommendationCarousel.tsx`, link `"Ver detalhes"` e novas unidades em `lib/format.ts`.
  - Commit: `feat(P4): support OPTION recommendation card, Ver detalhes link and new SPEC_UNITS`
- [x] **Task 3 (Red)**: Adicionar testes unitarios para `createSession(null)`, omissao de `context_filters` no modo catalogo, token fixo no modo mock sem produto e `useChatSession` reutilizando sessao entre produtos.
  - Commit: `test(P4): add unit tests for catalog-mode session, streamChat and mock-api`
- [ ] **Task 4 (Green)**: Atualizar `chat-api.ts`, `mock-api.ts`, `use-chat-session.ts`, criar `ConsultantProvider.tsx` e montar em `app/layout.tsx`.
  - Commit: `feat(P4): add ConsultantProvider and update useChatSession for catalog and product modes`
- [ ] **Task 5 (Red)**: Adicionar testes unitarios para `ProductAssistant` em modo catalogo, `CATALOG_SUGGESTIONS`, `suggestionsFor` para novas categorias, botao flutuante na `CatalogView` e continuidade da conversa para `ProductPageView`.
  - Commit: `test(P4): add unit tests for catalog assistant drawer, suggestions and home-to-product handoff`
- [ ] **Task 6 (Green)**: Atualizar `ProductAssistant.tsx`, `ContextualChatDrawer.tsx`, `CatalogView.tsx` e `ProductPageView.tsx`.
  - Commit: `feat(P4): enable unified consultant across CatalogView, ProductPageView and ProductAssistant`
- [ ] **Task 7 (E2E)**: Adicionar teste E2E Playwright (`tests/e2e/consultor.spec.ts`) com SSE mockado via `page.route` validando o fluxo home -> pergunta -> cards `OPTION` -> `"Ver detalhes"` -> pagina de produto mantendo mensagens e enviando `current_product_sku` no proximo turno.
  - Commit: `test(P4): add Playwright E2E test for unified consultant home-to-product handoff`

## 5. Comandos de Validacao
- `pnpm -C frontend run test:unit`
- `pnpm -C frontend run test:e2e`
- `pnpm -C frontend run lint`
- `pnpm -C frontend exec tsc --noEmit`
