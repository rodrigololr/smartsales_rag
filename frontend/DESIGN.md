---
name: SmartSales RAG
description: Vitrine com Consultor IA ancorado ao produto, citações verificáveis e preço/estoque do banco.
colors:
  primary: "oklch(0.457 0.24 277.023)"
  primary-foreground: "oklch(0.962 0.018 272.314)"
  ring: "oklch(0.585 0.233 277.117)"
  background: "oklch(1 0 0)"
  foreground: "oklch(0.145 0 0)"
  muted: "oklch(0.97 0 0)"
  muted-foreground: "oklch(0.5 0 0)"
  border: "oklch(0.922 0 0)"
  destructive: "oklch(0.577 0.245 27.325)"
  stock-in: "#047857"
  stock-out: "#be123c"
  voltage-220: "#92400e"
  voltage-127: "#075985"
  voltage-bivolt: "#065f46"
typography:
  page-title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  product-title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.25
  section-title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.625
  label:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.33
  meta:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1.45
  price:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 700
    fontFeature: "tnum"
rounded:
  sm: "6px"
  md: "8px"
  lg: "10px"
  xl: "14px"
  2xl: "18px"
  full: "9999px"
spacing:
  gutter-mobile: "16px"
  gutter-tablet: "24px"
  gutter-desktop: "32px"
  stack-tight: "8px"
  stack: "12px"
  section: "20px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.lg}"
    height: "32px"
    padding: "0 10px"
  button-buy:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.lg}"
    height: "36px"
  chip-suggestion:
    backgroundColor: "oklch(0.457 0.24 277.023 / 10%)"
    textColor: "{colors.primary}"
    rounded: "{rounded.full}"
    padding: "6px 12px"
  card-product:
    backgroundColor: "{colors.background}"
    rounded: "{rounded.2xl}"
  segmented-filter:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.muted-foreground}"
    rounded: "{rounded.lg}"
    padding: "4px"
---

# Design System: SmartSales RAG

## Overview

**Creative North Star: "O balcão do especialista"**

Uma loja limpa, de fundo branco e cinzas neutros, onde um único índigo marca tudo o que é ação ou conhecimento do consultor: o botão de compra, o chat, as citações. A interface se comporta como um balcão de loja técnica: o produto no centro, o especialista ao lado, e a ficha técnica sempre à mão. Densidade média; nada decorativo compete com preço, voltagem e estoque.

O sistema é shadcn/ui (Base UI) sobre Tailwind CSS 4 com tokens OKLCH em `src/app/globals.css`. A identidade vive nos detalhes: o selo de voltagem colorido por tensão, a citação em acordeão com trecho literal, e o painel do consultor ancorado na borda esquerda no desktop (estilo Rufus).

**Key Characteristics:**
- Um acento (índigo) para ação e conhecimento; cores semânticas só para estado (estoque, voltagem, meta).
- Números em pt-BR e com algarismos tabulares onde são comparados (preço, métricas).
- Superfícies planas com borda fina; sombra só no buy box e no botão flutuante.
- Painel do consultor docado no desktop, *sheet* em tela cheia no celular.

## Colors

Neutros acromáticos com um índigo saturado; cores de estado vêm da escala do Tailwind e nunca substituem o rótulo de texto.

### Primary
- **Índigo Consultor** (`primary`): botões de compra, bolha do usuário, avatar do consultor, citações, chips de pergunta e barras de progresso.
- **Índigo Foco** (`ring`): anel e borda de foco visível em todos os controles.

### Neutral
- **Papel** (`background`) e **Tinta** (`foreground`): fundo e texto principal.
- **Cinza Nota** (`muted-foreground`): texto secundário; escurecido para 0.5 L para passar AA também sobre `muted`.
- **Névoa** (`muted`) e **Fio** (`border`): fundos de grupo (filtros, cabeçalho do chat) e divisórias.

### Named Rules
**The Label-With-Color Rule.** Estoque, voltagem e meta sempre têm texto ("Em estoque", "220V", "Na meta"); a cor reforça, nunca carrega sozinha o significado.
**The Dark-Status Rule.** Texto de estado usa os tokens `success`/`danger`/`warning` (emerald-700, rose-700, amber-800 no claro; 400/300 no escuro) ou o tom 800 sobre fundo 100; o tom 600 não passa AA em 12px.
**The Night-Counter Rule.** Tema escuro (Sistema/Claro/Escuro no cabeçalho): o índigo vira `indigo-400` com texto `indigo-950`, selos tonais usam fundo 950 e texto 200, e as ilustrações de produto ficam num bloco claro arredondado.

## Typography

**Body Font:** Inter (via `next/font`), com fallback de sistema.

**Character:** Uma família só; hierarquia por peso e tamanho, sem display decorativo.

