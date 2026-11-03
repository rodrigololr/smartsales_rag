# Especificação de Componente: Backend, Pipeline de Ingestão e Orquestrador RAG (`B01` a `B05`)

- **Pacotes da EAP / Rede CPM**: `EAP 4.1`, `4.2`, `4.3`, `4.4`, `5.1` (`B01`, `B02`, `B03`, `B04`, `B05`)
- **Responsáveis Técnicos**: **Filipe** (Tech Lead / Arquiteto & IA) e **Diogo** (Engenheiro de IA/ML & Back-end)
- **Stack**: Python 3.11+, FastAPI (Internal Worker), LangChain, OpenAI (`text-embedding-3-small`, `gpt-4o-mini`), SQLAlchemy 2.0 + `asyncpg`, `pgvector`, PyMuPDF / Unstructured, Pydantic v2, Pytest, RAGAS.

---

## 1. Arquitetura Interna dos Módulos do Backend (`backend/app/`)

```mermaid
flowchart LR
    subgraph INGEST ["1. Pipeline de Ingestão Offline (B01, B03)"]
        PDF["Seed local data/<br/>catalog.json/csv + Manuais PDF<br/>(CLI de ingestão — UC08)"] --> CLEAN["<b>TextCleaner & Normalizer</b><br/>Normaliza 127V/220V, Litros, Watts"]
        CLEAN --> CHUNK["<b>SemanticChunker</b><br/>500 tokens | overlap 50<br/>Preserva tabelas técnicas"]
        CHUNK --> EMB["<b>EmbeddingService</b><br/>text-embedding-3-small (1536d)"]
        EMB --> PG[("<b>PostgreSQL + pgvector</b><br/>products, manual_chunks (HNSW)<br/>& ingestion_jobs")]
        PG -.->|"Fim da ingestão"| VER["INCR catalog:version<br/>(Redis)"]
    end

    subgraph RUNTIME ["2. Pipeline de Inferência RAG Online (B02, B03, B04)"]
        REQ["Request do Gateway<br/>(query + history + filters)"] --> GIN["<b>InputGuardrail (G-IN)</b><br/>Anti-Injection & Classificador"]
        GIN --> HRET["<b>HybridRetriever (G-RET)</b><br/>Cosine >= limiar (0.72) + escopo do SKU"]
        HRET <--> PG
        HRET --> REC["<b>RecommendationEngine</b><br/>stock > 0: Primary + Upsell (<=+35%)<br/>+ 1 Cross-sell"]
        HRET --> GEN["<b>RAGStreamGenerator</b><br/>System Prompt + Context Chunks"]
        GEN --> GOUT["<b>OutputGuardrail (G-OUT)</b><br/>Valida Citações e Voltagem/Preço<br/>(retém e valida antes de publicar)"]
        REC & GOUT --> OUT["Stream Interno para o Gateway"]
    end

    style INGEST fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style RUNTIME fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
```

---

## 2. Especificação do Pipeline de Ingestão e Chunking (`B01`, `B03`)

### 2.0. Execução da Ingestão do Catálogo Local (`UC08`)
- Disparo pelo Operador/Lojista via CLI: `python -m app.ingestion.run --catalog data/catalog.json --manuals data/manuals/` (também usado no *seed* do `docker compose` e do CI).
- Etapas: validação de *schema* do catálogo (`UT-B01-01`) → *upsert* em `products`/`product_relations` → para cada PDF novo ou alterado (`content_hash` SHA-256 diferente) cria/atualiza `ingestion_jobs` (`PENDING → RUNNING → INDEXED`) → extração, *chunking*, *embeddings* e substituição transacional dos chunks da versão anterior (seção 6) → ao final, `INCR catalog:version` no Redis (`RN09`).
- Falhas: até `3` tentativas com *backoff* exponencial; esgotadas, o job vai para `NEEDS_INTERVENTION` e é listado na saída da CLI e no painel `/admin/metricas` (`UC09`). Produtos removidos do *seed* são marcados `is_active = FALSE` e seus *chunks* apagados.

