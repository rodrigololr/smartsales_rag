# Plano de Implementação — Pacote P1 (Data + KB Ingestion — Consultor Unificado)

- **Pacote**: `P1` (Data + KB ingestion — Consultor Unificado)
- **Branch**: `feat/consultor-p1`
- **Worktree**: `/home/antonio/Documentos/gerencia_projeto/smartsales_p1`
- **Especificação de Referência**: `specs/components/04_consultor_unificado_spec.md` (§3, §8, §9, §10, §11)

---

## 1. Objetivo e Escopo

Implementar o pacote **P1 (Data + KB ingestion)** do Consultor Unificado mantendo intactos `data/catalog.json`, `data/product_relations.json`, manuais legados, `golden_set.json` e `corpus_manifest.json` (homologação RAGAS):

1. **Catálogo e Relações do Consultor**:
   - `data/catalog_consultor.json` com os 15 novos SKUs de §8 (`PC-VX3-BIV`, `PC-VX5-BIV`, `PC-VX5P-220V`, `PC-VX7-220V`, `NB-NX15-BIV`, `NB-NX16-BIV`, `NB-NX17-BIV`, `MN-LM24-BIV`, `MN-LM27Q-BIV`, `MN-LM27U-BIV`, `WC-1080-60`, `WC-2K-60`, `SF-2L-150`, `SF-3L-180`, `SF-3L-210R`).
   - `data/product_relations_consultor.json` com os 6 relacionamentos de cross-sell PC/Notebook → Monitor (`affinity_weight = 0.900`, RN05).
   - Escadas de upsell compatíveis com RN04 (`ratio <= 1.35`) e `NB-NX17-BIV` com `stock_quantity = 0` (R03).
2. **Manuais e Imagens**:
   - 15 manuais `data/manuals/<SKU>.txt` com 6 páginas separadas por `\f` (`<= 400` tokens por página), tabela `## Desempenho em jogos` na página 4 de todos os 7 manuais de `Computadores` com FPS crescente por tier, e tabela de dimensões nos manuais de `Sofás`.
   - 15 placeholders SVG em `frontend/public/images/<sku-lower>.svg`.
3. **Base de Conhecimento Curada (`data/knowledge/`)**:
   - Reorganização nos 6 arquivos de §11 A2 (`KB-GTA6-PLATAFORMAS.txt`, `KB-GTA-RP.txt`, `KB-GTAV-REQUISITOS.txt`, `KB-ROBLOX-REQUISITOS.txt`, `KB-TWITCH-TRANSMISSAO.txt`, `KB-SOFA-ESPACO.txt`) contendo exclusivamente os fatos verificados existentes e as 7 strings congeladas de §11 A3 literalmente em linhas próprias.
   - Remoção dos 5 arquivos antigos e atualização de `data/knowledge/README.md` (incluindo documentação do comando de seed base-only para o RAGAS).
4. **DDL e Ingestão de `knowledge_chunks`**:
   - Tabela `knowledge_chunks` em `backend/app/db/schema.sql`.
   - Escritas de KB em `backend/app/db/repository.py`.
   - Módulo `backend/app/ingestion/knowledge.py` (`KnowledgeDoc`, `knowledge_docs`, indexação transacional idempotente e limpeza de `doc_id` removidos).
   - CLI `backend/app/ingestion/run.py` com `--catalog` e `--relations` como `action="append"` e novo argumento `--knowledge DIR`.
   - Atualização do comando `ingest` em `docker-compose.yml`.

---

## 2. Arquivos Afetados

- `data/catalog_consultor.json` (novo)
- `data/product_relations_consultor.json` (novo)
- `data/manuals/<15 novos SKUs>.txt` (novos)
- `data/knowledge/KB-*.txt` e `data/knowledge/README.md` (reorganizados/atualizados)
- `frontend/public/images/<15 novos skus>.svg` (novos)
- `backend/app/db/schema.sql` (modificado)
- `backend/app/db/repository.py` (modificado)
- `backend/app/ingestion/knowledge.py` (novo)
- `backend/app/ingestion/run.py` (modificado)
- `docker-compose.yml` (modificado)
- `backend/tests/unit/test_consultor_seed.py` (novo)
- `backend/tests/integration/test_knowledge_ingestion.py` (novo)

---

## 3. Lista de Tarefas Atômicas (TDD — 1 Commit por Task)

- [x] **Task 1 (Red — Testes Unitários do Seed e KB)**: Criar `backend/tests/unit/test_consultor_seed.py` validando catálogo consultor, relações RN05, escadas RN04, manuais (tabela de jogos na p. 4, dimensões de sofás, claims V/W/L), SVGs e strings congeladas da KB (§11 A2/A3).
  - Commit: `test(P1): add unit tests for consultor catalog, manuals, relations and KB seed`
- [x] **Task 2 (Green — Dados do Consultor, Manuais, SVGs e KB)**: Criar `data/catalog_consultor.json`, `data/product_relations_consultor.json`, 15 manuais em `data/manuals/`, 15 SVGs em `frontend/public/images/`, reorganizar `data/knowledge/` nos 6 arquivos de §11 A2/A3 e atualizar `data/knowledge/README.md`.
  - Commit: `feat(P1): add consultor catalog, relations, manuals, images and curated KB`
- [x] **Task 3 (Red — Testes de Integração de Ingestão da KB e Multi-Seed)**: Criar `backend/tests/integration/test_knowledge_ingestion.py` cobrindo `knowledge_docs`, ingestão idempotente de `knowledge_chunks`, atualização por SHA-256, remoção de doc excluído, preservação de `manual_chunks` e múltiplos `--catalog`/`--relations`.
  - Commit: `test(P1): add integration tests for knowledge_chunks and multi-file ingestion`
- [x] **Task 4 (Green — Schema, Repository, Knowledge Ingestion e CLI/Docker Compose)**: Implementar `knowledge_chunks` em `schema.sql`, funções de escrita em `repository.py`, `backend/app/ingestion/knowledge.py`, suporte multi-arquivo e `--knowledge` em `run.py` e comando seed em `docker-compose.yml`.
  - Commit: `feat(P1): implement knowledge_chunks ingestion and multi-file seed CLI`

---

## 4. Critérios de Aceite e Comandos de Validação

```bash
cd backend && /home/antonio/Documentos/gerencia_projeto/smartsales_rag/.venv/bin/python -m pytest tests/unit -q
cd backend && TEST_DATABASE_URL=postgresql://smartsales:smartsales@127.0.0.1:5561/smartsales /home/antonio/Documentos/gerencia_projeto/smartsales_rag/.venv/bin/python -m pytest tests/integration/test_knowledge_ingestion.py tests/integration/test_pgvector_ingestion.py -q
cd backend && /home/antonio/Documentos/gerencia_projeto/smartsales_rag/.venv/bin/python -m pytest tests/ragas_eval/test_corpus.py -q
cd backend && /home/antonio/Documentos/gerencia_projeto/smartsales_rag/.venv/bin/python -m ruff check app/db/repository.py app/ingestion/knowledge.py app/ingestion/run.py tests/unit/test_consultor_seed.py tests/integration/test_knowledge_ingestion.py
```
