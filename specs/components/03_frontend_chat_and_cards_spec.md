# Especificação de Componente: Frontend, Chat com Streaming SSE, Citações e Product Cards (`F01` a `F05`)

- **Pacotes da EAP / Rede CPM**: `EAP 3.4`, `4.8`, `4.9`, `4.10`, `4.11`, `5.2` (`F01`, `F02`, `F03`, `F04`, `F05`)
- **Responsáveis Técnicos**: **Eduardo** (Desenvolvedor Front-end & UI) e **Victor Hugo** (Designer UX/UI, Desenvolvedor Front-end & Analista de QA)
- **Stack**: Next.js 16 (App Router), React 19, TypeScript 6 (`strict: true`), Tailwind CSS 4 (CSS-first), shadcn/ui (Base UI + preset `base-nova`), Lucide React, Vitest + React Testing Library, Playwright (E2E).

---

## 1. Hierarquia de Componentes da Interface (`frontend/src/components/`)

A interface segue o padrão moderno de **Vitrine de Produtos + Painel Lateral Contextual de IA (*Contextual Side-Drawer*, inspirado no Amazon Rufus)**: quando o usuário entra em um item do catálogo, o painel do **Consultor IA** abre na lateral direita já ancorado no `SKU` e no manual PDF daquele produto, permitindo tirar dúvidas técnicas, comparar com concorrentes da loja e receber sugestões de *Upsell* e *Cross-sell* com links diretos de compra (`Amazon`, `Mercado Livre`, `Shopee`).

```mermaid
flowchart TD
    PAGE["<b>SmartSalesPage (app/page.tsx)</b><br/>Layout Split-View: Vitrine/Página do Produto + Side-Drawer do Consultor IA"]

    PAGE --> HEADER["<b>StoreHeader</b><br/>Seletor de Voltagem Preferida (127V / 220V) + Busca de Catálogo"]
    PAGE --> SHOWCASE["<b>CatalogAndProductView</b><br/>Grid de Produtos + Página de Detalhe do Produto Selecionado<br/>(Aciona abertura do Chat Contextual ao clicar no item)"]
    PAGE --> CHAT["<b>ContextualChatDrawer (ChatWidgetContainer)</b><br/>Painel lateral estilo Amazon pré-contextualizado com o SKU ativo"]

    CHAT --> MSGLIST["<b>MessageList</b><br/>Auto-scroll inteligente durante streaming"]
    CHAT --> INPUT["<b>ChatPromptInput</b><br/>Sugestões rápidas contextuais do item + bloqueio anti-duplo envio"]
    CHAT --> RESET["<b>ResetSessionButton</b><br/>Reiniciar conversa (UC07)<br/>DELETE /api/v1/sessions/{id}"]
    ADMIN["<b>AdminMetricsPage (app/admin/metricas/page.tsx)</b><br/>Painel do Operador/Lojista (UC09)<br/>GET /api/v1/metrics/summary + X-Admin-Token"]

    MSGLIST --> BUBBLE["<b>AssistantMessageBubble</b><br/>Renderizador Markdown incremental"]
    BUBBLE --> CIT["<b>CitationBadgeList</b><br/>Badges clicáveis: 📄 Manual Airfryer 4L, p. 14"]
    CIT --> MODAL_CIT["<b>CitationList (acordeão)</b><br/>Exibe o trecho original exato do manual"]

    BUBBLE --> CARDS["<b>ProductRecommendationCarousel</b><br/>Lista até 3 cards: PRIMARY, UPSELL e CROSS_SELL"]
    CARDS --> CARD["<b>ProductCard</b><br/>Foto, SKU, Selo, Voltagem, Preço R$ e CTA 'Comprar na Amazon/ML/Shopee'"]
    CARD --> MODAL_CHK["<b>MockCheckoutRedirectModal</b><br/>Registra conversão (UC05) e redireciona para o link do marketplace"]

    BUBBLE --> FB["<b>MessageFeedbackBar</b><br/>Botões 👍 Like e 👎 Dislike + Modal rápido de motivo (UC06)"]

    style PAGE fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style SHOWCASE fill:#e0f7fa,stroke:#00838f,stroke-width:2px
    style CHAT fill:#fff8e1,stroke:#f57f17,stroke-width:2px
    style BUBBLE fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style CARDS fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
```

