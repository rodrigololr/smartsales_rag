# Desenvolvimento local

Os incrementos B04, M03 e M02 implementam regras independentes já definidas em
`specs/01_BASELINE_REVISADA.md`. Os testes usam exemplos sintéticos e executam sem
banco, Redis ou credenciais de IA. As regras pertencem aos módulos de domínio;
adaptadores de infraestrutura deverão fornecer catálogo, contexto e stream.

## Preparação (Python 3.11+)

Na raiz do repositório, crie e ative um ambiente virtual. Exemplo no PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/Activate.ps1
python -m pip install -r requirements-dev.txt
```

Em Linux/macOS, ative com `source .venv/bin/activate`. A CI usa Python 3.12.
`requirements-dev.txt` fixa as ferramentas e inclui as dependências dos testes
documentais. Os módulos iniciais utilizam a biblioteca padrão do Python.

## Verificação

Na raiz, valide os contratos e exemplos documentais:

```powershell
python -m unittest discover -s tests -v
```

Entre em `backend/` e execute:

```powershell
python -m pytest tests/unit -v --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=70
python -m ruff check app tests/unit
python -m mypy app
```

Repita os mesmos comandos dentro de `middleend/`. Execute cada serviço em um
processo separado: ambos possuem seu próprio pacote `app`, como previsto na
arquitetura. O workflow `Python domain modules` executa essas verificações
independentemente para as duas camadas. `Specs and reference contracts` continua
validando a documentação e o OpenAPI.

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
