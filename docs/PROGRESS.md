# Yggdrasil — Progresso verificado

**Versão do aplicativo:** 0.7.0 — recuperação source-first e preferências de leitura
**Data:** 27/10/2026
**Fonte de verdade:** Plano Mestre v0.4.0 (`docs/MASTER-PLAN.md`) e código/testes presentes neste repositório.

## 27/10/2026 — Entrega 1/4 (fundação e qualidade da análise)

- Atualizado o Plano Mestre para v0.4.0 e organizado o roadmap em quatro entregas consolidadas.
- Atualizado `.env.example`: explica em destaque que `AI_PROVIDER=disabled` desliga deliberadamente as perguntas por IA e inclui um exemplo Gemini comentado, sem chave real. Os READMEs usam `gemini-3.6-flash` com `medium` como exemplo validado no ambiente do usuário em 27/10/2026, sujeito à disponibilidade da conta.
- Corrigido comentário antigo/versionado no adaptador para descrever genericamente a chamada nativa `generateContent` do Gemini.
- Ajustado o recuperador: a primeira seleção por papel prioriza relevância lexical dentro de cada tipo de arquivo; a busca de documentação usa nomes de símbolos encontrados na implementação; perguntas que pedem exemplo documentado podem reservar até dois trechos de documentação sem ultrapassar o limite de evidências.
- Adicionadas duas regressões sintéticas: documentação que menciona o método real da implementação deve superar um guia genérico; e o arquivo de teste relevante deve anteceder testes não relacionados.
- Registrada a baseline anterior à correção em `docs/evaluations/borax-baseline-2026-10-27.md`. Ela registra seis casos pontuados de sete, Hit@5 0,8333, Recall@5 0,75 e as falhas de documentação/testes reportadas pelo usuário. Criado também um corpus humano inicial para qualidade de respostas e um protocolo de revisão. O corpus de recuperação real ainda precisa ser reexecutado após a correção para medir o efeito.
- **Verificação da preparação no snapshot de trabalho empacotado:** `python -m pytest` — 85 testes passaram; `python -m compileall -q app tests` — passou; `npm run test:layout` — passou (420 nós, sem sobreposições).
- **Pendências de validação:** Ruff não estava instalado no ambiente desta execução. A tentativa de gerar `package-lock.json`/resolver dependências npm excedeu o limite de tempo deste ambiente; portanto, type-check, build e ESLint completos do frontend continuam não verificados. O snapshot usado para os 85 testes antecede um teste adicional do seletor `--latest` presente no diretório local do usuário; os testes devem ser repetidos depois de aplicar a entrega, não se deve inferir um total final a partir de snapshots diferentes.
- **Validação manual do modelo:** a resposta via `gemini-3.6-flash` com `medium` foi mais organizada, mas errou a semântica de `self.assertTrue(expected, actual)`; a chamada confirma conectividade, não comprova precisão semântica abrangente.

## Estado atual

A base de análise estática está funcional na máquina do usuário. A v0.7.0 corrige a classificação de perguntas que pedem implementação e também mencionam uma biblioteca, amplia a recuperação para definições por símbolo, testes/exemplos, trechos relevantes da documentação e relações do grafo; adiciona expansão lexical português→identificadores em inglês; recolhe as referências por padrão; e inclui preferências locais de fonte/tamanho. A IA continua opcional e desligada por padrão. Não foi feita chamada real a um provedor nesta fatia.

## 27/10/2026 — harness offline de avaliação RAG (tooling de desenvolvimento)
- Testes adicionais de endurecimento: o avaliador recusa corpus para outro repositório e exclui rótulos cuja fonte foi descoberta, mas não possui conteúdo persistido.

