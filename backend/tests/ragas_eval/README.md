# Avaliação B05

Este runner executa `RAGOrchestrator`, busca `PostgresCatalog`/pgvector e
`RecommendationService`. A entrada do sistema não recebe resposta esperada nem
IDs de evidência rotulados. O juiz recebe a pergunta, a resposta efetivamente
publicada e os blocos de evidência que chegaram ao modelo.

O corpus versionado contém **50 casos reconstruídos do seed sintético** nas
categorias 12/10/10/10/8. Isso não equivale a auditoria de manuais de fabricantes
ou aceite do PO. As citações usam UUIDs reais resolvidos no banco a partir de
SKU, fonte, hash, página e índice; o manifesto não inventa UUIDs de produção.

## Ambiente

Use Python 3.12 e um banco PostgreSQL 16 com pgvector **isolado para avaliação**,
contendo somente o seed declarado. Não se conecta automaticamente ao banco para
validar fontes offline. As dependências de RAGAS não entram na imagem de produção.

```sh
uv venv
uv pip install -r requirements-dev.txt -r backend/requirements-eval.lock
cd backend
export RAGAS_DO_NOT_TRACK=true
python -m tests.ragas_eval.eval_runner --mode validate
```

Esse comando audita estrutura e fontes; retorna status **PENDING**, métricas N/A e
nenhuma homologação. `--mode validate --gate-check` deve sair com código **1**.
Configuração ausente, incompatível ou erro de execução sai com código **2**.

Configure localmente, sem versionar valores secretos:

- `DATABASE_URL`: banco isolado de avaliação.
- `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` (opcional).
- `EMBEDDING_MODEL`: modelo usado tanto na ingestão quanto na consulta, 1536 dimensões.
- `EVAL_JUDGE_API_KEY`, `EVAL_JUDGE_MODEL` (distinto do gerador),
  `EVAL_JUDGE_BASE_URL` (opcional).
- `EVAL_EMBEDDING_MODEL`: embeddings do juiz para Answer Relevance.
- `EVAL_EMBEDDING_API_KEY`, `EVAL_EMBEDDING_BASE_URL` (opcionais): provedor
  separado para esses embeddings. Necessário quando o juiz só oferece chat, como a
  API da DeepSeek. Sem `EVAL_EMBEDDING_API_KEY`, a chave e a URL do juiz são
  reutilizadas; com ela, a URL do juiz nunca é herdada (sem `EVAL_EMBEDDING_BASE_URL`,
  vale o endpoint padrão da OpenAI).

O gerador e seu modelo de embeddings usam o mesmo endpoint compatível com OpenAI,
conforme os adaptadores atuais de produção. O juiz precisa de chat compatível com
OpenAI; os embeddings vêm do mesmo endpoint ou do provedor configurado acima. Os parâmetros de chunking/geração e limiar devem
corresponder à versão que será homologada; a identidade inclui esses valores.
`JudgeSettings` lê variáveis de ambiente `EVAL_*`; exporte-as no shell. Chaves não
entram no relatório/checkpoint. URLs são sanitizadas e endpoints participam do hash.

## Execução real

A ingestão usa chamadas de embeddings; a avaliação usa as APIs do gerador e juiz.
Depois de configurar os provedores e um banco isolado:

```sh
python -m app.ingestion.run --catalog ../data/catalog.json --manuals ../data/manuals --relations ../data/product_relations.json
python -m tests.ragas_eval.eval_runner --mode live --gate-check --output ../.ragas-evaluation/report.json --checkpoint ../.ragas-evaluation/checkpoint.json
```

A identidade inclui commit/checkout limpo, código, dependências, configuração,
corpus, relações, IDs e hash dos vetores. O banco é verificado antes e depois da
execução. Conteúdo, fingerprint de ingestão, vetores inválidos, catálogo ou relações
diferentes do seed impedem aprovação. O cenário de estoque zero é um overlay de
leitura aplicado também ao serviço de recomendações; não atualiza o banco.

Checkpoints são atômicos e exclusivos da identidade da execução. Formato antigo,
modo/commit/configuração/corpus diferentes ou IDs incoerentes são rejeitados. Não
aproveitar o checkpoint antigo para continuar uma homologação nova. `--limit N`
serve para diagnóstico e sempre reprova o gate de execução completa.

As respostas de recusa/fallback também são verificadas. Texto parcial emitido
antes de uma falha continua entrando na checagem técnica, mesmo quando o Gateway
substitui a bolha. Bloqueios internos do G-OUT são contados separadamente.

## Gates e auditoria

Faithfulness e Answer Relevance usam RAGAS 0.3.0 com juiz separado, sem substituto
lexical. Erro, NaN, resposta vazia ou ausência de amostras reprovam. P@5 usa cinco
slots quando há pelo menos cinco evidências relevantes; com menos evidências,
precision@returned e recall exigem ambos >= 0,80. Ação e regras exigem 100%;
qualquer violação crítica publicada reprova, independentemente da média.

`expected_offers` lista ofertas obrigatórias. A política `required` permite outros
cards que satisfaçam RN01/RN04–RN06; `exact` exige correspondência exata quando o
caso especificar uma lista fechada. Não converter ausência de recomendação em
aprovação nem inventar ofertas observadas a partir do gabarito.

O gate exige integração da B04 corrigida (`0181b20` ou descendente), 50 IDs únicos
observados e auditoria humana registrada em `audit.json`. O arquivo começa como
`pending`; o responsável humano deve conferir as fontes e registrar aprovação,
identificação, data e hashes da fixture/corpus efetivamente auditados. Commitar a
auditoria antes da execução final. Não alterar limiares, referências ou pesos para
aprovar uma execução já observada; mudanças exigem nova versão e nova execução.

O CI das PRs valida o mecanismo offline, sem afirmar qualidade cognitiva. A Action
**B05 live quality evaluation (manual)** só chama APIs ao ser disparada com
`confirm_live=true` e configuração de secrets/variables correspondente. O relatório
continua reprovado se algum gate de qualidade/auditoria não passar. B05 e issue #14
permanecem pendentes até a execução real completa e aceite humano; retestar em F05.
