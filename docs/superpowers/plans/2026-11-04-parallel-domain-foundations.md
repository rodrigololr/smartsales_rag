# B04, M03 e M02 — plano de implementação

Execução paralela autorizada pelo usuário em 04/11/2026. Implementar três
entregas pequenas da arquitetura existente, cada uma verificável sem serviços
externos. Baseline: `specs/01_BASELINE_REVISADA.md`; os contratos públicos não mudam.

## B04 — motor determinístico

- [x] Criar testes de elegibilidade, limites inclusivos de preço, compatibilidade,
  ordenação por score/preço/SKU e composição de até três recomendações.
- [x] Executar os testes e observar falha antes da implementação.
- [x] Implementar modelos de domínio e `RecommendationEngine` em
  `backend/app/recommendation/`, com Decimal e candidatos fornecidos pelo chamador.
- [x] Validar testes, cobertura, lint e tipagem. Não declarar SQL/RAGAS integrados.

## M03 — identidade do cache

- [x] Criar testes de NFC/espaços, preservação de ordem, filtros completos,
  histórico cronológico e invalidação por versões.
- [x] Executar os testes e observar falha antes da implementação.
- [x] Implementar `build_cache_key` em `middleend/app/cache/`, independente de Redis.
- [x] Validar testes, cobertura, lint e tipagem.

## M02 — gerador SSE

- [x] Criar testes de sucesso, fallback, EOF, falha parcial, desconexão,
  cancelamento, persistência antes de done e liberação de recursos.
- [x] Executar os testes e observar falha antes da implementação.
- [x] Implementar `sse_chat_generator` em `middleend/app/sse/` com stream e
  callbacks injetados. Recebe somente texto previamente validado pelo Backend.
- [x] Validar testes, cobertura, lint e tipagem.

## Integração

- [x] Manter as suítes de cada serviço separadas: ambos possuem pacote `app`.
- [x] Adicionar ambiente de desenvolvimento reproduzível, comandos e CI.
- [x] Corrigir a descoberta de exemplos documentais que varria `.venv`, com
  regressão primeiro; continuar validando documentos raiz e toda a pasta specs.
- [x] Rever os três módulos e executar contratos, testes, cobertura, lint e mypy.

Critério de parada: módulos locais testados e documentados. Estes incrementos não
concluem os pacotes B04/M02/M03: faltam adaptadores SQL/Redis/HTTP, API integrada,
frontend, medições de SLA e Golden Set curado. Nenhum deploy ou push nesta entrega.

## Resultado verificado em 04/11/2026

- Backend: 40 testes aprovados; cobertura incluindo branches de 89,62%.
- Middle-end: 60 testes aprovados (31 cache e 29 SSE); cobertura incluindo
  branches de 95,78%.
- Contratos/documentação: 17 testes aprovados, incluindo três regressões de
  descoberta de exemplos.
- Ruff e mypy estrito aprovados nas duas camadas.
- Revisão independente encerrada sem achados críticos ou importantes pendentes.
  Foram corrigidas rejeição de campos opcionais nos cards SSE e aceitação de
  voltagens/preços fora do contrato, com testes de regressão.

Total: 117 testes locais aprovados. A CI foi configurada; sua execução remota
depende da publicação da branch. Não foi realizada homologação integrada.