- Adicionado `services/api/app/application/rag_evaluation.py` para carregar/validar corpora rotulados e medir a recuperação em uma análise persistida.
- Adicionado `services/api/scripts/evaluate_rag.py`: executa localmente, sem chamadas à IA, e gera métricas Hit@k, Recall@k, MRR e acurácia de intenção.
- Adicionado corpus inicial `services/api/evaluation/corpora/borax.json` com seis casos de `kinegratii/borax`, incluindo um caso `insufficient_evidence` explicitamente fora das métricas de geração.
- Caminhos esperados que não existem no snapshot são reportados como anotações inválidas e excluídos das métricas; o resultado registra SHA, ID da análise, limites e não inclui snippets.
- Documentação de uso, significado das métricas e limitações em `docs/RAG-EVALUATION.md`.
- **Verificação desta iteração:** `python -m pytest -q` em `services/api`: 83 testes passaram, incluindo 7 testes novos do harness. Os testes exercitam o avaliador e sua integração com o recuperador por meio de fixtures sintéticas; eles não representam uma avaliação real de RAG em Borax.
- **Ainda pendente:** executar o corpus sobre uma análise real de Borax, revisar manualmente os rankings/citações e ampliar os casos por linguagem/intenção. A correção semântica das respostas e a abstinência do modelo continuam sem métrica automatizada.
- O frontend, o build de produção e o lint não foram alterados nem validados nesta iteração. A versão funcional da aplicação continua referenciada como v0.7.0; este incremento é tooling de avaliação, não uma declaração de release funcional nova.

## Implementado e verificado

- **Ingestão GitHub:** URL pública validada, SHA do commit fixado, download de arquivo compactado com limite e fallback seletivo por árvore/arquivos elegíveis quando o ZIP é grande; verificação de integridade de blobs e avisos para cobertura parcial.
- **Parsing e grafo Python:** parsing estático pela biblioteca `ast`, extração limitada de módulos, classes, funções, métodos, imports, endpoints, testes reconhecíveis e chamadas locais inferidas; relações determinísticas e inferidas têm proveniência diferenciada.
- **Skills determinísticas:** detecção inicial de possíveis segredos com redação antes da persistência e inventário simples de arquivos de teste; achados estruturados e revisão humana persistente.
- **Layout do grafo:** visão inicial limitada a 180 nós, filtros/busca para até 500 correspondências e layout dinâmico testado com 420 nós sem colisões.
- **Persistência:** snapshots, arquivos redigidos, nós, arestas, achados, eventos e relatórios Markdown persistidos. A escrita de achados/nós/arestas respeita dependências de chave estrangeira.
- **Diagnóstico:** falhas de análise registram ID, estágio, classe da exceção, stack locations e identificadores seguros de restrições sem SQL/parâmetros/conteúdo-fonte.
- **IA/RAG — primeira fatia:** endpoint `POST /api/v1/analyses/{analysis_id}/questions`; recuperação lexical de trechos de código redigidos, recuperação de achados relevantes e relações do grafo; limitação de contexto/evidências; adaptador opcional para provedores compatíveis com OpenAI Chat Completions e caminho nativo Gemini generateContent; timeout e tratamento de falhas; JSON validado; citações conferidas no servidor contra IDs reais de evidência recuperada; resposta inconclusiva se não houver referência válida.
- **Segurança da IA:** prompt trata README, strings, comentários e código como dados não confiáveis; modelo não recebe ferramentas nem acesso ao terminal/filesystem; a chave fica no backend; endpoint remoto exige HTTPS, enquanto HTTP sem chave só é permitido para hosts locais reconhecidos; UI pede confirmação explícita antes de enviar trechos redigidos.
- **Privacidade da conversa:** perguntas/respostas não são persistidas nesta versão. Quando a IA é usada, a pergunta e os trechos recuperados são enviados ao endpoint configurado; não se envia o repositório inteiro.
- **Documentação:** README, exemplo de ambiente, modelo de segurança, roadmap e ADR atualizados.

## Testes executados nesta fatia