---

## 2. Interfaces TypeScript Estritas (`frontend/src/types/chat.ts`)

```typescript
export type VoltageType = "127V" | "220V" | "BIVOLT" | "N/A";
export type RecommendationType = "PRIMARY" | "UPSELL" | "CROSS_SELL";
export type MarketplaceType = "AMAZON" | "MERCADO_LIVRE" | "SHOPEE" | "LOJA_OFICIAL";
export type FeedbackRating = "LIKE" | "DISLIKE";

export interface ManualCitation {
  chunk_id: string;
  sku: string;
  manual_title: string;
  page_number: number;
  section_title?: string;
  similarity_score: number;
  excerpt: string;
}

export interface ProductCardData {
  sku: string;
  name: string;
  price: number;
  stock_quantity: number;
  voltage: VoltageType;
  capacity_liters?: number | null;
  power_watts?: number | null;
  image_url: string;
  marketplace: MarketplaceType;
  checkout_url: string;
  recommendation_type: RecommendationType;
  badge_label: string;
  justification: string;
}

export type SSEEventName =
  | "metadata"
  | "token"
  | "correction"
  | "citations"
  | "recommendations"
  | "error"
  | "done";

export type StreamErrorCode =
  | "GUARDRAIL_BLOCKED"
  | "LOW_SIMILARITY_FALLBACK"
  | "LLM_UNAVAILABLE"
  | "INTERNAL_ERROR";

export type FeedbackReasonCategory = "HALLUCINATION" | "WRONG_VOLTAGE" | "SLOW" | "OTHER";

export interface MetricsSummary {
  turns: number;
  ttft_p50_ms: number;
  ttft_p95_ms: number;
  total_latency_p95_ms: number;
  cache_hit_ratio: number;
  error_5xx_rate: number;
  like_ratio: number;
  card_ctr: number;
  confirmed_checkouts: number;
  top_questions: { question: string; count: number }[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming: boolean;
  ttftMs?: number;
  cacheHit?: boolean;
  citations: ManualCitation[];
  recommendations: ProductCardData[];
  feedback?: FeedbackRating | null;
  errorFallback?: string | null;
  errorCode?: StreamErrorCode | null;
  wasCorrected?: boolean;
}
```

---

## 3. Especificação do Hook de Streaming SSE (`useSSEChatStream` — `F02`)

O hook `useSSEChatStream` gerencia o ciclo de vida da requisição `POST /api/v1/chat/stream` usando `fetch` + `ReadableStream` (`TextDecoderStream`) — **não** `EventSource`, que não suporta `POST` — para enviar o payload JSON (`session_id`, `message`, `context_filters`) e ler progressivamente os eventos SSE definidos em [`03_openapi_and_sse_contracts.md`](../architecture/03_openapi_and_sse_contracts.md):

1. **Estados Visuais da Conversa** (alinhados ao [Diagrama de Estados](../diagrams_and_pm/06_diagrama_estados.md)):
   - `IDLE`: Input habilitado; sugestões rápidas visíveis;
   - `CONNECTING` (`0 ms` a `TTFT`): Exibe *skeleton* pulsante *"Consultando manuais oficiais e estoque..."*;
   - `STREAMING`: A cada evento `token`, concatena `delta` ao estado da mensagem atual com *requestAnimationFrame* para evitar *layout thrashing*; ao receber `correction`, **substitui** todo o texto da bolha por `content` e marca `wasCorrected = true`;
   - `ENRICHING`: Ao receber `citations` e `recommendations`, renderiza com transição suave os *badges* de página do manual e o carrossel de *Product Cards*;
   - `ERROR`: Ao receber `error`, exibe `fallback_message` em destaque (sem *badges* de citação) e mantém os cards de `recommendations` que vierem em seguida;
   - `COMPLETED`: Ao receber `done` (sempre o último evento), habilita a barra de feedback (`👍` / `👎`) e reabilita o campo de envio.
   - *Estes estados são apenas visuais; não correspondem a `chat_sessions.state` (`ACTIVE | ENDED`).*
