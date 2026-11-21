# Product

<!-- impeccable:product-schema 1 -->

> Registro escrito sem entrevista (execução delegada). Cada fato abaixo foi inferido do `CLAUDE.md` da raiz, de `specs/product/` e do código atual; nada foi confirmado em conversa com o time.

## Platform

web

## Users

- **Comprador final (B2B2C)** em e-commerce de produtos tecnicamente complexos (eletroportáteis, eletrônicos, periféricos, cosméticos). Chega a uma página de produto com uma dúvida técnica concreta (voltagem, capacidade, compatibilidade, cuidados de uso) e precisa de uma resposta confiável antes de comprar. Usa celular com frequência.
- **Operador / time comercial (B2B)** que acompanha a qualidade e a conversão do consultor em `/admin/metricas`: TTFT, latência, cache, erros 5xx, aprovação, CTR dos cards e checkouts.

## Product Purpose

SmartSales RAG é um consultor de vendas em tempo real, acoplado à vitrine. Ele responde dúvidas técnicas ancorado apenas nos manuais oficiais e no catálogo SQL, cita a página da fonte e recomenda o produto certo (principal, upsell até +35% de preço, cross-sell de acessório compatível) com preço e estoque sempre do banco. Sucesso: faithfulness ≥ 90%, alucinação ≤ 5%, TTFT ≤ 1,5 s e conversão rastreada pelo checkout simulado.

## Positioning

Um consultor que prefere dizer "isso não consta no manual" a adivinhar. Cada afirmação técnica vem com citação verificável (manual, página, trecho literal), e nenhum preço ou estoque sai de texto gerado.

## Operating Context

- Vitrine (`/`) → página do produto (`/produto/[sku]`) com o Consultor IA ancorado à esquerda no desktop (estilo Amazon Rufus) e em uma *sheet* no celular, aberta por um botão flutuante.
- Conversa via SSE (`metadata → token → citations → recommendations → done`), com fallback seguro (`LOW_SIMILARITY_FALLBACK`, `GUARDRAIL_BLOCKED`) e feedback útil / não útil por resposta.
- Cards de recomendação abrem um checkout simulado que revalida preço e estoque antes de enviar ao marketplace (Amazon, Mercado Livre, Shopee, Loja Oficial).
- Painel do operador protegido por `X-Admin-Token`.

## Capabilities and Constraints

- Regras inegociáveis (CLAUDE.md §2): sem alucinação técnica (R01); fallback seguro abaixo do limiar de similaridade; produto esgotado nunca aparece como compra (R03); preço e estoque do card e do checkout vêm do SQL (R09); citação obrigatória com `chunk_id`, manual e página.
- Stack: Next.js 16 App Router, React 19, TypeScript strict, Tailwind CSS 4, shadcn/ui (Base UI), lucide-react. Sem novas dependências de runtime.
- Modo demonstração: sem `NEXT_PUBLIC_API_BASE_URL`, a loja usa dados simulados e o token `admin-demo`.

## Brand Commitments

- Nome: **SmartSales RAG**; o assistente se chama **Consultor IA**.
- Toda a interface é em português do Brasil, com acentuação correta e formatação pt-BR (R$ 499,90; 4,8; 1,5 s).
- Voz: consultiva, precisa, sem exageros comerciais; admite o que não sabe.

## Evidence on Hand

- Catálogo seed em `data/catalog.json` (7 SKUs, com `specs_json`) e ilustrações SVG em `frontend/public/images/`.
- Avaliações e número de reviews do mock são dados de demonstração; não existem depoimentos, clientes ou benchmarks reais e nada disso deve ser inventado.

## Product Principles

1. Confiança antes de conversão: a fonte aparece antes do botão de compra.
2. Dados determinísticos mandam: preço, estoque, voltagem e especificações exibidos vêm do banco, nunca do texto gerado.
3. A voltagem é o erro mais caro: ela sempre aparece de forma destacada.
4. Contexto sem troca de tela: a dúvida é respondida ao lado do produto.
5. O operador lê o estado de relance: meta, valor e desvio na mesma vista.

## Accessibility & Inclusion

WCAG 2.2 AA: contraste AA, foco visível, landmarks e hierarquia de títulos corretas, `prefers-reduced-motion` respeitado, sem rolagem horizontal a 320 px.
