# SmartSales RAG — Camada Frontend (`frontend/`)

Este diretório contém o módulo de interface conversacional e vitrine de catálogo do **SmartSales RAG**, implementado em **Next.js 14+ (App Router)**, **React 18**, **TypeScript 5 (strict)** e **Tailwind CSS**.

---

## 1. Contexto e Protótipos Figma (EAP 3.4 / 4.9)

A interface foi projetada para vendas consultivas B2B/B2B2C de produtos técnicos (eletroportáteis, eletrônicos, cosméticos), baseada no conceito de **Vitrine Split-View com Painel Lateral Contextual (*Contextual Side-Drawer*, inspirado no Amazon Rufus)**:

### 1.1. Componentes Principais
- **Barra Superior (`StoreHeader`)**:
  - Busca de catálogo em tempo real por nome, SKU ou marca.
  - Seletor de voltagem preferida (`127V`, `220V` ou `Todas`).
  - Acesso rápido ao chat contextual com o produto atualmente selecionado.
- **Vitrine e Busca (`CatalogAndProductView`)**:
  - Grid responsivo (mobile `375px`, tablet `768px`, desktop `1440px`).
  - Cards de produto com indicação visual estrita de voltagem (`127V`, `220V`, `Bivolt`), preço formatado em BRL (`Intl.NumberFormat`) e estoque em tempo real.
  - Botão de ação primária *"Consultar IA sobre este item"* (`data-testid="consult-ai-btn-{sku}"`) que ancora a sessão do chat no SKU ativo.
- **Painel Lateral do Consultor IA (`ContextualChatDrawer`)**:
  - Drawer deslizante no lado direito (`sm:w-[500px]`, mobile tela cheia).
  - Ancoragem automática no manual do produto selecionado (`current_product_sku`).
  - Sugestões rápidas inteligentes (pílulas de perguntas frequentes do item ativo).
  - Botão de reiniciar conversa (`ResetSessionButton`) vinculado a `DELETE /api/v1/sessions/{id}` (`UC07`).
  - Acessibilidade: sem overflow horizontal, `role="dialog"`, suporte a teclado e leitores de tela.

---

## 2. Streaming em Tempo Real com Server-Sent Events (`useSSEChatStream` — F02)

O hook `useSSEChatStream` gerencia o ciclo completo de comunicação com o endpoint `POST /api/v1/chat/stream`:

1. **Ciclo de Eventos SSE**:
   - `metadata`: captura latência `TTFT`, `message_id` e status de `cache_hit`.
   - `token`: streaming progressivo token a token renderizado na bolha do assistente.
   - `correction`: substituição atômica pelo texto seguro validado em caso de interceptação de saída (`wasCorrected: true`).
   - `citations`: anexação de metadados das fontes oficiais (manuais em PDF).
   - `recommendations`: exibição dos cards consultivos (`PRIMARY`, `UPSELL`, `CROSS_SELL`).
   - `error`: descarte do conteúdo parcial instável e exibição de mensagem de fallback segura (`LOW_SIMILARITY_FALLBACK`).
   - `done`: encerramento do stream com liberação dos inputs.
2. **Resiliência e Idempotência (R07)**:
   - Geração de `client_request_id` (UUID v4) antes de enviar a pergunta.
   - Reconexão automática única em caso de queda de rede antes do evento `done`, reutilizando exatamente o mesmo `client_request_id`.
   - Tratamento de `HTTP 409` (`TURN_IN_PROGRESS`) e botão de `"Tentar novamente"`.

---

## 3. Estrutura de Diretórios

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
│   │   │   ├── AssistantMessageBubble.tsx  # Bolha de resposta com skeleton e correction
│   │   │   ├── ContextualChatDrawer.tsx    # Drawer lateral do Consultor IA
│   │   │   ├── MessageList.tsx             # Lista de mensagens com auto-scroll
│   │   │   └── ResetSessionButton.tsx      # Botão de reiniciar sessão (DELETE /sessions/{id})
│   │   └── layout/
│   │       └── StoreHeader.tsx             # Cabeçalho com busca e seletor de voltagem
│   ├── hooks/
│   │   └── useSSEChatStream.ts      # Hook resiliente de streaming SSE (POST /chat/stream)
│   ├── test/
│   │   └── setup.ts                 # Configuração de jest-dom e polyfills JSDOM
│   ├── types/
│   │   ├── catalog.ts               # Contratos de catálogo de produtos
│   │   └── chat.ts                  # Schemas OpenAPI 3.1 (SSE, citações, cards, métricas)
│   └── utils/
│       └── sseParser.ts             # Parser determinístico de blocos SSE
├── tests/
│   └── unit/
│       ├── ContextualChatDrawer.test.tsx # Teste de integração do drawer
│       ├── SmartSalesPage.test.tsx       # Teste TDD UT-F01-01
│       └── useSSEChatStream.test.tsx     # Testes TDD UT-F02-01 e UT-F02-02
├── next.config.js                   # Configurações do Next.js
├── tailwind.config.ts               # Paleta e extensões do Tailwind CSS
├── tsconfig.json                    # TypeScript com strict: true e paths "@/..."
└── vitest.config.ts                 # Runner de testes Vitest com ambiente JSDOM
```

---

## 4. Scripts e Comandos de Desenvolvimento

```bash
# Executar servidor de desenvolvimento
npm run dev

# Executar testes unitários (Vitest)
npm run test:unit

# Executar linter (ESLint)
npm run lint

# Executar build de produção
npm run build
```
