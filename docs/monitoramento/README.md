# Monitoramento e Controle (`EAP 6.0` · pacote `RES` · issue #21)

> **Situação em 20/11/2026.** Os relatórios desta pasta foram reconstituídos
> retroativamente a partir das specs, do histórico Git da `develop` e do GitHub
> (PRs e issues). Não há atas, listas de presença, horas apontadas nem custos reais
> no repositório: esses campos aparecem como **⚠️ A preencher pelo GP**.
> Aprovador: Antônio Rodrigo. Responsável: Walber.

## 1. Conteúdo

| Arquivo | Pacote EAP | Rotinas de comunicação | O que contém |
| :--- | :---: | :---: | :--- |
| [01_rituais_ageis.md](01_rituais_ageis.md) | `6.1` | `C02`, `C03`, `C08` | Calendário de *Plannings*, *Dailies* e *Reviews* e o que foi entregue em cada janela de sprint. |
| [02_controle_prazo_escopo_riscos.md](02_controle_prazo_escopo_riscos.md) | `6.2` | `C05`, `C06` | Caminho crítico (planejado × real), marcos, escopo por pacote, riscos `R01`–`R20` e reserva de contingência. |
| [03_relatorios_evm_semanais.md](03_relatorios_evm_semanais.md) | `6.3` | `C05` | Relatórios EVM semanais `S1`–`S9` (`PV`, `EV`, `SV`, `SPI`; `AC` e `CPI` pendentes). |

Documentos relacionados, sem repetir o conteúdo deles:

- Encerramento: [roteiro da demo](../encerramento/01_roteiro_demo.md),
  [relatório de encerramento](../encerramento/02_relatorio_encerramento.md) e
  [lições aprendidas](../encerramento/03_licoes_aprendidas.md).
- Linha de base: [Gantt](../../specs/diagrams_and_pm/08_cronograma_gantt.md),
  [custos e EVM](../../specs/diagrams_and_pm/09_quadro_custos_eac.md),
  [comunicações](../../specs/diagrams_and_pm/15_gestao_comunicacoes.md),
  [riscos](../../specs/diagrams_and_pm/16_gestao_riscos.md),
  [rede CPM](../../specs/diagrams_and_pm/07_diagrama_rede_atividades_cpm.md),
  [EAP](../../specs/diagrams_and_pm/01_eap.md) e
  [RACI](../../specs/diagrams_and_pm/02_matriz_raci.md).

## 2. Fontes de dados e regras

| Dado | Fonte | Regra |
| :--- | :--- | :--- |
| Datas planejadas | `08_cronograma_gantt.md` (seção 3) | Data de término de cada pacote. |
| Orçamento (`BAC`, `PV` da Curva S) | `09_quadro_custos_eac.md` (seções 3.4 e 4.1) | Valores copiados sem alteração. |
| Data real de conclusão | GitHub: data de fechamento da issue do pacote; para `G01`/`G03`, o merge do PR #1 | Pacote concluído = issue fechada (DoD da spec 09: só conta o que foi aceito). PR mesclado sem issue fechada = parcial (não gera `EV`). |
| Escopo em andamento | `gh pr list --state open` | PR aberto que fecha a issue = "em PR aberto". |
| Atividade no repositório | `git log origin/develop --format='%h %ad %s' --date=short` | Usado só como evidência de trabalho, não como aceite. |

## 3. Como atualizar

1. Coletar os dados (cada comando com `-R rodrigololr/smartsales_rag` fora do clone):

   ```bash
   gh pr list --state merged --limit 100 --json number,title,mergedAt,author
   gh pr list --state open --json number,title,createdAt,headRefName
   gh issue list --state all --limit 100 --json number,title,closedAt,state
   git fetch origin && git log origin/develop --format='%h %ad %s' --date=short
   ```

2. Em `02_controle_prazo_escopo_riscos.md`, atualizar a data real e a situação dos
   pacotes que mudaram e o estado dos riscos com nova evidência (PR, issue ou
   relatório). Sem evidência, o risco continua "sem evidência no repositório".
3. Em `03_relatorios_evm_semanais.md`, somar ao `EV` o orçamento dos pacotes cujas
   issues fecharam até a sexta-feira da semana e recalcular `SPI = EV / PV`. Não
   alterar o `PV`: ele é a linha de base.
4. Preencher os campos **⚠️ A preencher pelo GP** apenas com dados que tenham
   registro (ata, planilha de horas, fatura). Se o dado não existir, escrever
   "não registrado" em vez de estimar.
5. Na semana de `20/11` (feriado), o relatório `C05` sai em `19/11`; o fechamento
   definitivo de `S9` é em `24/11/2026` (Marco `M5`).