### 2.1. Regras de Processamento de Manuais Técnicos (`EAP 4.2`)
1. **Extração por Página com Preservação de Tabelas**:
   - Cada página do PDF é extraída mantendo seu número original (`page_number >= 1`).
   - Tabelas de ficha técnica (*Dimensões, Potência, Tensão Elétrica, Consumo*) são convertidas em formato Markdown estruturado (`| Atributo | Valor |`) para evitar perda de alinhamento coluna-valor (mitigação direta da causa **Matéria-Prima** do [Diagrama de Ishikawa](../diagrams_and_pm/11_qualidade_diagrama_ishikawa.md)).
2. **Parâmetros de Segmentação (*Chunking*)**:
   - `chunk_size = 500 tokens` (medidos via `tiktoken` `cl100k_base`);
   - `chunk_overlap = 50 tokens`;
   - Separadores hierárquicos: `["\n## ", "\n### ", "\n\n", "\n", ". ", " "]`.
3. **Injeção de Cabeçalho de Contexto em Cada Chunk**:
   - Todo *chunk* salvo em `manual_chunks.content` recebe um prefixo canônico antes de gerar o vetor:
     ```text
     [PRODUTO: Airfryer SmartChef 4L Digital | SKU: AF-400-220V | VOLTAGEM: 220V | CAPACIDADE: 4.0L | MANUAL PÁG: 14]
     <conteúdo do trecho extraído>
     ```
   - Isso impede que um *chunk* do modelo `127V` seja confundido semanticamente com um *chunk* do modelo `220V` (`R01`).

---

## 3. Especificação do *System Prompt* Oficial Anti-Alucinação (`B02`, `B03`)

```text
Você é o Consultor Técnico Especialista do SmartSales RAG.
Sua missão é ajudar o cliente a tirar dúvidas técnicas e escolher o produto ideal usando EXCLUSIVAMENTE os dados fornecidos nos blocos <CATALOGO_SQL> e <CHUNKS_MANUAIS>.

REGRAS OBRIGATÓRIAS E INEGOCIÁVEIS:
1. FIDELIDADE ABSOLUTA: Responda apenas com base nas informações explícitas em <CATALOGO_SQL> e <CHUNKS_MANUAIS>. NUNCA invente, deduza ou extrapole voltagem (127V/220V/Bivolt), potência (W), capacidade (L), dimensões, compatibilidade de materiais ou preços.
2. CITAÇÃO OBRIGATÓRIA: Toda afirmação técnica extraída de um manual DEVE terminar com a citação exata no formato: [Fonte: <manual_title>, p. <page_number>].
3. INFORMAÇÃO AUSENTE: Se a pergunta exigir um dado técnico que não está presente em <CHUNKS_MANUAIS>, diga claramente: "Essa especificação específica não consta no manual técnico oficial deste modelo." Jamais tente adivinhar.
4. CONSULTORIA DE CAPACIDADE E VOLTAGEM:
   - Se o cliente informar uma necessidade superior à capacidade do produto consultado (ex.: família de 5+ pessoas para cesto de 4L), explique a limitação técnica e apresente a opção de UPSELL disponível em <RECOMENDACOES_SQL>.
   - Sempre destaque a voltagem exata do produto recomendado.
5. TOM E FORMATO: Seja objetivo, cordial, técnico e estruturado em tópicos curtos.
```

**Parâmetros de geração**: `LLM_MODEL=gpt-4o-mini` (*snapshot* fixado — `R14`), `temperature = 0.2`, `max_tokens = 600`, `stream = True`; *timeout* de `3 s` até o 1º token com **1** nova tentativa (`RNF07`).

---

## 4. Contratos Internos Pydantic v2 (`backend/app/models/schemas.py`)

```python
from decimal import Decimal
from typing import Annotated, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, PlainSerializer

Money = Annotated[Decimal, PlainSerializer(float, when_used="json")]

class RetrievedChunk(BaseModel):
    chunk_id: UUID
    sku: str
    manual_title: str
    page_number: int = Field(ge=1)
    section_title: Optional[str] = None
    content: str
    similarity_score: float = Field(ge=0.0, le=1.0)

class ProductRecommendation(BaseModel):
    sku: str
    name: str
    price: Money = Field(gt=0, max_digits=10, decimal_places=2)
    stock_quantity: int = Field(gt=0)
    voltage: Literal["127V", "220V", "BIVOLT", "N/A"]
    capacity_liters: Optional[float] = None
    power_watts: Optional[int] = None
    image_url: str
    marketplace: Literal["AMAZON", "MERCADO_LIVRE", "SHOPEE", "LOJA_OFICIAL"]
    checkout_url: str
    recommendation_type: Literal["PRIMARY", "UPSELL", "CROSS_SELL"]
    badge_label: str
    justification: str

class GuardrailCheckResult(BaseModel):
    passed: bool
    violation_code: Optional[Literal[
        "PROMPT_INJECTION",
        "OUT_OF_DOMAIN",
        "LOW_SIMILARITY_SCORE",
        "VOLTAGE_MISMATCH",
        "PRICE_MISMATCH",
        "MISSING_CITATION",
        "CAPACITY_MISMATCH", "POWER_MISMATCH", "UNSUPPORTED_CLAIM"
    ]] = None
    safe_fallback_response: Optional[str] = None
```

