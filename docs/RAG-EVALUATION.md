# Avaliação RAG do Yggdrasil

## Objetivo e limites

O harness `services/api/scripts/evaluate_rag.py` mede a recuperação lexical/estrutural de arquivos rotulados manualmente como relevantes. Ele não chama um provedor de IA, não persiste perguntas/respostas, não executa código do repositório-alvo e não inclui trechos de código no relatório.

**As métricas de recuperação não avaliam se o modelo interpretou corretamente uma evidência.** A qualidade da resposta gerada exige uma revisão separada das afirmações técnicas, citações, interpretação de testes, reconhecimento de lacunas e abstinência quando a evidência é insuficiente.

O corpus de recuperação mede seleção de arquivos; os casos de qualidade de resposta são revistos manualmente em `docs/evaluations/borax-answer-quality-cases.json`, conforme `docs/evaluations/RESPONSE-REVIEW-PROTOCOL.md`.

## Pré-requisitos

1. Inicie o Yggdrasil e analise `https://github.com/kinegratii/borax`, usando `master`.
2. Espere a análise terminar; `completed_with_warnings` também pode ser avaliada, mas os avisos devem ser revisados.
3. Execute a avaliação contra a mesma base de dados em que a análise foi persistida. A avaliação não precisa de IA habilitada.

### Com Docker Compose

Na raiz do repositório:

```powershell
docker compose up -d --build api
docker compose exec api python scripts/evaluate_rag.py --latest --cases evaluation/corpora/borax.json
```

`--latest` seleciona a análise concluída mais recente **do repositório declarado no corpus**, não a análise mais recente de qualquer projeto. A saída registra o ID e o SHA selecionados. Para repetir uma avaliação exatamente sobre o mesmo run, use o ID registrado:

```powershell
docker compose exec api python scripts/evaluate_rag.py --analysis-id "ID_DA_ANALISE" --cases evaluation/corpora/borax.json --output /tmp/rag-evaluation-borax.json
docker compose cp api:/tmp/rag-evaluation-borax.json .\rag-evaluation-borax.json
```

### Execução no ambiente Python local

A partir de `services/api` e usando o mesmo ambiente que acessa a base de dados:

```powershell
python scripts/evaluate_rag.py --analysis-id "ID_DA_ANALISE" --cases evaluation/corpora/borax.json --output .\data\rag-evaluation-borax.json
```

O `DATABASE_URL` precisa apontar para a base que contém a análise. Com SQLite, mudar o diretório atual pode fazer a aplicação abrir outro arquivo de banco; execute no diretório `services/api`.

## Métricas

- **Intent accuracy:** proporção dos casos cuja intenção classificada corresponde à intenção anotada.
- **Hit@k:** proporção dos casos respondíveis em que pelo menos um caminho esperado aparece entre as primeiras `k` evidências com caminho.
- **Recall@k:** fração média dos caminhos esperados recuperados até `k`.
- **MRR (Mean Reciprocal Rank):** média do inverso da posição da primeira evidência que corresponde a um caminho esperado.

O corpus não é uma lista exaustiva de todos os arquivos relevantes e irrelevantes. Portanto, essas métricas não equivalem a precisão global, correção semântica da resposta ou cobertura completa do repositório. Casos `insufficient_evidence` e `manual_review` não são pontuados quanto à abstinência do modelo.

## Corpus Borax

`services/api/evaluation/corpora/borax.json` é um corpus inicial versionado para o repositório `kinegratii/borax`. Na revisão de 27/10/2026, ele contém sete casos: implementação da conversão lunar, exemplo documentado, testes, visão geral, API pública, metadados de empacotamento e uma pergunta que exige reconhecer que análise estática não prova ausência de vulnerabilidades.

Os caminhos esperados são rótulos humanos e devem ser verificados contra o SHA exato da análise. Um caminho ausente ou presente sem conteúdo lido invalida a anotação daquele caso e o exclui das métricas de recuperação, em vez de contar automaticamente como falha do recuperador.

## Baseline inicial

