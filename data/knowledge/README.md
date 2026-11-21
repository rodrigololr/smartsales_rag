# Base de conhecimento curada (`data/knowledge/`)

Textos curtos e verificados que dão ao assistente SmartSales RAG contexto de uso para perguntas que os manuais de produto não cobrem (jogos, streaming, espaço para móveis).
Cada arquivo segue o formato dos manuais em `data/manuals/`: título, linha `Base de conhecimento curada — verificada em DD/MM/AAAA`, seções `## ` separadas por form feed (`\f`, uma "página" por seção), uma frase factual por linha e a seção final `## Fontes` com a URL e a data de verificação.

## Regra híbrida

- **Fatos numéricos ou técnicos** (requisitos de sistema, bitrate, datas, medidas, voltagem, preço) só podem vir destes arquivos, do catálogo SQL ou dos manuais, sempre com citação.
- **Contexto geral não numérico** (ex.: o que é roleplay, para que serve uma webcam) pode vir do modelo, mas deve ser sinalizado como orientação geral e não pode citar números.
- Se a informação não estiver aqui nem no catálogo/manuais, vale o fallback seguro (`LOW_SIMILARITY_FALLBACK`): não inventar.
- Frases marcadas como inferência, recomendação geral ou "não verificado" não devem ser apresentadas como especificação oficial.

## Como atualizar

1. Reabra cada URL da seção `## Fontes` e confira os valores; prefira sempre a fonte oficial (fabricante/plataforma).
2. Corrija os fatos, registre conflitos entre fontes no próprio texto e atualize a data em `verificada em` e em cada fonte.
3. Mantenha cada arquivo com até ~60 linhas e uma frase factual por linha.
4. Reexecute a ingestão (`cd backend && python -m app.ingestion.run ...`).
   Atenção: em 21/11/2026 a ingestão lê manuais apenas de `data/manuals/<SKU>.*`; `data/knowledge/` ainda precisa ser ligada ao pipeline.

## Arquivos e fontes

| Arquivo | Tema | Fontes principais |
|---|---|---|
| `KB-GTA6.txt` | GTA VI: plataformas, status de lançamento, PC | rockstargames.com/VI, Rockstar Newswire, Al Jazeera, Engadget |
| `KB-GTAV-PC.txt` | GTA V PC (Enhanced e Legacy), GTA RP, FiveM | support.rockstargames.com, fivem.net, docs.fivem.net, redm.net, forum.cfx.re |
| `KB-ROBLOX.txt` | Requisitos e plataformas do Roblox | en.help.roblox.com (artigos 203312800, 203625474, Meta Quest FAQ) |
| `KB-TWITCH.txt` | Resolução, fps, bitrate, encoder, webcam | help.twitch.tv (Broadcasting Guidelines, Broadcast Health, 2K Streaming) |
| `KB-SOFA-ESPACO.txt` | Sofá: parede, profundidade, circulação, entrega | homesandgardens.com, crateandbarrel.com, potterybarn.com |
