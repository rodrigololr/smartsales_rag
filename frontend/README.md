# SmartSales RAG — Camada Frontend (`frontend/`)

Este diretório contém o módulo de interface conversacional e vitrine de catálogo do **SmartSales RAG**, implementado em **Next.js 16 (App Router)**, **React 19**, **TypeScript 6 (strict)**, **Tailwind CSS 4** e **shadcn/ui** (preset `base-nova`).

---

## 1. Contexto e Protótipos Figma (EAP 3.4)

A interface foi projetada para vendas consultivas B2B/B2B2C de produtos técnicos (eletroportáteis, eletrônicos, cosméticos), baseada no conceito de **Vitrine Split-View com Painel Lateral Contextual (*Contextual Side-Drawer*, inspirado no Amazon Rufus)**:

### 1.1. Diretrizes de UI/UX e Componentes do Figma
- **Vitrine e Busca (`CatalogAndProductView`)**:
  - Grid responsivo (mobile `375px`, tablet `768px`, desktop `1440px`).
  - Cards de produto com indicação visual estrita de voltagem (`127V`, `220V`, `Bivolt`), preço formatado em BRL (`Intl.NumberFormat`) e estoque em tempo real.
  - Botão de ação primária *"Consultar IA sobre este item"* (`data-testid="consult-ai-btn-{sku}"`) que ancora a sessão do chat no SKU ativo.
- **Painel Lateral do Consultor IA (`ContextualChatDrawer`)**:
  - Drawer deslizante no lado direito (`sm:w-[480px]`, mobile tela cheia).
  - Ancoragem automática no manual do produto selecionado (`current_product_sku`).
  - Sugestões rápidas inteligentes (pílulas de perguntas frequentes do item ativo).
  - Acessibilidade: sem overflow horizontal, `role="dialog"`, suporte a teclado e leitores de tela.

---

## 2. Estrutura de Diretórios

```text
frontend/
├── src/
│   ├── app/
│   │   ├── globals.css              # Diretivas Tailwind e variáveis de tema
│   │   ├── layout.tsx               # Root Layout com metadados e lang="pt-BR"
│   │   ├── page.tsx                 # SmartSalesPage: vitrine, busca, detalhe e drawer
│   │   └── admin/metricas/page.tsx  # Painel do operador (UC09)
│   ├── components/
│   │   ├── admin/
│   │   │   └── AdminMetricsDashboard.tsx   # Token gate, KPIs e dúvidas frequentes
│   │   ├── catalog/
│   │   │   └── CatalogAndProductView.tsx   # Grid de produtos e seletores
│   │   ├── chat/
│   │   │   ├── ContextualChatDrawer.tsx    # Drawer lateral do Consultor IA (Sheet)
│   │   │   ├── AssistantMessage.tsx        # Bolha, citações, cards e feedback
│   │   │   ├── CitationList.tsx            # Badges + trecho literal do manual
│   │   │   └── MessageFeedbackBar.tsx      # Like/Dislike com motivo
│   │   ├── checkout/
│   │   │   └── CheckoutDialog.tsx          # Mock checkout e redirect ao marketplace
│   │   ├── shop/
│   │   │   ├── ProductDetailPanel.tsx      # Página de detalhe do produto selecionado
│   │   │   └── ProductRecommendationCarousel.tsx
│   │   ├── shared/
│   │   │   └── ProductThumb.tsx            # Thumbnail ilustrado por categoria
│   │   └── ui/                      # Componentes shadcn/ui (Button, Card, Badge, Sheet...)
│   ├── hooks/
│   │   └── use-chat-session.ts      # Estado da conversa (API real ou mock)
│   ├── lib/
│   │   ├── format.ts                # BRL, percentuais, marketplace e datas
│   │   ├── chat-api.ts              # Cliente real: sessões e SSE do chat
│   │   ├── sse-parser.ts            # Parser incremental de text/event-stream
│   │   ├── mock-api.ts              # SSE, checkout, feedback e métricas simulados
│   │   ├── mock-data.ts             # Catálogo, recomendações, citações e KPIs
│   │   └── utils.ts                 # Helper cn() para composição de classes
│   ├── test/
│   │   └── setup.ts                 # Configuração de jest-dom para testes
│   └── types/
│       ├── catalog.ts               # Contratos de catálogo de produtos
│       └── chat.ts                  # Schemas OpenAPI 3.1 (SSE, citações, cards, métricas)
├── tests/
│   └── unit/                        # UT-F01-01, UT-F02-01, UT-F03-01/02, UT-F04-01, UT-F05-01
├── components.json                  # Configuração do shadcn/ui
├── eslint.config.mjs                # ESLint flat config (Next.js 16)
├── next.config.js                   # Configurações do Next.js
├── postcss.config.mjs               # Plugin @tailwindcss/postcss (Tailwind v4)
├── tsconfig.json                    # TypeScript com strict: true e paths "@/..."
└── vitest.config.mts                # Runner de testes Vitest com ambiente JSDOM
```