O relatório observado em 27/10/2026 está registrado em [`evaluations/borax-baseline-2026-10-27.md`](evaluations/borax-baseline-2026-10-27.md). A primeira execução teve seis casos pontuados de sete; Hit@5 foi 0,8333 e Recall@5 foi 0,75. Os principais defeitos observados foram a documentação específica de `lunardate` não aparecer no caso de exemplo e o teste relacionado ficar em oitavo lugar na consulta por testes.

A Entrega 1 adiciona regressões sintéticas para esses padrões e ajusta a seleção lexical/estrutural. A alteração só pode ser considerada melhoria no corpus real depois de reexecutar o avaliador no mesmo snapshot e comparar métricas/rankings.

## Revisão manual da resposta gerada

Em 27/10/2026, foi feita uma pergunta real via `gemini-3.6-flash` com raciocínio `medium` sobre conversão de datas solares/lunares. A resposta explicou o fluxo principal e reconheceu lacunas de evidência, mas não recuperou a documentação relevante e interpretou incorretamente uma chamada a `self.assertTrue` em `tests/test_lunardate.py` como comparação entre o esperado e o resultado. A documentação existe em `docs/guides/lunardate.md`, com exemplo concreto de `LunarDate.from_solar_date`.

Este caso mostra por que a avaliação precisa separar três dimensões:

1. **Recuperação:** os arquivos corretos foram entregues ao modelo?
2. **Fundamentação:** as citações apontam para fontes que sustentam as frases?
3. **Correção semântica:** a frase descreve corretamente o código/teste citado?

A chave de citação validada pelo backend impede IDs inventados, mas não garante que a conclusão esteja correta. A revisão manual é um caso de avaliação, não uma métrica automatizada nem uma afirmação de desempenho geral do modelo.

## Segurança e privacidade

O harness lê apenas dados já persistidos da análise e evidências redigidas. Não chama o provedor e não inclui trechos-fonte no relatório. Na pergunta por IA, ao contrário, a pergunta e os trechos selecionados e redigidos podem ser transmitidos ao provedor depois da confirmação explícita na interface. Não envie código privado, credenciais ou informação que não possa ser transmitida.

## Avaliação de respostas geradas

O avaliador `services/api/scripts/evaluate_answers.py` complementa `evaluate_rag.py`: ele chama a rota real de perguntas no mesmo processo da API, mede a latência completa, lista os caminhos recuperados e compara os caminhos esperados com os citados. O JSON guarda metadados de citação, mas não copia trechos-fonte.

Primeiro faça uma simulação sem chamadas de IA:

```powershell
docker compose up -d --build api
docker compose exec api python scripts/evaluate_answers.py --latest
```

Para gerar respostas usando o provedor configurado, acrescente `--run-provider`. Isso autoriza até uma solicitação de nível de resposta por caso com evidência recuperada; o adaptador pode fazer novas tentativas e o uso pode consumir cota ou gerar custo. O script recusa por padrão SHA diferente do anotado no corpus.

```powershell
docker compose exec api python scripts/evaluate_answers.py --latest --run-provider --output /tmp/answer-quality-borax.json
docker compose cp api:/tmp/answer-quality-borax.json .\answer-quality-borax.json
```

A avaliação automatiza latência, caminhos e integridade estrutural das referências. No relatório de recuperação, `missing_expected_paths` é mantido como alias histórico de `missing_from_snapshot_paths`; ele não significa falha no ranking. `not_retrieved_expected_paths` indica arquivos esperados que estavam disponíveis no snapshot, mas não apareceram entre os caminhos recuperados. Correção factual, suporte semântico de cada citação, interpretação de testes e qualidade da abstenção continuam como revisão humana; não se produz uma nota automática de qualidade semântica. Não publique relatórios antes de revisar o conteúdo das respostas.

## Recuperação direcionada para perguntas sobre testes e avaliação por caso

Para perguntas classificadas como `tests`, os trechos dos arquivos de teste são agora escolhidos por relevância lexical em blocos sobrepostos, em vez de sempre enviar apenas o início do arquivo. Isso ajuda perguntas sobre uma asserção que aparece após o cabeçalho; a resposta ainda precisa ser conferida contra o código completo.

