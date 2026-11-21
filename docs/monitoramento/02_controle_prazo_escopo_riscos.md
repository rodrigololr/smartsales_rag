# Controle de Prazo, Escopo e Riscos (`EAP 6.2` · `C05`, `C06`)

> **Nota.** Campos marcados como *declarado pelo GP* foram preenchidos em 21/11/2026
> pelo Gerente do Projeto com base no plano (specs 02, 08, 09, 15, 16); não há registro
> primário anexado (atas, timesheets ou faturas).

> **Situação em 20/11/2026 (sexta-feira, feriado — dados até 19/11).** Datas
> planejadas de [`08_cronograma_gantt.md`](../../specs/diagrams_and_pm/08_cronograma_gantt.md)
> e da [rede CPM](../../specs/diagrams_and_pm/07_diagrama_rede_atividades_cpm.md); datas
> reais do GitHub. Riscos de [`16_gestao_riscos.md`](../../specs/diagrams_and_pm/16_gestao_riscos.md).
> Aprovador: Antônio Rodrigo. Responsável: Walber.
>
> **Governança.** O GP é autor, aprovador e fonte dos valores declarados deste
> controle. Recomenda-se que o PO Walber (aprovação de entregas na
> [matriz RACI](../../specs/diagrams_and_pm/02_matriz_raci.md)) revise e aprove, como
> segundo aprovador, todos os campos *declarado pelo GP*.

## 1. Caminho crítico (`B01 → B02 → B03 → B04 → F05 → G02`)

| Pacote | Término planejado | Data real de conclusão | Evidência | Desvio (dias úteis) |
| :---: | :---: | :---: | :--- | :---: |
| `B01` | 02/10/2026 | 19/11/2026 | Issue #4 fechada; [PR #27](https://github.com/rodrigololr/smartsales_rag/pull/27). Primeira entrega do backend na `develop` em 10/11 (PR #25 via #24). | **+30** |
| `B02` | 16/10/2026 | 19/11/2026 | Issue #7 fechada; código no [PR #25](https://github.com/rodrigololr/smartsales_rag/pull/25) (07/11). | **+22** |
| `B03` | 29/10/2026 | 19/11/2026 | Issue #10 fechada; [PR #28](https://github.com/rodrigololr/smartsales_rag/pull/28). | **+14** |
| `B04` | 10/11/2026 | 19/11/2026 | Issue #13 fechada; [PR #22](https://github.com/rodrigololr/smartsales_rag/pull/22) (07/11) e [PR #29](https://github.com/rodrigololr/smartsales_rag/pull/29). | **+7** |
| `F05` | 17/11/2026 | Pendente (projeção: 23/11) | Issue #19 aberta; suíte E2E e sonda de SLA no [PR #33](https://github.com/rodrigololr/smartsales_rag/pull/33) (19/11). Em 16/11: 6 testes E2E passando, 4 `fixme`, sonda com código 1 ([relatório de encerramento](../encerramento/02_relatorio_encerramento.md), seção 5). | ≥ +2 (em 19/11); +3 se fechar em 23/11 |
| `G02` | 23/11/2026 | Pendente (projeção: 24/11, depois de `F05`) | Issue #20 aberta; rascunhos no [PR #34](https://github.com/rodrigololr/smartsales_rag/pull/34). | +1 projetado (usa o dia de reserva) |
| `G04` (não crítico, folga 2d; predecessor de `G02`) | 13/11/2026 | 19/11/2026 | Issue #18 fechada; [PR #32](https://github.com/rodrigololr/smartsales_rag/pull/32). | **+4** (2 além da folga) |

Método do desvio: dias úteis entre o término planejado e a data real, pelo
calendário UFAL 2026.2 (sem fins de semana, 12/10, 15/10, 28/10, 02/11 e 20/11).
Conclusão = issue do pacote fechada.

