# Baseline SDD revisada — decisões normativas

Status: aprovada tecnicamente somente após revisão da PR. Responsáveis: contratos Pablo, RAG Filipe/Diogo, aceite Walber. Mudanças de comportamento atualizam contrato, regras e testes no mesmo PR. Esta baseline e `openapi.yaml` prevalecem sobre exemplos ilustrativos antigos; inconsistências devem ser corrigidas antes de implementar.

1. Cache preserva a ordem e inclui histórico, filtros completos e versão da política. Dinheiro usa JSON number com serialização explícita de Decimal; não calcular dinheiro em float.
2. G-OUT valida sentenças em buffer privado por SKU, atributo, unidade e suporte da evidência. Correction não autoriza expor erro factual temporário. Preço de outro SKU não é evidência.
3. Preferência elétrica restringe oferta; SKU explícito continua recuperável para explicar incompatibilidade.
4. Métricas de recuperação aplicam-se a casos respondíveis; negativos exigem recusa/fallback correto. Não converter erro/NaN de avaliação em aprovação.
5. Reindexação substitui atomicamente a versão completa do manual; turno repetido possui client_request_id persistente por sessão; vitrine possui GET products.
6. EOF interno sem end e falha após token resultam em erro; cleanup sempre ocorre. Só texto aprovado é persistido/reproduzido. UI descarta conteúdo parcial no evento error.
7. B05 prepara testes; o aceite completo exige versão integrada após B04 e reteste em F05. Caminhos de ingestão/recomendação/dados/configurações também acionam gate.
8. Ranking define normalização, fallback por tier para produtos sem litros e desempate determinístico.

Definition of Ready: requisito identificável, entradas/saídas tipadas, negativos/fronteiras, responsável e decisões aprovadas antes de codificar. RED deve falhar pelo comportamento esperado; GREEN e REFACTOR preservam testes. Não declarar testes de aplicação ou 50 fixtures concluídos nesta branch documental.

Rastreabilidade das correções: itens da revisão 01 cache (CT-SDD-01), 02 buffer (02), 03 evidência (03), 04 métricas (04), 05 dinheiro (05), 06 versões (06), 07 retry (07), 08 vitrine (08), 09 fatos por SKU (09), 10 gatilhos (10), 11 aceite final (11), 12 ranking (12), 13 stream (13). O catálogo define as asserções. Fixtures reais restantes continuam obrigação anterior à homologação, não foram inventadas para aprovar a documentação.
