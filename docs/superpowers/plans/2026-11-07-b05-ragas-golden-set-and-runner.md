# B05: Golden Set e Runner RAGAS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o Golden Set canônico de 50 casos auditados (`golden_set.json`), os modelos de validação, os cálculos de métricas cognitivas e comerciais e o runner de avaliação automatizada com verificação estrita dos gates de homologação da spec B05/EAP 5.1.

**Architecture:** Módulo autocontido em `backend/tests/ragas_eval/` estruturado em camadas: modelos Pydantic (`models.py`) para tipagem estrita de fixtures e relatórios; motor de métricas (`metrics.py`) para Faithfulness, Precision@5/Precision@returned/Recall, Alucinação Técnica (G-OUT), Answer Relevance e Filtros de Negócio; runner executável (`eval_runner.py`) capaz de rodar em modo determinístico/mock ou conectado a LLM; e suíte de testes (`test_golden_set.py`) integrada ao pytest e CI.

**Tech Stack:** Python 3.12, Pydantic 2.12+, Pytest 9+, standard library (json, pathlib, dataclasses, math).

**Spec:** [`specs/tdd_and_quality/03_rag_golden_set_and_ragas_spec.md`](file:///C:/Users/diogo/Documents/GP/smartsales_rag/specs/tdd_and_quality/03_rag_golden_set_and_ragas_spec.md)

## Global Constraints

- **Faithfulness macro médio**: $\ge 0,85$ (meta SMART $\ge 0,90$) nos casos respondíveis aplicáveis.
- **Taxa de Alucinação Técnica ($G\text{-OUT}$)**: $\le 0,05$ ($5\%$) de respostas com dados críticos divergentes (voltagem, potência, capacidade, pressão, preço, citação).
- **Precisão de Recuperação**: $P@5 \ge 0,80$ para casos com $\ge 5$ chunks; nos demais, $\text{precision@returned} \ge 0,80$ e $\text{recall} \ge 0,80$.
- **Answer Relevance**: $\ge 0,85$ nos casos com resposta publicada.
- **Aderência aos Filtros de Negócio**: $100\%$ (`stock > 0`, voltagem solicitada respeitada, teto $+35\%$ upsell).
- **Casos Adversariais e Negativos**: $100\%$ de `expected_action` correto (`REFUSE` em G-IN, `FALLBACK` em baixa similaridade), com zero chamadas abertas de LLM e zero alucinação técnica.
- **Média macro**: ignora exclusivamente casos rotulados como não aplicáveis (`applicable_metrics`), nunca falhas ou NaN.
- **Fim de linha**: LF obrigatório em todos os arquivos (`.json`, `.py`, `.md`).

## Review Focus

1. **Casos não-respondíveis**: Casos com `expected_action="REFUSE"` ou `"FALLBACK"` não devem computar Faithfulness ou P@5, devendo exigir 100% de recusa/fallback corretos sem gerar NaN na média macro.
2. **Casos com menos de 5 evidências no corpus**: Não penalizar artificialmente no denominador 5 quando a spec define apenas 1 a 4 chunks relevantes rotulados — usar `precision@returned` e `recall` conforme Seção 5 da spec.
3. **Casos adversariais de injeção**: Confirmar que tentativas de sobrescrita de regras ("esqueça as instruções...") são capturadas pelo `InputGuardrail` (`G-IN`) retornando código de violação `PROMPT_INJECTION`.
4. **Violações críticas de voltagem**: Qualquer menção de 127V para SKU 220V ou vice-versa em resposta gerada deve ser detectada como violação de Alucinação Técnica mesmo que o score de similaridade textual seja alto.
5. **Fixtures auditadas e imutáveis**: O JSON de 50 casos deve conter distribuição exata (12 Cat 1, 10 Cat 2, 10 Cat 3, 10 Cat 4, 8 Cat 5) com SKUs válidos do catálogo oficial `data/catalog.json`.

---

### Task 1: Estrutura do Golden Set Canônico (`golden_set.json`)

**Files:**
- Create: `backend/tests/ragas_eval/golden_set.json`
- Test: `backend/tests/ragas_eval/test_golden_set.py`

**Interfaces:**
- Produces: 50 fixtures canônicas em JSON distribuídas em 5 categorias (`RAGAS-GS-01` a `RAGAS-GS-50`), consumidas pelo runner e suíte de testes.

- [ ] **Step 1: Escrever teste de validação do arquivo e schema do Golden Set**
- [ ] **Step 2: Executar teste e verificar falha (arquivo não encontrado)**
- [ ] **Step 3: Criar `backend/tests/ragas_eval/golden_set.json` com os 50 casos canônicos auditados**
- [ ] **Step 4: Executar teste e verificar aprovação com 50 fixtures válidas**
- [ ] **Step 5: Commit do Golden Set**

---

### Task 2: Modelos Pydantic de Fixtures e Avaliação (`models.py`)

**Files:**
- Create: `backend/tests/ragas_eval/models.py`
- Test: `backend/tests/ragas_eval/test_golden_set.py`

**Interfaces:**
- Produces: `GoldenSetFixture`, `EvalCaseResult`, `MetricScore`, `EvaluationReport` com validações estritas de categorias, ações esperadas e formatos de citação.

- [ ] **Step 1: Escrever teste unitário para parsing e validação com os modelos Pydantic**
- [ ] **Step 2: Executar teste e verificar falha (módulo não encontrado)**
- [ ] **Step 3: Implementar `models.py` com dataclasses/Pydantic models tipados**
- [ ] **Step 4: Executar teste e verificar aprovação de validação**
- [ ] **Step 5: Commit dos modelos**

---

### Task 3: Motores de Métricas Cognitivas e Comerciais (`metrics.py`)

**Files:**
- Create: `backend/tests/ragas_eval/metrics.py`
- Test: `backend/tests/ragas_eval/test_golden_set.py`

**Interfaces:**
- Consumes: `GoldenSetFixture`, `EvalCaseResult` de `models.py`.
- Produces: funções `calculate_faithfulness()`, `calculate_retrieval_precision()`, `calculate_technical_hallucination()`, `calculate_answer_relevance()`, `calculate_business_rule_adherence()`, `aggregate_macro_metrics()`.

- [ ] **Step 1: Escrever testes unitários para cada métrica com casos controlados de acerto e falha**
- [ ] **Step 2: Executar testes e verificar falha**
- [ ] **Step 3: Implementar calculadoras determinísticas em `metrics.py`**
- [ ] **Step 4: Executar testes e verificar aprovação com assertions matemáticas exatas**
- [ ] **Step 5: Commit das métricas**

---

### Task 4: Runner de Homologação e Relatórios (`eval_runner.py`)

**Files:**
- Create: `backend/tests/ragas_eval/eval_runner.py`
- Test: `backend/tests/ragas_eval/test_golden_set.py`

**Interfaces:**
- Consumes: `golden_set.json`, `models.py`, `metrics.py`, `backend/app/guardrails`.
- Produces: CLI e função `run_ragas_evaluation(fixture_path, mock_mode=True)` gerando relatório com verificação dos gates (Pass/Fail) e sumário em markdown.

- [ ] **Step 1: Escrever teste para a execução completa do runner em mock/offline**
- [ ] **Step 2: Executar teste e verificar falha**
- [ ] **Step 3: Implementar `eval_runner.py` com CLI (`--fixture`, `--output`, `--gate-check`)**
- [ ] **Step 4: Executar teste e verificar aprovação dos 5 gates de homologação**
- [ ] **Step 5: Commit do runner**

---

### Task 5: Integração Completa com Pytest, Ruff e Mypy

**Files:**
- Modify: `backend/tests/ragas_eval/test_golden_set.py`
- Create: `backend/tests/ragas_eval/__init__.py`

**Interfaces:**
- Consumes: toda a suíte de avaliação.
- Produces: 100% dos testes rodando em `pytest tests -v`, com `ruff check app tests` e `mypy app` estritamente limpos.

- [ ] **Step 1: Executar suíte completa de testes no backend**
- [ ] **Step 2: Executar linter `ruff check app tests` e corrigir eventuais avisos**
- [ ] **Step 3: Executar typechecker `mypy` e validar conformidade**
- [ ] **Step 4: Conferir integridade de bytes (LF e zero CRLF)**
- [ ] **Step 5: Executar checklist `entrega-revisavel` e commit final**
