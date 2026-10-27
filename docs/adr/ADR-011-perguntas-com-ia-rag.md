# ADR-011 — Perguntas com IA usando recuperação de evidências

- **Status:** adotado para a primeira fatia do MVP
- **Data:** 26/10/2026

## Contexto

O Yggdrasil precisa responder perguntas sobre um snapshot sem fazer o modelo inventar estrutura não observada nem receber o repositório inteiro. A análise determinística deve continuar utilizável sem IA.

## Decisão

- Expor `POST /api/v1/analyses/{analysis_id}/questions` para análises concluídas.
- Recuperar trechos lexicalmente relevantes do conteúdo já redigido, achados estruturados e algumas relações do grafo.
- Limitar contexto por tamanho/quantidade e vincular todas as fontes ao commit selecionado.
- Usar adaptador configurável, desligado por padrão. Para endpoints Google Gemini, usar a API nativa `generateContent`, com `thinkingLevel=LOW`, `responseJsonSchema` para JSON estruturado e chave no cabeçalho `x-goog-api-key`; manter Chat Completions para outros provedores compatíveis.
- Não disponibilizar ferramentas, shell, filesystem ou escrita ao modelo.
- Solicitar resposta estruturada e validar no backend IDs de citação contra os IDs realmente recuperados. Sem citação verificável, a resposta torna-se inconclusiva.
- Exigir confirmação da interface antes de enviar trechos redigidos a um provedor configurado.
- Não persistir conversas na primeira fatia.

## Alternativas consideradas

- **Enviar o repositório inteiro:** rejeitado por custo, privacidade e contexto excessivo.
- **Embeddings/pgvector no primeiro passo:** adiado até existir corpus/benchmark que demonstre benefício sobre busca lexical/estrutural.
- **IA sempre ligada:** rejeitada; análise estática e relatório continuam funcionando sem provedor.
- **Agente com ferramentas:** rejeitado para o MVP por ampliar desnecessariamente a autoridade sobre conteúdo não confiável.

## Consequências

A primeira versão é simples de operar e verificável, mas a busca lexical pode falhar com sinônimos e a saída semântica ainda exige revisão humana. Configurar um provedor pode transmitir a pergunta e trechos de código redigidos para um serviço externo; a interface avisa e exige confirmação.
