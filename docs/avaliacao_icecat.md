# Avaliação do Open Icecat como fonte de dados do catálogo

> **Nota técnica de 20/11/2026.** Decisão: **registrado como trabalho futuro, não
> adotado nesta entrega** (prazo improrrogável do Marco `M5` em 24/11/2026). Nenhum
> código foi escrito e nenhuma conta foi criada. As afirmações sobre o Icecat
> descrevem o serviço em linhas gerais e precisam ser conferidas na documentação
> oficial antes de qualquer implementação.

## 1. Contexto

Hoje o catálogo é um *seed* sintético de demonstração:

- `data/catalog.json`: 7 produtos em duas categorias (`Eletroportáteis` e
  `Acessórios`), validados pelo modelo `CatalogProduct` em
  `backend/app/models/schemas.py`;
- `data/manuals/`: manuais `.txt` sintéticos com o nome do SKU (`AF-400-220V.txt`,
  `AF-550-220V.txt`, `CF-15B-127V.txt`). O carregador
  (`backend/app/ingestion/manuals.py`) aceita `.pdf`, `.txt` e `.md`, com PDFs lidos
  por `pypdf` página a página;
- ingestão pela CLI `python -m app.ingestion.run --catalog ... --manuals ... [--relations ...]`
  (`backend/app/ingestion/run.py`, `UC08`).

O Open Icecat é a camada gratuita do Icecat, um catálogo de conteúdo de produtos
(fichas técnicas estruturadas, imagens e, em parte dos itens, documentos como
manuais em PDF, expostos em campos como `ManualPDFURL`). A pergunta é se ele pode
substituir ou enriquecer o *seed* com dados reais de fabricantes.

## 2. O que ele nos daria

| Necessidade do projeto | O que o Icecat oferece | Observação |
| :--- | :--- | :--- |
| Nome, marca, categoria | Dados gerais do produto e taxonomia própria | A taxonomia do Icecat precisa ser mapeada para `category`/`subcategory`. |
| Especificações técnicas (`specs_json`) | Grupos de características estruturadas (nome, valor, unidade) | É o principal ganho: fichas reais no lugar das sintéticas. |
| Voltagem, potência, capacidade | Podem existir como características | Nomes e unidades variam por categoria; ver o risco de `R01` na seção 5. |
| Imagens (`image_url`) | Galeria de imagens do produto | Uso e *hotlinking* dependem dos termos de licença. |
| Manuais (`data/manuals/<SKU>.pdf`) | Link de manual em PDF quando o fabricante fornece | Frequentemente vazio (seção 4). |
| Identificação | Busca por marca + código do fabricante, GTIN/EAN ou ID Icecat | Útil para casar com o SKU interno. |

O Icecat **não** fornece dados comerciais: preço, estoque, marketplace e link de
checkout continuam vindo da nossa fonte, como exige a regra `R09` do `CLAUDE.md`.

## 3. Requisitos de acesso e licença

- **Conta gratuita obrigatória.** As chamadas ao Open Icecat exigem um usuário
  cadastrado no site do Icecat. As credenciais seriam lidas de variável de ambiente
  (por exemplo `ICECAT_USERNAME`) e nunca versionadas, como as demais chaves do
  projeto.
- **Licença e atribuição.** Os termos de uso do Open Icecat (condições de
  reprodução de textos e imagens, exigência de atribuição, limites de requisições e
  quais marcas entram na camada gratuita) **precisam ser lidos e confirmados no
  site oficial do Icecat** antes de usar os dados. Esta nota não resume esses termos
  para não registrar condições não verificadas. Responsável pela verificação: a
  definir.
- **Manuais em PDF.** O direito de copiar o PDF para `data/manuals/` e de exibir
  trechos citados no chat pertence ao fabricante; a permissão também precisa ser
  confirmada caso a caso.

## 4. Aderência e lacunas

| Ponto | Avaliação |
| :--- | :--- |
| Categorias do projeto (eletroportáteis, eletrônicos, periféricos) | Eletrônicos e periféricos tendem a ser a base do Icecat; a cobertura de eletroportáteis de cozinha (airfryers, cafeteiras) e de marcas vendidas no Brasil é **desconhecida** e precisa de amostragem antes de qualquer decisão. |
| Camada gratuita × completa | O Open Icecat cobre só parte das marcas; o restante fica na versão paga. A lista vigente deve ser consultada no site. |
| Manuais (`ManualPDFURL`) | O campo existe, mas costuma vir vazio. Sem manual, o produto só teria a ficha técnica como fonte do RAG, e a busca de *chunks* cairia mais vezes no `LOW_SIMILARITY_FALLBACK`. |
| Voltagem do mercado brasileiro | Fichas pensadas para outros mercados podem trazer tensões como 230 V, que não existem no nosso enum (`127V`, `220V`, `BIVOLT`, `N/A`). |
| Idioma | O conteúdo pode não estar em português para todos os produtos; o *prompt* e os guardrails foram calibrados em português. |
| Campos sem equivalente | `price`, `stock_quantity`, `marketplace`, `checkout_url` e `tier_rank` não vêm do Icecat. |

