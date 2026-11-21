# Relatórios EVM Semanais `S1`–`S9` (`EAP 6.3` · `C05`)

> **Nota.** Campos marcados como *declarado pelo GP* foram preenchidos em 21/11/2026
> pelo Gerente do Projeto com base no plano (specs 02, 08, 09, 15, 16); não há registro
> primário anexado (atas, timesheets ou faturas).

> **Reconstituídos em 20/11/2026.** Os relatórios semanais `C05` não estão no
> repositório; os números abaixo foram calculados retroativamente com a linha de base
> de [`09_quadro_custos_eac.md`](../../specs/diagrams_and_pm/09_quadro_custos_eac.md) e
> as datas reais do GitHub. Relatórios emitidos na época: não há cópia para anexar; o
> GP declara que o status semanal foi passado verbalmente ao PO e ao patrocinador
> (declarado pelo GP). Aprovador: Antônio Rodrigo. Responsável: Walber.

## 1. Método

### 1.1. Fórmulas

| Indicador | Fórmula | Limiar (spec 09, seção 4.2) |
| :--- | :--- | :---: |
| Valor planejado | `PV(t)` = valor acumulado da Curva S (spec 09, seção 4.1) | Linha de base |
| Orçamento do pacote | `BAC_p = BAC × d_p / 121` | — |
| Valor agregado | `EV(t) = Σ BAC_p` dos pacotes concluídos até a sexta-feira `t` | `EV ≥ 0,90 × PV` |
| Variação de prazo | `SV = EV − PV` | ≥ 0 |
| Índice de prazo | `SPI = EV / PV` | **≥ 0,90** |
| Custo real | `AC` = horas × valor-hora + serviços + reserva usada (seção 3) | `AC ≤ EV` |
| Índice de custo | `CPI = EV / AC` | ≥ 0,95 |
| Estimativa no término | `EAC = BAC / CPI` | ≤ R$ 115.670,50 |

- `BAC` = R$ 115.670,50 (spec 09, seção 3.4).
- `d_p` = duração planejada do pacote em dias úteis (Gantt, seção 3). A soma dos 19
  pacotes é 121 dias; `RES` (reserva) não recebe orçamento de trabalho. A spec 09 não
  distribui o orçamento por pacote, então o peso por duração é uma premissa deste
  relatório, confirmada pelo GP como critério oficial de distribuição do `BAC`
  (declarado pelo GP): não há horas estimadas por pacote na linha de base.
- Critério de conclusão (regra 0/100): o pacote só agrega valor quando a issue dele
  está fechada (DoD da spec 09: "apenas itens que cumpram a DoD"). PR mesclado com a
  issue aberta não conta. Para `G01` e `G03`, vale o merge do PR #1 (03/11), mesma
  data do fechamento das issues #2 e #3.

### 1.2. Orçamento por pacote

| Pacote | `d_p` | `BAC_p` (R$) | Pacote | `d_p` | `BAC_p` (R$) |
| :---: | :---: | ---: | :---: | :---: | ---: |
| `G01` | 6 | 5.735,73 | `B03` | 8 | 7.647,64 |
| `G03` | 3 | 2.867,86 | `M03` | 7 | 6.691,68 |
| `B01` | 9 | 8.603,59 | `F03` | 7 | 6.691,68 |
| `M01` | 8 | 7.647,64 | `B04` | 7 | 6.691,68 |
| `F01` | 8 | 7.647,64 | `M04` | 7 | 6.691,68 |
| `B02` | 8 | 7.647,64 | `B05` | 5 | 4.779,77 |
| `M02` | 8 | 7.647,64 | `F04` | 7 | 6.691,68 |
| `F02` | 7 | 6.691,68 | `M05` | 5 | 4.779,77 |
| — | — | — | `G04` | 3 | 2.867,86 |
| — | — | — | `F05` | 5 | 4.779,77 |
| — | — | — | `G02` | 3 | 2.867,86 |

