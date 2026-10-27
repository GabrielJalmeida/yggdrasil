# ADR-012 — Recuperação contextual por intenção da pergunta

- **Status:** adotado para a evolução v0.6.0 de IA/RAG
- **Data:** 26/10/2026

## Contexto

A recuperação lexical pura encontra definições e trechos que compartilham palavras com a pergunta, mas perguntas amplas como “do que se trata o projeto?” exigem fontes distintas: documentação, manifestos, pontos de entrada, perfil estrutural e relações do grafo. Um modelo não consegue interpretar evidências que não recebe.

## Decisão

- Classificar a pergunta deterministicamente em visão geral, arquitetura, fluxo, segurança/AppSec, dependências, testes, símbolo específico ou geral.
- Construir um perfil determinístico a partir de metadados do repositório, caminhos e estados de arquivo, contagens de nós e relações persistidas.
- Priorizar fontes diferentes por intenção e diversificar evidências entre caminhos em vez de deixar um único arquivo ocupar todo o contexto.
- Incluir relações do grafo com proveniência explicitada; relações inferidas continuam marcadas como não confirmadas.
- Passar ao provedor uma orientação específica da intenção, sem conceder ferramentas nem alterar o princípio de usar exclusivamente evidências redigidas.
- Retornar ao frontend o tipo de pergunta e os tipos de evidência recuperados para melhorar a transparência.
- Manter limites de quantidade/contexto configuráveis e fixar todas as evidências ao commit analisado.

## Alternativas consideradas

- **Aumentar apenas o tamanho do prompt:** rejeitado; mais tokens não resolvem seleção de contexto irrelevante.
- **Enviar o repositório inteiro:** rejeitado por custo, privacidade e dificuldade de inspeção.
- **Usar outra chamada de IA para planejar a busca em todas as perguntas:** adiado para evitar latência/custo duplicado antes de um corpus de avaliação.
- **Embeddings/pgvector imediatamente:** adiado até medir o ganho da classificação, da busca lexical e da expansão no grafo.

## Consequências e limitações

O procedimento agora prioriza a família correta de evidências para perguntas comuns e constrói contexto estrutural a partir do banco. A classificação é heurística e pode escolher a estratégia errada; a recuperação lexical ainda não encontra todos os sinônimos nem representa fluxos dinâmicos completos. Uma citação existente não prova que a conclusão é semanticamente correta. O próximo gate é um corpus de perguntas com respostas esperadas e avaliação real com provedor configurado.