**Mapeamento `violation_code` → evento SSE** (ver [`03_openapi_and_sse_contracts.md`](../architecture/03_openapi_and_sse_contracts.md)):

| `violation_code` | Guardrail | Evento SSE emitido |
| :--- | :---: | :--- |
| `PROMPT_INJECTION`, `OUT_OF_DOMAIN` | `G-IN` | `error` com `code = "GUARDRAIL_BLOCKED"` |
| `LOW_SIMILARITY_SCORE` | `G-RET` | `error` com `code = "LOW_SIMILARITY_FALLBACK"` + `recommendations` (similares em estoque) |
| `VOLTAGE_MISMATCH`, `PRICE_MISMATCH`, `MISSING_CITATION`, `CAPACITY_MISMATCH`, `POWER_MISMATCH`, `UNSUPPORTED_CLAIM` | `G-OUT` | Bloqueia a sentença privada e publica somente template validado |

---

## 5. Especificação do Verificador Factual antes da Publicação (`OutputGuardrail` — `B03`)

O módulo retém cada sentença do LLM em buffer privado. Antes de publicar qualquer token dessa sentença, resolve as afirmações como `(sku, atributo, valor, unidade, chunk_id, página)`. Compara voltagem, preço, capacidade e potência com o registro daquele SKU e verifica que a evidência citada sustenta a afirmação, não apenas que o ID existe. Comparações são verificadas separadamente por SKU. O conjunto de preços dos cards não é um validador de associação.

Afirmações ambíguas, unidades não normalizáveis e fatos sem suporte são substituídos, antes da publicação, por template determinístico de ausência de evidência. Para compatibilidade, materiais e dimensões sem validador determinístico, publicar apenas extrato literal do trecho verificado ou fallback; nunca confiar somente no LLM como verificador. Recomendações SQL e chunks dos produtos recomendados são obtidos antes de montar o prompt e verificar suas afirmações.

O evento `correction` fica reservado à substituição por conteúdo seguro após falha de transporte; não é mecanismo para corrigir um fato incorreto já exposto. Código de violação interno inclui `CAPACITY_MISMATCH`, `POWER_MISMATCH`, `UNSUPPORTED_CLAIM`, além dos existentes. Toda medição de alucinação avalia os fatos do texto efetivamente publicado. As tentativas bloqueadas são contadas separadamente. O orçamento de 320 ms de entrada, 90 ms de recuperação e 1.150 ms de geração passa a incluir o buffer/validação da primeira sentença; TTFT nominal é alvo a medir, não garantia provada pela soma de estimativas. Homologação exige medir p95 até o primeiro token validado no navegador, sem desabilitar G-OUT para atingir SLA.

## 6. Ingestão versionada e publicação atômica

Cada manual possui `manual_source` estável e `manual_version` (SHA-256 do PDF). A extração e os embeddings são preparados fora da transação. Sob lock do produto, uma única transação apaga todos os chunks do `manual_source` substituído e insere o conjunto completo da nova versão; apenas depois marca o job INDEXED. Falha faz rollback e preserva integralmente a versão anterior. PDF menor não deixa páginas antigas. `INCR catalog:version` ocorre após commit; falha no Redis bloqueia leitura/escrita do cache até reconciliar a versão. Uma revisão nunca mistura versões na mesma busca.

Se não houver nenhuma sentença aprovada e a consulta não puder ser respondida com evidência, emitir error LOW_SIMILARITY_FALLBACK, recomendações determinísticas e end; o Gateway conclui com done(fallback). Nunca transmitir o rascunho rejeitado.