> **Tailwind CSS 4**: a configuração é *CSS-first*. Tokens de tema (cores, raios, fontes) ficam em `src/app/globals.css` via `@theme inline`; não existe mais `tailwind.config.ts`.

---

## 3. Scripts e Comandos de Desenvolvimento

Este projeto usa **pnpm** (o `pnpm-lock.yaml` é o lockfile oficial).

```bash
# Instalar dependências
pnpm install

# Executar servidor de desenvolvimento
pnpm dev

# Executar testes unitários (Vitest)
pnpm test:unit

# Executar linter (ESLint)
pnpm lint

# Executar build de produção
pnpm build
```

---

## 4. Contratos e Tipagem Estrita

Todos os contratos de eventos SSE, citações (`ManualCitation`), cards de recomendação (`ProductCardData`), feedbacks (`FeedbackRating`), checkout (`Checkout`/`CheckoutConflict`) e métricas (`MetricsSummary`) estão estritamente tipados em `src/types/chat.ts`, em total conformidade com a especificação OpenAPI 3.1 do gateway (`specs/architecture/03_openapi_and_sse_contracts.md`).

---

## 5. MVP de Interface (dados mockados)

Enquanto o backend/middle-end não expõem os endpoints, a camada de UI roda com uma API simulada em `src/lib/mock-api.ts` (mesmos tipos do OpenAPI). Telas e fluxos disponíveis:

- **Vitrine responsiva (mobile first)**: busca por nome/SKU/marca, filtro por voltagem, grid `1 → 2 → 3` colunas e página de detalhe do produto selecionado.
- **Detalhe do produto**: especificações, estoque, preço, CTA de compra e abertura do consultor.
- **Consultor IA (Side-Drawer)**: streaming token a token simulado, *skeleton* de consulta, respostas contextuais por produto, citações clicáveis com trecho literal do manual, carrossel `PRIMARY`/`UPSELL`/`CROSS_SELL`, feedback Like/Dislike com motivo, reinício de sessão e *fallback* seguro com retry.
- **Mock Checkout**: validação simulada de estoque/preço, confirmação e link de redirect para o marketplace; estados de `OUT_OF_STOCK`/`PRICE_CHANGED` já tratados.
- **Painel `/admin/metricas`**: token gate em `sessionStorage`, KPIs comparados às metas (TTFT, p95, cache, 5xx, likes, CTR, checkouts) e ranking de dúvidas frequentes. Token de demonstração: `admin-demo`.

### 5.1. Chat com o middle-end real

Defina `NEXT_PUBLIC_API_BASE_URL` (veja `.env.example`) com a origem do middle-end, por exemplo `http://localhost:8000`. Com a variável definida, o `useChatSession` passa a usar `src/lib/chat-api.ts`:

- cria a sessão em `POST /api/v1/sessions` com o `current_product_sku` do produto aberto;
- envia `POST /api/v1/chat/stream` com `context_filters.current_product_sku` e um `client_request_id` por pergunta, consumindo o SSE com `fetch` + `ReadableStream` (parser em `src/lib/sse-parser.ts`);
- se a conexão cair antes de `done`, descarta o texto parcial e reenvia uma única vez com o mesmo `client_request_id`; `409 TURN_IN_PROGRESS` aguarda o `Retry-After`; outros erros HTTP não são repetidos.

Sem a variável, a UI continua usando a API simulada. Checkout, feedback e métricas ainda são simulados nos dois modos.