- `python -m pytest -q services/api`: **76 testes passaram**. Incluem regressão para classificar a pergunta real sobre datas lunares como implementação (não dependências), expansão PT→identificadores, recuperação da classe/método, teste, documentação e relação do grafo.
- `python -m compileall -q app tests`: passou.
- `npm run test:layout`: passou; 420 nós sintéticos sem sobreposição.
- TypeScript/TSX: transpilação sintática de 5 arquivos passou com zero diagnósticos; não equivale a type-check.
- Instalação de dependências npm excedeu 120s; build Vite/type-check e ESLint do frontend permanecem não verificados.
- `python -m ruff` não está instalado; lint do backend não executado.
- O usuário já validou chamadas reais com Gemini Flash-Lite em uma versão anterior; não fiz nova chamada real com o novo fluxo de recuperação nesta fatia.
- Compilação sintática TypeScript/TSX via TypeScript global: 5 arquivos aprovados.
- Ruff não está instalado no ambiente; lint do backend não executado.
- `npm install --no-audit --no-fund` excedeu o limite de execução e o `npm run build` confirmou ausência das dependências (React, Vite e tipos). O build completo do frontend continua não verificado.
- A chamada real ao Gemini/provedor externo não foi executada nesta fatia.

## Configuração da IA

O `.env.example` define `AI_PROVIDER=disabled` por padrão. Para habilitar perguntas, use `AI_PROVIDER=openai-compatible`, configure `AI_MODEL` com o identificador realmente disponível no provedor e configure `AI_API_KEY` e `AI_BASE_URL`. A chave é opcional apenas quando o endpoint está em um dos hosts locais reconhecidos. Reinicie a API e recarregue o navegador para atualizar o status de IA.

## Limitações conhecidas

- A recuperação v0.6.0 classifica intenção e faz curadoria/expansão lexical-estrutural, mas continua heurística; ainda não usa embeddings nem reranking semântico e pode perder sinônimos, intenções ambíguas ou relações dinâmicas.
- A implementação exige JSON do modelo; provedores/modelos que não aceitam o formato de resposta JSON podem retornar erro controlado.
- A validade sintática de uma citação é garantida pelo servidor; a veracidade de cada conclusão semântica não é garantida. O usuário deve abrir as fontes e revisar respostas.
- Redação de segredos por padrões pode ter falsos negativos. Não envie código cuja transmissão ao provedor não seja autorizada.
- Não há histórico de chat, login, autorização por usuário, repositórios privados, suporte completo a outras linguagens, advisories de dependências, embeddings/pgvector, análise incremental ou worker durável.
- O projeto permanece para uso local; não o exponha à rede/internet sem autenticação, autorização e revisão de segurança.

## v0.6.1 — diagnóstico de erro do provedor

- Faz uma segunda tentativa limitada para respostas transitórias 500/502/503/504 do Gemini, com espera de até 2 segundos baseada em `Retry-After` quando disponível.
- Se persistir, retorna `AI_PROVIDER_UNAVAILABLE` com status HTTP e enum seguro (por exemplo `UNAVAILABLE`), sem expor a mensagem bruta do Google.
- Loga provedor, status, enum, número de tentativas e ID do modelo; não grava chave, pergunta, evidência ou corpo do erro.
- Testes simulados: 503 seguido de sucesso; 503 persistente; ausência de mensagem sensível nos erros/logs.
- A chamada real na conta do usuário continua sem verificação; o código de status real ainda precisa ser observado localmente.

## Próximos passos

1. Instalar as dependências npm, gerar `package-lock.json` e validar `npm run lint` + `npm run build`.
2. Fazer uma prova local com o provedor real já configurado pelo usuário; conferir respostas, citações, tempo e consumo, sem imprimir a chave.
3. Criar corpus de perguntas/respostas esperadas por intenção, incluindo prompt injection e falta de evidência; medir pertinência da recuperação, correção das conclusões e falsos positivos.
4. Melhorar a representação de fluxos e corrigir lacunas encontradas na avaliação; adicionar busca semântica só se o corpus demonstrar benefício.
5. Consolidar critérios de aceite do MVP e repetir instalação/execução a partir de ambiente limpo.

