# Lições Aprendidas (`EAP 7.4` · `C09`)

> **Rascunho de 11/11/2026.** As lições técnicas abaixo saíram do histórico do
> repositório (issues, PRs e código) e precisam ser validadas na retrospectiva final.
> As gerenciais são hipóteses para a equipe confirmar, corrigir ou descartar.
> Aprovador: Antônio Rodrigo. Responsável: Walber.

## 1. Como ler

Cada lição tem o fato observado, o efeito no projeto e a recomendação para o próximo
ciclo. A coluna "Etapa PDCA" liga a lição ao ciclo de
`specs/diagrams_and_pm/13_qualidade_ciclo_pdca.md`.

## 2. Lições técnicas

| # | Fato observado | Efeito | Recomendação | Etapa PDCA |
| :-: | :--- | :--- | :--- | :---: |
| T1 | O limiar de similaridade das specs (0,72) foi definido para o `text-embedding-3-small`. Com o `gemini-embedding-001`, respostas corretas ficaram entre 0,64 e 0,72 e perguntas fora do escopo perto de 0,47; o MVP usa 0,60. | Com 0,72, perguntas válidas cairiam no *fallback*. | Tratar o limiar como parâmetro do modelo de embedding e recalibrar a cada troca de modelo ou de manuais (`python -m app.retrieval.inspect`). | Agir |
| T2 | Com o Gemini, o TTFT medido ficou entre 1,3 s e 6 s (issue #7), acima da meta de 2 s p95. | O SLA de latência depende do provedor, não só do código. | Medir TTFT desde a Sprint 2 com a sonda de SLA e decidir cedo entre trocar de modelo, reduzir contexto ou rever a meta. | Verificar |
| T3 | O G-OUT valida cada sentença antes de publicar, então o primeiro token só sai depois da primeira sentença completa. | A segurança factual custa latência no primeiro token. | Declarar esse custo no orçamento de latência e medir o TTFT no navegador, sem desligar o guardrail para atingir a meta. | Planejar |
| T4 | Issues e specs divergiram em detalhes: sobreposição de chunks de 80 na issue #10 e 50 nas specs; `GET /sessions/{id}` na issue #8 e ausente no `openapi.yaml`; temperatura 0,1 na issue #7 e 0,2 na spec. | Quem implementa precisa escolher uma fonte e justificar. | Declarar o `openapi.yaml` e `specs/` como fonte normativa e gerar o texto das issues a partir deles. | Planejar |
| T5 | O MVP guardava sessões em memória e não tinha cache; a troca para Redis exigiu tornar o armazenamento uma interface assíncrona com dois adaptadores. | Retrabalho nas rotas e nos testes. | Definir a interface de persistência antes da primeira implementação, mesmo que o primeiro adaptador seja em memória. | Executar |
| T6 | Cache de respostas pode servir preço ou estoque antigos. A solução combinou versão do catálogo na chave com revalidação dos cards no PostgreSQL antes de cada *hit*. | Um card esgotado ou reajustado nunca sai do cache. | Manter a regra: cache só serve o que consegue revalidar. | Executar |
| T7 | Os cards de recomendação são montados só com valores do SQL; o texto do LLM continua restrito ao produto consultado. | Preço e voltagem dos cards não passam pelo modelo. | Preservar essa separação ao incluir recomendações no texto gerado. | Executar |
| T8 | Os testes de integração travavam no Windows: o `psycopg` assíncrono não roda no loop padrão e `localhost` resolvia para IPv6. | Parte da equipe não conseguia rodar a suíte completa localmente. | Documentar o ambiente de teste por sistema operacional e rodar a integração no CI desde o primeiro PR. | Verificar |
| T9 | PRs encadeados (#25 com base na branch do #24, #26 com base na do #25) deixaram trabalho mesclado fora da `develop` por um tempo. | Dificuldade para saber o que já estava integrado. | Abrir PR sempre contra a `develop` ou, se for empilhado, registrar a ordem de merge na descrição. | Executar |
| T10 | **[PREENCHER: lições do frontend, do Golden Set e da homologação.]** | | | |

## 3. Lições gerenciais (hipóteses a validar)

| # | Fato observado | Hipótese de lição | Validada? |
| :-: | :--- | :--- | :---: |
| G1 | Em 11/11/2026 havia 16 issues abertas, cinco delas com prazo vencido em outubro. | Atualizar o estado das issues no mesmo dia da entrega evita que o quadro deixe de refletir o projeto. | **[ ]** |
| G2 | Vários pacotes ficaram "implementados em PR" sem os itens da issue marcados. | Fechar a issue exige checklist marcado e PR mesclado; um comentário de status não substitui. | **[ ]** |
| G3 | O caminho crítico (`B01` a `B04`, `F05`, `G02`) concentrou-se em poucas pessoas. | Parear nas atividades críticas desde o início reduz o risco de atraso em cadeia. | **[ ]** |
| G4 | A troca de provedor de IA no MVP não aparece como mudança de escopo aprovada. | Mudanças de stack entram no controle de mudanças, com impacto em custo e qualidade. | **[ ]** |
| G5 | **[PREENCHER: comunicação, rituais `C01` a `C09`, estimativas PERT.]** | | **[ ]** |

## 4. O que funcionou bem

- Specs e casos de teste escritos antes do código deram critério objetivo de pronto.
- CI com cobertura mínima de 70%, `ruff` e `mypy --strict` nas duas camadas Python.
- Regras de negócio puras (motor de recomendação, chave de cache, gerador SSE)
  testadas sem banco nem rede.
- **[PREENCHER: itens da retrospectiva.]**

## 5. O que mudar no próximo projeto

- **[PREENCHER: até cinco ações, cada uma com responsável.]**

## 6. Registro

| Campo | Valor |
| :--- | :--- |
| Data da retrospectiva final | **[PREENCHER]** |
| Participantes | **[PREENCHER]** |
| Onde este documento fica arquivado | `docs/encerramento/` no repositório |
