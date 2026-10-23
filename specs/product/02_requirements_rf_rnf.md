# Especificação de Requisitos Funcionais (`RF`) e Não-Funcionais (`RNF`) — `EAP 1.2`, `1.4`

Este documento detalha todos os **Requisitos Funcionais (`RF01` a `RF16`)** e **Requisitos Não-Funcionais (`RNF01` a `RNF12`)** do **SmartSales RAG**, mapeados diretamente aos **Casos de Uso (`UC01` a `UC09`)**, aos pacotes da **EAP (`1.0` a `7.0`)** e à **Árvore de Métricas de Qualidade**.

---

## 1. Catálogo de Requisitos Funcionais (`RF01` a `RF16`)

| ID | Requisito Funcional | Caso de Uso | Pacote EAP / Gantt | Prioridade | Camada Principal |
| :---: | :--- | :---: | :---: | :---: | :---: |
| **RF01** | **Ingestão e Normalização de Catálogo**: O sistema deve ingerir dados estruturados do catálogo de produtos (`SKU`, nome, categoria, marca, preço atual, estoque atual, voltagem `127V`/`220V`/`Bivolt`, capacidade em litros, potência em watts, URL de imagem, `marketplace` [`AMAZON`, `MERCADO_LIVRE`, `SHOPEE`, `LOJA_OFICIAL`] e `checkout_url` direto de afiliado/anúncio) a partir do arquivo *seed* local (`data/catalog.json` ou `.csv`), persistindo-os no PostgreSQL por meio da CLI de ingestão (`python -m app.ingestion.run`), validando o *schema* e incrementando `catalog:version` no Redis ao final. | `UC08`, `UC02` | `EAP 4.1` (`B01`) | Alta (*Must*) | Backend / DB |
| **RF02** | **Extração, Chunking e Indexação Vetorial de Manuais PDF**: O sistema deve extrair textos e tabelas de manuais PDF, segmentá-los em *chunks* de `500 tokens` com *overlap* de `50 tokens`, preservar metadados (`sku`, `manual_title`, `page_number`, `section`) e indexar seus *embeddings* (`1536d`) no `pgvector` com índice `HNSW`, registrando o status de cada manual em `ingestion_jobs` (com *retry* e estado `NEEDS_INTERVENTION`). | `UC08`, `UC02` | `EAP 4.2` (`B03`) | Alta (*Must*) | Backend / IA |
| **RF03** | **Gestão de Sessão e Histórico Multi-turno**: O sistema deve criar e manter sessões de conversa identificadas por `session_id` (`UUID v4`), armazenando os últimos turnos da conversa no Redis (`TTL = 1800s` de inatividade) e no PostgreSQL para resolução de correferências (ex.: *"e ele cabe na bancada?"*). | `UC07` | `EAP 4.5` (`M01`, `M02`) | Alta (*Must*) | Middle-end |
| **RF04** | **Classificação de Intenção e Extração de Entidades**: Ao receber uma mensagem do usuário, o orquestrador deve identificar a intenção (`TECHNICAL_QA`, `PRODUCT_COMPARISON`, `PURCHASE_INTENT`, `OUT_OF_DOMAIN`) e extrair filtros estruturados (`categoria`, `voltagem`, `capacidade_min`, `orcamento_max`, `sku_referencia`). | `UC01`, `UC03` | `EAP 4.3` (`B02`) | Alta (*Must*) | Backend / IA |
| **RF05** | **Busca Híbrida Semântica + Filtros SQL**: O sistema deve realizar busca híbrida combinando distância de cosseno no `pgvector` (`similarity_score >= 0.72`, `top_k = 5`) com cláusulas SQL obrigatórias (`is_active = TRUE`, escopo do `SKU` em contexto e compatibilidade de voltagem/categoria). O filtro `stock_quantity > 0` **não** se aplica à busca de *chunks* (permite responder sobre item esgotado), mas é obrigatório em toda recomendação (`RN01`). | `UC02` | `EAP 4.3` (`B02`, `B03`) | Alta (*Must*) | Backend / DB |
| **RF06** | **Geração de Resposta Contextualizada via Streaming SSE**: O sistema deve transmitir a resposta gerada pelo LLM token a token para o cliente utilizando o protocolo *Server-Sent Events* (`text/event-stream`). | `UC01` | `EAP 4.6` (`B02`, `M02`) | Alta (*Must*) | Middle-end / Back |
| **RF07** | **Citação Estruturada e Verificável da Fonte**: Toda resposta baseada em manual técnico deve incluir citações estruturadas (`manual_title`, `page_number`, `chunk_id`, `excerpt`) tanto no texto quanto no evento SSE `citations`. | `UC01` | `EAP 4.3`, `4.9` (`B03`, `F03`) | Alta (*Must*) | Back / Front |
| **RF08** | **Guardrail Anti-Alucinação e Fallback Seguro**: Caso a busca híbrida retorne `0 chunks` ou `similarity_score < 0.72`, ou caso o validador pós-geração detecte divergência numérica de voltagem/capacidade/preço, o sistema deve bloquear a resposta alucinada e emitir mensagem padronizada de *fallback* seguro. | `UC01`, `UC02` | `EAP 4.3` (`B03`) | Alta (*Must*) | Backend / IA |
| **RF09** | **Cache Semântico de Consultas Frequentes no Redis**: O Middle-end deve verificar se a consulta normalizada (com mesmos filtros de produto/voltagem) já consta em cache no Redis (`TTL = 3600s`), retornando a resposta validada sem custo adicional de LLM em caso de *Cache Hit*. | `UC02` | `EAP 4.7` (`M03`) | Média (*Should*) | Middle-end |
| **RF10** | **Interface Conversacional Contextual (Painel Lateral Estilo Amazon) com Streaming**: Ao selecionar um produto na vitrine, o Frontend deve abrir o **Painel Lateral do Consultor IA (*Side-Drawer / Split-View*)** pré-contextualizado com o `SKU` selecionado, exibindo indicadores de processamento (*"Consultando manual técnico..."*) e renderizando os tokens SSE progressivamente. | `UC07`, `UC01` | `EAP 4.9` (`F01`, `F02`) | Alta (*Must*) | Frontend |
| **RF11** | **Exibição Interativa de Badges de Citação**: O Frontend deve renderizar *badges* clicáveis ao final das afirmações técnicas (ex.: `📄 Manual Airfryer 4L — p. 14`), permitindo ao usuário inspecionar o trecho original do manual. | `UC01` | `EAP 4.9` (`F03`) | Alta (*Must*) | Frontend |
| **RF12** | **Motor Consultivo de Cross-selling e Upselling**: O sistema deve calcular e retornar até 3 recomendações estruturadas por turno: produto principal (`PRIMARY`), até 1 item complementar compatível (`CROSS_SELL`) e até 1 modelo superior (`UPSELL` com preço até `+35%` do item base), todos com `stock_quantity > 0`. | `UC03` | `EAP 4.4` (`B04`, `M04`) | Alta (*Must*) | Backend / IA |
| **RF13** | **Vitrine Dinâmica de Product Cards no Chat com Link de Marketplace**: O Frontend deve renderizar *Product Cards* interativos abaixo da resposta textual contendo foto, nome, `SKU`, badge de voltagem, preço formatado (`R$`), selo da recomendação (*Ideal para você*, *Upgrade recomendado*, *Compre junto*) e CTA indicando o canal (`Comprar na Amazon / Mercado Livre / Shopee`). | `UC03`, `UC04` | `EAP 4.10` (`F04`) | Alta (*Must*) | Frontend |
| **RF14** | **Coleta de Feedback Explícito (*Like / Dislike*)**: O usuário deve poder avaliar cada resposta do assistente com *Like* (`👍`) ou *Dislike* (`👎` + motivo opcional), registrando o evento com `session_id`, `message_id` e `chunk_ids` para auditoria do ciclo PDCA. | `UC06` | `EAP 4.11` (`F03`, `M05`) | Alta (*Must*) | Front / Mid |
| **RF15** | **Fluxo de Mock Checkout, Rastreamento de Conversão e Redirecionamento Direto**: Ao clicar no CTA de compra em um *Product Card*, o sistema deve validar em tempo real o estoque e o preço atualizados via endpoint `POST /api/v1/checkout/mock`, registrar a conversão (CTR) no banco e redirecionar/abrir o `checkout_url` direto do produto no marketplace (`Amazon`, `Mercado Livre`, `Shopee` ou `Loja Oficial`). | `UC05` | `EAP 4.8` (`M05`, `F04`) | Alta (*Must*) | Mid / Front |
| **RF16** | **Painel de Métricas de Conversão e Qualidade do RAG**: O sistema deve disponibilizar ao Operador/Lojista a página `/admin/metricas` (protegida por `ADMIN_TOKEN`, sem login multi-lojista) que consome `GET /api/v1/metrics/summary` e exibe CTR dos cards, conversões confirmadas, dúvidas mais frequentes, `TTFT` (`p50`/`p95`), tempo total `p95`, *cache hit ratio*, taxa de erros `5xx` e aprovação (*likes/dislikes*). | `UC09` | `EAP 4.7`, `4.10` (`M04`, `F04`) | Média (*Should*) | Mid / Front |

