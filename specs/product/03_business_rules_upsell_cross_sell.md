# Especificação das Regras de Negócio, Motor de *Upsell / Cross-sell* e *Guardrails* (`EAP 4.3`, `4.4`)

Este documento define as **Regras de Negócio (`RN01` a `RN10`)** e os algoritmos determinísticos do **SmartSales RAG** para filtragem de catálogo, recomendações de **Upselling** e **Cross-selling** (`UC03`) e **Guardrails Anti-Alucinação** (`UC01`, `UC02`).

---

## 1. Catálogo de Regras de Negócio (`RN01` a `RN10`)

| Código | Regra de Negócio | Condição / Fórmula Determinística | Ação do Sistema | Risco Mitigado |
| :---: | :--- | :--- | :--- | :---: |
| **RN01** | **Exclusão Obrigatória de Itens Sem Estoque** | `product.stock_quantity > 0` E `product.is_active == TRUE` | Produtos com `stock_quantity <= 0` são filtrados na cláusula `WHERE` do SQL de **toda recomendação** (`PRIMARY`, `UPSELL`, `CROSS_SELL`) e de todo card. A busca de *chunks* de manual não filtra estoque (permite responder dúvidas sobre item esgotado e oferecer substituto). | `R09` |
| **RN02** | **Limiar Mínimo de Similaridade Semântica** | $\text{cosine\_similarity}(q, c_i) \ge 0,72$ (com `top_k = 5`) | *Chunks* com similaridade $< 0,72$ são descartados. Se nenhum *chunk* atingir $\ge 0,72$, aciona-se o **Fallback Seguro** (`RN03`). O valor `0,72` é o ponto de partida configurável (`SIMILARITY_THRESHOLD`), a ser calibrado empiricamente no *Golden Set* (`EAP 5.1`). | `R01`, `R03` |
| **RN03** | **Fallback Seguro por Ausência de Evidência** | `len(valid_chunks) == 0` | O LLM não é invocado; o sistema emite o evento SSE `error` (`LOW_SIMILARITY_FALLBACK`) com a resposta padronizada informando ausência no manual, seguido de `recommendations` com itens similares em estoque. | `R01` |
| **RN04** | **Elegibilidade de Upsell (`UC03`)** | Mesma categoria + `tier_rank > base.tier_rank` (ou `capacity_liters > base.capacity_liters`) + $1,00 < \frac{\text{price}_{\text{upsell}}}{\text{price}_{\text{base}}} \le 1,35$ + voltagem compatível + `stock > 0` | Seleciona o produto superior com melhor *score* composto dentro do **teto máximo de +35% de preço** sobre o produto base. | `R09` |
| **RN05** | **Elegibilidade de Cross-sell (`UC03`)** | Relação cadastrada em `product_relations` (`relation_type = 'CROSS_SELL'`) OU categoria complementar compatível + $\text{price}_{\text{cross}} \le 0,40 \times \text{price}_{\text{base}}$ + `stock > 0` | Seleciona **1** acessório ou consumível (o de maior $S_{\text{cross}}$) diretamente compatível com o `SKU` principal, respeitando o máximo de 3 cards por turno. | `R09` |
| **RN06** | **Imutabilidade de Preço e Voltagem pelo LLM** | `card.price == db.product.price` E `card.voltage == db.product.voltage` | Os dados exibidos nos *Product Cards* são injetados diretamente do PostgreSQL pelo Backend/Middle-end, jamais extraídos do texto livre do LLM. | `R01`, `R09` |
| **RN07** | **Obrigatoriedade de Citação Técnica** | Resposta utiliza `manual_chunks` ($\text{count} \ge 1$) | O output deve conter pelo menos 1 item em `citations[]` com `manual_title`, `page_number` ($\ge 1$) e `chunk_id` existente nos *chunks* recuperados. | `R01` |
| **RN08** | **Validação de Grandezas antes da Publicação** | Afirmações estruturadas por SKU, atributo, valor e unidade | Reter cada sentença; validar voltagem, preço, capacidade, potência e suporte da citação antes de emitir tokens. Substituir sentença privada inválida por template seguro; jamais publicar fato incorreto para corrigi-lo depois. | `R01` |
| **RN09** | **Identidade de Cache** | SHA-256 de JSON canônico com versão de catálogo/política, consulta em ordem, filtros resolvidos e histórico cronológico | Ver função normativa de cache em `components/02_middleend_gateway_sse_redis_spec.md`; cache compartilhado somente para histórico vazio. | `R10`, `R09` |
| **RN10** | **Revalidação Atômica no Mock Checkout (`UC05`)** | `SELECT stock_quantity, price FROM products WHERE sku = :sku FOR UPDATE` no instante do clique | Se o estoque zerou ou o preço mudou entre a exibição do card e o clique em `Comprar agora`, o endpoint retorna `HTTP 409` (`OUT_OF_STOCK` ou `PRICE_CHANGED`) com os valores atuais em vez de confirmar pedido inválido. | `R09` |

---

## 2. Fluxo Decisório do Motor de *Upsell* e *Cross-sell* (`B04` / `M04`)