2. **Resiliência em Conexões Móveis Instáveis (Mitigação do Risco `R07`)**:
   - Se a conexão cair antes do evento `done`, o hook descarta o texto parcial e **reenvia a mesma requisição `POST`, incluindo o mesmo `client_request_id`, uma única vez**; caso persista a falha, exibe botão `"Tentar novamente"` mantendo a pergunta do usuário preservada. Como o estado do turno no servidor é desconhecido após a interrupção, esse `Tentar novamente` manual **reutiliza o mesmo `client_request_id`**; um novo ID só é gerado depois que o turno terminou de forma conhecida (`done` ou erro terminal, como HTTP 5xx).

---

## 4. Regras de UI/UX para *Product Cards*, Citações e Feedback (`F03`, `F04`)

### 4.1. Anatomia Obrigatória do `ProductCard` (`EAP 4.10`)
Cada card renderizado na vitrine da mensagem deve exibir obrigatoriamente:
- **Badge Superior Diferenciado por Tipo**:
  - `PRIMARY`: Azul (`"Produto Consultado"`);
  - `UPSELL`: Roxo/Dourado (`"Upgrade Recomendado — Maior Capacidade"`);
  - `CROSS_SELL`: Verde (`"Compre Junto Compatível"`).
- **Tag de Voltagem em Destaque Visual**: Pílula de alto contraste (`220V`, `127V` ou `Bivolt`) para prevenir compra de tensão errada pelo consumidor.
- **Justificativa Consultiva Curta**: 1 frase explicando por que o item foi sugerido para o contexto do usuário.
- **Preço Formatado em `BRL` (`Intl.NumberFormat('pt-BR')`), Estoque e Botão Direto de Marketplace (`EAP 4.8`)**:
  - Exibe `"Em estoque (X un.)"` e o selo do canal oficial (`Amazon`, `Mercado Livre`, `Shopee` ou `Loja Oficial`).
  - O botão de ação primária **`Comprar na {Marketplace}`** (`data-testid="buy-now-btn-{sku}"`) dispara `POST /api/v1/checkout/mock` (validando estoque/preço em tempo real e registrando a métrica de conversão CTR no PostgreSQL) e, ao confirmar `status: "CONFIRMED"`, abre o modal de confirmação/redireciona para o `redirect_checkout_url` (link de afiliado/anúncio do marketplace). Em `HTTP 409` (`OUT_OF_STOCK` ou `PRICE_CHANGED`), atualiza o card com `current_stock`/`current_price` e exibe alerta amigável sugerindo um item alternativo no chat (`UC05`).
  - Decisões da issue #17 (F04): o `message_id` enviado é o do evento SSE `metadata` do turno que exibiu o card. Sem `badge_label`, o selo vem do tipo (`PRIMARY` → `Ideal`, `UPSELL` → `Upgrade`, `CROSS_SELL` → `Acessório`). Em `PRICE_CHANGED`, o modal mostra `current_price` e só reenvia com `displayed_price = current_price` depois que o usuário clica em `Confirmar por R$ X`. Em `OUT_OF_STOCK`, não há link de compra e o card passa a `Esgotado` com o botão desabilitado e rotulado `Indisponível` (`R03`). O link `redirect_checkout_url` abre em nova aba com `rel="noopener noreferrer"`. `404/410/422/429/5xx` mostram mensagem em português e `Tentar novamente` com o mesmo corpo.
