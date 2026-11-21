# Rituais Ágeis (`EAP 6.1` · `C02`, `C03`, `C08`)

> **Nota.** Campos marcados como *declarado pelo GP* foram preenchidos em 21/11/2026
> pelo Gerente do Projeto com base no plano (specs 02, 08, 09, 15, 16); não há registro
> primário anexado (atas, timesheets ou faturas).

> **Situação em 20/11/2026.** Datas planejadas de
> [`15_gestao_comunicacoes.md`](../../specs/diagrams_and_pm/15_gestao_comunicacoes.md) e
> [`08_cronograma_gantt.md`](../../specs/diagrams_and_pm/08_cronograma_gantt.md).
> As evidências de entrega vêm do GitHub e do Git. **Não há atas, pautas nem listas de
> presença no repositório**: a realização de cada ritual e quem participou constam
> como **(declarado pelo GP)**.

**Participantes declarados** (equipe da
[matriz RACI](../../specs/diagrams_and_pm/02_matriz_raci.md), seção 2): Antônio Rodrigo
(GP / Scrum Master), Walber (PO / co-GP), Filipe (Tech Lead / IA), Diogo (IA / Back),
Pablo (Middle-end / API), Well (Middle-end / SSE), Eduardo (Front-end) e Victor Hugo
(UX / Front / QA). *Planning* (`C02`) e *Review* (`C08`) conduzidas por Walber com os
oito integrantes; *dailies* (`C03`) conduzidas por Antônio Rodrigo com a equipe de
desenvolvimento e QA (declarado pelo GP).

## 1. Calendário planejado

| Sprint | Janela | Dias úteis | *Sprint Planning* (`C02`) | *Sprint Review* + retrospectiva (`C08`) | Marco |
| :---: | :---: | :---: | :---: | :---: | :---: |
| Sprint 1 | 22/09 a 02/10/2026 | 9 | 22/09/2026 | 02/10/2026 | `M1` |
| Sprint 2 | 05/10 a 16/10/2026 | 8 (sem 12/10 e 15/10) | 05/10/2026 | 16/10/2026 | `M2` |
| Sprint 3 | 19/10 a 30/10/2026 | 9 (sem 28/10) | 19/10/2026 | 30/10/2026 | `M3` (29/10) |
| Sprint 4 | 03/11 a 13/11/2026 | 9 (02/11 é feriado) | 03/11/2026 | 13/11/2026 | `M4` (10/11) |
| Homologação | 16/11 a 24/11/2026 | 6 (sem 20/11) | — (não prevista) | Entrega final `C09` em 24/11/2026 | `M5` |

*Dailies* (`C03`, 15 min): todos os dias úteis de 22/09 a 24/11/2026, exceto 12/10,
15/10, 28/10, 02/11 e 20/11 — **41 dailies planejadas** (9 + 8 + 9 + 9 + 6).

## 2. Registro por sprint

Método: para cada janela de sprint, listam-se os PRs mesclados e as issues fechadas
entre a *Planning* e o último dia útil da janela, pelas datas `mergedAt` e
`closedAt` do GitHub. Commits sem merge aparecem só como atividade.

### 2.1. Sprint 1 (22/09 a 02/10/2026)

| Item | Planejado | Evidência no repositório |
| :--- | :--- | :--- |
| *Planning* | 22/09/2026 | Realizada em 22/09, junto com o *kick-off* `C01`; oito participantes. Comprometidos 5 itens: `G01`, `G03`, `B01`, `M01`, `F01` (declarado pelo GP). |
| *Review* | 02/10/2026 (`M1`) | Realizada em 02/10; 0 de 5 itens aceitos, `M1` não atingido; retrospectiva: carga das avaliações AB1 da UFAL (até 25/09) e repositório ainda não criado; os 5 itens passam para a Sprint 2 (declarado pelo GP). |
| *Dailies* | 9 | 9 realizadas (declarado pelo GP). |
| Pacotes previstos | `G01`, `G03`, `B01`, `M01`, `F01` | Nenhum PR mesclado e nenhuma issue fechada. O primeiro commit do repositório é de 21/10/2026. |