---

## 2. Catálogo de Requisitos Não-Funcionais (`RNF01` a `RNF12`)

| ID | Categoria (ISO 25010) | Especificação Técnica e Limiar de Aceite (SLA / Gate) | Métrica na Árvore de Qualidade | Pacote EAP |
| :---: | :--- | :--- | :--- | :---: |
| **RNF01** | **Eficiência de Desempenho (TTFT)** | O tempo até o primeiro token (*Time to First Token — TTFT*) via SSE deve ser **$\le 1,5\text{ s}$** (alvo nominal) e **$\le 2,0\text{ s}$ no percentil 95 (`p95`)**. | Latência de Streaming (`TTFT`) | `EAP 4.6`, `5.3` |
| **RNF02** | **Eficiência de Desempenho (Tempo Total)** | O tempo total de geração completa da resposta + cards deve ser **$\le 8,0\text{ s}$ no percentil 95 (`p95`)**. | Tempo Total de Resposta | `EAP 4.6`, `5.3` |
| **RNF03** | **Eficiência de Recursos (Cache)** | A camada de cache semântico no Redis deve atingir **$\text{Cache Hit Ratio} \ge 30\%$** nas baterias de perguntas recorrentes de catálogo. | Eficiência de Cache (`Redis`) | `EAP 4.7`, `5.3` |
| **RNF04** | **Adequação Funcional (Fidelidade RAG)** | O índice de fidelidade ao contexto (*Faithfulness*) avaliado via RAGAS no *Golden Set* deve ser **$\ge 0,85$** (bloqueante de CI), com meta de precisão técnica **$\ge 90\%$** e **Taxa de Alucinação $\le 5\%$**. | Fidelidade & Alucinação | `EAP 4.3`, `5.1` |
| **RNF05** | **Adequação Funcional (Precisão de Busca)** | A recuperação híbrida e o motor de recomendação devem atingir **$\text{Precision@5 (P@5)} \ge 0,80$** e **100% de aderência** aos filtros de estoque e voltagem. | Relevância de Recomendação | `EAP 4.4`, `5.1` |
| **RNF06** | **Confiabilidade e Disponibilidade** | O API Gateway e o Orquestrador devem operar com **Disponibilidade $\ge 99\%$** durante as janelas de teste e **Taxa de Erros `5xx` $\le 1\%$**. | Disponibilidade da API | `EAP 4.5`, `5.2` |
| **RNF07** | **Tolerância a Falhas e Resiliência** | Em caso de *timeout* (`> 3 s` sem o 1º token) ou falha `5xx` na API da OpenAI, o sistema deve executar **1** nova tentativa com *backoff* de `250 ms` e, persistindo a falha, retornar recomendações determinísticas via SQL sem derrubar a sessão (`HTTP 200` com evento SSE `error` `LLM_UNAVAILABLE` + `recommendations` + `done`). Pior caso $\approx 6,3\text{ s}$, dentro do `RNF02`. | Resiliência / Riscos `R13`, `R02` | `EAP 4.5`, `4.6` |
| **RNF08** | **Usabilidade e Responsividade** | A interface deve ser 100% responsiva (`360px` mobile a `1920px` desktop), atingir aprovação de usuários **$\ge 80\%$ de *likes*** e **CTR nos cards $\ge 10\%$**. | Usabilidade e Conversão | `EAP 4.9`, `4.10` |
| **RNF09** | **Segurança e Anti-Prompt Injection** | Todas as entradas do usuário devem ser sanitizadas contra *Prompt Injection*, *Jailbreak* e *SQL Injection* (uso exclusivo de *queries* parametrizadas e bloqueio de instruções que tentem sobrescrever o *System Prompt* ou alterar preços). | Segurança / Risco `R05` | `EAP 4.3`, `4.5` |
| **RNF10** | **Manutenibilidade e Testabilidade** | O código nas 3 camadas deve manter **cobertura de testes automatizados $\ge 70\%$** e **`0` defeitos críticos abertos** na branch `main`. | Manutenibilidade e Código | `EAP 3.5`, `5.2`, `5.4` |
| **RNF11** | **Padronização de Contratos** | Todas as APIs entre Frontend, Middle-end e Backend devem ser especificadas e validadas sob **OpenAPI 3.1** e `Pydantic v2` / `TypeScript strict`. | Governança de Contratos | `EAP 3.3`, `7.1` |
| **RNF12** | **Portabilidade e Reprodutibilidade** | Todo o ambiente local de desenvolvimento (`PostgreSQL 16 + pgvector`, `Redis 7`, `Backend`, `Middle-end`, `Frontend`) deve subir de forma determinística via `docker compose up`. | Infraestrutura / Docker | `EAP 3.5` (`B01`) |

