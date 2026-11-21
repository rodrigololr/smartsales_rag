# Controle de Prazo, Escopo e Riscos (`EAP 6.2` · `C05`, `C06`)

> **Situação em 20/11/2026 (sexta-feira, feriado — dados até 19/11).** Datas
> planejadas de [`08_cronograma_gantt.md`](../../specs/diagrams_and_pm/08_cronograma_gantt.md)
> e da [rede CPM](../../specs/diagrams_and_pm/07_diagrama_rede_atividades_cpm.md); datas
> reais do GitHub. Riscos de [`16_gestao_riscos.md`](../../specs/diagrams_and_pm/16_gestao_riscos.md).
> Aprovador: Antônio Rodrigo. Responsável: Walber.

## 1. Caminho crítico (`B01 → B02 → B03 → B04 → F05 → G02`)

| Pacote | Término planejado | Data real de conclusão | Evidência | Desvio (dias úteis) |
| :---: | :---: | :---: | :--- | :---: |
| `B01` | 02/10/2026 | 19/11/2026 | Issue #4 fechada; [PR #27](https://github.com/rodrigololr/smartsales_rag/pull/27). Primeira entrega do backend na `develop` em 10/11 (PR #25 via #24). | **+30** |
| `B02` | 16/10/2026 | 19/11/2026 | Issue #7 fechada; código no [PR #25](https://github.com/rodrigololr/smartsales_rag/pull/25) (07/11). | **+22** |
| `B03` | 29/10/2026 | 19/11/2026 | Issue #10 fechada; [PR #28](https://github.com/rodrigololr/smartsales_rag/pull/28). | **+14** |
| `B04` | 10/11/2026 | 19/11/2026 | Issue #13 fechada; [PR #22](https://github.com/rodrigololr/smartsales_rag/pull/22) (07/11) e [PR #29](https://github.com/rodrigololr/smartsales_rag/pull/29). | **+7** |
| `F05` | 17/11/2026 | Pendente | Issue #19 aberta; suíte E2E e sonda de SLA no [PR #33](https://github.com/rodrigololr/smartsales_rag/pull/33) (19/11). Em 16/11: 6 testes E2E passando, 4 `fixme`, sonda com código 1 ([relatório de encerramento](../encerramento/02_relatorio_encerramento.md), seção 5). | ≥ +2 (em 19/11) |
| `G02` | 23/11/2026 | Pendente | Issue #20 aberta; rascunhos no [PR #34](https://github.com/rodrigololr/smartsales_rag/pull/34). | Ainda no prazo |

Método do desvio: dias úteis entre o término planejado e a data real, pelo
calendário UFAL 2026.2 (sem fins de semana, 12/10, 15/10, 28/10, 02/11 e 20/11).
Conclusão = issue do pacote fechada.

**Leitura.** O caminho crítico não tem folga e atrasou desde o primeiro pacote:
`B01` concluiu 30 dias úteis depois do planejado. Os quatro pacotes de backend
fecharam no mesmo dia (19/11), ou seja, foram executados em paralelo e não em
sequência. Em 19/11, `F05` já passou do término planejado e `G02` depende dele.

Ações previstas na spec e registro:

| Ação de controle | Gatilho na spec | Registro |
| :--- | :--- | :--- |
| Alerta de risco crítico (`C06`) | Ao identificar desvio | ⚠️ A preencher pelo GP (data e destinatários de cada alerta). |
| *Crashing* interno por pareamento em `B02`–`B04`/`F05` | `SPI < 0,90` | ⚠️ A preencher pelo GP (se foi acionado, quando e quem pareou). |

## 2. Marcos

