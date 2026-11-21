# Base de conhecimento curada (`data/knowledge/`)

Textos curtos e verificados que dão ao assistente SmartSales RAG contexto de uso para perguntas que os manuais de produto não cobrem (jogos, streaming, espaço para móveis).

## Formato dos arquivos (`KB-*.txt`)

1. **Linha 1**: Título do documento **sem vírgula** (usado em citações `[Fonte: <título>, p. <N>]`).
2. **Linha 2**: `Fonte de referência: <url oficial principal>; consultado em 21/11/2026 (curadoria SmartSales).`
3. **Páginas**: Separadas por form feed (`\f`, até 400 tokens por página). Valores estruturados usam linhas de tabela Markdown `| <rótulo> | <número> <unidade> |`.
4. **Última página**: Seção `## Fontes` com todas as URLs verificadas e a data de consulta.

## Regra híbrida

- **Fatos numéricos ou técnicos** (requisitos de sistema, bitrate, datas, medidas, voltagem, preço) só podem vir destes arquivos (`knowledge_chunks`), do catálogo SQL (`products`) ou dos manuais (`manual_chunks`), sempre com citação.
- **Contexto geral não numérico** pode vir em frases prefixadas por `Informação geral:`, sem números, unidades, preços ou ranking de marcas.
- Se a informação não estiver na base nem no catálogo/manuais, vale o fallback seguro (`LOW_SIMILARITY_FALLBACK`): não inventar.

## Comandos de ingestão (`UC08`)

### Seed completo (Catálogo Base + Consultor Unificado + Base de Conhecimento)

```bash
cd backend && python -m app.ingestion.run \
  --catalog ../data/catalog.json \
  --catalog ../data/catalog_consultor.json \
  --manuals ../data/manuals \
  --relations ../data/product_relations.json \
  --relations ../data/product_relations_consultor.json \
  --knowledge ../data/knowledge
```

### Seed base-only (Isolado para Homologação RAGAS B05)

O verificador `verify_database()` do runner RAGAS (`backend/tests/ragas_eval/`) exige um banco contendo **exclusivamente** o snapshot homologado em `corpus_manifest.json` (`data/catalog.json` e `data/product_relations.json`, sem os SKUs do consultor):

```bash
cd backend && python -m app.ingestion.run \
  --catalog ../data/catalog.json \
  --manuals ../data/manuals \
  --relations ../data/product_relations.json
```

## Arquivos e fontes

| `doc_id` | Título (Linha 1) | Fontes principais |
|---|---|---|
| `KB-GTA6-PLATAFORMAS` | `GTA 6 plataformas e versão para PC` | rockstargames.com/VI, Rockstar Newswire, Al Jazeera, Engadget, Game Informer |
| `KB-GTA-RP` | `GTA RP no PC` | fivem.net, docs.fivem.net, redm.net, forum.cfx.re, support.rockstargames.com |
| `KB-GTAV-REQUISITOS` | `Requisitos do GTA V para PC` | support.rockstargames.com |
| `KB-ROBLOX-REQUISITOS` | `Requisitos do Roblox para PC` | en.help.roblox.com (artigos 203312800, 203625474, Meta Quest FAQ), create.roblox.com |
| `KB-TWITCH-TRANSMISSAO` | `Twitch qualidade de transmissão` | help.twitch.tv (Broadcasting Guidelines, Broadcast Health, 2K Streaming) |
| `KB-SOFA-ESPACO` | `Sofá espaço necessário no ambiente` | homesandgardens.com, crateandbarrel.com, potterybarn.com |