---

## 3. Critérios de Aceite em Formato Gherkin (Exemplos Executáveis para SDD/TDD)

### Cenário 1: Dúvida Técnica com Citação Verificável do Manual (`RF05`, `RF07`, `RNF04`)
```gherkin
Funcionalidade: Resposta técnica ancorada em manual PDF com citação verificável
  Cenário: Usuário pergunta se pode colocar forma de alumínio ou papel alumínio na Airfryer 4L
    Dado que o produto "Airfryer SmartChef 4L" (SKU "AF-400-220V", estoque 15) possui seu manual PDF indexado no pgvector
    E o chunk da página 14 contém a regra "Retire todos os plásticos; formas de alumínio são permitidas desde que não bloqueiem a circulação de ar"
    Quando o usuário envia a mensagem "Posso colocar pote de plástico ou forma de alumínio dentro da Airfryer de 4L?"
    Então o orquestrador RAG recupera o chunk da página 14 com similarity_score >= 0.72
    E transmite via SSE o primeiro token em menos de 1.5 segundos (TTFT <= 1.5s)
    E a resposta alerta que plástico é proibido e forma de alumínio é permitida com circulação de ar
    E emite o evento SSE "citations" contendo manual_title="Manual Airfryer SmartChef 4L" e page_number=14
```