## Estado do Git

A entrega está em diretório de trabalho empacotado. Não foi executado push nem publicação remota.


## v0.6.2 — cobertura e consulta do grafo

- `/api/v1/analyses/{id}` apresenta contadores de cobertura: total inventariado, conteúdo elegível/lido, ignorados por política, falhas de leitura, arquivos não suportados, Python total/parseado/falhou/pendente e arquivos sem parsing estrutural Python.
- `/api/v1/analyses/{id}/graph` aceita `node_type` e `q` para busca no servidor por label, stable key e caminho. A API retorna contadores do snapshot, nós correspondentes, nós/arestas retornados e flags de truncamento separadas.
- A interface informa a contagem exata da parte truncada e deixa claro que o limite de visualização não prova ingestão incompleta. Avisos de ingestão são listados todos; filtros e busca recuperam no servidor os nós fora do conjunto inicial de 2.000.
- Corrigido o polling que recarregava grafo e achados a cada 2 segundos após análise terminal; o polling e SSE são encerrados ao concluir, e a atualização do grafo acontece na transição terminal, nos eventos de domínio ou por ação explícita do usuário. As consultas agregadas de cobertura são feitas somente em análises terminais.
- Testes automatizados cobrem contadores, truncamento e busca/filter de caminho/nó antes do limite.


## Limitações atuais do grafo

- A primeira consulta geral retorna no máximo 2.000 nós e 4.000 relações. A UI apresenta uma visão resumida de até 180 nós e renderiza até 500 nós por busca/filtro. A busca e os filtros agora consultam o servidor; cada resposta segue limitada a 2.000 nós e 4.000 relações, e ainda não existe paginação cursor-based para percorrer sequencialmente centenas de milhares de resultados.
- A cobertura do inventário é contabilizada separadamente da cobertura do parser Python. Arquivos ignorados por política ou linguagens sem parser podem estar inventariados sem terem sido analisados estruturalmente.


## v0.7.0 — recuperação de implementação e leitura ajustável

- Prioridade de intenção corrigida: pedidos explícitos de investigação/implementação são classificados antes de termos genéricos como “biblioteca”, que antes desviavam a recuperação para dependências.
- Vocabulário PT→código/EN, separação de CamelCase e expansão para conceitos como “datas lunares” ajudam perguntas em português a localizar identificadores como `LunarDate`, `from_solar_date` e diretórios `calendar`. A expansão de termos só ocorre no texto da pergunta, não indiscriminadamente em cada snippet.
- Recuperação source-first: começa por definições/classes/métodos relevantes no grafo e trechos de código, traz teste/exemplo relacionado, trecho de documentação que realmente corresponde ao termo e relações conectadas aos símbolos.
- Novos testes com fixture de código, README, métodos, testes e arestas; o teste exige que a resposta possa receber contexto de mais de uma fonte e checa que a pergunta completa não é classificada como dependências.
- Fontes citadas ficam em `<details>` recolhido por padrão; continuam disponíveis sob demanda.
- Preferências visuais locais: família de fonte e tamanho pequeno/normal/grande no menu “Texto” do topo.
- Tentativa de instalação npm excedeu 120s neste ambiente. Build completo do Vite continua não verificado; teste de layout e sintaxe TypeScript/TSX foram verificados separadamente.

## 27/10/2026 — Fase B: avaliação offline executável no Docker

- O avaliador offline e o corpus são incluídos na imagem da API, para consultar o mesmo PostgreSQL que armazena as análises da interface.
- A CLI permite selecionar a última análise concluída do repositório anotado no corpus (`--latest`) ou fixar a execução por ID (`--analysis-id`); o relatório registra o SHA usado.
- O corpus de Borax passa a ter sete casos e inclui explicitamente recuperação de exemplo documentado (`docs/guides/lunardate.md`) junto à implementação (`borax/calendars/lunardate.py`).
- Adicionado teste para garantir que `--latest` não selecione análise de outro repositório nem funcione com corpus sem `target_repository`.
- **Pendente:** executar o corpus numa análise real de `kinegratii/borax` e revisar os rankings/citações contra o SHA registrado. Esta ferramenta mede recuperação; não mede ainda a qualidade semântica da resposta, abstinência do modelo, latência ou custo de geração.