- **Buy box da página do produto (fora do chat)**: como `CheckoutCreate` exige o `message_id` de um turno do chat, o botão `Comprar na {Marketplace}` (`data-testid="buy-btn-{sku}"`) é um link direto para o `checkout_url` do produto (nova aba), sem `POST /checkout/mock` e sem contar no CTR dos cards. Preço e estoque vêm do `GET /api/v1/products/{sku}`; produto esgotado aparece como `Esgotado`, sem link (`R03`).
- **Ficha técnica da página do produto** (`data-testid="product-specs"`): marca, categoria, voltagem, potência e capacidade do produto, seguidas das chaves escalares de `specs_json` com rótulo humanizado em pt-BR (ex.: `temperatura_max_c` → `Temperatura máx.` / `200 °C`; a unidade vem do sufixo da chave) e do SKU. Valores nulos, objetos e listas são omitidos; nada é inferido (`R01`). No celular a ordem é título → preço/compra → ficha técnica.
- **Erros de rota**: `app/error.tsx` e `app/produto/[sku]/error.tsx` mostram mensagem em português com `Tentar novamente` (`retry()` do Next 16; a doc do Next 16.4 recomenda `retry` em vez de `reset`) e `Voltar ao catálogo`; `app/global-error.tsx` cobre falha do layout raiz com o próprio `<html>`/`<body>` e a mesma mensagem; `app/not-found.tsx` cobre SKU inexistente.

### 4.2. Interação de Citação Verificável (`CitationBadge` — `EAP 4.9`)
- Clicar no item `Manual Airfryer SmartChef 4L — p. 14` expande um acordeão acessível (`button` com `aria-expanded`/`aria-controls`, operável por teclado) exibindo o `excerpt` literal extraído da página 14 do PDF e a seção técnica correspondente (quando houver). Decisão da issue #12 (F03).

### 4.3. Interação de Feedback (`MessageFeedbackBar` — `EAP 4.11`)
- Clicar em `👍` dispara imediatamente `POST /api/v1/feedback` com `rating: "LIKE"` e exibe confirmação `"Obrigado pelo feedback!"`.
- Clicar em `👎` exibe 4 pílulas rápidas e envia `POST /api/v1/feedback` com `rating: "DISLIKE"` e o `reason_category` correspondente — `"Informação imprecisa"` → `HALLUCINATION`, `"Voltagem/medida incorreta"` → `WRONG_VOLTAGE`, `"Demorou a responder"` → `SLOW`, `"Outro"` → `OTHER` —, alimentando o [Ciclo PDCA](../diagrams_and_pm/13_qualidade_ciclo_pdca.md). Cada mensagem aceita uma única avaliação (`UC06`).

### 4.4. Painel de Métricas do Operador/Lojista (`AdminMetricsPage` — `UC09`, `RF16`)
- Rota `/admin/metricas` (fora do layout da vitrine), solicita o `ADMIN_TOKEN` uma vez (guardado em `sessionStorage`) e chama `GET /api/v1/metrics/summary` com o cabeçalho `X-Admin-Token`.
- Exibe *cards* de KPI (`TTFT p50/p95`, tempo total `p95`, *cache hit ratio*, taxa `5xx`, aprovação de *likes*, CTR dos cards e checkouts confirmados) comparados às metas da [Árvore de Qualidade](../diagrams_and_pm/10_qualidade_arvore_metricas.md) e a lista das dúvidas mais frequentes. Em `401`, volta a pedir o token.
- O token fica só no `sessionStorage` e só viaja no cabeçalho `X-Admin-Token` (nunca na URL nem em logs). Seletor de janela `24h` / `7 dias` (padrão, igual ao do gateway) / `30 dias` envia `from`/`to` em ISO 8601. Janela sem turnos mostra estado vazio; outros erros mantêm o token e oferecem `Tentar novamente`. Os indicadores "Na meta"/"Fora da meta" usam as metas do `CLAUDE.md` §2 (TTFT p50 ≤ 1,5 s, TTFT p95 ≤ 2,0 s, total p95 ≤ 8 s, cache ≥ 30%) e dos `RNF06`/`RNF08` (5xx ≤ 1%, likes ≥ 80%, CTR ≥ 10%).

## 5. Vitrine, retry e texto seguro

