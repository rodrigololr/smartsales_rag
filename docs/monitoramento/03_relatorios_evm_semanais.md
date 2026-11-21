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
>
> **Governança.** O GP é autor, aprovador e fonte dos valores declarados deste
> relatório. Recomenda-se que o PO Walber (aprovação de entregas na
> [matriz RACI](../../specs/diagrams_and_pm/02_matriz_raci.md)) revise e aprove, como
> segundo aprovador, todos os campos *declarado pelo GP*.

## 1. Método

### 1.1. Fórmulas

| Indicador | Fórmula | Limiar (spec 09, seção 4.2) |
| :--- | :--- | :---: |
| Linha de base de desempenho | `PMB = BAC − reserva de contingência` = 115.670,50 − 10.515,50 = **R$ 105.155,00** | — |
| Valor planejado | `PV(t)` = acumulado da coluna "Custo Base Semanal" da Curva S (spec 09, seção 4.1), sem a reserva | Linha de base |
| Orçamento do pacote | `BAC_p = PMB × d_p / 121` | — |
| Valor agregado | `EV(t) = PMB × Σ d_p / 121`, somando os pacotes aceitos até a data de corte | `EV ≥ 0,90 × PV` |
| Variação de prazo | `SV = EV − PV` | ≥ 0 |
| Índice de prazo | `SPI = EV / PV` | **≥ 0,90** |
| Custo real | `AC` = horas × valor-hora + serviços + reserva de aquisições usada (seção 3) | `AC ≤ EV` |
| Índice de custo | `CPI = EV / AC` | ≥ 0,95 |
| Estimativa no término | `EAC = PMB / CPI = PMB × AC / EV` (com o `CPI` sem arredondamento) | `EAC ≤ PMB`; acima disso, pedir a reserva |

- `BAC` = R$ 115.670,50 (spec 09, seção 3.4). A reserva de contingência geral
  (categoria 4, R$ 10.515,50) só é liberada por solicitação ao patrocinador (spec 09,
  seção 4.2); por isso fica fora da linha de medição: não é distribuída aos pacotes,
  não gera `EV` e é mostrada à parte. A reserva de aquisições (item 2.2, R$ 900,00)
  faz parte do custo base e continua no `PMB`.
- Gatilho da reserva: a spec 09 usa `EAC = BAC / CPI` e pede a reserva quando
  `EAC > BAC`, o que equivale a `CPI < 1`. Com o `PMB`, a mesma condição é
  `EAC = PMB / CPI > PMB`; este relatório usa essa forma e mostra também a comparação
  com o `BAC` (se a reserva cobre o desvio).
- `d_p` = duração planejada do pacote em dias úteis (Gantt, seção 3). A soma dos 19
  pacotes é 121 dias; `RES` (reserva de cronograma) não recebe orçamento de trabalho.
  A spec 09 não distribui o orçamento por pacote, então o peso por duração é uma
  premissa deste relatório, confirmada pelo GP como critério oficial de distribuição
  do orçamento por pacote (declarado pelo GP): não há horas estimadas por pacote na
  linha de base. O `EV` é calculado pela soma dos dias e arredondado uma vez, para
  não acumular resíduo de arredondamento dos `BAC_p`.
