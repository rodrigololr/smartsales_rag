# M02 — revisão e plano de correção

Base: PR #30 cc8cd6c; integração B04 0181b20 (inclui B01/B03) no merge a889524.

## Problemas e decisões

1. Idempotência normativa (architecture/03 e schema/02 §5) precisa sobreviver à perda do Redis e à queda do worker. Implementar repositório PostgreSQL para sessões, mensagens e reservas com estados RUNNING/COMPLETED/FAILED/EXPIRED. Transação por sessão, proprietário UUID e lease. Payload terminal por 24h; tombstone até encerramento/retenção máxima de 90 dias. Nenhum retry automático de uma reserva órfã.
2. Locks precisam de renovação e verificação de propriedade antes de persistir/publicar; perda de lease resulta em erro, nunca done(stop) sem histórico. Finalizar registro antes de done. Redis serve janela de 10 mensagens e estado transitório; PostgreSQL é autoridade.
3. Operações Redis de aquisição, snapshot e exclusão devem ser atômicas. Não criar chaves de turno em sessão excluída. Recarregar histórico sob a reserva do turno.
4. Estados formais do Gateway e cleanup protegido em desconexão/erro/cancelamento. Liberar reserva mesmo se construção do adaptador falhar.
5. Manter POST /sessions para restauração, como baseline/OpenAPI; documentar GET citado pela issue como decisão contratual pendente. Não alegar SLA real nem homologação B05.

## Execução e validação

- RED: regressões de sessão excluída, expiração de lock, Redis perdido após conclusão, worker órfão, payload conflitante, falha terminal, retomada entre instâncias e 24h/tombstone.
- GREEN: storage tipado + migração idempotente + integração no lifespan/Compose, lease guard e estados.
- Testes com PostgreSQL/Redis isolados, contratos SSE, backend integrado, Ruff/mypy e CI no head publicado.
- Entregar achados, correções, limitações e comentário de revisão sem postagem/merge automático.
