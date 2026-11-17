# Correções da avaliação B05 / PR #26

## Objetivo e aceite

Implementar uma avaliação que observe o pipeline de produção e reprove evidência,
métrica ou cobertura inválida. A entrega não declara homologação enquanto não
existir uma execução real dos 50 casos no commit integrado após B04, conforme a
baseline e a seção 5 da spec. O seed atual contém manuais sintéticos de demonstração;
o relatório deve identificar isso e não alegar auditoria do fabricante ou do PO.

## Plano de execução

1. Escrever regressões para vazamento de gabarito, ação inventada, checkpoints de
   outra execução, juiz ausente/NaN, recuperação vazia/recall baixo, inversão
   elétrica, fatos sugeridos na pergunta, preço/capacidade/página inventados e
   ofertas incompatíveis com estoque/tensão/preço.
2. Reconstruir os 50 casos nas categorias 12/10/10/10/8 usando somente páginas e
   fatos existentes. Registrar referências estáveis de origem, página, trecho e
   SHA-256; validar os trechos no chunking de produção e resolver os UUIDs do banco
   em tempo de execução. Estoque zero será cenário explícito, sem alterar o seed
   nem o banco de produção. Casos B04 mantêm suas expectativas e podem reprovar a
   integração atual; não substituir uma recomendação ausente por um gabarito.
3. Separar entrada do pipeline, observação do turno e dados de referência. Executar
   RAGOrchestrator com os mesmos adaptadores de produção, observando recuperação,
   chamadas ao gerador, eventos, citações, erros e ofertas realmente publicadas.
   Validar que o banco corresponde ao corpus/configuração declarados.
4. Usar RAGAS versionado com juiz configurado separadamente do gerador para
   fidelidade/relevância. Não oferecer pontuação lexical substituta. Validar fatos
   críticos determinísticos por unidade/SKU e regras de negócio em dados
   estruturados. Falhas do juiz e ausência de amostras bloqueiam o aceite.
5. Associar checkpoints à configuração completa: modo, commit/código, fixtures,
   corpus, chunking, modelos, endpoints e política. Rejeitar formato legado e
   cache incompatível; salvar atomicamente e sem segredos.
6. Atualizar documentação e CI: testes offline verificam o mecanismo, sem conceder
   homologação; execução live exige configuração explícita e gera relatório
   rastreável. Invalidar as conclusões do relatório antigo e preparar comentário
   para a PR com evidências e pendências reais.

## Validação

- Testes de regressão do avaliador, adapter do orquestrador e corpus.
- Suítes unitárias backend/middleend e contratos documentais.
- Ruff, mypy, cobertura e integração PostgreSQL/pgvector quando disponível.
- Verificar falha explícita da CLI sem configuração live, sem rede nos testes.
- Execução cognitiva real apenas com configuração de geração/juiz e banco
  verificado; falta de configuração permanece PENDENTE no relatório.

## Fontes de implementação

- `specs/01_BASELINE_REVISADA.md` e spec B05, seção 5.
- `backend/app/rag/orchestrator.py`, ingestão e repositório PostgreSQL atuais.
- RAGAS 0.3.0: Faithfulness e ResponseRelevancy / SingleTurnSample.
  O resolver comprovou que 0.3.9/0.4.2 exigem Instructor incompatível com o
  OpenAI SDK 3.46.0 do projeto. Fixar também langchain-community 0.3.31 (a versão
  0.4 removeu imports necessários) e Pillow, sem alterar o SDK de produção.
  <https://docs.ragas.io/en/v0.3.0/concepts/metrics/available_metrics/faithfulness/>


## Retomada e execução integrada

Integração B01/B03/B04 concluída, incluindo a regressão de compra exclusiva
corrigida na B04 (`0181b20`). O adaptador agora usa o motor de recomendações real,
registra as evidências efetivamente entregues ao gerador e preserva o texto emitido
antes de erros. Corpus/relacionamentos/vetores e checkpoints são verificados;
relatório anterior retirado como evidência de aceite. CI e gate real foram
separados, com lockfile e Action manual. Fontes e auditoria permanecem pendentes
de aprovação humana. O usuário está confirmando provedores/modelos com o time;
nenhuma chave/configuração de execução real estava disponível nesta sessão.

Relatório: `docs/reviews/2026-11-16-b05-review.md`.
