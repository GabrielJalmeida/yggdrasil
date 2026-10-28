# Baseline do RAG — Borax — 27/10/2026

## Origem do resultado

- Repositório: `kinegratii/borax`
- Referência solicitada: `master`
- Commit analisado: `01cbbbf7ce33ee22d23c462c525d07e1320e67a7`
- ID da análise local: `78d0fe83908a41939456c90b018a6ccf`
- Corpus: `borax-lunar-rag` v`0.1.0`
- Execução: offline; `provider_calls = 0`; o relatório não incluiu excertos de código.

## Métricas observadas antes das regressões da Entrega 1

| Métrica | Resultado |
|---|---:|
| Casos pontuados | 6/7 |
| Intent accuracy | 1.0000 |
| MRR | 0.7208 |
| Hit@1 | 0.6667 |
| Hit@3 | 0.6667 |
| Hit@5 | 0.8333 |
| Recall@1 | 0.5000 |
| Recall@3 | 0.5833 |
| Recall@5 | 0.7500 |

O caso `absence-of-security-proof` ficou fora da pontuação de recuperação por exigir avaliar abstinência/limites da resposta, capacidade que o harness ainda não mede.

## Falhas verificadas manualmente

1. **Exemplo documentado:** a pergunta sobre um exemplo de conversão solar para `LunarDate` recuperou `borax/calendars/lunardate.py`, `tests/test_lunardate.py`, `borax/calendars/data_parser.py` e `docs/guides/festivals2.md`, mas deixou fora `docs/guides/lunardate.md`. O guia correto contém um exemplo de `LunarDate.from_solar_date(2018, 8, 11)`.
2. **Consulta sobre testes:** `tests/test_lunardate.py` apareceu na oitava posição; a consulta foi precedida por arquivos menos específicos como `tests/test_json.py`.
3. **Resposta gerada:** o modelo explicou boa parte do fluxo de conversão, mas descreveu `self.assertTrue(LunarDate(2033, 10, 1, 0), dt2)` como se comparasse o esperado com `dt2`. Isso é incorreto: o segundo argumento de `assertTrue` é a mensagem opcional de falha. Para comparar os valores, o teste apropriado seria `assertEqual(expected, actual)`. O erro está no teste do repositório-alvo e na interpretação da resposta; não é uma falha do Yggdrasil ao executar testes, pois ele não os executa.

## Interpretação

Esta baseline indica que a classificação determinística de intenção foi correta nos casos rotulados, mas recuperação e ordenação ainda deixam a desejar. O resultado não prova que 75% de todas as evidências relevantes sejam recuperadas: o Recall usa apenas os caminhos anotados.

A Entrega 1 acrescenta dois testes de regressão no recuperador:

- escolher documentação alinhada com os símbolos encontrados na implementação, quando a pergunta pede um exemplo documentado;
- priorizar arquivos de teste relevantes à pergunta em vez de selecionar arquivos apenas pela ordem alfabética.

O resultado após a alteração ainda precisa ser obtido no banco local do usuário sobre o mesmo SHA. Não reutilizar as métricas acima como se fossem a medição pós-correção.