- Critério de aceite (regra 0/100, conservador): o pacote só agrega valor quando a
  issue dele está fechada **e** ele cumpre a própria DoD (spec 09: "apenas itens que
  cumpram a DoD"). PR mesclado com a issue aberta não conta. Para `G01` e `G03`, vale
  o merge do PR #1 (03/11), mesma data do fechamento das issues #2 e #3.
- Ficam fora do `EV`, apesar da issue fechada em 19/11 (dado do GitHub): `B02` (meta
  de TTFT não atingida: p95 de 4.739 ms na sonda de 16/11, teto de 2.000 ms; risco
  `R02`) e `B05` (o
  [relatório de homologação](../../backend/tests/ragas_eval/RAGAS_HOMOLOGATION_REPORT.md)
  está `PENDING` e diz que a issue #14 deve permanecer aberta até o aceite completo).
  Os dois aparecem só na linha de sensibilidade "se `B02`/`B05` forem aceitos".
- Data de corte: `S1`–`S8` na sexta-feira; `S9` em 19/11 para `PV`, `EV` e `AC` (4 dos
  6 dias úteis da semana: 16, 17, 18 e 19/11).

### 1.2. Orçamento por pacote

| Pacote | `d_p` | `BAC_p` (R$) | Pacote | `d_p` | `BAC_p` (R$) |
| :---: | :---: | ---: | :---: | :---: | ---: |
| `G01` | 6 | 5.214,30 | `B03` | 8 | 6.952,40 |
| `G03` | 3 | 2.607,15 | `M03` | 7 | 6.083,35 |
| `B01` | 9 | 7.821,45 | `F03` | 7 | 6.083,35 |
| `M01` | 8 | 6.952,40 | `B04` | 7 | 6.083,35 |
| `F01` | 8 | 6.952,40 | `M04` | 7 | 6.083,35 |
| `B02` | 8 | 6.952,40 | `B05` | 5 | 4.345,25 |
| `M02` | 8 | 6.952,40 | `F04` | 7 | 6.083,35 |
| `F02` | 7 | 6.083,35 | `M05` | 5 | 4.345,25 |
| — | — | — | `G04` | 3 | 2.607,15 |
| — | — | — | `F05` | 5 | 4.345,25 |
| — | — | — | `G02` | 3 | 2.607,15 |

Valor por dia útil: R$ 105.155,00 / 121 = R$ 869,05.

## 2. Consolidado

`PV` pela Curva S do custo base (spec 09, seção 4.1): R$ 11.683,89 por semana em
`S1`–`S8`; em `S9`, R$ 11.683,88 na semana inteira, dos quais 4/6 (R$ 7.789,25) até o
corte de 19/11.

| Semana | Data de corte | Pacotes aceitos na semana | `EV` acumulado (R$) | `PV` acumulado (R$) | `SV` (R$) | `SPI` | Status |
| :---: | :---: | :--- | ---: | ---: | ---: | :---: | :---: |
| `S1` | 25/09 | — | 0,00 | 11.683,89 | −11.683,89 | **0,00** | Abaixo de 0,90 |
| `S2` | 02/10 | — | 0,00 | 23.367,78 | −23.367,78 | **0,00** | Abaixo de 0,90 |
| `S3` | 09/10 | — | 0,00 | 35.051,67 | −35.051,67 | **0,00** | Abaixo de 0,90 |
| `S4` | 16/10 | — | 0,00 | 46.735,56 | −46.735,56 | **0,00** | Abaixo de 0,90 |
| `S5` | 23/10 | — | 0,00 | 58.419,45 | −58.419,45 | **0,00** | Abaixo de 0,90 |
| `S6` | 30/10 | — | 0,00 | 70.103,34 | −70.103,34 | **0,00** | Abaixo de 0,90 |
| `S7` | 06/11 | `G01`, `G03` | 7.821,45 | 81.787,23 | −73.965,78 | **0,10** | Abaixo de 0,90 |
| `S8` | 13/11 | `F01`, `F02` | 20.857,19 | 93.471,12 | −72.613,93 | **0,22** | Abaixo de 0,90 |
| `S9` (parcial) | 19/11 | `B01`, `B03`, `B04`, `M02`, `M03`, `G04` | 57.357,27 | 101.260,37 | −43.903,10 | **0,57** | Abaixo de 0,90 |

Sensibilidade (não é o número oficial): se `B02`/`B05` forem aceitos, o `EV` de `S9`
sobe para R$ 68.654,92 (`SV` −32.605,45; `SPI` 0,68). `S1`–`S8` não mudam, porque as
duas issues fecharam em 19/11.

**O `SPI` ficou abaixo do limiar de 0,90 em todas as nove semanas.** De `S1` a `S6`
nenhum pacote foi concluído (`SPI = 0`); o primeiro valor agregado aparece em `S7`. Pela
regra da spec 09, desde `S1` deveria ter sido acionado o pareamento técnico
(*crashing* interno) nas atividades críticas. Registro do acionamento: só na
*Planning* de 03/11 (`S7`), por duplas de cada camada (declarado pelo GP; detalhe no
[controle de prazo](02_controle_prazo_escopo_riscos.md), seção 1).

`S9`: o relatório da semana do feriado de 20/11 sai em 19/11 (`C05`), com corte único
em 19/11 para `PV`, `EV` e `AC`: `PV(19/11)` = 93.471,12 + 7.789,25 = R$ 101.260,37.
Os 2/6 restantes do `PV` de `S9` (23 e 24/11, R$ 3.894,63) entram no fechamento. O
fechamento definitivo é em 24/11/2026, com o critério da seção 4 (`S9`, fechamento)
(declarado pelo GP).

### 2.1. Conferência: `PV` pelo Gantt com o mesmo critério 0/100

O número oficial é o da Curva S (seção 2). A Curva S distribui o `PV` de forma linear
no tempo, enquanto o `EV` usa a regra 0/100 por pacote; para conferir o efeito dessa
diferença, o `PV` foi recalculado só como verificação: soma de `BAC_p` dos pacotes
cujo término planejado (Gantt, seção 3) cai até a data de corte.

| Semana | Pacotes com término planejado até o corte | `PV` Gantt 0/100 (R$) | `EV` (R$) | `SPI` Gantt 0/100 |
| :---: | :--- | ---: | ---: | :---: |
| `S1` | — | 0,00 | 0,00 | indefinido (`PV` = 0) |
| `S2` | `G01`, `G03`, `B01`, `M01`, `F01` | 29.547,69 | 0,00 | 0,00 |
| `S3` | (nenhum novo) | 29.547,69 | 0,00 | 0,00 |
| `S4` | + `F02`, `B02`, `M02` | 49.535,83 | 0,00 | 0,00 |
| `S5` | + `F03` | 55.619,17 | 0,00 | 0,00 |
| `S6` | + `M03`, `B03` | 68.654,92 | 0,00 | 0,00 |
| `S7` | + `M05`, `B05` | 77.345,41 | 7.821,45 | 0,10 |
| `S8` | + `M04`, `F04`, `B04`, `G04` | 98.202,60 | 20.857,19 | 0,21 |
| `S9` (19/11) | + `F05` | 102.547,85 | 57.357,27 | 0,56 |

Os valores não coincidem com os da Curva S (`S1` indefinido contra 0,00; `S8` 0,21
contra 0,22; `S9` 0,56 contra 0,57), porque os dois critérios distribuem o `PV` de
forma diferente. A conferência só confirma que a conclusão não depende do critério:
o `SPI` fica abaixo de 0,90 em todas as semanas com `PV` > 0 nas duas leituras.

### 2.2. Sensibilidade ao critério de conclusão

- Se o critério fosse o primeiro commit em vez da issue fechada, `G01` e `G03`
  apareceriam em `S5` (commits de specs em 22/10), e o `SPI` de `S5` e `S6` ficaria
  em torno de 0,13 e 0,11 pela Curva S — ainda abaixo de 0,90. A conta usa a data
  de aceite porque é o que a spec 09 manda.
- Pacotes com código mesclado e issue aberta (`F03`, `F04`, `F05`, `G02`) e com PR
  aberto (`M01`, `M04`, `M05`) somam R$ 36.500,08 e entram no `EV` quando as issues
  fecharem e a DoD for cumprida.
- Se `B02` e `B05` forem aceitos: `EV` de `S9` R$ 68.654,92, `SPI` 0,68, `CPI` 1,156 e
  `EAC` R$ 90.964,99. Não é o número oficial: `B02` não cumpriu a meta de TTFT e o
  relatório B05 está `PENDING` (ver
  [controle de escopo](02_controle_prazo_escopo_riscos.md#3-escopo-por-pacote)).

## 3. Custos (`AC`, `CPI`, `EAC`)

O repositório não tem apontamento de horas nem faturas. Os valores desta seção são
**declarados pelo GP** (cenário simulado de mercado da spec 09), calculados com as
premissas abaixo; não são dados verificáveis no GitHub.

**Fórmula (declarado pelo GP):**
`AC(semana) = Σ (horas da trilha × valor-hora da trilha) + serviços de nuvem/IA +
infraestrutura + reserva de aquisições usada`; `AC` acumulado = soma das semanas;
`CPI = EV / AC` acumulados; `EAC = PMB / CPI` (seção 1.1; equivalente ao gatilho da
spec 09, seção 4.2).

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
8. Reserva de contingência financeira (`4`, R$ 10.515,50): não consumida até 19/11;
   não entra no `AC` nem no `PMB`. Os pedidos de uso estão na tabela "Gatilho da
   reserva", abaixo.

| Semana | Horas (equipe) | `AC` da semana (R$) | `AC` acumulado (R$) | `EV` acumulado (R$) | `CPI = EV / AC` | `EAC = PMB / CPI` (R$) |
| :---: | ---: | ---: | ---: | ---: | :---: | ---: |
| `S1` | 70 | 4.700,00 | 4.700,00 | 0,00 | 0,000 | indefinido (`CPI` = 0) |
| `S2` | 70 | 4.700,00 | 9.400,00 | 0,00 | 0,000 | indefinido (`CPI` = 0) |
| `S3` | 70 | 4.700,00 | 14.100,00 | 0,00 | 0,000 | indefinido (`CPI` = 0) |
| `S4` | 70 | 4.700,00 | 18.800,00 | 0,00 | 0,000 | indefinido (`CPI` = 0) |
| `S5` | 70 | 4.700,00 | 23.500,00 | 0,00 | 0,000 | indefinido (`CPI` = 0) |
| `S6` | 70 | 4.700,00 | 28.200,00 | 0,00 | 0,000 | indefinido (`CPI` = 0) |
| `S7` | 160 | 11.583,89 | 39.783,89 | 7.821,45 | 0,197 | 534.872,04 |
| `S8` | 160 | 11.583,89 | 51.367,78 | 20.857,19 | 0,406 | 258.979,23 |
| `S9` (até 19/11) | 106,67 | 8.022,59 | 59.390,37 | 57.357,27 | 0,966 | 108.882,35 |

Todas as linhas de `AC`, `CPI` e `EAC` acima: (declarado pelo GP). Composição do `AC`
semanal: `S1`–`S6` = 2.600,00 + 2.100,00; `S7` e `S8` = 2.600,00 + 8.400,00 + 288,89 +
295,00; `S9` = 7.333,33 (RH × 4/6) + 192,59 + 196,67 + 300,00.

O `EAC` usa o `CPI` sem arredondamento (`PMB × AC / EV`). Exemplo, `S8`:
105.155,00 × 51.367,78 / 20.857,19 = R$ 258.979,23; dividir pelo `CPI` arredondado
(0,406) daria R$ 259.002,46, diferença que é só arredondamento. Sensibilidade (não
oficial): se `B02`/`B05` forem aceitos, `S9` fica com `CPI` 1,156 e `EAC`
R$ 90.964,99.

**Gatilho da reserva (spec 09, seção 4.2).** Nas três semanas com `CPI` > 0 o `EAC`
passou do `PMB`, e a spec manda pedir uso da reserva de contingência ao patrocinador:

| Semana | `EAC − PMB` (R$) | `EAC` × `BAC` | Registro |
| :---: | ---: | :--- | :--- |
| `S7` | +429.717,04 | Acima do `BAC`: a reserva não cobre o desvio projetado | Solicitação de uso da reserva e alerta `C06` enviados ao patrocinador com o relatório `C05` de 06/11, informando que o desvio vem sobretudo do `EV` atrasado pela regra 0/100 (declarado pelo GP). |
| `S8` | +153.824,23 | Acima do `BAC`: a reserva não cobre o desvio projetado | Solicitação e alerta reiterados ao patrocinador com o relatório `C05` de 13/11 (declarado pelo GP). |
| `S9` | +3.727,35 | Abaixo do `BAC` (−6.788,15): cabe na reserva | Solicitação de uso parcial de R$ 3.727,35 da reserva enviada ao patrocinador com o relatório `C05` de 19/11 (declarado pelo GP). Consumo efetivo da reserva até 19/11: R$ 0,00. |

**Leitura.**

- `S1`–`S6`: houve custo sem valor agregado (`CPI` = 0); `EAC` indefinido.
- `S7`–`S8`: `CPI` abaixo de 0,95 e `EAC` acima do `PMB` e do `BAC`; o pedido de
  reserva está registrado acima. A causa principal é o `EV` atrasado (regra 0/100), e
  não gasto acima do previsto, mas isso não dispensa o pedido que a spec exige.
- `S9`: `CPI` de 0,966, acima do limiar de 0,95 mas menor que 1, então o `EAC`
  (R$ 108.882,35) passa do `PMB` em R$ 3.727,35 e fica dentro do `BAC`. O salto em
  relação a `S8` vem da regra 0/100, que reconheceu em 19/11 seis pacotes executados em
  `S7`–`S9`, e da carga reduzida dos desenvolvedores em `S1`–`S6`. Não indica
  eficiência sustentada. Pela fórmula alternativa `EAC = AC + (PMB − EV)` =
  59.390,37 + 47.797,73 = R$ 107.188,10, também acima do `PMB` e abaixo do `BAC`.
- O `SPI` continua abaixo de 0,90 em todas as semanas (seção 2); o problema principal
  do projeto é prazo.

**Cenário real acadêmico (declarado pelo GP):** gasto real de R$ 0,00. A chave do
provedor de IA (Gemini) ficou na cota gratuita durante todo o projeto, sem cartão nem
fatura; os HTTP 429 de 16/11 (`R13`) são o limite dessa cota. Com `AC` real = 0, o
`CPI` real não tem significado (divisão por zero).

## 4. Relatórios semanais

Cada relatório segue o formato `C05` (prazo, escopo, custos, riscos e caminho
crítico). Riscos detalhados em
[02_controle_prazo_escopo_riscos.md](02_controle_prazo_escopo_riscos.md#4-riscos-r01-a-r20--atualização).

### `S1` — sexta-feira 25/09/2026

- **Prazo:** `PV` R$ 11.683,89; `EV` R$ 0,00; `SPI` 0,00. Abaixo de 0,90.
- **Escopo:** nenhum pacote previsto terminava na semana; nenhum commit no repositório.
- **Caminho crítico:** `B01` em execução pelo plano (término 02/10); sem evidência de trabalho.
- **Custos e riscos:** `AC` da semana R$ 4.700,00 (acumulado R$ 4.700,00); `CPI` 0,000; `EAC` indefinido. `R19` em observação (avaliações AB1 da UFAL até 25/09); demais riscos sem evento (declarado pelo GP).

### `S2` — sexta-feira 02/10/2026 (Marco `M1`)

- **Prazo:** `PV` R$ 23.367,78; `EV` R$ 0,00; `SPI` 0,00. Abaixo de 0,90.
- **Escopo:** `G01`, `G03`, `B01`, `M01` e `F01` deveriam terminar; nenhum concluído. `M1` não atingido.
- **Caminho crítico:** `B01` atrasado a partir desta data.
- **Custos e riscos:** `AC` da semana R$ 4.700,00 (acumulado R$ 9.400,00); `CPI` 0,000; `EAC` indefinido. `R19` acionado com a perda do `M1`; alerta `C06` em 02/10 a Walber e Filipe (declarado pelo GP).

### `S3` — sexta-feira 09/10/2026

- **Prazo:** `PV` R$ 35.051,67; `EV` R$ 0,00; `SPI` 0,00. Abaixo de 0,90.
- **Escopo:** sem entregas; `B02`, `M02` e `F02` deveriam estar em curso.
- **Caminho crítico:** `B02` não pode iniciar formalmente sem `B01`.
- **Custos e riscos:** `AC` da semana R$ 4.700,00 (acumulado R$ 14.100,00); `CPI` 0,000; `EAC` indefinido. `R19` ativo; sem novo evento de risco (declarado pelo GP).

### `S4` — sexta-feira 16/10/2026 (Marco `M2`)

- **Prazo:** `PV` R$ 46.735,56; `EV` R$ 0,00; `SPI` 0,00. Abaixo de 0,90.
- **Escopo:** `F02`, `B02` e `M02` deveriam terminar; nenhum concluído. `M2` não atingido.
- **Caminho crítico:** `B01` e `B02` atrasados.
- **Custos e riscos:** `AC` da semana R$ 4.700,00 (acumulado R$ 18.800,00); `CPI` 0,000; `EAC` indefinido. `M2` perdido; alerta `C06` em 16/10 (declarado pelo GP).

### `S5` — sexta-feira 23/10/2026

- **Prazo:** `PV` R$ 58.419,45; `EV` R$ 0,00; `SPI` 0,00. Abaixo de 0,90.
- **Escopo:** primeiros commits do repositório (21/10 e 22/10): specs SDD/TDD e de gestão, ainda sem merge. `F03` deveria terminar.
- **Caminho crítico:** `B01`, `B02` atrasados; `B03` deveria estar em curso.
- **Custos e riscos:** `AC` da semana R$ 4.700,00 (acumulado R$ 23.500,00); `CPI` 0,000; `EAC` indefinido. `R19` ativo; repositório criado em 21/10 como resposta (declarado pelo GP).

### `S6` — sexta-feira 30/10/2026 (Marco `M3` em 29/10)

- **Prazo:** `PV` R$ 70.103,34; `EV` R$ 0,00; `SPI` 0,00. Abaixo de 0,90.
- **Escopo:** `M03` e `B03` deveriam terminar; nenhum concluído. `M3` não atingido. Nenhum commit na semana.
- **Caminho crítico:** `B01`, `B02`, `B03` atrasados.
- **Custos e riscos:** `AC` da semana R$ 4.700,00 (acumulado R$ 28.200,00); `CPI` 0,000; `EAC` indefinido. `M3` perdido; alerta `C06` em 30/10 e decisão de parear o caminho crítico na Sprint 4 (declarado pelo GP).

### `S7` — sexta-feira 06/11/2026

- **Prazo:** `PV` R$ 81.787,23; `EV` R$ 7.821,45; `SPI` = 7.821,45 / 81.787,23 = **0,10**. Abaixo de 0,90.
- **Escopo:** `G01` e `G03` concluídos em 03/11 (PR #1). Atividade de código a partir de 04/11 (`B04`) e 06/11 (frontend), ainda sem merge.
- **Caminho crítico:** nenhum pacote crítico concluído.
- **Custos e riscos:** `AC` da semana R$ 11.583,89 (acumulado R$ 39.783,89); `CPI` 0,197; `EAC` R$ 534.872,04, acima do `PMB` e do `BAC`: solicitação de uso da reserva e alerta `C06` enviados ao patrocinador neste relatório (declarado pelo GP). Pareamento acionado em 03/11; troca OpenAI → Gemini aprovada pelo GP em 07/11 (`525c1c8`), sem mudança de `BAC` e com maior exposição em `R02` e `R13` (declarado pelo GP).

### `S8` — sexta-feira 13/11/2026 (Marco `M4` em 10/11)

- **Prazo:** `PV` R$ 93.471,12; `EV` R$ 20.857,19; `SPI` = 20.857,19 / 93.471,12 = **0,22**. Abaixo de 0,90.
- **Escopo:** `F01` (07/11) e `F02` (10/11) concluídos. MVP do chat RAG na `develop` desde 10/11 (PRs #25 → #24), sem fechar issues de backend. `M4` não atingido.
- **Caminho crítico:** `B01`–`B04` com código parcial, nenhum fechado.
- **Riscos:** `R02` acionado (TTFT de 1,3 s a 6 s, issue #7, 07/11). Demais: `M4` perdido, alerta `C06` em 10/11 com o patrocinador incluído; `R19` ativo; `R13` ainda sem evento (declarado pelo GP).
- **Custos:** `AC` da semana R$ 11.583,89 (acumulado R$ 51.367,78); `CPI` 0,406; `EAC` R$ 258.979,23, acima do `PMB` e do `BAC`; solicitação de reserva reiterada ao patrocinador (declarado pelo GP).

### `S9` — quinta-feira 19/11/2026 (antecipado pelo feriado; parcial)

- **Prazo:** `PV` R$ 101.260,37 (corte em 19/11); `EV` R$ 57.357,27; `SPI` = 57.357,27 / 101.260,37 = **0,57**. Abaixo de 0,90. Se `B02`/`B05` forem aceitos: `EV` R$ 68.654,92, `SPI` 0,68.
- **Escopo:** issues de `B01`, `B02`, `B03`, `B04`, `B05`, `M02`, `M03` e `G04` fechadas em 19/11; `B02` (TTFT) e `B05` (homologação `PENDING`) ficam fora do `EV`. Abertos: `M01`, `M04`, `M05` (PRs #35 e #36), `F03`, `F04`, `F05` e `G02`.
- **Caminho crítico:** `B01`, `B03` e `B04` aceitos; `B02` com issue fechada e meta de TTFT não atingida; `F05` atrasado (término planejado 17/11). `G04` fechou com 4 dias úteis de atraso e consumiu a folga de 2 dias; `G02` (predecessoras `G04`, `B05`, `F05`) fica projetado para 24/11, depois de `F05`.
- **Riscos:** `R02` e `R13` acionados (sonda de 16/11); `R19` materializado como atraso. Ver controle de riscos.
- **Custos:** `AC` da semana R$ 8.022,59 até 19/11, com R$ 300,00 da reserva de aquisições por `R13` (acumulado R$ 59.390,37); `CPI` 0,966; `EAC` R$ 108.882,35, R$ 3.727,35 acima do `PMB` e dentro do `BAC`; solicitação de uso parcial da reserva (R$ 3.727,35) enviada ao patrocinador (declarado pelo GP).
- **Fechamento em 24/11 (declarado pelo GP):** 23/11 é usado para fechar `F05`
  (caminho crítico); o dia de reserva de 24/11 fecha `G02`, depois de `F05`, os PRs
  #35 a #38 e os pacotes `F03` e `F04`. O reteste do B05 corre dentro de `F05`; sem
  ele, `B05` segue fora do `EV`. O `EV` final será o de 19/11 somado ao `BAC_p` dos
  pacotes cujas issues fecharem até 24/11 com a DoD cumprida, com teto de
  R$ 105.155,00 (`PMB`, `SPI` 1,00) se os sete fecharem e `B02`/`B05` forem aceitos;
  isso é projeção, não resultado. O `AC` projetado até 24/11 é R$ 63.251,67 (os 2/6
  restantes de `S9`: R$ 3.861,30). O `EAC` por índice supõe que o trabalho restante
  segue no mesmo desempenho; com o corte de escopo em 24/11, o `AC` projetado fica
  abaixo do `PMB` e a reserva financeira de contingência não será consumida, apesar do
  pedido de 19/11. `EV`, `SPI` e `CPI` finais serão registrados no relatório de
  encerramento (`C09`).