Carregar a vitrine e a pesquisa em `GET /api/v1/products` com os parâmetros/resultado normativos da seção 5 do contrato. A vitrine (`app/page.tsx`) e a página do produto (`app/produto/[sku]/page.tsx`) são Server Components renderizados a cada requisição (`connection()` + `fetch` com `cache: "no-store"`): a vitrine percorre todas as páginas com `page_size=100`, a página do produto usa `GET /api/v1/products/{sku}` e `404` vira `notFound()`. O `next build` não depende do gateway. No servidor, o endereço é `API_INTERNAL_BASE_URL` (padrão: `NEXT_PUBLIC_API_BASE_URL`). Sem `NEXT_PUBLIC_API_BASE_URL`, ambas usam o mock local. Criar `client_request_id` UUID v4 antes de enviar a pergunta e preservar o mesmo ID/payload na única reconexão automática. Tratar 409 TURN_IN_PROGRESS aguardando Retry-After sem criar outro turno; 409 IDEMPOTENCY_CONFLICT é erro de cliente, não retry; 410 pede novo envio explícito. No evento error, descartar todo conteúdo parcial e mostrar fallback. Nenhum token recebido pode depender de correction posterior para se tornar factualmente seguro.

## 6. Tema claro/escuro

- O `StoreHeader` (e o cabeçalho do painel `/admin/metricas`) exibe um grupo de botões `role="group"` rotulado `Tema` com três opções: `Tema do sistema` (padrão, segue `prefers-color-scheme` e acompanha mudanças do sistema em tempo real), `Tema claro` e `Tema escuro`. Cada botão tem `aria-label` e `aria-pressed`; o grupo é operável por teclado (Tab + Enter/Espaço).
- A escolha fica em `localStorage["smartsales-theme"]` (`light` | `dark`; `Sistema` remove a chave). Leituras e gravações ficam em `try/catch`: com o armazenamento bloqueado, a escolha vale só para a página aberta.
- Um script inline em `<head>` (`app/layout.tsx` e `app/global-error.tsx`) aplica a classe `.dark` no `<html>` antes da primeira pintura, sem flash de tema errado; o `<html>` usa `suppressHydrationWarning`.
- Cores: no escuro o índigo primário vira `indigo-400` com texto `indigo-950` (texto `text-primary` ≥ 5,7:1 sobre `card`); texto de estado usa os tokens `success`/`danger`/`warning` (700/800 no claro, 300/400 no escuro); selos tonais (voltagem, tipo de recomendação, meta) usam fundo 950 e texto 200 no escuro. Ilustrações de produto continuam sobre um bloco claro arredondado para manter a leitura da arte.

## 7. Fallback, leitores de tela e foco no chat

- **Alerta de fallback por código** (`data-testid="assistant-fallback-{id}"`, `data-tone`): o código bruto nunca aparece para o usuário. `LOW_SIMILARITY_FALLBACK` é uma resposta segura esperada (tom informativo, índigo/neutro, título `Informação não encontrada no manual`); `GUARDRAIL_BLOCKED` usa tom de aviso (`Pergunta fora do escopo do consultor`); `LLM_UNAVAILABLE` (`Consultor indisponível no momento`) e `INTERNAL_ERROR` (`Não foi possível concluir a resposta`) usam tom de erro e são os únicos com `Tentar novamente`. O botão fica na coluna do texto (`col-start-2`), sem espremer a mensagem a 390 px.
- **Leitores de tela**: o histórico (`data-testid="chat-log"`) não é região viva; recebe `aria-busy="true"` durante o streaming. Uma região `sr-only` (`data-testid="chat-announcer"`, `aria-live="polite"`) anuncia uma única vez a resposta concluída (ou `Título. mensagem` do fallback).
- **Foco**: o campo de pergunta permanece habilitado durante o streaming (o foco não se perde); apenas o envio (Enter e botão `Enviar pergunta`) fica bloqueado até o `done`.

## 8. Filtro de voltagem

O filtro da vitrine tem `Todas`, `127V`, `220V` e `Bivolt`. Produtos `BIVOLT` funcionam nas duas tensões e por isso aparecem também em `127V` e em `220V`, com o selo `Bivolt` e a nota `Inclui modelos bivolt, que funcionam em 127V e 220V.` na contagem; o filtro `Bivolt` mostra só eles. Em todos os selos e na ficha técnica, `BIVOLT` é exibido como `Bivolt`.