O avaliador de respostas aceita `--case-id` repetido para executar somente casos selecionados, evitando repetir chamadas que já foram medidas. Exemplo de reteste isolado com menor esforço de raciocínio para reduzir o risco de timeout:

```powershell
docker compose up -d --build api
docker compose exec -e AI_REASONING_EFFORT=low api python scripts/evaluate_answers.py --latest --case-id lunar-test-assertion-semantics --run-provider --output /tmp/answer-quality-test-assertion.json
docker compose cp api:/tmp/answer-quality-test-assertion.json .\answer-quality-test-assertion.json
```

`AI_REASONING_EFFORT=low` é passado apenas ao processo `exec` desse comando; não altera o `.env` nem a configuração persistente do container. A seleção por `--case-id` não altera o corpus fixado nem a análise selecionada. Para avaliar outro caso, substitua o ID e o nome do relatório. Chamadas reais podem consumir cota ou gerar custo.

## Formato de marcadores de citação e validação do avaliador

O prompt do provedor exige marcadores entre colchetes, como `[E2]`, e proíbe placeholders literais como `E#E2`. O avaliador separa marcadores válidos de tokens de citação malformados e conta estes últimos como incompatibilidades de formatação. Esse diagnóstico é estrutural: não comprova que uma citação sustente semanticamente a afirmação.

Após aplicar a correção, rode a validação completa antes de reconstruir a API. Depois, reavalie um único caso já selecionado para confirmar que as respostas usam marcadores como `[E1]` ou `[E2]` com IDs reais, sem repetir benchmarks desnecessários.

## Semântica de asserções unittest em perguntas sobre testes

Para perguntas classificadas como `tests`, o Yggdrasil pode anexar uma nota determinística quando a AST identifica uma chamada de dois argumentos a `assertTrue` dentro de uma classe que herda de `unittest.TestCase` e não redefine esse método. A nota explica que a assinatura padrão é `assertTrue(expr, msg=None)`: o primeiro argumento é testado por truthiness e o segundo é a mensagem opcional, não uma comparação de igualdade. A nota não afirma que o teste foi executado e só é produzida quando o trecho é lexicalmente relevante à pergunta.

Essa nota auxilia o modelo, mas não garante a correção da resposta. A revisão manual continua pendente, e a validação deve conferir se a resposta não contradiz a nota nem afirma que `assertTrue` compara esperado e atual.

## Validação de citações agrupadas

O avaliador aceita marcadores unitários como `[E2]` e grupos separados por vírgula como `[E2, E3]`. Os IDs dentro do grupo são expandidos individualmente para verificar se há registros correspondentes. Tokens fora de colchetes (como `E4`) e formatos não conformes (como `E#E5` ou `[E2; E3]`) continuam sinalizados como malformados. Isso verifica o formato e a associação aos registros, não a sustentação semântica da frase.

## Entrega 3 — trilha de evidências e avaliação das skills

A pergunta pode ser enviada pelo endpoint `POST /api/v1/analyses/{id}/questions/stream`, que emite `question_started`, `question_retrieval`, `question_answer` ou `question_error`. `question_retrieval` contém caminhos, linhas, IDs de evidência e IDs dos nós do grafo relacionados; não inclui trechos de código nem raciocínio privado do modelo. A interface anima os nós reais associados à recuperação enquanto o provedor gera a resposta. Nós citados e apenas recuperados têm estilos diferentes.

Durante a etapa de skills, `analysis_path_step` registra os arquivos realmente visitados por cada skill determinística e os IDs dos nós persistidos daquele caminho. O frontend usa estes eventos para mostrar o arquivo atual no grafo. Isso é trilha de execução das skills, não uma alegação de execução do código do repositório.

Para avaliar as skills AppSec e inventário de testes sem chamadas externas, execute no diretório `services/api`:

```powershell
python scripts/evaluate_skills.py
```

O corpus `evaluation/corpora/skill-quality-cases.json` cobre detecções positivas, placeholders/indireções negativas e casos ambíguos que devem permanecer em revisão humana. A avaliação não executa os testes do repositório-alvo e não prova a validade de credenciais. Embeddings e reranking permanecem fora deste incremento até que um benchmark indique ganho mensurável.
