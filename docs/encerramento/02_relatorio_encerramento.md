# Relatório de Encerramento do Projeto (`EAP 7.3` · Marco `M5`)

> **Rascunho de 11/11/2026.** Estrutura e dados já conhecidos do repositório. Os
> campos **[PREENCHER]** dependem do fechamento da homologação (16/11 a 24/11) e do
> apontamento de horas. Aprovador: Antônio Rodrigo. Responsável: Walber.

## 1. Identificação

| Campo | Valor |
| :--- | :--- |
| Projeto | SmartSales RAG — assistente de vendas consultivas com RAG |
| Período planejado | 22/09/2026 a 24/11/2026 (9 semanas) |
| Gerente do projeto | Antônio Rodrigo |
| Product Owner | Walber |
| Tech Lead | Filipe |
| Data de encerramento | **[PREENCHER]** |

## 2. Balanço de escopo

Situação dos pacotes em 11/11/2026, pelas issues do repositório. Atualizar na data
de encerramento.

| Pacote | Entrega | Situação em 11/11 | Situação final |
| :---: | :--- | :--- | :---: |
| `G01`, `G03` | Specs SDD/TDD e baseline de gestão | Concluído (PR #1). | **[PREENCHER]** |
| `F01`, `F02` | Protótipos, setup e chat com SSE | Concluídos (PRs #23 e #24). | **[PREENCHER]** |
| `B01` | Docker, pgvector, ingestão do catálogo | Em andamento: Redis no compose, `product_relations` e `ingestion_jobs` implementados em branch, sem PR. | **[PREENCHER]** |
| `B02` | Busca híbrida e orquestração LLM | Implementado (PR #25). Falta comprovar o TTFT com medição. | **[PREENCHER]** |
| `B03` | Ingestão de manuais e guardrails | Implementado (PR #25); controle por `ingestion_jobs` e `catalog:version` em branch, sem PR. | **[PREENCHER]** |
| `B04` | Motor de recomendação | Motor mesclado (PR #22); ligação ao fluxo do RAG em branch, sem PR. | **[PREENCHER]** |
| `B05` | Golden Set e runner RAGAS | PR #26 aberto. | **[PREENCHER]** |
| `M01` | Gateway, contratos e segurança base | Aberto. *Rate limiting* não implementado. | **[PREENCHER]** |
| `M02` | SSE e sessões no Redis | SSE mesclado; sessões no Redis em branch, sem PR. | **[PREENCHER]** |
| `M03` | Cache e invalidação | Chave canônica mesclada; cache no Redis com revalidação em branch, sem PR. | **[PREENCHER]** |
| `M04`, `M05` | Catálogo, telemetria, checkout e feedback | Abertos. | **[PREENCHER]** |
| `F03`, `F04` | Citação, feedback, cards e painel | Abertos. | **[PREENCHER]** |
| `F05` | Testes E2E e aferição de KPIs | Suíte Playwright e sonda de SLA em branch, sem execução na pilha real. | **[PREENCHER]** |
| `G04` | Documentação técnica | README e guia de desenvolvimento atualizados em branch, sem PR. | **[PREENCHER]** |
| `G02` | Demo, relatório e lições | Este documento. | **[PREENCHER]** |

Mudanças de escopo aprovadas: **[PREENCHER: listar com data e aprovador, por
exemplo o uso do Google Gemini no lugar da OpenAI no MVP]**.

Itens não entregues e motivo: **[PREENCHER]**.

## 3. Balanço de prazo

| Marco | Data planejada | Data real | Desvio (dias úteis) |
| :---: | :---: | :---: | :---: |
| `M1` — Fundação e contratos | 02/10/2026 | **[PREENCHER]** | **[PREENCHER]** |
| `M2` — Streaming ponta a ponta | 16/10/2026 | **[PREENCHER]** | **[PREENCHER]** |
| `M3` — Ingestão, guardrails e cache | 29/10/2026 | **[PREENCHER]** | **[PREENCHER]** |
| `M4` — Recomendação e gate RAGAS | 10/11/2026 | **[PREENCHER]** | **[PREENCHER]** |
| `M5` — Entrega final e pitch | 24/11/2026 | **[PREENCHER]** | **[PREENCHER]** |

Em 11/11/2026 havia 16 issues abertas, entre elas pacotes com prazo vencido em
outubro (`B01`, `B02`, `M02`, `B03`, `M03`). Registrar aqui a causa do atraso e a
ação tomada: **[PREENCHER]**.

Índice de desempenho de prazo no encerramento: `SPI = EV / PV` =
**[PREENCHER]** (limiar de controle: ≥ 0,90).

## 4. Balanço de custos

O projeto tem dois cenários (`specs/diagrams_and_pm/09_quadro_custos_eac.md`): o
simulado de mercado, usado como linha de base, e o real acadêmico, sem desembolso.

| Categoria | Orçado (simulado) | Realizado (`AC`) | Variação |
| :--- | ---: | ---: | ---: |
| 1. Recursos humanos (1.440 h) | R$ 99.000,00 | **[PREENCHER: horas apontadas × valor-hora]** | **[PREENCHER]** |
| 2. Materiais, serviços e aquisições cloud | R$ 3.500,00 | **[PREENCHER]** | **[PREENCHER]** |
| 3. Maquinário, infraestrutura e ferramental | R$ 2.655,00 | **[PREENCHER]** | **[PREENCHER]** |
| 4. Reserva de contingência (10%) | R$ 10.515,50 | **[PREENCHER: quanto foi consumido]** | **[PREENCHER]** |
| **Total (`BAC`)** | **R$ 115.670,50** | **[PREENCHER]** | **[PREENCHER]** |

| Indicador | Fórmula | Valor | Limiar |
| :--- | :--- | :---: | :---: |
| Valor agregado (`EV`) | % concluído × `BAC` | **[PREENCHER]** | — |
| Custo real (`AC`) | soma do realizado | **[PREENCHER]** | — |
| `CPI` | `EV / AC` | **[PREENCHER]** | ≥ 0,95 |
| Estimativa no término (`EAC`) | `BAC / CPI` | **[PREENCHER]** | — |
| Variação no término (`VAC`) | `BAC − EAC` | **[PREENCHER]** | — |

Custo real no cenário acadêmico: R$ 0,00 planejado. Confirmar se houve gasto com a
chave do provedor de IA: **[PREENCHER]**.

## 5. Árvore de qualidade

Metas de `specs/diagrams_and_pm/10_qualidade_arvore_metricas.md`.

| Métrica | Meta | Medido | Atendida | Evidência |
| :--- | :---: | :---: | :---: | :--- |
| Fidelidade do RAG | ≥ 0,85 | **[PREENCHER]** | **[ ]** | Relatório RAGAS (`B05`). |
| Precisão das respostas técnicas | ≥ 90% | **[PREENCHER]** | **[ ]** | Gabarito do Golden Set. |
| Taxa de alucinação | ≤ 5% | **[PREENCHER]** | **[ ]** | Relatório RAGAS. |
| `P@5` | ≥ 0,80 | **[PREENCHER]** | **[ ]** | Relatório RAGAS. |
| Aderência aos filtros de negócio | 100% | **[PREENCHER]** | **[ ]** | Testes de recomendação e E2E-02. |
| TTFT p95 | ≤ 2 s | **[PREENCHER]** | **[ ]** | `python -m app.telemetry.sla_probe`. |
| Tempo total p95 | ≤ 8 s | **[PREENCHER]** | **[ ]** | `sla_probe`. |
| Taxa de acerto do cache | ≥ 30% | **[PREENCHER]** | **[ ]** | `sla_probe` com perguntas recorrentes. |
| Disponibilidade do chat | ≥ 99% | **[PREENCHER]** | **[ ]** | Monitoramento da homologação. |
| Taxa de erro da API | ≤ 1% | **[PREENCHER]** | **[ ]** | Logs do gateway. |
| Aprovação das respostas | ≥ 80% | **[PREENCHER]** | **[ ]** | `feedback_logs` (depende do `M04`). |
| Cliques em "Comprar agora" | ≥ 10% dos cards | **[PREENCHER]** | **[ ]** | `checkout_events` (depende do `M05`). |
| Cobertura de testes | ≥ 70% | **[PREENCHER]** | **[ ]** | CI da `develop`. |
| Defeitos críticos abertos | 0 | **[PREENCHER]** | **[ ]** | Issues com rótulo de defeito. |
| `SPI` | ≥ 0,90 | **[PREENCHER]** | **[ ]** | Seção 3. |
| Itens aceitos na *Sprint Review* | ≥ 90% | **[PREENCHER]** | **[ ]** | Atas das revisões (`C08`). |

Já registrado no repositório em 07/11/2026: com o Gemini, o TTFT medido ficou entre
1,3 s e 6 s (comentário da issue #7), acima da meta. Informar a medição final e a
decisão tomada: **[PREENCHER]**.

## 6. Riscos

| Risco | Ocorreu? | Impacto | Resposta aplicada |
| :--- | :---: | :--- | :--- |
| `R01` — alucinação técnica | **[PREENCHER]** | **[PREENCHER]** | Guardrails em três níveis e Golden Set. |
| `R2` — falha na ingestão do catálogo | **[PREENCHER]** | **[PREENCHER]** | `ingestion_jobs` com novas tentativas. |
| `R09` — preço ou estoque dessincronizado | **[PREENCHER]** | **[PREENCHER]** | Cards lidos do SQL e revalidação no *cache hit*. |
| Indisponibilidade ou latência do provedor de IA | **[PREENCHER]** | **[PREENCHER]** | *Fallback* `LLM_UNAVAILABLE` e provedor configurável. |
| **[PREENCHER: demais riscos de `16_gestao_riscos.md`]** | | | |

## 7. Aceite formal

| Entrega | Critério | Aceite | Data | Quem |
| :--- | :--- | :---: | :---: | :--- |
| Produto em homologação | Smoke test da demo aprovado. | **[ ]** | **[PREENCHER]** | Walber |
| Documentação técnica | Guia reproduzido em máquina limpa. | **[ ]** | **[PREENCHER]** | Filipe |
| Relatório de qualidade | Metas bloqueantes atendidas ou desvio aprovado. | **[ ]** | **[PREENCHER]** | Antônio Rodrigo |
| Encerramento do projeto | Este relatório e as lições aprendidas. | **[ ]** | **[PREENCHER]** | Patrocinador |

Pendências transferidas e para quem: **[PREENCHER]**.
