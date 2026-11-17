# Dependências das PRs abertas — 16/11/2026

Foram lidas as descrições e discussões das nove PRs e comparados os commits atuais.
Esta análise estabelece dependências; não substitui a revisão funcional de cada pacote.

| PR | Pacote | Dependência confirmada no histórico |
| --- | --- | --- |
| #27 | B01 — Redis, relações e jobs | develop |
| #28 | B03 — ingestão versionada | #27, mais 3 commits |
| #29 | B04 — recomendações no RAG | #28, mais 3 commits |
| #30 | M02 — sessões Redis | #29, mais 4 commits |
| #31 | M03 — cache e revalidação | #30, mais 3 commits |
| #32 | G04 — documentação técnica | #31, mais 3 commits |
| #33 | F05 — E2E e SLA | #32, mais 4 commits |
| #34 | G02 — encerramento | #33, mais 3 commits |
| #26 | B05 — Golden Set e RAGAS | branch separada, diverge da pilha em develop |

A pilha existente é B01 → B03 → B04 → M02 → M03 → G04 → F05 → G02.
Os heads de cada antecessora estão integralmente contidos na seguinte (`behind_by=0`).
Todos os alvos são develop. Correções novas precisam ser propagadas para as branches
posteriores antes de validá-las; não basta assumir que elas já incluem uma correção futura.

Para o trabalho de backend: revisar B01 antes de B03, depois B04 e B05.
A spec de B05 exige homologação no commit integrado após B04 e repetição após mudanças
semânticas até M5. M02 e M03 devem integrar a rodada final quando alterarem o fluxo avaliado.
É possível preparar a suíte antes; o relatório final deve registrar o commit efetivamente avaliado.
F05 usa os resultados da suíte e mede E2E/SLA; G02 deve consumir medições verificadas.

Fontes: https://github.com/rodrigololr/smartsales_rag/pulls (PRs #26 a #34),
comparações por SHA do GitHub e specs/tdd_and_quality/03_rag_golden_set_and_ragas_spec.md §5.
Nenhum merge, aprovação ou comentário foi publicado por esta análise.
