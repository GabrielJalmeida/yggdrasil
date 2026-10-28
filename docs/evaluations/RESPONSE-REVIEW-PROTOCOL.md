# Protocolo de revisão manual de respostas RAG

Use este protocolo com `borax-answer-quality-cases.json`. Ele é revisão humana, não pontuação automatizada, e deve ser usado no mesmo snapshot e com a configuração de modelo registrada.

## Registrar antes de comparar

- ID da análise e SHA do commit;
- modelo, provedor e nível de raciocínio;
- pergunta exata;
- latência observada desde o envio até a resposta completa;
- evidências/caminhos apresentados pelo Yggdrasil e citações efetivamente abertas;
- resposta completa recebida.

Nunca registre a chave de API nem copie segredos reais para o relatório.

## Pontuação por dimensão

Atribua 0, 1 ou 2 para cada dimensão; anote os motivos e os trechos que fundamentam a revisão.

| Dimensão | 0 | 1 | 2 |
|---|---|---|---|
| Correção factual | Erro material ou conclusão inventada | Parcialmente correta, com omissões importantes | Afirmações essenciais corretas perante o snapshot |
| Recuperação de fontes | Falta fonte essencial | Fontes parcialmente pertinentes | Implementação/documentação/testes necessários foram recuperados |
| Fundamentação/citações | Citação ausente, inválida ou contraditória | Citações sustentam só parte das afirmações | Cada afirmação técnica essencial tem evidência suficiente |
| Calibração/abstinência | Certeza falsa ou afirma que provou o que não pode | Reconhece algumas lacunas, mas extrapola | Expõe limites e se abstém quando faltam evidências |
| Leitura de testes | Interpreta errado a asserção ou o alcance | Identifica o teste sem confirmar a semântica | Descreve corretamente o que a asserção realmente verifica |

Não combine essas dimensões em uma nota única até haver número suficiente de casos e avaliadores para definir uma regra consistente. Latência deve ser registrada como medida independente, não interpretada isoladamente como qualidade.

## Comparação de alterações

Compare as respostas com a mesma pergunta, snapshot e configuração. Se a recuperação mudou, registre também a lista de evidências que foi enviada: uma resposta diferente pode ser consequência de contexto diferente, não apenas do modelo. Não troque simultaneamente modelo, esforço de raciocínio e algoritmo de recuperação em um experimento que pretende isolar uma variável.

## Executar e registrar o benchmark de respostas

O corpus fixado para `kinegratii/borax` é distribuído em `services/api/evaluation/corpora/borax-answer-quality.json`. A simulação `python scripts/evaluate_answers.py --latest` seleciona a análise e confere o SHA sem chamar o modelo. Para chamar o provedor, execute com `--run-provider`; isso pode consumir cota/custo. Registre o JSON resultante junto à revisão manual.

O avaliador calcula cobertura de caminhos na recuperação e nas citações, verifica marcadores estruturais e mede a latência de ponta a ponta da rota. A detecção de frases de limitação é apenas heurística. Marque manualmente `manual_review` após comparar `expected_facts`, `must_not_claim`, a resposta completa e os caminhos/linhas citados. Não interprete `insufficient_evidence` do endpoint, isoladamente, como prova de que a abstenção foi semanticamente correta.