Valor por dia útil: R$ 115.670,50 / 121 = R$ 955,95.

## 2. Consolidado

| Semana | Sexta-feira | Pacotes concluídos na semana | `EV` acumulado (R$) | `PV` acumulado (R$) | `SV` (R$) | `SPI` | Status |
| :---: | :---: | :--- | ---: | ---: | ---: | :---: | :---: |
| `S1` | 25/09 | — | 0,00 | 12.852,28 | −12.852,28 | **0,00** | Abaixo de 0,90 |
| `S2` | 02/10 | — | 0,00 | 25.704,56 | −25.704,56 | **0,00** | Abaixo de 0,90 |
| `S3` | 09/10 | — | 0,00 | 38.556,83 | −38.556,83 | **0,00** | Abaixo de 0,90 |
| `S4` | 16/10 | — | 0,00 | 51.409,11 | −51.409,11 | **0,00** | Abaixo de 0,90 |
| `S5` | 23/10 | — | 0,00 | 64.261,39 | −64.261,39 | **0,00** | Abaixo de 0,90 |
| `S6` | 30/10 | — | 0,00 | 77.113,67 | −77.113,67 | **0,00** | Abaixo de 0,90 |
| `S7` | 06/11 | `G01`, `G03` | 8.603,59 | 89.965,94 | −81.362,35 | **0,10** | Abaixo de 0,90 |
| `S8` | 13/11 | `F01`, `F02` | 22.942,91 | 102.818,22 | −79.875,31 | **0,22** | Abaixo de 0,90 |
| `S9` (parcial) | 19/11 | `B01`, `B02`, `B03`, `B04`, `B05`, `M02`, `M03`, `G04` | 75.520,41 | 115.670,50 | −40.150,09 | **0,65** | Abaixo de 0,90 |

**O `SPI` ficou abaixo do limiar de 0,90 em todas as nove semanas.** De `S1` a `S6`
nenhum pacote foi concluído (`SPI = 0`); o primeiro valor agregado aparece em `S7`. Pela
regra da spec 09, desde `S1` deveria ter sido acionado o pareamento técnico
(*crashing* interno) nas atividades críticas. Registro do acionamento: só na
*Planning* de 03/11 (`S7`), por duplas de cada camada (declarado pelo GP; detalhe no
[controle de prazo](02_controle_prazo_escopo_riscos.md), seção 1).

`S9`: o relatório da semana do feriado de 20/11 sai em 19/11 (`C05`), mas o `PV` da
Curva S para `S9` é o da semana inteira, até 24/11; por isso o `SPI` de 19/11 é
parcial. O fechamento definitivo é em 24/11/2026, com o critério da seção 4 (`S9`,
fechamento) (declarado pelo GP).

### 2.1. Verificação cruzada: `PV` pelo mesmo critério 0/100

A Curva S da spec distribui o `PV` de forma linear no tempo, enquanto o `EV` usa a
regra 0/100 por pacote. Para conferir que o desvio não vem dessa diferença de
critério, o `PV` foi recalculado com a mesma regra: soma de `BAC_p` dos pacotes cujo
término planejado (Gantt, seção 3) cai até a sexta-feira.

| Semana | Pacotes com término planejado até a sexta | `PV` 0/100 (R$) | `EV` (R$) | `SPI` 0/100 |
| :---: | :--- | ---: | ---: | :---: |
| `S1` | — | 0,00 | 0,00 | indefinido (`PV` = 0) |
| `S2` | `G01`, `G03`, `B01`, `M01`, `F01` | 32.502,45 | 0,00 | 0,00 |
| `S3` | (nenhum novo) | 32.502,45 | 0,00 | 0,00 |
| `S4` | + `F02`, `B02`, `M02` | 54.489,41 | 0,00 | 0,00 |
| `S5` | + `F03` | 61.181,09 | 0,00 | 0,00 |
| `S6` | + `M03`, `B03` | 75.520,41 | 0,00 | 0,00 |
| `S7` | + `M05`, `B05` | 85.079,95 | 8.603,59 | 0,10 |
| `S8` | + `M04`, `F04`, `B04`, `G04` | 108.022,86 | 22.942,91 | 0,21 |
| `S9` (19/11) | + `F05` | 112.802,64 | 75.520,41 | 0,67 |