## 27/10/2026 — Complemento da Entrega 1: avaliação de respostas RAG

- O relatório de recuperação agora separa os caminhos ausentes do snapshot (`missing_from_snapshot_paths`) dos caminhos esperados que não entraram no ranking (`not_retrieved_expected_paths`); os campos anteriores são preservados para compatibilidade.
- Adicionado teste de regressão para distinguir arquivo inexistente no snapshot de falha de recuperação.
- Adicionado `evaluate_answers.py` com corpus fixado ao snapshot Borax, comparação dos caminhos recuperados e citados, metadados das citações, latência, triagem lexical de abstenção e campos para revisão humana.
- **Pendente após aplicação:** reconstruir a imagem, rodar testes/lint e executar o benchmark real com `--run-provider`. A revisão semântica não é declarada concluída automaticamente.

## 27/10/2026 — Recuperação direcionada de trechos de teste

- A revisão de `borax-answer-quality-review` revelou que a busca de intenção `tests` enviava o cabeçalho do arquivo e cortava a asserção consultada nas linhas posteriores.
- Ajustada a seleção dos trechos de arquivos de teste para priorizar blocos lexicalmente relevantes; incluído teste de regressão com a asserção após a linha 60.
- O avaliador de respostas passou a aceitar `--case-id` repetido e registrar os IDs selecionados, permitindo retestes isolados sem repetir todas as chamadas do benchmark.
- Pendente após aplicação: executar a validação completa, reconstruir a API e rerodar apenas `lunar-test-assertion-semantics` com `AI_REASONING_EFFORT=low`. A correção semântica continua exigindo revisão manual.

## 27/10/2026 — Contrato de formato dos marcadores de evidência

- A resposta revisada detectou corretamente o defeito de `assertTrue`, mas emitiu `E#E2`, formato que o avaliador anterior não reconhecia e por isso deixou escapar a divergência.
- O prompt agora exige marcadores como `[E2]`; o avaliador registra tokens malformados e inclui esses casos na métrica de incompatibilidade de citação.
- Pendente: validação completa e nova avaliação seletiva para conferir o formato de citação, sem presumir que isso garante a sustentação semântica.

## 27/10/2026 — Nota estática sobre semântica de assertTrue

- O benchmark de `lunar-test-assertion-semantics` demonstrou variabilidade: o modelo identificou corretamente o defeito em uma execução, mas depois afirmou incorretamente que `assertTrue` comprova a conversão.
- Adicionada uma nota determinística baseada em AST para chamadas de dois argumentos a `assertTrue` dentro de classes `unittest.TestCase`, sem execução do código-alvo.
- Incluídos testes de regressão para o conteúdo da nota e para o contrato do prompt.
- Pendente: validar no ambiente local, reconstruir a API e repetir apenas o caso selecionado. A avaliação de conteúdo permanece manual.

## 27/10/2026 — Marcadores agrupados de evidência

- O benchmark v4 confirmou a interpretação correta de `assertTrue`, com apoio da nota estática e duas evidências.
- O avaliador marcou incorretamente `E3` como malformado dentro de `[E2, E3]`.
- O extrator agora aceita IDs separados por vírgula dentro dos mesmos colchetes, mas continua sinalizando IDs não bracketed, placeholders e separadores inválidos.
- A validação completa e os testes de regressão devem passar antes do rebuild.

## Entrega 2 — Cobertura, confiabilidade e grafo (incremento local)