### Cenário 2: Recomendação de Upsell e Cross-sell Respeitando Estoque e Teto de Preço (`RF12`, `RF13`)
```gherkin
Funcionalidade: Motor consultivo de Upsell e Cross-sell
  Cenário: Usuário com família de 5 pessoas consulta Airfryer de 4L
    Dado que a "Airfryer SmartChef 4L" custa R$ 499,90 (estoque=15)
    E a "Airfryer SmartChef Pro 5.5L" custa R$ 629,90 (+26% <= +35% teto de upsell, estoque=8)
    E o "Kit Cesto Silicone + Grelha Dupla" custa R$ 79,90 (cross-sell compatível, estoque=25)
    E a "Airfryer Industrial 10L" custa R$ 1.299,00 (+160% > +35% teto) e a "Airfryer 6L" está sem estoque (estoque=0)
    Quando o usuário pergunta "Essa Airfryer de 4L dá conta de fazer batata frita de uma vez para 5 pessoas?"
    Então o assistente explica a capacidade de 4L e sugere o modelo de 5.5L como Upsell e o Kit Silicone como Cross-sell
    E o evento SSE "recommendations" inclui apenas os SKUs "AF-400-220V" (PRIMARY), "AF-550-220V" (UPSELL) e "KIT-SIL-01" (CROSS_SELL)
    E NÃO inclui produtos com estoque=0 nem produtos acima do teto de +35% de Upsell
```

### Cenário 3: Bloqueio de Alucinação quando Informação Não Consta no Manual (`RF08`, `RNF04`)
```gherkin
Funcionalidade: Guardrail anti-alucinação e fallback seguro
  Cenário: Usuário pergunta especificação inexistente nos manuais indexados
    Dado que nenhum chunk no pgvector possui similarity_score >= 0.72 para a pergunta "Qual a resistência sísmica em graus Richter da cafeteira?"
    Quando o usuário envia essa pergunta no chat
    Então o orquestrador RAG NÃO gera especificação inventada
    E retorna a mensagem de fallback seguro informando que essa informação técnica específica não consta no manual oficial do fabricante
```
