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
│   │   └── page.tsx                 # SmartSalesPage: orquestrador da vitrine e drawer
│   ├── components/
│   │   ├── catalog/
│   │   │   └── CatalogAndProductView.tsx   # Grid de produtos e seletores
│   │   ├── chat/
│   │   │   └── ContextualChatDrawer.tsx    # Drawer lateral do Consultor IA (Sheet)
│   │   └── ui/                      # Componentes shadcn/ui (Button, Card, Badge, Sheet...)
│   ├── lib/
│   │   └── utils.ts                 # Helper cn() para composição de classes
│   ├── test/
│   │   └── setup.ts                 # Configuração de jest-dom para testes
│   └── types/
│       ├── catalog.ts               # Contratos de catálogo de produtos
│       └── chat.ts                  # Schemas OpenAPI 3.1 (SSE, citações, cards, métricas)
├── tests/
│   └── unit/
│       └── SmartSalesPage.test.tsx  # Teste TDD UT-F01-01
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

Todos os contratos de eventos SSE, citações (`ManualCitation`), cards de recomendação (`ProductCardData`) e feedbacks (`FeedbackRating`) estão estritamente tipados em `src/types/chat.ts`, em total conformidade com a especificação OpenAPI 3.1 do gateway (`specs/architecture/03_openapi_and_sse_contracts.md`).
