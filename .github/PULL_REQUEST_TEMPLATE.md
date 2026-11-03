## 1. Identificação do Pacote (EAP / Gantt)

- **Pacote Operacional (`G01–G04`, `B01–B05`, `M01–M05`, `F01–F05`)**: `<!-- Ex: B01 -->`
- **Subpacote(s) da EAP (`1.1–7.4`)**: `<!-- Ex: 3.5, 4.1 -->`
- **Issue Relacionada**: Closes #`<!-- Número da Issue -->`
- **Marco (*Milestone*)**: `<!-- M1 / M2 / M3 / M4 / M5 -->`

---

## 2. Resumo das Alterações

- 

---

## 3. Governança RACI e Revisão Obrigatória

- **Executor (`R` — *Responsible*)**: @
- **Aprovador da Camada (`A` — *Accountable*)**: @

---

## 4. Checklist de Pronto (*Definition of Done — DoD*)

- [ ] **Aderência à Spec (SDD)**: Todos os requisitos (`RF`/`RNF`/`RN`) e contratos (`openapi.yaml` / DDL) da Spec em `specs/` foram respeitados.
- [ ] **Testes Automatizados (TDD)**: Casos de teste (`UT-*` / `IT-*` / `E2E-*`) implementados e passando com cobertura $\ge 70\%$.
- [ ] **Guardrails e Zero Alucinação**: Sem regressão de *Faithfulness* ($\ge 0,85$), voltagem (`127V`/`220V`) ou estoque (`stock_quantity > 0`).
- [ ] **Clean Code e Layers**: Isolamento `Presentation -> Application -> Domain <- Infrastructure` preservado, sem *magic numbers*.