## 5. Impacto em qualidade e guardrails

- **`R01` (proibição de alucinação técnica).** Os guardrails comparam a resposta com
  os *chunks* e os metadados SQL; se o importador inferir voltagem, potência ou
  capacidade, o erro entra no banco como "fato" e o guardrail deixa de protegê-lo.
  Regra para o importador: só preencher `voltage`, `power_watts` e
  `capacity_liters` quando a característica vier explícita e numa unidade
  reconhecida; caso contrário, `N/A` ou `null`. Tensão fora do enum (por exemplo
  230 V) vira `N/A`, nunca `220V`.
- **Golden Set e RAGAS (`B05`).** As 50 fixtures de `backend/tests/ragas_eval/`
  estão amarradas ao *seed* atual por hashes (`corpus_manifest.json`). Trocar o
  catálogo invalida o Golden Set: seria preciso reconstruir as fixtures, refazer a
  auditoria humana (`audit.json`) e executar o runner de novo. O corpus do Icecat
  deve ficar separado do corpus de homologação.
- **Limiar de similaridade.** Manuais reais mudam a distribuição de similaridade;
  o limiar (hoje 0,72 em `backend/app/config.py`, 0,60 no MVP com Gemini) teria de
  ser recalibrado (lição T1 em
  [lições aprendidas](encerramento/03_licoes_aprendidas.md)).
- **`R04` (tabelas em PDF).** Manuais reais trazem tabelas que o `pypdf` extrai sem
  estrutura; o risco, hoje sem evidência porque o *seed* é `.txt`, passaria a ser
  exercitado.

## 6. Desenho proposto (futuro)

Um importador opcional, fora do fluxo principal, que gera os mesmos arquivos que a
CLI já consome. A ingestão (`run.py`) não muda.

1. Script separado, por exemplo `backend/app/ingestion/icecat_import.py`, desligado
   por padrão e acionado só por *flag* explícita (por exemplo `--source icecat`) e com
   `ICECAT_USERNAME` definido.
2. Entrada: uma lista de produtos com SKU interno, marca + código do fabricante ou
   GTIN, e os dados comerciais da nossa fonte (preço, estoque, marketplace, link).
3. Para cada item: buscar a ficha no Icecat, mapear para `CatalogProduct` (tabela
   abaixo), validar com o próprio modelo Pydantic (`extra="forbid"`) e descartar com
   log o que não validar.
4. Baixar o PDF do manual, quando houver link, para um diretório separado
   (`data/manuals_icecat/<SKU>.pdf`), registrando URL e hash para auditoria.
5. Saída: `data/catalog.icecat.json` e o diretório de manuais, ingeridos com a CLI
   existente apontando para eles. Nada sobrescreve `data/catalog.json`.
6. Testes: mapeamento com respostas JSON gravadas (sem rede), incluindo os casos de
   tensão fora do enum e de manual ausente.

| Campo de `CatalogProduct` | Origem proposta |
| :--- | :--- |
| `sku` | Nossa fonte (SKU interno) |
| `name`, `brand` | Icecat (dados gerais) |
| `category`, `subcategory` | Icecat, via tabela de-para para as nossas categorias |
| `price`, `stock_quantity`, `marketplace`, `checkout_url` | Nossa fonte (nunca o Icecat) |
| `voltage` | Icecat só se explícito e no enum; senão `N/A` |
| `capacity_liters`, `power_watts` | Icecat só se explícito e com unidade reconhecida; senão `null` |
| `tier_rank` | Nossa fonte (regra de upsell `RN04`) |
| `image_url` | Icecat, se a licença permitir; senão imagem própria |
| `description` | Icecat (texto de marketing), se a licença permitir |
| `specs_json` | Características do Icecat achatadas em chave → valor (`str`, `int`, `float` ou `bool`) |
| `manual_title` | Montado a partir do nome do produto quando o PDF for baixado |
| `is_active` | `true` por padrão |

## 7. Conclusão

O Open Icecat pode trazer fichas técnicas reais e, em parte dos produtos, manuais
oficiais, o que fortaleceria o RAG. Ao mesmo tempo, exige conta, confirmação de
licença, amostragem de cobertura para eletroportáteis vendidos no Brasil e
reconstrução do Golden Set. Nenhum desses passos cabe antes de 24/11/2026.

**Decisão:** registrado como trabalho futuro; não adotado nesta entrega. Próximo
passo sugerido, depois do `M5`: criar a conta, ler os termos e testar a busca de
10 a 20 produtos das nossas categorias para medir cobertura de fichas e de
`ManualPDFURL`.