**Leitura.** O caminho crítico não tem folga e atrasou desde o primeiro pacote:
`B01` concluiu 30 dias úteis depois do planejado. Os quatro pacotes de backend
fecharam no mesmo dia (19/11), ou seja, foram executados em paralelo e não em
sequência. Em 19/11, `F05` já passou do término planejado e `G02` depende dele.
`G04` não é crítico, mas fechou 4 dias úteis depois do planejado e consumiu a folga de
2 dias: pela rede, `G02` só poderia começar em 23/11 (primeiro dia útil depois de
19/11) e, com 3 dias de duração, terminaria em 25/11, depois do `M5`. `G02` só cabe em
24/11 porque os rascunhos foram adiantados em paralelo (PR #34, 19/11); a projeção de
fechamento está na seção 5.

Ações previstas na spec e registro:

| Ação de controle | Gatilho na spec | Registro |
| :--- | :--- | :--- |
| Alerta de risco crítico (`C06`) | Ao identificar desvio | Emitido por Antônio Rodrigo a Walber e Filipe em cada marco perdido: 02/10 (`M1`, `B01` atrasado), 16/10 (`M2`), 30/10 (`M3`) e 10/11 (`M4`); o patrocinador foi incluído a partir de 10/11, com o `M5` em risco (declarado pelo GP). |
| *Crashing* interno por pareamento em `B02`–`B04`/`F05` | `SPI < 0,90` | Acionado tardiamente na *Planning* de 03/11, e não em `S1` como a regra exige: Filipe e Diogo em `B01`–`B04` em paralelo; Pablo e Well em `M02`/`M03`; Eduardo e Victor Hugo em `F01`, `F02` e `F05`. De `S1` a `S6` os alertas saíram, mas não havia código em execução para parear (declarado pelo GP). O fechamento conjunto de `B01`–`B04` em 19/11 é coerente com essa execução em paralelo. |

## 2. Marcos

| Marco | Data planejada | Pacotes condicionantes | Situação em 19/11 |
| :---: | :---: | :--- | :--- |
| `M1` | 02/10/2026 | `G01`, `G03`, `B01`, `M01`, `F01` | **Não atingido**: `M01` aberto (issue #5; [PR #36](https://github.com/rodrigololr/smartsales_rag/pull/36) aberto). |
| `M2` | 16/10/2026 | `B02`, `M02`, `F02` | Atingido em 19/11/2026 pelo critério de issue fechada (+22 dias úteis). `B02` fica fora do `EV` conservador por não cumprir a meta de TTFT (seção 3). |
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
| `B02` | #7 | 16/10 | Concluído em 19/11 (issue fechada); **fora do `EV` conservador** | PR #25. A meta de TTFT não foi atingida (seção 4, `R02`), então o pacote não cumpre a DoD e não gera `EV` ([relatório EVM](03_relatorios_evm_semanais.md), seção 1.1). |
| `M02` | #8 | 16/10 | Concluído em 19/11 | PRs #22, #25 e #30 |
| `B03` | #10 | 29/10 | Concluído em 19/11 | PRs #25 e #28 |
| `M03` | #11 | 27/10 | Concluído em 19/11 | PRs #22 e #31 |
| `B04` | #13 | 10/11 | Concluído em 19/11 | PRs #22 e #29 |
| `B05` | #14 | 06/11 | Concluído em 19/11 (issue fechada, preparação); **fora do `EV` conservador** | [PR #26](https://github.com/rodrigololr/smartsales_rag/pull/26). **Inconsistência**: o próprio relatório B05 diz que a issue #14 "deve permanecer aberta até o aceite completo"; a execução real dos 50 casos e a auditoria humana do Golden Set (`audit.json`) estão pendentes. Por isso o pacote não gera `EV`. |
| `G04` | #18 | 13/11 | Concluído em 19/11 (+4 dias úteis; folga de 2 dias) | [PR #32](https://github.com/rodrigololr/smartsales_rag/pull/32) |
| `M01` | #5 | 01/10 | Em PR aberto | [PR #36](https://github.com/rodrigololr/smartsales_rag/pull/36) (*rate limiting*, envelope de erros) |
| `M04` | #15 | 09/11 | Em PR aberto (parte de catálogo) | [PR #35](https://github.com/rodrigololr/smartsales_rag/pull/35) (`Refs #15`); telemetria/métricas não cobertas por ele |
| `M05` | #16 | 05/11 | Em PR aberto | PR #35 (`Closes #16`) |
| `F03` | #12 | 23/10 | Parcial | Commit `343b677` (06/11, mesclado com o PR #23) implementa citações na camada *mock*; sem PR que feche a issue. |
| `F04` | #17 | 09/11 | Parcial | Commits `343b677`, `78958f7` e `bb09d31` (06/11) com cards e painel na camada *mock*; sem PR que feche a issue. |
| `F05` | #19 | 17/11 | Parcial | PR #33 |
| `G02` | #20 | 23/11 | Parcial | PR #34 (rascunhos) |
| `RES` | #21 | 24/11 | Em andamento | Esta pasta |

Resumo: 12 de 19 pacotes com issue fechada (63%), dos quais 10 aceitos no `EV`
conservador (sem `B02` e `B05`); 3 em PR aberto (`M01`, `M04`, `M05`) e 4 parciais
(`F03`, `F04`, `F05`, `G02`), sem contar `RES`.

Mudanças de escopo: o repositório registra a troca do provedor de IA de OpenAI para
Google Gemini no MVP (commit `525c1c8`, 07/11), sem registro de aprovação formal no
repositório. Aprovação (declarado pelo GP): aprovada por Antônio Rodrigo (GP) em
07/11/2026, data do commit `525c1c8`, com o PO Walber informado. Impacto declarado:

- **Custo:** a linha `2.1.1` da spec 09 (R$ 1.200,00, API de LLM e *embeddings*)
  passa a cobrir o Gemini no cenário simulado, sem alterar o `BAC`; no cenário real
  o gasto é R$ 0,00 (cota gratuita).
- **Qualidade:** o novo *embedding* exigiu recalibrar o limiar de similaridade de
  0,72 para 0,60 (issue #7). Evidência: o commit `525c1c8` (07/11) define
  `SIMILARITY_THRESHOLD=0.60` em `.env.example` e `backend/.env.example`, com a
  calibração na mensagem do commit (respostas corretas entre 0,64 e 0,72; fora do
  escopo perto de 0,47). O padrão em `backend/app/config.py` continua 0,72, e o
  `CLAUDE.md` da raiz e as specs ainda dizem 0,72: é mudança aplicada só por
  configuração, pendente de atualização formal da spec. Fidelidade e `P@5` seguem
  sem medição (B05 `PENDING`).
- **Risco:** aumentou a exposição em `R02` (TTFT de 1,3 s a 6 s) e `R13` (HTTP 429 da
  cota gratuita); ver seção 4.

Ver também a lição G4 em [lições aprendidas](../encerramento/03_licoes_aprendidas.md).

## 4. Riscos `R01` a `R20` — atualização

Regra: "Acionado" só quando há evidência no repositório de que o evento ocorreu;
"Resposta implementada" quando a ação preventiva existe no código mesclado, sem
afirmar que ela foi eficaz; "Sem evidência" quando o repositório não permite dizer
nada.

Reavaliação de probabilidade (`P`) e impacto (`I`), escala 1–5 da
[spec 16](../../specs/diagrams_and_pm/16_gestao_riscos.md) (declarado pelo GP). Só
mudam os riscos com evidência; os demais mantêm `P` e `I` da linha de base.

| Cód. | `P` × `I` original (Sev.) | `P` × `I` reavaliado (Sev.) | Motivo |
| :---: | :---: | :---: | :--- |
| `R02` | 3 × 5 (15) | 5 × 5 (25) | Ocorreu: TTFT p95 de 4.739 ms na sonda de 16/11. |
| `R13` | 3 × 5 (15) | 5 × 5 (25) | Ocorreu: 5 de 30 requisições com HTTP 429 em 16/11. |
| `R19` | 4 × 3 (12) | 5 × 5 (25) | Ocorreu: caminho crítico até 30 dias úteis atrasado e `M5` em risco. |
| `R14` | 2 × 5 (10) | 1 × 5 (5) | Provedor já trocado e fixado no MVP; nova troca até 24/11 é improvável. |
| `R20` | 3 × 3 (9) | 2 × 3 (6) | Golden Set de 50 casos mesclado (#26); resta a auditoria humana. |

| Cód. | Risco | Situação | Evidência |
| :---: | :--- | :--- | :--- |
| `R01` | Alucinação em especificações | Resposta implementada; eficácia **não medida** | Guardrails e citação em `B03` (#10) e verificador de cards por SKU em `B04` (#29). Fidelidade e taxa de alucinação ainda não medidas: [relatório B05](../../backend/tests/ragas_eval/RAGAS_HOMOLOGATION_REPORT.md) `PENDING`. |
| `R02` | Latência elevada no RAG | **Acionado** | TTFT entre 1,3 s e 6 s com o Gemini (comentário da issue #7, 07/11); sonda de 16/11 com TTFT p95 de 4.739 ms (teto 2.000 ms). Cache no Redis entregue (#31). |
| `R03` | *Chunks* irrelevantes | Resposta parcial; eficácia não medida | *Top-k* = 5 e limiar recalibrado para 0,60 com o embedding do Gemini (issue #7; `SIMILARITY_THRESHOLD=0.60` nos `.env.example` do commit `525c1c8`; spec e `CLAUDE.md` ainda em 0,72). `P@5` não medido (B05 `PENDING`). |
| `R04` | Falha na extração de tabelas de PDFs | Sem evidência | Os manuais do seed são `.txt` (`data/manuals/`); a extração de tabelas de PDF não foi exercitada. |
| `R05` | *Prompt injection* | Resposta parcial | Guardrail de entrada na `develop` (ajustado em `b341335`); *rate limiting* só no PR #36, aberto. |
| `R06` | Ambiguidade semântica | Sem evidência | — |
| `R07` | Queda do SSE no mobile | Resposta parcial | Botão "Tentar novamente" em `frontend/src/components/chat/AssistantMessage.tsx`. Reconexão automática não verificada. |
| `R08` | Esgotamento de conexões no PostgreSQL | Sem evidência | — |
| `R09` | Dessincronização de preço/estoque | Resposta implementada | `catalog:version` (#28), cards relidos do SQL (#29) e revalidação no *cache hit* (#31). Revalidação no checkout só no PR #35, aberto. |
| `R10` | Invalidação prematura do cache | Resposta implementada | Invalidação por `catalog:version` (#28, #31). |
| `R11` | Quebra de contratos OpenAPI | Resposta parcial | Testes de contrato da documentação (`tests/test_spec_contracts.py`); contratos do gateway no PR #36, aberto. |
| `R12` | Baixo CTR nas vitrines | Sem evidência | Depende de `M05`/`F04` (abertos); CTR não medido. |
| `R13` | Quota / *rate limit* da API de LLM | **Acionado** | Sonda de 16/11: 5 de 30 requisições falharam com `LLM_UNAVAILABLE` por HTTP 429 do provedor ([relatório de encerramento](../encerramento/02_relatorio_encerramento.md), seção 5). Uso da reserva de aquisições (R$ 900,00), declarado pelo GP: uso parcial de R$ 300,00 no cenário simulado em `S9`, para o pico de consumo de *tokens* da sonda de SLA e da execução do Golden Set; saldo de R$ 600,00. No cenário real o gasto foi R$ 0,00: os 429 são o limite da cota gratuita, que não foi ampliada. |
| `R14` | Mudança de versão do modelo de LLM | Não ocorreu como previsto | A troca OpenAI → Gemini (`525c1c8`) foi decisão da equipe, não depreciação; está registrada como mudança de escopo (seção 3). |
| `R15` | Vazamento de dados pessoais (LGPD) | Sem evidência | — |
| `R16` | *Scraping* / bots | Resposta pendente | *Rate limiting* no PR #36, aberto. |
| `R17` | Responsividade dos cards no mobile | Sem evidência | Depende de `F04` (aberto). |
| `R18` | Falha no tracking do checkout | Resposta pendente | Depende de `M05` (PR #35, aberto). |
| `R19` | Sobrecarga da squad / prazo | **Acionado (atraso)** | Nenhum merge até 03/11; caminho crítico entre 7 e 30 dias úteis atrasado (seção 1). Causa (declarado pelo GP): concentração das avaliações da UFAL (AB1 até 25/09) e da carga das demais disciplinas nas Sprints 1 a 3, com o repositório criado só em 21/10; agravante previsto na spec 16. |
| `R20` | Massa de testes insuficiente | Resposta parcial | Golden Set de 50 casos mesclado (#26); auditoria humana pendente (`backend/tests/ragas_eval/audit.json`). |

## 5. Reserva de contingência (24/11/2026)

| Item | Valor |
| :--- | :--- |
| Reserva planejada | 1 dia útil (24/11/2026), após o fim do desenvolvimento em 23/11 |
| Dias úteis restantes após 19/11 | 2: 23/11 (último dia de `G02` no plano; na projeção, fechamento de `F05`) e 24/11 (reserva + `M5`; na projeção, `G02` depois de `F05`) |
| Escopo aberto em 19/11 | `M01`, `M04`, `M05` (PRs abertos), `F03`, `F04`, `F05`, `G02` (parciais) |
| Probabilidade de cumprir `M5` | A estimativa de ≈ 73% do Gantt supunha o plano em dia e não vale mais. Decisão de corte de escopo (declarado pelo GP), sem nova estimativa numérica: entram na entrega final os pacotes cujas issues fecharem até 24/11; o que não fechar é entregue como parcial, fora do `EV`, e registrado no relatório de encerramento. |
| Uso da reserva | Consumida (declarado pelo GP): `F05` (caminho crítico) fecha em 23/11; 24/11 é usado para fechar `G02`, depois de `F05`, os PRs abertos #35 (`M04`/`M05`), #36 (`M01`), #37 (`M04`, métricas) e #38 (`RES`) e os pacotes de frontend `F03` e `F04`. Prioridade: `F05`, depois `G02`, `M01`, `M04`/`M05` e `F03`/`F04`. Aprovado por Antônio Rodrigo com o PO Walber e comunicado ao patrocinador (`C06`). A reserva financeira de contingência (R$ 10.515,50) não foi consumida; os pedidos de uso exigidos pela spec 09 (`EAC` acima do `PMB` em `S7`, `S8` e `S9`) estão no [relatório EVM](03_relatorios_evm_semanais.md#3-custos-ac-cpi-eac). |

Com sete pacotes ainda abertos e dois dias úteis, a reserva de 24/11 não cobre todo o
escopo restante. A decisão sobre o que entra na entrega final é do GP e do PO, com o
patrocinador, e deve ser registrada aqui e no
[relatório de encerramento](../encerramento/02_relatorio_encerramento.md).