```mermaid
flowchart TD
    START(["Produto Base Identificado na Conversa<br/>(ex.: Airfryer 4L — R$ 499,90 | 220V)"]) --> CHECK_NEED{"Usuário expressou demanda<br/>acima da capacidade base<br/>ou pediu comparativo?"}

    CHECK_NEED -->|"Sim (ou Busca Consultiva)"| Q_UP["<b>Busca Candidatos de UPSELL (RN04)</b><br/>• Mesma subcategoria<br/>• Capacidade / Potência superior<br/>• Preço entre 100% e 135% do Base<br/>• Voltagem compatível (220V ou Bivolt)<br/>• stock_quantity > 0"]
    CHECK_NEED -->|"Apenas Dúvida / Compra Direta"| Q_CROSS

    Q_UP --> HAS_UP{"Encontrou candidato<br/>válido de Upsell?"}
    HAS_UP -->|"Sim"| ADD_UP["Anexa Card <b>UPSELL</b><br/>(ex.: Airfryer Pro 5.5L — R$ 629,90)<br/>+ Justificativa Técnica"]
    HAS_UP -->|"Não"| Q_CROSS

    ADD_UP --> Q_CROSS["<b>Busca Candidatos de CROSS-SELL (RN05)</b><br/>• Tabela product_relations (CROSS_SELL)<br/>• Compatibilidade física confirmada<br/>• Preço ≤ 40% do Produto Base<br/>• stock_quantity > 0"]

    Q_CROSS --> HAS_CROSS{"Encontrou candidato<br/>válido de Cross-sell?"}
    HAS_CROSS -->|"Sim"| ADD_CROSS["Anexa Card <b>CROSS_SELL</b><br/>(ex.: Kit Formas Silicone — R$ 79,90)<br/>+ Justificativa de Uso"]
    HAS_CROSS -->|"Não"| FINAL

    ADD_CROSS --> FINAL(["Monta Payload Final de Recomendação:<br/>[1. PRIMARY, 2. UPSELL, 3. CROSS_SELL]<br/>(Máximo de 3 Product Cards por turno)"])

    style START fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style Q_UP fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style ADD_UP fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style Q_CROSS fill:#fff8e1,stroke:#f57f17,stroke-width:2px
    style ADD_CROSS fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style FINAL fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px
```

---

## 3. Fórmulas de *Scoring* de Recomendação (`EAP 4.4`)

### 3.1. Score de Ranking de *Upsell* ($S_{\text{upsell}}$)
Para cada candidato $u$ que satisfaz os filtros rígidos da **RN04**, o score é calculado como:

$$S_{\text{upsell}}(u)=0,50 \cdot sim(q,u)+0,30 \cdot gain(u)+0,20 \cdot pricefit(u)$$

- Prioriza o item que melhor responde à necessidade semântica do usuário, entrega ganho real de capacidade/potência e possui o acréscimo de preço mais próximo ao orçamento original.

### 3.2. Score de Ranking de *Cross-sell* ($S_{\text{cross}}$)
Para cada acessório/complemento $c$ que satisfaz os filtros rígidos da **RN05**:

$$S_{\text{cross}}(c) = 0,60 \cdot \text{PesoRelação}(\text{base}, c) + 0,25 \cdot \text{Sim}_{\text{contexto}}(q, c) + 0,15 \cdot \left(1 - \frac{\text{Preço}(c)}{0,40 \cdot \text{Preço}(\text{base})}\right)$$

Onde $\text{PesoRelação}(\text{base}, c) \in [0, 1]$ é o peso de afinidade cadastrado na tabela `product_relations` (ex.: `0.95` para *Cesto de Silicone Compatível com Airfryer 4L/5.5L*).

---

## 4. Arquitetura em 3 Níveis de *Guardrails* (`EAP 4.3` | Mitigação de `R01`)

| Nível | Nome do Guardrail | Momento de Execução | Regra de Bloqueio / Sanitização |
| :---: | :--- | :---: | :--- |
| **G-IN** | **Input Guardrail (Anti-Injection & Escopo)** | Antes da busca vetorial | Bloqueia padrões de *Prompt Injection* (`"ignore previous instructions"`, `"você agora é..."`, `"altere o preço para R$ 1,00"`) e perguntas totalmente fora do domínio do e-commerce, retornando redirecionamento educado em `< 50 ms` (evento SSE `error` com `GUARDRAIL_BLOCKED`). |
| **G-RET** | **Retrieval Guardrail (Limiar de Evidência)** | Após a consulta ao `pgvector` | Exige `similarity_score >= 0.72` (limiar calibrável). Se `valid_chunks == []`, aborta a chamada livre ao LLM e aciona o template determinístico de *Fallback Seguro* (evento `error` com `LOW_SIMILARITY_FALLBACK`). O filtro `stock_quantity > 0` é aplicado às recomendações (`RN01`). |
| **G-OUT** | **Verificador Factual** | Antes de publicar cada sentença | Validação por SKU de grandezas e suporte da evidência; ambiguidades geram template seguro ainda no buffer privado. |

### 3.3. Definição operacional do ranking

`sim(q,u)` é o máximo cosseno entre a query e chunks ativos do candidato, limitado a [0,1]; zero se não há chunk. `gain(u) = min(1, max(0, (capacity_u-capacity_base)/capacity_base))` quando ambas capacidades são positivas; nos demais casos usa `min(1, max(0, (tier_u-tier_base)/4))`. `pricefit(u) = max(0, min(1, 1-(price_u-price_base)/(0.35*price_base)))`. Calcular com Decimal, sem arredondar intermediários; ordenar score decrescente, preço crescente e SKU lexicográfico crescente. `Sim_contexto` no cross-sell usa a mesma regra de sim; relação explícita fornece affinity_weight, compatibilidade por categoria comprovada sem relação recebe peso 0.5. Sem prova de compatibilidade, rejeitar. Não inferir ganho de litros para monitor. Base de preço deve ser positiva; nulos não satisfazem comparações de capacidade e a elegibilidade por tier permanece possível.