### 2.2. Sprint 2 (05/10 a 16/10/2026)

| Item | Planejado | Evidência no repositório |
| :--- | :--- | :--- |
| *Planning* | 05/10/2026 | Realizada em 05/10; oito participantes. Comprometidos 8 itens: `B02`, `M02`, `F02` e os 5 remanescentes da Sprint 1 (declarado pelo GP). |
| *Review* | 16/10/2026 (`M2`) | Realizada em 16/10; 0 de 8 itens aceitos, `M2` não atingido; retrospectiva: priorizar a criação do repositório e das specs SDD/TDD na Sprint 3 (declarado pelo GP). |
| *Dailies* | 8 | 8 realizadas (declarado pelo GP). |
| Pacotes previstos | `B02`, `M02`, `F02` | Nenhum PR mesclado, nenhuma issue fechada e nenhum commit na janela. |

### 2.3. Sprint 3 (19/10 a 30/10/2026)

| Item | Planejado | Evidência no repositório |
| :--- | :--- | :--- |
| *Planning* | 19/10/2026 | Realizada em 19/10; oito participantes. Comprometidos 11 itens: `B03`, `M03`, `F03` e os 8 remanescentes; meta da sprint: repositório e specs SDD/TDD (declarado pelo GP). |
| *Review* | 30/10/2026 (`M3`) | Realizada em 30/10; 0 de 11 itens aceitos (specs de 22/10 ainda sem merge), `M3` não atingido; retrospectiva: mesclar a baseline na Sprint 4 e acionar pareamento no caminho crítico (declarado pelo GP). |
| *Dailies* | 9 | 9 realizadas (declarado pelo GP). |
| Pacotes previstos | `B03`, `M03`, `F03` | Nenhum PR mesclado e nenhuma issue fechada. Atividade: primeiro commit (21/10) e 9 commits de specs SDD/TDD e gestão em 22/10 (`ae96681`, `f43fd01`, `fec6246` e outros), mesclados só na Sprint 4 pelo PR #1. |

### 2.4. Sprint 4 (03/11 a 13/11/2026)

