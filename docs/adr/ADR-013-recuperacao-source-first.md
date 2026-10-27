# ADR-013 — Recuperação source-first para perguntas de implementação

- **Status:** Aceita
- **Data:** 2026-10-27
- **Escopo:** v0.7.0

## Contexto

Uma pergunta que pedia classes, funções, entradas, resultados, exemplos e testes sobre um módulo de datas lunares foi classificada como “dependências” porque continha a palavra “biblioteca”. O contexto enviado ao modelo ficou concentrado em README/documentação e não trouxe definições nem testes suficientes. Além disso, o léxico original não relacionava expressões em português como “datas lunares” a identificadores ingleses como `LunarDate`/`calendar`, nem dividia CamelCase.

## Decisão

- Priorizar a intenção explícita de investigar implementação antes de intenções mais genéricas.
- Remover a palavra isolada “biblioteca” do classificador de dependências; exigir frases que realmente peçam dependências.
- Expandir termos de consulta PT→termos comuns do código apenas na consulta, e dividir identificadores CamelCase para recuperação.
- Para perguntas de implementação, priorizar definições de símbolos, código-fonte, testes/exemplos relacionados, um trecho da documentação com correspondência real e arestas do grafo ligadas aos nós recuperados.
- Nunca considerar ausência de nós como prova de ausência de implementação; se o parser não cobrir um arquivo, explicitar a lacuna.
- Manter referências recolhidas por padrão e oferecer preferências visuais locais para fonte/tamanho.

## Consequências

A recuperação tende a incluir mais evidência direta para questões de implementação e será menos vulnerável a palavras que desviam a classificação. A expansão continua heurística: não é tradução semântica geral e precisa ser avaliada com corpus de perguntas/respostas esperadas. Mais fontes não garantem conclusões corretas; as citações ainda precisam ser verificadas semanticamente.

## Verificação

Testes de regressão cobrem classificação de perguntas de implementação que mencionam “biblioteca”, identificadores CamelCase, expansão “datas lunares”, e a recuperação simultânea de fonte, teste, documentação e relação do grafo.
