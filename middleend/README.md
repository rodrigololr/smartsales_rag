# Gateway M02

Produção usa **PostgreSQL e Redis**. Configure `DATABASE_URL`, `REDIS_URL` e
`BACKEND_INTERNAL_URL`; `docker-compose.yml` já os fornece. O startup aplica a migração
idempotente de `app/db/schema.sql` sob advisory lock. A role do Gateway precisa das
permissões de criação/migração e leitura/escrita das tabelas `chat_*`.

Sessões anônimas expiram após 1800s de inatividade. A janela enviada ao Backend contém
10 mensagens (5 turnos completos). `POST /api/v1/sessions` com ID ativo recupera o
histórico inclusive após reinício do Gateway ou perda de chaves Redis. DELETE encerra
no SQL e remove a projeção Redis; um worker antigo não pode ressuscitar a sessão.

`client_request_id` identifica uma única execução por sessão. O mesmo payload concluído
ou falho reproduz o terminal com o mesmo `message_id`; payload diferente retorna 409.
Um pedido em execução retorna 409 + `Retry-After`. Falha/desconexão/worker órfão não
provoca regeneração automática: envie uma nova pergunta com novo ID para tentar de novo.
Antes de replay, cards são conferidos contra preço, estoque, atividade e atributos atuais do SQL.
Se houver divergência, o replay devolve fallback seguro com o mesmo ID e sem cards,
solicitando uma nova pergunta; não reinicia geração nem altera métricas lógicas.
Depois de 24h o payload é apagado e o ID retorna 410. A retenção máxima SQL é de 90 dias,
com manutenção periódica e verificação de validade em toda leitura.

O lock/lease de 60s recebe heartbeat a cada 10s; uma resposta longa mantém exclusão e
histórico. Perda de propriedade encerra o SSE com erro. O Gateway persiste mensagens,
terminal e métricas lógicas na mesma transação antes de `done`. Falhas usam somente
fallback seguro e não entram no contexto do próximo pedido.

Configurações adicionais (padrões):

| Variável | Valor |
| --- | --- |
| SESSION_TTL_SECONDS | 1800 |
| SESSION_HISTORY_MAX_MESSAGES | 10, par e >=2 |
| SESSION_LOCK_TTL_SECONDS | 60 |
| SESSION_HEARTBEAT_SECONDS | 10, menor que ambos os TTLs |
| SESSION_MAINTENANCE_SECONDS | 60 |
| SESSION_DB_CONNECT_TIMEOUT_SECONDS | 2 |
| SESSION_DB_QUERY_TIMEOUT_MS | 2000 |
| REDIS_SOCKET_TIMEOUT_SECONDS | 2 |
| REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS | 2 |
| BACKEND_FIRST_EVENT_TIMEOUT_SECONDS | 8, uma nova tentativa só em erro de conexão ou HTTP 5xx antes de qualquer evento |
| BACKEND_TIMEOUT_SECONDS | 30, timeout HTTP após início |

Retries automáticos do cliente Redis estão desativados. Indisponibilidade de storage
antes do SSE retorna 503 no envelope de erro; durante o SSE resulta em `error` e
`done(error)`, sem reconhecer sucesso não persistido. Nenhuma falha SQL ativa fallback
em memória. Sem DATABASE_URL, os adaptadores em memória/Redis são modos de desenvolvimento
e não atendem à durabilidade de produção. Não misture réplicas de modos diferentes.

Verificação local, a partir de `middleend/`, com serviços isolados configurados via
`TEST_DATABASE_URL` e `TEST_REDIS_URL`:

```sh
python -m pytest tests -q --cov=app --cov-branch --cov-fail-under=70
python -m ruff check app tests
python -m mypy app
```

Os testes não chamam provedores de IA. RAGAS/B05, revalidação de catálogo/M03 e SLA
ponta a ponta/F05 são validações separadas. Compatibilidade com Upstash e blackhole
real de rede ainda requer validação no ambiente alvo.