### Hierarchy
- **Page title** (700, 1.5rem, tracking -0.025em): "Catálogo", "Métricas do Consultor IA".
- **Product title** (600, 1.5rem): nome do produto, único `h1` da página.
- **Section title** (600, 1rem): "Ficha técnica", "Sobre este item", "Dúvidas mais frequentes".
- **Body** (400, 0.875rem, 1.625): resposta do consultor, descrições; listas limitadas a `max-w-prose`.
- **Label** (500, 0.75rem): estados, metas, rótulos de filtro.
- **Meta** (500, 0.6875rem): TTFT, SKU em mono, notas de rodapé do chat. Nunca abaixo de 11px.

### Named Rules
**The Eleven-Pixel Floor.** Nenhum texto legível abaixo de 11px; selos internos (`Cache`, `Resposta corrigida`) ficam em 10px por serem redundantes ao contexto.

## Layout

Contêiner central `max-w-7xl` com gutters de 16/24/32px para vitrine, admin e páginas de erro; o cabeçalho alinha com esse contêiner (`StoreHeader contained`). A página do produto é exceção: cabeçalho de borda a borda, consultor docado com 360–400px à esquerda a partir de `lg`, e o conteúdo em grade `galeria | detalhes | buy box (260px)` no `xl`, `galeria | título+buy box` no `md`, e no celular a ordem título → preço/compra → ficha técnica. Grade de produtos 2/3/4 colunas. Métricas em 2 colunas no celular e 3 no `lg` (9 indicadores, sem órfãos). Sem rolagem horizontal a 320px.

## Elevation & Depth

Plano por padrão: bordas `border` de 1px separam superfícies. Sombra apenas onde há prioridade ou flutuação: `shadow-xs` no buy box, `shadow-md` no hover do card de produto e `shadow-lg` no botão flutuante "Pergunte ao Consultor IA".

## Shapes

Raio base 10px (`--radius: 0.625rem`), com cards de produto e buy box em 18px, chips de pergunta e botão flutuante em pílula, e bolhas de chat com o canto de origem reduzido (`rounded-tl-sm` no consultor, `rounded-tr-sm` no usuário).

## Components

### Buttons
- **Shape:** 10px; alturas 24/28/32/36px (xs/sm/default/lg).
- **Primary:** índigo sólido com texto claro; "Comprar na {Marketplace}" é sempre primário.
- **Hover / Focus:** escurece no hover; foco com borda e anel `ring` de 3px.
- **Ghost / Outline:** ações secundárias (Atualizar, Sair, Voltar à loja, Tentar novamente).

### Chips
- **Perguntas sugeridas:** pílula índigo 10% com texto índigo.
- **Filtro segmentado (Voltagem / Janela):** fundo `muted`, item ativo em `background` com `shadow-xs` e `aria-pressed`.

### Cards / Containers
- **Produto:** 18px, borda fina, imagem quadrada, preço tabular, selo de voltagem e estado de estoque com ícone.
- **Recomendação:** 252px (máx. 80vw), tom por tipo (sky = principal, violet = upsell, emerald = cross-sell); produto esgotado mostra "Esgotado" e botão desabilitado "Indisponível".
- **Métrica:** rótulo, valor tabular, selo "Na meta"/"Fora da meta", barra opcional e linha "Meta:".

### Inputs / Fields
- **Style:** borda `input`, 10px, ícone de busca à esquerda, limpar à direita.
- **Focus:** borda e anel `ring`; caret índigo.

### Navigation
- Cabeçalho fixo com logotipo e link "Métricas" (ícone só no celular, alvo de 40px); trilha de navegação em `ol` com `aria-current`. Link "Pular para o conteúdo" visível no foco.

### Citação em acordeão (assinatura)
Lista com borda índigo 20%, cada item "Manual — p. X" expande o trecho literal entre aspas, a seção e a similaridade.

## Do's and Don'ts

### Do:
- **Do** mostrar preço, estoque e voltagem apenas a partir dos dados do catálogo (R09), com `tabular-nums` no preço.
- **Do** formatar números em pt-BR (`4,8`, `1.284`, `1.460 ms`) via `formatNumber`/`formatBRL`.
- **Do** manter o selo de voltagem visível em todo card e no topo do consultor.
- **Do** respeitar `prefers-reduced-motion` (regra global em `globals.css` e rolagem do chat).

### Don't:
- **Don't** oferecer compra de item esgotado: nada de "Comprar" ativo quando `stock_quantity <= 0` (R03).
- **Don't** usar texto de estado em tom 600 ou cor sem rótulo.
- **Don't** criar novos acentos de cor fora do índigo e das cores de estado.
- **Don't** colocar rótulos *eyebrow* acima de títulos.