- A API de grafo aceita `offset` e devolve `offset`, `page_size` e `has_more_nodes`; a flag de truncamento considera a posição do lote e não apenas a quantidade retornada.
- O canvas distingue nós no snapshot, nós correspondentes à busca/filtro, nós retornados pela API e nós renderizados. A visão geral permanece resumida; busca/filtro permite percorrer páginas de 500 nós dentro dos lotes de até 2.000 retornados pela API.
- A API de análise expõe os mapas completos de estados de elegibilidade e parsing e sintetiza motivos conhecidos para análise parcial a partir de avisos persistidos e falhas registradas. Não interpreta “fora do parsing Python” como falha automaticamente.
- O endpoint SSE envia diretiva `retry: 1500`; o frontend mostra conectado/reconectando/encerrado, continua usando polling do estado persistido como fallback e deduplica eventos replayados pelo `Last-Event-ID`.
- Testes de regressão exercitam offset do grafo, ordem e replay de eventos SSE após cursor, sem depender de um provedor externo.

**Limitações mantidas:** o processamento da análise continua em background no mesmo processo da API; um reinício abrupto não transforma automaticamente toda execução em estado terminal durável. A paginação evita desenhar centenas de milhares de nós simultaneamente, mas cada página ainda é limitada por `limit`/`edge_limit` e as arestas de cada lote descrevem as relações entre nós retornados naquele lote. Revisar o comportamento local na interface após aplicar a Entrega 2.

## Entrega 3/4 — inteligência e exploração interativa

- [x] Trilha de varredura para os arquivos realmente inspecionados pelas skills determinísticas, ligada a eventos persistidos e nós do grafo.
- [x] Perguntas em SSE POST: a trilha de recuperação chega antes da resposta do modelo, com caminho/linhas e IDs de nós; a interface destaca a evidência durante a geração e diferencia evidência citada.
- [x] Corpus offline de avaliação de skills AppSec e inventário de testes, com casos positivos, negativos e ambíguos.
- [x] Testes de regressão para callback da varredura, endpoint SSE e nós destacados no overview.
- [ ] Validar na máquina local a execução completa, o streaming da pergunta com o provedor configurado e a interação visual no navegador.
- [ ] Não habilitar embeddings/reranking até que a comparação de qualidade com a linha de base mostre ganho mensurável.

## Entrega 4 — distribuição desktop para Windows (implementação preparada)

**Estado em 27/10/2026:** inicializador e pipeline de empacotamento preparados; a versão ainda não é considerada release validada até passar o smoke test em Windows e a verificação adicional em ambiente limpo.

- `desktop/launcher.py` inicia um processo de API separado, prepara/migra o banco SQLite, espera o health check, abre a interface no navegador e encerra o processo por endpoint local autenticado quando a janela é fechada.
- O runtime do pacote usa somente `127.0.0.1` e uma porta livre escolhida ao iniciar. A API exige um token aleatório de sessão em todas as requisições `/api/`; o token é entregue pelo bootstrap da própria página sem cache e não fica na URL.
- A configuração opcional de IA fica no inicializador, fora do frontend web. A chave é armazenada por DPAPI para o usuário Windows atual; `settings.json` contém somente habilitação, URL, modelo e nível de raciocínio. A IA começa desligada em primeira execução e os controles determinísticos continuam disponíveis.
- O script `desktop/build-windows.ps1` roda lint, testes e builds, empacota os runtimes com PyInstaller, monta o ZIP a partir de uma pasta limpa e recusa artefatos locais como `.env`, banco, logs, preferências ou arquivo de chave.
- `desktop/test-windows-package.ps1` verifica o início, HTML/assets, token de sessão, health check, banco SQLite e encerramento/reinício. O aceite final ainda depende de executar esse roteiro em Windows e, depois, em Windows limpo sem Python, Node.js ou Docker.
- O visual já funcional foi mantido; melhorias cosméticas foram deliberadamente adiadas e não bloqueiam o trabalho de distribuição desta etapa.

**Limite de validação:** os testes unitários de desktop e os testes de proteção da API estão incluídos. Não marcar o critério de Windows limpo como concluído antes de registrar a saída real do build e do smoke test na máquina/VM de destino.