| Item | Planejado | Evidência no repositório |
| :--- | :--- | :--- |
| *Planning* | 03/11/2026 | Realizada em 03/11 (mesmo dia do merge do PR #1); oito participantes. Comprometidos 18 itens: os 7 previstos para a sprint e os 11 remanescentes; acionado o pareamento por duplas no caminho crítico (declarado pelo GP). |
| *Review* | 13/11/2026 (`M4` em 10/11) | Realizada em 13/11; 4 de 18 itens aceitos (`G01`, `G03`, `F01`, `F02`), demonstração do MVP do chat RAG na `develop`; `M4` não atingido; retrospectiva: troca para o Gemini e TTFT acima da meta (`R02`) (declarado pelo GP). |
| *Dailies* | 9 | 9 realizadas (declarado pelo GP). |
| Pacotes previstos | `B04`, `B05`, `M04`, `M05`, `F04`, `G04`, início de `F05` | Ver PRs e issues abaixo. |

| Data | Evidência | Pacote |
| :---: | :--- | :---: |
| 03/11 | [PR #1](https://github.com/rodrigololr/smartsales_rag/pull/1) mesclado na `main` (specs SDD/TDD e baseline de gestão); issues #2 e #3 fechadas. | `G01`, `G03` |
| 07/11 | [PR #22](https://github.com/rodrigololr/smartsales_rag/pull/22) mesclado: fundações de recomendação, cache e SSE. | `B04`, `M02`, `M03` (parcial) |
| 07/11 | [PR #23](https://github.com/rodrigololr/smartsales_rag/pull/23) mesclado; issue #6 fechada. | `F01` |
| 07/11 | [PR #25](https://github.com/rodrigololr/smartsales_rag/pull/25) mesclado na branch do `F02` (MVP do chat RAG); chegou à `develop` com o PR #24. | `B01`–`B03`, `M01`, `M02` (parcial) |
| 10/11 | [PR #24](https://github.com/rodrigololr/smartsales_rag/pull/24) mesclado; issue #9 fechada. | `F02` |
| 11/11 | Commits de `B01`, `B03`, `B04`, `M02`, `M03`, `G04`, `F05` e `G02` em branches de feature (sem merge na janela). | — |

### 2.5. Homologação (16/11 a 24/11/2026)

| Item | Planejado | Evidência no repositório |
| :--- | :--- | :--- |
| *Dailies* | 6 | 4 realizadas até 19/11 (16, 17, 18 e 19/11); 23/11 e 24/11 previstas (declarado pelo GP). |
| Entrega final (`C09`) | 24/11/2026 | Pendente (data futura em 20/11). |
| Pacotes previstos | `F05`, `G02`, reserva | Ver PRs e issues abaixo. |

| Data | Evidência | Pacote |
| :---: | :--- | :---: |
| 16/11 | Correções de revisão em `B01`, `B03`, `B04`, `B05`, `M02`, `M03` e `G04` (31 commits). | — |
| 19/11 | PRs mesclados: [#26](https://github.com/rodrigololr/smartsales_rag/pull/26) (`B05`), [#27](https://github.com/rodrigololr/smartsales_rag/pull/27) (`B01`), [#28](https://github.com/rodrigololr/smartsales_rag/pull/28) (`B03`), [#29](https://github.com/rodrigololr/smartsales_rag/pull/29) (`B04`), [#30](https://github.com/rodrigololr/smartsales_rag/pull/30) (`M02`), [#31](https://github.com/rodrigololr/smartsales_rag/pull/31) (`M03`), [#32](https://github.com/rodrigololr/smartsales_rag/pull/32) (`G04`), [#33](https://github.com/rodrigololr/smartsales_rag/pull/33) (`F05`, parcial) e [#34](https://github.com/rodrigololr/smartsales_rag/pull/34) (`G02`, rascunhos). | vários |
| 19/11 | Issues fechadas: #4 (`B01`), #7 (`B02`), #8 (`M02`), #10 (`B03`), #11 (`M03`), #13 (`B04`), #14 (`B05`) e #18 (`G04`). | vários |
| 19/11 | PRs abertos: [#35](https://github.com/rodrigololr/smartsales_rag/pull/35) (`M04`/`M05`) e [#36](https://github.com/rodrigololr/smartsales_rag/pull/36) (`M01`). | `M01`, `M04`, `M05` |

## 3. Leitura

- As quatro primeiras janelas de sprint não têm entrega mesclada. Todo o `EV` do
  projeto foi gerado a partir de 03/11 (Sprint 4) — ver
  [03_relatorios_evm_semanais.md](03_relatorios_evm_semanais.md).
- O repositório não mostra se os rituais aconteceram. Trabalho fora do GitHub nas
  Sprints 1 a 3: rituais, estudo da stack e rascunhos das specs que viraram os commits
  de 21 e 22/10, com cerca de 5 h por desenvolvedor por semana; sem artefato anexado
  (declarado pelo GP). Essa carga é a usada no `AC` de
  [03_relatorios_evm_semanais.md](03_relatorios_evm_semanais.md#3-custos-ac-cpi-eac).
- Indicador "Itens aceitos na *Sprint Review* ≥ 90%" (árvore de qualidade), com os
  itens comprometidos e aceitos declarados acima (remanescentes recontados a cada
  sprint): Sprint 1 0/5 (0%), Sprint 2 0/8 (0%), Sprint 3 0/11 (0%), Sprint 4 4/18
  (22%). Abaixo da meta de 90% em todas as sprints (declarado pelo GP; os aceites
  conferem com as datas de fechamento no GitHub).