| Marco | Data planejada | Pacotes condicionantes | Situação em 19/11 |
| :---: | :---: | :--- | :--- |
| `M1` | 02/10/2026 | `G01`, `G03`, `B01`, `M01`, `F01` | **Não atingido**: `M01` aberto (issue #5; [PR #36](https://github.com/rodrigololr/smartsales_rag/pull/36) aberto). |
| `M2` | 16/10/2026 | `B02`, `M02`, `F02` | Atingido em 19/11/2026 (+22 dias úteis). |
| `M3` | 29/10/2026 | `B03`, `M03`, `F03` | **Não atingido**: `F03` aberto (issue #12). |
| `M4` | 10/11/2026 | `B04`, `B05`, `M04`, `M05`, `F04` | **Não atingido**: `M04`, `M05` e `F04` abertos. Além disso, o gate RAGAS do commit integrado não foi executado ([relatório B05](../../backend/tests/ragas_eval/RAGAS_HOMOLOGATION_REPORT.md): status `PENDING`); pela regra da seção 4.2 do Gantt, `M4` fica atrasado e aciona `C06`. |
| `M5` | 24/11/2026 | `G04`, `F05`, `G02` + reserva | Em risco (ver seção 5). |

## 3. Escopo por pacote

Legenda: **Concluído** = issue fechada; **Em PR aberto** = há PR aberto que fecha a
issue; **Parcial** = há código mesclado, mas a issue segue aberta; **Pendente** =
sem PR.

| Pacote | Issue | Término planejado | Situação em 19/11 | Evidência |
| :---: | :---: | :---: | :--- | :--- |
| `G01` | #2 | 29/09 | Concluído em 03/11 | [PR #1](https://github.com/rodrigololr/smartsales_rag/pull/1) |
| `G03` | #3 | 02/10 | Concluído em 03/11 | PR #1 |
| `F01` | #6 | 01/10 | Concluído em 07/11 | [PR #23](https://github.com/rodrigololr/smartsales_rag/pull/23) |
| `F02` | #9 | 13/10 | Concluído em 10/11 | [PR #24](https://github.com/rodrigololr/smartsales_rag/pull/24) |
| `B01` | #4 | 02/10 | Concluído em 19/11 | PRs #25 e #27 |
| `B02` | #7 | 16/10 | Concluído em 19/11 | PR #25. A meta de TTFT não foi atingida (seção 4, `R02`). |
| `M02` | #8 | 16/10 | Concluído em 19/11 | PRs #22, #25 e #30 |
| `B03` | #10 | 29/10 | Concluído em 19/11 | PRs #25 e #28 |
| `M03` | #11 | 27/10 | Concluído em 19/11 | PRs #22 e #31 |
| `B04` | #13 | 10/11 | Concluído em 19/11 | PRs #22 e #29 |
| `B05` | #14 | 06/11 | Concluído em 19/11 (preparação) | [PR #26](https://github.com/rodrigololr/smartsales_rag/pull/26). **Inconsistência**: o próprio relatório B05 diz que a issue #14 "deve permanecer aberta até o aceite completo"; a execução real dos 50 casos e a auditoria humana do Golden Set (`audit.json`) estão pendentes. |
| `G04` | #18 | 13/11 | Concluído em 19/11 | [PR #32](https://github.com/rodrigololr/smartsales_rag/pull/32) |
| `M01` | #5 | 01/10 | Em PR aberto | [PR #36](https://github.com/rodrigololr/smartsales_rag/pull/36) (*rate limiting*, envelope de erros) |
| `M04` | #15 | 09/11 | Em PR aberto (parte de catálogo) | [PR #35](https://github.com/rodrigololr/smartsales_rag/pull/35) (`Refs #15`); telemetria/métricas não cobertas por ele |
| `M05` | #16 | 05/11 | Em PR aberto | PR #35 (`Closes #16`) |
| `F03` | #12 | 23/10 | Parcial | Commit `343b677` (06/11, mesclado com o PR #23) implementa citações na camada *mock*; sem PR que feche a issue. |
| `F04` | #17 | 09/11 | Parcial | Commits `343b677`, `78958f7` e `bb09d31` (06/11) com cards e painel na camada *mock*; sem PR que feche a issue. |
| `F05` | #19 | 17/11 | Parcial | PR #33 |
| `G02` | #20 | 23/11 | Parcial | PR #34 (rascunhos) |
| `RES` | #21 | 24/11 | Em andamento | Esta pasta |

Resumo: 12 de 19 pacotes concluídos (63%), 3 em PR aberto (`M01`, `M04`, `M05`) e
4 parciais (`F03`, `F04`, `F05`, `G02`), sem contar `RES`.

Mudanças de escopo: o repositório registra a troca do provedor de IA de OpenAI para
Google Gemini no MVP (commit `525c1c8`, 07/11), sem registro de aprovação formal.
⚠️ A preencher pelo GP: aprovador, data e impacto em custo e qualidade (ver também
lição G4 em [lições aprendidas](../encerramento/03_licoes_aprendidas.md)).

## 4. Riscos `R01` a `R20` — atualização

Regra: "Acionado" só quando há evidência no repositório de que o evento ocorreu;
"Resposta implementada" quando a ação preventiva existe no código mesclado, sem
afirmar que ela foi eficaz; "Sem evidência" quando o repositório não permite dizer
nada. Probabilidade e impacto não foram reavaliados (⚠️ A preencher pelo GP).

| Cód. | Risco | Situação | Evidência |
| :---: | :--- | :--- | :--- |
| `R01` | Alucinação em especificações | Resposta implementada; eficácia **não medida** | Guardrails e citação em `B03` (#10) e verificador de cards por SKU em `B04` (#29). Fidelidade e taxa de alucinação ainda não medidas: [relatório B05](../../backend/tests/ragas_eval/RAGAS_HOMOLOGATION_REPORT.md) `PENDING`. |
| `R02` | Latência elevada no RAG | **Acionado** | TTFT entre 1,3 s e 6 s com o Gemini (comentário da issue #7, 07/11); sonda de 16/11 com TTFT p95 de 4.739 ms (teto 2.000 ms). Cache no Redis entregue (#31). |
| `R03` | *Chunks* irrelevantes | Resposta parcial; eficácia não medida | *Top-k* = 5 e limiar recalibrado para 0,60 com o embedding do Gemini (issue #7). `P@5` não medido (B05 `PENDING`). |
| `R04` | Falha na extração de tabelas de PDFs | Sem evidência | Os manuais do seed são `.txt` (`data/manuals/`); a extração de tabelas de PDF não foi exercitada. |
| `R05` | *Prompt injection* | Resposta parcial | Guardrail de entrada na `develop` (ajustado em `b341335`); *rate limiting* só no PR #36, aberto. |
| `R06` | Ambiguidade semântica | Sem evidência | — |
| `R07` | Queda do SSE no mobile | Resposta parcial | Botão "Tentar novamente" em `frontend/src/components/chat/AssistantMessage.tsx`. Reconexão automática não verificada. |
| `R08` | Esgotamento de conexões no PostgreSQL | Sem evidência | — |
| `R09` | Dessincronização de preço/estoque | Resposta implementada | `catalog:version` (#28), cards relidos do SQL (#29) e revalidação no *cache hit* (#31). Revalidação no checkout só no PR #35, aberto. |
| `R10` | Invalidação prematura do cache | Resposta implementada | Invalidação por `catalog:version` (#28, #31). |
| `R11` | Quebra de contratos OpenAPI | Resposta parcial | Testes de contrato da documentação (`tests/test_spec_contracts.py`); contratos do gateway no PR #36, aberto. |
| `R12` | Baixo CTR nas vitrines | Sem evidência | Depende de `M05`/`F04` (abertos); CTR não medido. |
| `R13` | Quota / *rate limit* da API de LLM | **Acionado** | Sonda de 16/11: 5 de 30 requisições falharam com `LLM_UNAVAILABLE` por HTTP 429 do provedor ([relatório de encerramento](../encerramento/02_relatorio_encerramento.md), seção 5). Uso da reserva de aquisições (R$ 900,00): ⚠️ A preencher pelo GP. |
| `R14` | Mudança de versão do modelo de LLM | Não ocorreu como previsto | A troca OpenAI → Gemini (`525c1c8`) foi decisão da equipe, não depreciação; está registrada como mudança de escopo (seção 3). |
| `R15` | Vazamento de dados pessoais (LGPD) | Sem evidência | — |
| `R16` | *Scraping* / bots | Resposta pendente | *Rate limiting* no PR #36, aberto. |
| `R17` | Responsividade dos cards no mobile | Sem evidência | Depende de `F04` (aberto). |
| `R18` | Falha no tracking do checkout | Resposta pendente | Depende de `M05` (PR #35, aberto). |
| `R19` | Sobrecarga da squad / prazo | **Acionado (atraso)** | Nenhum merge até 03/11; caminho crítico entre 7 e 30 dias úteis atrasado (seção 1). Causa não registrada no repositório: ⚠️ A preencher pelo GP. |
| `R20` | Massa de testes insuficiente | Resposta parcial | Golden Set de 50 casos mesclado (#26); auditoria humana pendente (`backend/tests/ragas_eval/audit.json`). |

## 5. Reserva de contingência (24/11/2026)

| Item | Valor |
| :--- | :--- |
| Reserva planejada | 1 dia útil (24/11/2026), após o fim do desenvolvimento em 23/11 |
| Dias úteis restantes após 19/11 | 2: 23/11 (último dia de `G02`) e 24/11 (reserva + `M5`) |
| Escopo aberto em 19/11 | `M01`, `M04`, `M05` (PRs abertos), `F03`, `F04`, `F05`, `G02` (parciais) |
| Probabilidade de cumprir `M5` | A estimativa de ≈ 73% do Gantt supunha o plano em dia e não vale mais. ⚠️ A preencher pelo GP: nova estimativa ou decisão de corte de escopo. |
| Uso da reserva | ⚠️ A preencher pelo GP: se a reserva será consumida, para qual pacote e quem aprovou (patrocinador, conforme `C06`). |

Com sete pacotes ainda abertos e dois dias úteis, a reserva de 24/11 não cobre todo o
escopo restante. A decisão sobre o que entra na entrega final é do GP e do PO, com o
patrocinador, e deve ser registrada aqui e no
[relatório de encerramento](../encerramento/02_relatorio_encerramento.md).
