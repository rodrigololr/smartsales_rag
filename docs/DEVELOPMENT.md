# Desenvolvimento local

Os incrementos B04, M03 e M02 implementam regras independentes já definidas em
`specs/01_BASELINE_REVISADA.md`. Os testes usam exemplos sintéticos e executam sem
banco, Redis ou credenciais de IA. As regras pertencem aos módulos de domínio;
adaptadores de infraestrutura deverão fornecer catálogo, contexto e stream.

## Preparação (uv + Python 3.12)

Use o [uv](https://docs.astral.sh/uv/) para o ambiente Python. Na raiz:

```bash
uv venv --python 3.12
uv pip install -r requirements-dev.txt
```

`requirements-dev.txt` inclui as dependências de `backend/requirements.txt`,
`middleend/requirements.txt` e dos testes documentais. Execute cada serviço em um
processo separado: ambos possuem seu próprio pacote `app`, como previsto na
arquitetura.

## Verificação

Na raiz, valide os contratos e exemplos documentais:

```bash
uv run --no-project python -m unittest discover -s tests -v
```

Entre em `backend/` (e depois em `middleend/`) e execute:

```bash
uv run --no-project python -m pytest tests -v --cov=app --cov-branch --cov-fail-under=70
uv run --no-project python -m ruff check app tests
uv run --no-project python -m mypy app
```

O teste de integração do backend (`tests/integration`) usa um PostgreSQL com
pgvector descartável e só roda com `TEST_DATABASE_URL` definido:

```bash
docker run -d --name smartsales-pgvector-test -p 5544:5432 -e POSTGRES_USER=smartsales \
  -e POSTGRES_PASSWORD=smartsales -e POSTGRES_DB=smartsales pgvector/pgvector:pg16
TEST_DATABASE_URL=postgresql://smartsales:smartsales@localhost:5544/smartsales \
  uv run --no-project python -m pytest tests/integration -v
```

O workflow `Python domain modules` sobe esse banco como serviço e executa as
verificações das duas camadas com uv. `Specs and reference contracts` continua
validando a documentação e o OpenAPI.

## MVP sem Docker (três terminais)

```bash
# 1. backend (:8001) — precisa de DATABASE_URL e LLM_API_KEY (veja backend/.env.example)
cd backend && uv run --no-project python -m app.ingestion.run --catalog ../data/catalog.json --manuals ../data/manuals/
cd backend && uv run --no-project uvicorn app.main:app --port 8001
# 2. middleend (:8000)
cd middleend && uv run --no-project uvicorn app.main:app --port 8000
# 3. frontend (:3000) apontando para o gateway
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 pnpm -C frontend dev
```

Contrato interno: o middle-end chama `POST /internal/rag/stream` do backend com
`{sku, question, history}` e recebe NDJSON com os eventos internos do M02
(`token` só com sentenças aprovadas pelo G-OUT, `citations`, `error`, `end`).

## Frentes paralelas e limites

| Frente | Implementação | Entradas e responsabilidades do chamador |
| --- | --- | --- |
| B04 — recomendações | `backend/app/recommendation/` | Catálogo atual, similaridades de chunks ativos e provas de compatibilidade. O motor aplica estoque, voltagem, limites monetários e ranking determinístico com Decimal. |
| M03 — cache | `middleend/app/cache/` | Versões de catálogo/política, consulta, filtros resolvidos e histórico cronológico. A função calcula a identidade canônica; armazenamento e invalidação Redis serão conectados pelo Gateway. |
| M02 — SSE | `middleend/app/sse/` | Stream interno de texto previamente aprovado pelo G-OUT, estado de conexão e callbacks de persistência, fallback e liberação do turno. O módulo emite o protocolo público e trata término e falhas. |

O gerador SSE recebe conteúdo já validado. O adaptador do Backend é responsável
pelo G-OUT, pelas citações verificáveis e por converter falhas de transporte.
O serviço chamador persiste o resultado antes de `done`; resultados de erro
ficam fora do cache. A UI deverá descartar conteúdo parcial no evento `error`.

Dentro de `backend/`, a interface pública está em `app.recommendation`:
`Product`, `RecommendationCandidate`, `CompatibilityEvidence` e
`RecommendationEngine`. `select_upsell()` e `select_cross_sell()` retornam uma
recomendação ou `None`; `recommend()` retorna uma tupla com até três itens.
`requested_voltage` restringe as ofertas à preferência do comprador;
`allow_upsell=False` atende turnos sem intenção de upgrade. Um produto-base
esgotado pode servir de comparação, mas é excluído dos cards de compra.

Dentro de `middleend/`, importe `build_cache_key` de `app.cache`. A assinatura é
`build_cache_key(catalog_version, query, resolved_filters, history, policy_version)`.
Os filtros aceitos são `current_product_sku`, `preferred_voltage`, `category`,
`capacity_min` e `budget_max`; ausentes são tratados como `null`, desconhecidos
são rejeitados. O chamador fornece somente os turnos anteriores em ordem
cronológica e mantém uma representação numérica consistente entre chamadas.
A normalização de NFC e espaços se aplica exclusivamente à consulta.

O gerador é importado de `app.sse`. Sua interface é
`sse_chat_generator(request, session_id, message_id, backend_stream, cache_hit,
release_turn, fallback_products, complete_turn, *, started_at=None, clock=...)`.
O Backend fornece um iterador assíncrono com `aclose()` e eventos internos
terminados em `end`. `request.is_disconnected()` informa a conexão; `release_turn`
libera o lock; `fallback_products` consulta alternativas atuais. `complete_turn`
recebe `CompletedTurn` e persiste o snapshot aprovado de forma idempotente antes
do encerramento público. O serviço chamador também registra os turnos com falha,
sem armazená-los no cache. O adaptador HTTP fecha o gerador se parar de consumi-lo.

Estas entregas são incrementos dos pacotes, e ainda exigem adaptadores reais e
testes de integração para o aceite completo. O Golden Set de 50 casos precisa
ser curado sobre os manuais reais. Os testes unitários não medem RAGAS, latência
de rede, hit ratio de cache ou desempenho em produção.
