# B05 — homologação pendente

**Status: PENDING. Não há homologação válida do pipeline integrado.**

O relatório anterior e suas porcentagens foram retirados como evidência de aceite:
o runner usava o gabarito como contexto, IDs de recuperação fixados pela fixture e
uma heurística lexical no lugar de RAGAS. Seu resultado não mede retrieval,
geração, recomendações ou fidelidade do pipeline de produção. A versão histórica
permanece no Git (por exemplo, commit `6fe9e4f`) para rastreabilidade.

O runner corrigido observa o orquestrador, pgvector e recomendações reais da B04,
valida o corpus/configuração e usa um juiz RAGAS distinto. Há 50 fixtures
reconstruídas com fontes e hashes do seed sintético de demonstração, cuja auditoria
humana está **pendente** em `audit.json`.

Ainda faltam configuração de provedores/modelos, execução real dos 50 casos no
commit integrado e aprovação das fontes. Testes offline, CI verde ou validação
das fixtures não substituem esses passos. Nenhuma porcentagem antiga é reutilizada
ou apresentada como resultado atual. Precision@5/precision@returned + recall,
Faithfulness, relevância, ações, regras e alucinação permanecem **não medidos**
para homologação real.

Consulte [README.md](README.md) para comandos, condições dos gates e relatório JSON
rastreável. O arquivo gerado por uma execução real deve identificar commit,
configuração, denominadores, exclusões, erros, bloqueios internos e casos falhos.
A issue #14 deve permanecer aberta até o aceite completo, com reteste em F05.