As duas leituras concordam: `SPI` abaixo de 0,90 em todas as semanas com `PV` > 0.

### 2.2. Sensibilidade ao critério de conclusão

- Se o critério fosse o primeiro commit em vez da issue fechada, `G01` e `G03`
  apareceriam em `S5` (commits de specs em 22/10), e o `SPI` de `S5` e `S6` ficaria
  em torno de 0,13 e 0,11 pela Curva S — ainda abaixo de 0,90. A conta usa a data
  de aceite porque é o que a spec 09 manda.
- Pacotes com código mesclado e issue aberta (`F03`, `F04`, `F05`, `G02`) e com PR
  aberto (`M01`, `M04`, `M05`) somam R$ 40.150,09 e entram no `EV` quando as issues
  fecharem.
- `B05` está contado como concluído (issue #14 fechada em 19/11), mas o relatório do
  B05 declara a homologação `PENDING` (ver
  [controle de escopo](02_controle_prazo_escopo_riscos.md#3-escopo-por-pacote)). Sem
  ele, o `EV` de `S9` cai para R$ 70.740,64 (`SPI` 0,61).

## 3. Custos (`AC`, `CPI`, `EAC`)

O repositório não tem apontamento de horas nem faturas. Os valores desta seção são
**declarados pelo GP** (cenário simulado de mercado da spec 09), calculados com as
premissas abaixo; não são dados verificáveis no GitHub.

**Fórmula (declarado pelo GP):**
`AC(semana) = Σ (horas da trilha × valor-hora da trilha) + serviços de nuvem/IA +
infraestrutura + reserva de aquisições usada`; `AC` acumulado = soma das semanas;
`CPI = EV / AC` acumulados; `EAC = BAC / CPI` (spec 09, seção 4.2).

**Premissas (declarado pelo GP):**

1. Valores-hora e alocação da spec 09, seção 3.1: Back/IA R$ 75 (Filipe, Diogo),
   Middle-end R$ 70 (Pablo, Well), Front-end R$ 65 (Eduardo, Victor Hugo), GP/PO
   R$ 65 (Antônio Rodrigo, Walber); carga plena de 20 h por integrante por semana.
2. GP/PO: carga plena (40 h, R$ 2.600,00/semana) em todas as semanas, pela condução
   dos rituais e da linha de base.
3. Desenvolvedores, `S1`–`S6` (sem código no repositório até 21/10 e nenhum pacote
   técnico aceito): 5 h por integrante por semana (25% da carga: rituais, estudo da
   stack e rascunhos) = 30 h, R$ 2.100,00/semana.
4. Desenvolvedores, `S7`–`S9` (código em execução a partir de 04/11 e pareamento
   acionado em 03/11): carga plena, 120 h, R$ 8.400,00/semana.
5. Serviços previstos (`2.1`, R$ 2.600,00 / 9 = R$ 288,89/semana) e infraestrutura
   (`3`, R$ 295,00/semana) só a partir de `S7`, quando o sistema passou a rodar; antes
   não houve consumo.
6. `S9` vai só até 19/11: 4 dos 6 dias úteis da semana, então RH, serviços e
   infraestrutura entram com 4/6 do valor semanal.
7. Reserva de aquisições (`2.2`, R$ 900,00): uso parcial de R$ 300,00 em `S9` pelo
   risco `R13` (HTTP 429 na sonda de 16/11), para o pico de consumo de *tokens* da
   sonda e do Golden Set; saldo de R$ 600,00.
8. Reserva de contingência financeira (`4`, R$ 10.515,50): não usada; não entra no
   `AC`.

| Semana | Horas (equipe) | `AC` da semana (R$) | `AC` acumulado (R$) | `EV` acumulado (R$) | `CPI = EV / AC` | `EAC = BAC / CPI` (R$) |
| :---: | ---: | ---: | ---: | ---: | :---: | ---: |
| `S1` | 70 | 4.700,00 | 4.700,00 | 0,00 | 0,00 | indefinido (`CPI` = 0) |
| `S2` | 70 | 4.700,00 | 9.400,00 | 0,00 | 0,00 | indefinido (`CPI` = 0) |
| `S3` | 70 | 4.700,00 | 14.100,00 | 0,00 | 0,00 | indefinido (`CPI` = 0) |
| `S4` | 70 | 4.700,00 | 18.800,00 | 0,00 | 0,00 | indefinido (`CPI` = 0) |
| `S5` | 70 | 4.700,00 | 23.500,00 | 0,00 | 0,00 | indefinido (`CPI` = 0) |
| `S6` | 70 | 4.700,00 | 28.200,00 | 0,00 | 0,00 | indefinido (`CPI` = 0) |
| `S7` | 160 | 11.583,89 | 39.783,89 | 8.603,59 | 0,22 | 534.872,36 |
| `S8` | 160 | 11.583,89 | 51.367,78 | 22.942,91 | 0,45 | 258.979,21 |
| `S9` (até 19/11) | 106,67 | 8.022,59 | 59.390,37 | 75.520,41 | 1,27 | 90.965,00 |

Todas as linhas de `AC`, `CPI` e `EAC` acima: (declarado pelo GP). Composição do `AC`
semanal: `S1`–`S6` = 2.600,00 + 2.100,00; `S7` e `S8` = 2.600,00 + 8.400,00 + 288,89 +
295,00; `S9` = 7.333,33 (RH × 4/6) + 192,59 + 196,67 + 300,00.

**Leitura.**

- `S1`–`S6`: houve custo sem valor agregado (`CPI` = 0); `EAC` indefinido.
- `S7`–`S8`: `CPI` abaixo de 0,95; pela regra da spec 09 caberia pedir uso da
  reserva ao patrocinador. O GP declara que não pediu, porque o desvio vinha do `EV`
  atrasado (regra 0/100) e não de gasto acima do previsto.
- `S9`: `CPI` de 1,27 e `EAC` abaixo do `BAC`. O salto vem da regra 0/100, que
  reconheceu em 19/11 oito pacotes executados em `S7`–`S9`, e da carga reduzida dos
  desenvolvedores em `S1`–`S6`. Não indica eficiência sustentada. Pela fórmula
  alternativa `EAC = AC + (BAC − EV)` = 59.390,37 + 40.150,09 = R$ 99.540,46, também
  abaixo do `BAC`.
- O `SPI` continua abaixo de 0,90 em todas as semanas (seção 2); o problema do projeto
  é prazo, não custo.

**Cenário real acadêmico (declarado pelo GP):** gasto real de R$ 0,00. A chave do
provedor de IA (Gemini) ficou na cota gratuita durante todo o projeto, sem cartão nem
fatura; os HTTP 429 de 16/11 (`R13`) são o limite dessa cota. Com `AC` real = 0, o
`CPI` real não tem significado (divisão por zero).

## 4. Relatórios semanais

Cada relatório segue o formato `C05` (prazo, escopo, custos, riscos e caminho
crítico). Riscos detalhados em
[02_controle_prazo_escopo_riscos.md](02_controle_prazo_escopo_riscos.md#4-riscos-r01-a-r20--atualização).

### `S1` — sexta-feira 25/09/2026

- **Prazo:** `PV` R$ 12.852,28; `EV` R$ 0,00; `SPI` 0,00. Abaixo de 0,90.
- **Escopo:** nenhum pacote previsto terminava na semana; nenhum commit no repositório.
- **Caminho crítico:** `B01` em execução pelo plano (término 02/10); sem evidência de trabalho.
- **Custos e riscos:** `AC` da semana R$ 4.700,00 (acumulado R$ 4.700,00); `CPI` 0,00; `EAC` indefinido. `R19` em observação (avaliações AB1 da UFAL até 25/09); demais riscos sem evento (declarado pelo GP).

### `S2` — sexta-feira 02/10/2026 (Marco `M1`)

- **Prazo:** `PV` R$ 25.704,56; `EV` R$ 0,00; `SPI` 0,00. Abaixo de 0,90.
- **Escopo:** `G01`, `G03`, `B01`, `M01` e `F01` deveriam terminar; nenhum concluído. `M1` não atingido.
- **Caminho crítico:** `B01` atrasado a partir desta data.
- **Custos e riscos:** `AC` da semana R$ 4.700,00 (acumulado R$ 9.400,00); `CPI` 0,00; `EAC` indefinido. `R19` acionado com a perda do `M1`; alerta `C06` em 02/10 a Walber e Filipe (declarado pelo GP).

### `S3` — sexta-feira 09/10/2026

- **Prazo:** `PV` R$ 38.556,83; `EV` R$ 0,00; `SPI` 0,00. Abaixo de 0,90.
- **Escopo:** sem entregas; `B02`, `M02` e `F02` deveriam estar em curso.
- **Caminho crítico:** `B02` não pode iniciar formalmente sem `B01`.
- **Custos e riscos:** `AC` da semana R$ 4.700,00 (acumulado R$ 14.100,00); `CPI` 0,00; `EAC` indefinido. `R19` ativo; sem novo evento de risco (declarado pelo GP).

### `S4` — sexta-feira 16/10/2026 (Marco `M2`)

- **Prazo:** `PV` R$ 51.409,11; `EV` R$ 0,00; `SPI` 0,00. Abaixo de 0,90.
- **Escopo:** `F02`, `B02` e `M02` deveriam terminar; nenhum concluído. `M2` não atingido.
- **Caminho crítico:** `B01` e `B02` atrasados.
- **Custos e riscos:** `AC` da semana R$ 4.700,00 (acumulado R$ 18.800,00); `CPI` 0,00; `EAC` indefinido. `M2` perdido; alerta `C06` em 16/10 (declarado pelo GP).

### `S5` — sexta-feira 23/10/2026

- **Prazo:** `PV` R$ 64.261,39; `EV` R$ 0,00; `SPI` 0,00. Abaixo de 0,90.
- **Escopo:** primeiros commits do repositório (21/10 e 22/10): specs SDD/TDD e de gestão, ainda sem merge. `F03` deveria terminar.
- **Caminho crítico:** `B01`, `B02` atrasados; `B03` deveria estar em curso.
- **Custos e riscos:** `AC` da semana R$ 4.700,00 (acumulado R$ 23.500,00); `CPI` 0,00; `EAC` indefinido. `R19` ativo; repositório criado em 21/10 como resposta (declarado pelo GP).

### `S6` — sexta-feira 30/10/2026 (Marco `M3` em 29/10)

- **Prazo:** `PV` R$ 77.113,67; `EV` R$ 0,00; `SPI` 0,00. Abaixo de 0,90.
- **Escopo:** `M03` e `B03` deveriam terminar; nenhum concluído. `M3` não atingido. Nenhum commit na semana.
- **Caminho crítico:** `B01`, `B02`, `B03` atrasados.
- **Custos e riscos:** `AC` da semana R$ 4.700,00 (acumulado R$ 28.200,00); `CPI` 0,00; `EAC` indefinido. `M3` perdido; alerta `C06` em 30/10 e decisão de parear o caminho crítico na Sprint 4 (declarado pelo GP).

### `S7` — sexta-feira 06/11/2026

- **Prazo:** `PV` R$ 89.965,94; `EV` R$ 8.603,59; `SPI` = 8.603,59 / 89.965,94 = **0,10**. Abaixo de 0,90.
- **Escopo:** `G01` e `G03` concluídos em 03/11 (PR #1). Atividade de código a partir de 04/11 (`B04`) e 06/11 (frontend), ainda sem merge.
- **Caminho crítico:** nenhum pacote crítico concluído.
- **Custos e riscos:** `AC` da semana R$ 11.583,89 (acumulado R$ 39.783,89); `CPI` 0,22; `EAC` R$ 534.872,36. Pareamento acionado em 03/11; troca OpenAI → Gemini aprovada pelo GP em 07/11 (`525c1c8`), sem mudança de `BAC` e com maior exposição em `R02` e `R13` (declarado pelo GP).

### `S8` — sexta-feira 13/11/2026 (Marco `M4` em 10/11)

- **Prazo:** `PV` R$ 102.818,22; `EV` R$ 22.942,91; `SPI` = 22.942,91 / 102.818,22 = **0,22**. Abaixo de 0,90.
- **Escopo:** `F01` (07/11) e `F02` (10/11) concluídos. MVP do chat RAG na `develop` desde 10/11 (PRs #25 → #24), sem fechar issues de backend. `M4` não atingido.
- **Caminho crítico:** `B01`–`B04` com código parcial, nenhum fechado.
- **Riscos:** `R02` acionado (TTFT de 1,3 s a 6 s, issue #7, 07/11). Demais: `M4` perdido, alerta `C06` em 10/11 com o patrocinador incluído; `R19` ativo; `R13` ainda sem evento (declarado pelo GP).
- **Custos:** `AC` da semana R$ 11.583,89 (acumulado R$ 51.367,78); `CPI` 0,45; `EAC` R$ 258.979,21 (declarado pelo GP).

### `S9` — quinta-feira 19/11/2026 (antecipado pelo feriado; parcial)

- **Prazo:** `PV` R$ 115.670,50 (semana até 24/11); `EV` R$ 75.520,41; `SPI` = 75.520,41 / 115.670,50 = **0,65**. Abaixo de 0,90.
- **Escopo:** `B01`, `B02`, `B03`, `B04`, `B05`, `M02`, `M03` e `G04` concluídos em 19/11. Abertos: `M01`, `M04`, `M05` (PRs #35 e #36), `F03`, `F04`, `F05` e `G02`.
- **Caminho crítico:** `B01`–`B04` concluídos; `F05` atrasado (término planejado 17/11); `G02` previsto para 23/11.
- **Riscos:** `R02` e `R13` acionados (sonda de 16/11); `R19` materializado como atraso. Ver controle de riscos.
- **Custos:** `AC` da semana R$ 8.022,59 até 19/11, com R$ 300,00 da reserva de aquisições por `R13` (acumulado R$ 59.390,37); `CPI` 1,27; `EAC` R$ 90.965,00 (declarado pelo GP).
- **Fechamento em 24/11 (declarado pelo GP):** o dia de reserva de 24/11 é usado para
  fechar os PRs #35 a #38 e os pacotes `F03`, `F04` e `F05`; `G02` fecha em 23/11. O
  `EV` final será o de 19/11 somado ao `BAC_p` dos pacotes cujas issues fecharem até
  24/11, com teto de R$ 115.670,50 (`SPI` 1,00) se os sete fecharem; isso é projeção,
  não resultado. O `AC` projetado até 24/11 é R$ 63.251,67 (os 2/6 restantes de `S9`:
  R$ 3.861,30). A reserva financeira de contingência não será usada. `EV`, `SPI` e
  `CPI` finais serão registrados no relatório de encerramento (`C09`).
