# YGGDRASIL — Plano Mestre de Engenharia

> **Documento:** Plano Mestre / Fonte de Verdade do Projeto  
> **Versão do plano:** 0.3.0  
> **Atualizado em:** 27/10/2026  
> **Versão do aplicativo tomada como referência:** 0.7.0  
> **Status:** MVP local funcional em validação; não é uma versão pronta para exposição pública ou uso em produção  
> **Idioma principal:** português (pt-BR)  
> **Princípio de engenharia:** simplicidade sem improviso  
> **Nome:** Yggdrasil — a árvore que representa visualmente a rede de relações de um software

---

## 0. Como usar este documento

Este plano substitui as versões conceituais anteriores como referência principal para as próximas etapas. Ele registra **o que existe hoje**, o que foi testado, o que continua incerto e quais entregas vêm a seguir.

A regra é separar quatro estados:

- **Implementado:** há código na versão de referência.
- **Testado automaticamente:** há teste executado que cobre o comportamento indicado.
- **Validado manualmente:** o fluxo foi executado por uma pessoa, sem que isso represente validação exaustiva.
- **Planejado:** não deve ser apresentado como funcionalidade existente.

Em caso de conflito, verificar o código e os testes da versão em questão. O README explica como executar a versão distribuída; este plano explica a direção, os limites e as decisões do produto. O documento `docs/PROGRESS.md` mantém o diário de progresso mais detalhado.

---

## 1. Resumo executivo

**Yggdrasil** é uma ferramenta local de análise estática e compreensão de repositórios de software. Recebe a URL de um repositório público do GitHub, fixa a análise a um commit, inspeciona arquivos elegíveis sem executar o código-alvo e transforma os resultados em um inventário, um grafo consultável, achados iniciais e um relatório Markdown.

A versão atual combina:

- ingestão limitada de repositórios públicos do GitHub;
- parsing estático de Python;
- grafo persistido de arquivos, símbolos e relações;
- duas skills determinísticas iniciais — detecção de possíveis segredos e inventário de arquivos de teste;
- perguntas assistidas por IA com recuperação lexical/estrutural de evidências;
- uma interface web para explorar o grafo, consultar evidências, revisar achados e exportar relatórios.

O Yggdrasil **não é apenas um chatbot para resumir README**. Seu diferencial pretendido é ancorar a exploração e as respostas em artefatos do repositório vinculados a um commit e explicitar as limitações da análise.

### Proposta de valor

> Entender um repositório desconhecido por meio de um mapa consultável, fazer perguntas orientadas por evidências e obter um relatório técnico que permita verificar as conclusões.

### Estado honesto do produto

A v0.7.0 já percorre uma parte importante desse fluxo de ponta a ponta. O parsing é focado em Python, a busca para perguntas continua heurística e baseada principalmente em termos/estrutura, e o catálogo de skills é pequeno. Ainda faltam avaliação sistemática de qualidade, build/lint completos do frontend confirmados neste ambiente, ampliação das skills e endurecimento necessário para qualquer uso compartilhado ou hospedado.

---

## 2. Identidade, visão e problema

### 2.1 Significado do nome

Yggdrasil faz referência à árvore mitológica que conecta diferentes mundos. No produto, a árvore representa componentes identificáveis do software e as relações entre eles. A metáfora visual ajuda a navegar; não define a verdade técnica do grafo.

O modelo primário é um **grafo de conhecimento do código**. Relações determinísticas extraídas por regras e relações inferidas por heurísticas devem continuar distinguíveis. A IA interpreta evidências disponíveis; não substitui a origem nem converte uma hipótese em fato confirmado.

### 2.2 Visão

Permitir que uma pessoa investigue um repositório desconhecido, compreenda sua estrutura e encontre evidências relevantes sem depender somente da leitura manual de centenas de arquivos.

### 2.3 Problema

Entender uma base de código exige localizar pontos de entrada, seguir imports e chamadas, reconhecer regras de negócio, correlacionar implementação e testes e conferir configurações e dependências. A documentação pode estar ausente ou desatualizada. A análise assistida deve reduzir o esforço inicial, sem prometer compreensão perfeita.

### 2.4 Perguntas que queremos ajudar a responder

- Como o repositório está organizado?
- Quais arquivos, módulos, classes e funções foram identificados?
- Onde estão definidas certas regras ou interfaces?
- Quais testes parecem relacionados a uma funcionalidade?
- Que relações foram extraídas diretamente e quais são inferências?
- Quais possíveis segredos aparecem em arquivos elegíveis?
- Que evidência sustenta uma resposta ou recomendação?
- Quais arquivos ficaram fora da análise e por quê?
- O que ainda precisa ser verificado manualmente?

### 2.5 Público inicial

Desenvolvedores que precisam compreender bases existentes, estudantes que aprendem lendo código real, mantenedores, revisores técnicos e profissionais que fazem triagem estática inicial de AppSec. O sistema é uma ferramenta de apoio; não substitui revisão humana, testes, scanners especializados ou análise dinâmica.

---

## 3. Princípios obrigatórios

### 3.1 Evidência antes de conclusão

README, comentários e documentação são fontes úteis, mas não provam que a implementação atual se comporte como descrito. Respostas devem preferir código, testes, configuração e relações efetivamente recuperadas, citando caminho e linha quando disponíveis.

### 3.2 Fato, inferência, hipótese e recomendação não são sinônimos

- **Determinístico/extraído:** produzido por parser, API ou regra reprodutível.
- **Inferido:** sugerido com base em correspondências ou contexto, sem prova completa de execução.
- **Hipótese:** possibilidade que ainda exige validação.
- **Recomendação:** ação sugerida; não comprova que exista um defeito.

Não atribuir pontuações numéricas artificiais de confiança sem calibração empírica.

### 3.3 Segurança por padrão

O analisador não executa, importa, compila, instala nem testa o código do repositório-alvo. Código externo é conteúdo não confiável. URLs, arquivos, caminhos, conteúdo compactado e respostas da IA precisam permanecer sob limites explícitos.

### 3.4 Arquitetura proporcional

Manter o monólito modular enquanto atender ao uso atual. Não adicionar filas distribuídas, microsserviços, vetor store, cluster de agentes ou infraestrutura comercial por antecipação.

### 3.5 Fatias verticais verificáveis

Priorizar fluxos completos pequenos em vez de acumular telas e camadas incompletas. Uma funcionalidade só pode ser declarada pronta quando o comportamento relevante foi exercitado e suas limitações documentadas.

### 3.6 Não confundir visibilidade com cobertura

Um nó fora da visão inicial pode continuar presente no grafo persistido. Da mesma forma, um arquivo inventariado pode não ter tido seu conteúdo lido ou sua sintaxe analisada. A UI precisa separar cobertura da ingestão, do parser e da visualização.

### 3.7 A IA não possui autoridade operacional

A IA não recebe terminal, filesystem, ferramentas livres ou permissão de escrita no repositório. Conteúdo encontrado no README, nos comentários ou no código é dado não confiável e não pode substituir as instruções do sistema.

---

## 4. Estado real da versão 0.7.0

Esta seção descreve a referência funcional adotada por este plano. Não significa que cada requisito do plano completo esteja implementado.

### 4.1 Implementado

**Ingestão e inventário**

- Aceita URL canônica de repositório público do GitHub.
- Valida a origem e resolve a referência solicitada para um commit identificável.
- Tenta a ingestão por arquivo compactado dentro de um limite; quando necessário, usa a árvore do commit e busca seletiva de arquivos elegíveis.
- Aplica limites para tamanho compactado, número de entradas, tamanho individual e orçamento agregado de texto.
- Mantém avisos e razões para itens ignorados ou falhas de leitura.
- Não segue links arbitrários descobertos no conteúdo do repositório.

**Parsing e grafo**

- Usa a biblioteca padrão `ast` para parsing estático de Python.
- Extrai módulos, classes, funções/métodos, imports internos e alguns decorators que aparentam declarar endpoints.
- Identifica relações que podem ser determinadas a partir dos dados e marca separadamente relações inferidas, como chamadas possíveis por correspondência local.
- Persiste nós e arestas relacionados ao snapshot analisado.
- Suporta inspeção de nós, filtros por tipo e busca por nome/caminho.
- Expõe contadores de cobertura da ingestão e do parsing Python.

**Skills iniciais**

- `appsec.secrets-detection` — deteção por padrões de possíveis segredos, com redação dos padrões reconhecidos antes da persistência.
- `engineering.test-inventory` — inventário simples de arquivos de teste Python.

As skills são determinísticas e limitadas. O inventário de testes não executa testes nem mede cobertura. A deteção de segredos não detecta todos os formatos possíveis e não valida credenciais.

**Perguntas assistidas por IA**

- Há um endpoint de perguntas para uma análise concluída.
- A recuperação v0.7.0 classifica a intenção da pergunta, expande termos em português para identificadores comuns em inglês e prioriza definições/código, testes/exemplos, documentação relevante e relações do grafo.
- A recuperação é lexical e estrutural, com limite de evidências e de caracteres; não usa embeddings ou reranking semântico.
- O backend valida que as referências devolvidas pelo modelo correspondam às evidências recuperadas. Isso reduz citações inventadas, mas não garante que toda conclusão semântica esteja correta.
- O adaptador de IA é configurável e pode usar endpoints compatíveis com OpenAI Chat Completions ou o caminho de API nativa do Gemini implementado no projeto.
- A IA é opcional e desativada por padrão.
- A interface solicita confirmação antes de transmitir ao provedor a pergunta e os trechos de evidência redigidos.
- Perguntas e respostas não formam um histórico persistido nesta versão.

**Persistência, eventos e relatório**

- SQLAlchemy e migrations Alembic.
- SQLite é o padrão local; PostgreSQL pode ser configurado.
- Persistência de repositórios, snapshots, execuções, arquivos, nós, arestas, eventos, achados e exportações.
- Execuções de análise em background no processo da API.
- Eventos persistidos e stream SSE para acompanhar progresso e recuperar eventos recentes.
- Exportação do relatório Markdown a partir de dados persistidos.
- Revisão humana persistida dos achados, incluindo confirmação, falso positivo, risco aceito e estados relacionados.

**Interface**

- React, TypeScript, Vite e `@xyflow/react`.
- Canvas do grafo, pesquisa/filtros, inspetor contextual, painel de avisos, achados e exportação.
- A visão inicial é resumida para preservar legibilidade; pesquisar no servidor permite encontrar nós fora da primeira janela.
- Preferências locais de família e tamanho de fonte.

### 4.2 Testes e validações conhecidos

- **Backend:** 76 testes passaram na execução registrada em `docs/PROGRESS.md`, incluindo testes unitários e de integração com GitHub/provedor simulados.
- **Layout do grafo:** teste sintético passou para 420 nós sem sobreposições.
- **TypeScript/TSX:** foi verificada transpilação sintática de cinco arquivos; isso não equivale ao type-check completo nem a um build de produção.
- **Frontend:** instalação de dependências excedeu o limite do ambiente usado para a verificação; `npm run build` e `npm run lint` ainda não estão confirmados como aprovados.
- **Ruff:** não estava instalado no ambiente de verificação; lint do backend ainda precisa ser executado.
- **Provedor real:** houve teste manual do usuário na v0.7.0 com Gemini Flash-Lite para uma pergunta direcionada sobre datas lunares do repositório `kinegratii/borax`. A resposta trouxe caminhos e linhas de implementação/testes. Isso é um smoke test promissor, não uma avaliação exaustiva da precisão do RAG ou da correção de cada citação.

Os resultados de teste acima são um retrato do ambiente e da versão registrados, não uma garantia permanente. Repetir testes após alterações e antes de declarar uma release.

### 4.3 Não implementado ou não validado

- Suporte estrutural completo a JavaScript/TypeScript, Java ou outras linguagens.
- Fluxo de chamadas completo e preciso entre todas as camadas e chamadas dinâmicas.
- Embeddings, base vetorial e reranking semântico.
- Avaliação ampla do RAG com corpus de perguntas, respostas esperadas e métricas.
- Catálogo amplo de skills de arquitetura, autorização, validação de entradas, dependências e DevSecOps.
- Consulta automatizada e datada de advisories de dependências.
- OAuth e análise de repositórios privados.
- Histórico de conversas com IA.
- Análise incremental e comparação de commits/snapshots.
- Worker durável que sobreviva a reinicializações; tarefas longas são executadas no processo da API.
- Login, permissões por usuário, colaboração multiusuário e hardening para hospedagem pública.
- Verificação completa de build/type-check/lint do frontend na versão de referência.
- Execução de código, scanners dinâmicos ou testes do repositório analisado.

---

## 5. Escopo do produto

### 5.1 Escopo atual do MVP local

- Analisar repositórios **públicos** do GitHub.
- Vincular uma execução a um commit resolvido.
- Inventariar arquivos elegíveis sob limites configuráveis.
- Extrair uma camada inicial de estrutura Python por parsing estático.
- Construir um grafo navegável e inspecionável.
- Rodar skills determinísticas habilitadas.
- Fazer perguntas assistidas por IA com recuperação de evidências, quando explicitamente configurada.
- Revisar achados, exportar Markdown e exibir avisos/limitações.
- Trabalhar localmente, sem autenticação de usuários.

### 5.2 Fora do escopo atual

- Repositórios privados ou permissões GitHub por usuário.
- Execução de código ou instalação de dependências do alvo.
- Provar que um sistema está seguro ou livre de vulnerabilidades.
- Cobertura de todas as linguagens/frameworks.
- Fuzzing, exploração ativa ou testes em sistemas implantados.
- Alteração automática de código, criação de commit ou pull request.
- Acesso irrestrito da IA ao terminal, à rede, ao banco ou ao filesystem.
- SaaS multiusuário, faturamento e isolamento comercial completo.
- Prometer entendimento exaustivo de grandes sistemas dinâmicos.

### 5.3 Evolução possível

Após avaliar o MVP, considerar: melhora incremental da recuperação, corpus de avaliação versionado, skills AppSec adicionais, análise de dependências com fonte atual e data, busca semântica se benchmarks justificarem, suporte a outra linguagem, comparação de commits, importação de resultados de scanners externos sob contrato explícito e execução em sandbox isolada como projeto futuro independente.

---

## 6. Fluxo principal do usuário

1. O usuário cola uma URL canônica de repositório público.
2. O backend valida a URL e resolve a referência para um commit.
3. A análise é registrada e retorna um estado inicial.
4. O backend inventaria arquivos e aplica os limites de ingestão.
5. O parser extrai a estrutura Python suportada; o grafo é persistido.
6. As skills determinísticas habilitadas produzem achados candidatos.
7. A interface acompanha progresso e avisos e permite explorar o grafo.
8. O usuário abre um nó para examinar detalhes e evidências.
9. Quando a IA está habilitada, o usuário confirma o envio dos trechos redigidos e faz perguntas.
10. O usuário confere referências e registra a decisão humana sobre achados.
11. O usuário exporta um relatório Markdown.

Uma análise pode terminar com avisos ou cobertura parcial. O status terminal não significa que todos os arquivos foram analisados estruturalmente nem que todos os riscos foram encontrados.

### 6.1 Estados da execução

Os estados exatos devem seguir o contrato da implementação. Em termos de produto, é necessário distinguir fila/início, ingestão, parsing/construção, execução das skills, finalização, conclusão normal, conclusão com avisos, falha e cancelamento quando suportado. A interface não deve mostrar percentuais inventados.

### 6.2 Estados de cobertura de arquivo

Registrar, sempre que aplicável, se o item foi descoberto, lido, elegível, ignorado por política, não suportado ou falhou. Não confundir arquivo presente no inventário com arquivo lido, redigido ou interpretado pelo parser.

---

## 7. Interface e mapa

### 7.1 Regiões funcionais

A interface atual pode evoluir, mantendo quatro responsabilidades conceituais:

1. **Canvas:** mostra o grafo e destaca as relações selecionadas.
2. **Atividade/avisos:** informa etapa, contadores, avisos e falhas.
3. **Inspetor:** mostra detalhes, origem, linhas, evidências e achados do item selecionado.
4. **Perguntas/relatório:** permite consultar a análise e exportar resultados.

A linha do tempo é formada pelos eventos persistidos/SSE. Não criar painéis meramente decorativos sem uma finalidade operacional.

### 7.2 Limites de visualização

O sistema diferencia o grafo persistido da parte renderizada. Na v0.7.0, a visão inicial é resumida a até 180 nós; pesquisa/filtros podem recuperar até 2.000 nós e 4.000 arestas por resposta; a renderização interativa segue limitada a até 500 nós em uma consulta visual. Ainda não há paginação cursor-based para percorrer sequencialmente volumes muito grandes.

Esses limites são decisões de apresentação e API, não evidência de que os itens omitidos da visão inicial tenham sido removidos da análise.

### 7.3 Tipos de nós já relevantes

A extração atual inclui entidades como repositório/snapshot, diretórios/arquivos e símbolos Python — módulos, classes, funções/métodos — além de nós associados a testes, dependências e achados quando suportados pelo pipeline. O conjunto real depende do que o parser identifica; não fabricar tipos para preencher o mapa.

### 7.4 Relações

As relações atuais podem incluir contenção, imports/definições, relações com testes, dependências e chamadas inferidas quando suportadas pelos dados. Cada tipo deve ter semântica clara. Uma chamada inferida por nome não equivale a prova de que aquele alvo será executado em runtime.

### 7.5 UX e acessibilidade

Priorizar leitura, contraste, rótulos explícitos, estados de loading/empty/error/partial e navegação utilizável. Cor não deve ser o único sinal de proveniência. Preferências de fonte/tamanho devem permanecer opcionais e locais, salvo decisão posterior em contrário.

---

## 8. Pipeline de análise

### 8.1 Validar origem e fixar commit

- Aceitar somente a origem canônica `https://github.com/{owner}/{repo}` no MVP.
- Rejeitar host alternativo, credenciais na URL, parâmetros inesperados e formato ambíguo.
- Resolver a referência solicitada para SHA antes de obter arquivos.
- Usar endpoints de host fixo; não tratar a URL do usuário nem links encontrados nos arquivos como destino HTTP arbitrário.
- Tratar rate limit, repositório inexistente/indisponível e falhas de rede com mensagens seguras.

### 8.2 Inventário e limites

- Recuperar a árvore do commit ou arquivo compactado sob o limite configurado.
- Filtrar conteúdo binário, artefatos gerados, dependências vendorizadas, caches, arquivos excessivos e outros itens não elegíveis.
- Aplicar limites configuráveis de arquivo, quantidade e conteúdo total.
- Registrar avisos, omissões e cobertura parcial.
- Nunca presumir que um arquivo excluído está seguro ou foi revisado.

### 8.3 Parsing estático

- Parser atual: `ast` da biblioteca padrão Python.
- Extrair estrutura e localizações onde suportado.
- Não executar arquivos para descobrir definições.
- Tolerar falhas parciais sem interromper todo o repositório, salvo erro global relevante.
- Registrar claramente os casos não interpretados.

Tree-sitter e parsers adicionais são opções futuras, não devem ser descritos como parte funcional da v0.7.0.

### 8.4 Construção e persistência do grafo

- Criar identificadores estáveis dentro do snapshot.
- Manter origem de arquivo/caminho e linhas quando disponíveis.
- Separar relações determinísticas de inferidas.
- Impedir relações que cruzem snapshots incompatíveis.
- Persistir resultados para navegação, consulta e relatório.

### 8.5 Indexação e recuperação para perguntas

A v0.7.0 usa recuperação lexical e estrutural. A pergunta é classificada por intenção e termos em português podem ser expandidos para identificadores reconhecíveis em código. A seleção prioriza fontes apropriadas à intenção: definições e código, testes/exemplos, documentação relevante e relações do grafo.

Limitações: a seleção é heurística; sinônimos, nomes dinâmicos, documentação divergente e arquivos não ingeridos podem causar omissões. Não há embeddings, ranking semântico aprendido nem garantia de exaustividade. Se as evidências recuperadas não forem suficientes, o sistema deve preferir uma resposta inconclusiva e informar a lacuna.

**Próxima evolução da recuperação:** construir primeiro um corpus de avaliação representativo; medir relevância dos arquivos recuperados e correção das respostas; só então escolher entre melhorar heurísticas, buscar arquivos adicionais dentro do mesmo commit ou testar embeddings/reranking.

### 8.6 Skills e achados

- Executar apenas skills habilitadas e com entrada disponível.
- Priorizar regras determinísticas para verificações que não dependam de interpretação probabilística.
- Guardar categoria, severidade, estado, evidências, recomendação e limitações quando disponíveis.
- Tratar resultados como candidatos à revisão humana.
- Não registrar a ausência de achados como prova de ausência de vulnerabilidades.

### 8.7 Relatórios

Gerar Markdown a partir de dados persistidos da análise. O relatório deve incluir identidade do repositório/commit, escopo, inventário/cobertura, visão da estrutura, achados, referências, limitações e versão/metodologia. A exportação não deve inventar seções ou conclusões para lacunas sem dados.

---

## 9. Skills especializadas

### 9.1 Catálogo ativo atual

| ID | Modo | Objetivo | Limite principal |
|---|---|---|---|
| `appsec.secrets-detection` v0.2.0 | Determinístico | Identificar padrões conhecidos de possíveis credenciais e redigir o valor reconhecido | Falsos positivos e falsos negativos; não valida credencial |
| `engineering.test-inventory` v0.1.0 | Determinístico | Reconhecer arquivos de teste Python por convenções simples | Não executa testes nem mede cobertura |

Ambas operam sem efeitos colaterais externos e são de nível de autoridade A (leitura/diagnóstico).

### 9.2 Categorias futuras

Adicionar uma habilidade somente quando houver objetivo, critério de saída, exemplos, testes e forma de avaliar falsos positivos.

**AppSec:** autorização, validação de entrada, sinks perigosos e fluxos de dados, configuração insegura e revisão de logs/erros.  
**Dependências/DevSecOps:** inventário de versões, advisories com fonte/data, workflows e permissões, proteção de segredos e pipeline.  
**Qualidade/confiabilidade:** tratamento de erro, lacunas de testes, contratos, casos de borda e riscos de regressão.  
**Arquitetura/desempenho:** dependências circulares, acoplamento, possíveis consultas ineficientes e trabalho repetido, distinguindo sempre risco estático de gargalo medido.

### 9.3 Contrato mínimo de uma skill

Cada skill deve declarar:

- ID e versão estáveis;
- categoria e objetivo;
- modo determinístico ou assistido por IA;
- linguagem/framework e pré-condições;
- entradas, saídas e esquema de achado;
- fontes e procedimento de avaliação;
- ferramentas autorizadas e efeitos colaterais;
- limitações, casos positivos/negativos/ambíguos e testes;
- orçamento de tempo/recursos, quando aplicável.

### 9.4 Severidade e estado

Manter severidade separada de confiança. Achados não confirmados devem permanecer como `needs_review` até revisão. `confirmed` deve significar que um revisor aceitou a evidência disponível; não deve sugerir que houve exploração automática. `fixed_in_revision` registra uma decisão de revisão, não prova por si só que o Yggdrasil verificou a correção.

---

## 10. IA, RAG e privacidade

### 10.1 Contrato da IA

O adaptador de IA é infraestrutura substituível. Chamadas devem ter timeout, limites de contexto/saída, tratamento de falhas transitórias e validação da resposta. A falha do provedor não deve apagar o inventário nem o grafo já construído.

### 10.2 Conteúdo enviado a um provedor externo

Quando a IA é utilizada:

- a pergunta do usuário e os trechos selecionados para contexto são enviados ao endpoint configurado;
- os trechos são redigidos conforme os padrões de segredo implementados antes da persistência/uso previsto pelo pipeline;
- o repositório inteiro não é enviado como um único payload;
- a interface exige confirmação explícita antes do envio;
- a chave de API permanece no backend;
- a conversa não é persistida como histórico nesta versão.

**Importante:** redação por padrões reduz risco, mas não garante anonimização nem detecta todos os tipos de credenciais ou dados confidenciais. Não enviar código cujo compartilhamento com o provedor não esteja autorizado. Para uso com código sensível, é necessário avaliar um provedor local confiável ou não habilitar IA.

### 10.3 Prompt injection e conteúdo não confiável

Código, README, comentários, nomes de arquivos e strings podem conter instruções hostis. O modelo deve receber esses conteúdos claramente delimitados como dados. Não deve possuir ferramentas, terminal, acesso de escrita, acesso arbitrário à rede ou permissão para executar texto retornado.

Essas medidas reduzem a superfície de risco, mas não eliminam erros semânticos ou toda forma de prompt injection.

### 10.4 Integridade das citações

O backend aceita apenas IDs de citação que pertençam ao conjunto de evidências recuperadas para a pergunta. A UI deve expor caminho e linhas e incentivar a conferência da fonte. Uma citação tecnicamente válida pode ainda ser insuficiente para sustentar uma conclusão mais ampla; por isso, a precisão semântica precisa de testes próprios.

### 10.5 Busca semântica

Não implementar embeddings/pgvector apenas por popularidade. Primeiro, avaliar um corpus de perguntas com rótulos de arquivos/símbolos esperados. Incorporar busca semântica somente se produzir ganho mensurável, compensar custo/latência e mantiver boa proveniência.

---

## 11. Modelo de dados e persistência

A implementação da v0.7.0 usa entidades SQLAlchemy equivalentes a:

- `Repository` — identidade do repositório;
- `RepositorySnapshot` — referência/commit analisado;
- `AnalysisRun` — estado e metadados da execução;
- `SourceFile` — arquivo, metadados, status e texto redigido quando elegível;
- `GraphNode` — nó do grafo;
- `GraphEdge` — relação do grafo;
- `AnalysisEvent` — evento persistido da execução;
- `Finding` — achado estruturado e seu estado de revisão;
- `ReportExport` — exportação Markdown persistida.

SQLite é o padrão para desenvolvimento local; PostgreSQL é suportado pela configuração da conexão e pelo Compose. Migrations devem evoluir o esquema. A persistência de conteúdo deve manter-se limitada ao necessário e evitar valores reconhecidos como segredos.

### 11.1 Integridade esperada

- Relações de grafo devem pertencer ao mesmo snapshot.
- Chaves estrangeiras e constraints devem preservar a ordem válida de gravação.
- Eventos devem possuir sequência/identidade suficiente para deduplicação e reconstrução razoável do estado.
- Alterações de contrato devem vir acompanhadas de migrations e testes.
- Logs não devem armazenar segredo, conteúdo-fonte completo, chave de API ou corpo sensível do provedor.

### 11.2 Retenção

No MVP local, a base armazena histórico das análises e seus dados derivados. O usuário precisa saber onde fica o banco. Futuras necessidades de retenção, limpeza automática e limites de armazenamento devem ser definidas antes de qualquer serviço hospedado.

---

## 12. Arquitetura e stack atuais

### 12.1 Frontend

- React;
- TypeScript;
- Vite;
- `@xyflow/react` para o canvas;
- `lucide-react` para ícones.

### 12.2 Backend

- Python 3.11+;
- FastAPI e Uvicorn;
- Pydantic;
- SQLAlchemy;
- Alembic;
- Pytest;
- Ruff configurado, ainda pendente de execução de lint na verificação registrada.

### 12.3 Persistência e ingestão

- SQLite por padrão local;
- PostgreSQL via URL SQLAlchemy e Docker Compose;
- cliente de API/árvore GitHub e ingestão por ZIP/fallback seletivo;
- `ast` para estrutura Python;
- SSE para eventos servidor → navegador.

### 12.4 Estrutura real resumida

```text
yggdrasil/
├── apps/
│   └── web/                         # React, TypeScript, Vite, canvas
├── services/
│   └── api/
│       ├── app/
│       │   ├── api/                 # rotas HTTP
│       │   ├── application/         # orquestração e perguntas/RAG
│       │   ├── domain/              # grafo, skills, segredos, relatório
│       │   ├── infrastructure/      # GitHub, arquivo, provedor de IA
│       │   ├── schemas/
│       │   ├── config.py
│       │   ├── db.py
│       │   ├── models.py
│       │   └── main.py
│       ├── alembic/                 # migrations
│       └── tests/
├── skills/
│   ├── appsec/secrets-detection/
│   └── engineering/repository-inventory/
├── docs/
│   ├── adr/
│   ├── PROGRESS.md
│   └── SECURITY.md
├── scripts/
├── .env.example
├── docker-compose.yml
└── README.md
```

A árvore acima descreve os módulos existentes na versão de referência. Não criar diretórios vazios para representar funcionalidades futuras.

### 12.5 API relevante atual

Prefixo: `/api/v1`.

| Endpoint | Finalidade |
|---|---|
| `GET /health` | Status da API/banco e versão |
| `GET /skills` | Catálogo de skills ativo |
| `POST /analyses` | Registrar e iniciar análise, respondendo `202` |
| `GET /analyses` | Listar análises recentes |
| `GET /analyses/{id}` | Estado, commit, contadores e avisos |
| `GET /analyses/{id}/events` | Stream SSE e replay de eventos |
| `GET /analyses/{id}/graph` | Consultar nós/arestas e aplicar busca/filtros |
| `GET /analyses/{id}/nodes/{node_id}` | Detalhes do nó e evidência redigida |
| `GET /analyses/{id}/findings` | Listar achados com filtros suportados |
| `PATCH /analyses/{id}/findings/{finding_id}/status` | Registrar revisão humana de achado |
| `POST /analyses/{id}/questions` | Pergunta assistida por IA com evidências recuperadas |
| `GET /analyses/{id}/export/markdown` | Exportar relatório Markdown |
| `POST /analyses/{id}/exports/markdown` | Criar exportação persistida |
| `GET /exports/{export_id}` | Baixar exportação criada |

O OpenAPI é disponibilizado pelo FastAPI em `/docs`. Contratos devem ser confirmados no código e nos testes antes de alterações.

### 12.6 Tarefas longas e eventos

O pipeline atual usa execução em background no mesmo processo da API e eventos persistidos/SSE. Isso atende ao estágio local, mas não garante durabilidade após reinício do processo. Um worker externo só deve ser introduzido quando recuperação pós-crash, volume ou paralelismo exigirem essa complexidade; essa mudança precisará de desenho e testes específicos.

---

## 13. Segurança do próprio Yggdrasil

### 13.1 Ativos e ameaças

O Yggdrasil recebe conteúdo de terceiros, processa arquivos e, se habilitada, envia trechos para um provedor de IA. Riscos relevantes:

- URL maliciosa/SSRF ou redirecionamento indevido;
- traversal, symlink, arquivo compactado abusivo ou consumo excessivo;
- segredo no repositório ou log;
- prompt injection em conteúdo externo;
- erro/falso positivo produzido pela IA;
- exposição de código a provedor externo;
- abuso das rotas locais por outro processo/usuário da rede;
- corrupção de estado ou perda de eventos durante falhas do processo.

### 13.2 Controles presentes

- URL de ingestão limitada ao host e formato esperado do GitHub.
- Hosts de download fixos e redirecionamentos recusados nas operações relevantes.
- Referência resolvida para commit e limites aplicados a arquivos e conteúdo.
- Código do alvo nunca executado nem importado.
- Redação de padrões de segredos reconhecidos antes de persistir conteúdo elegível.
- CORS configurável.
- IA desativada por padrão e chave mantida no backend.
- Confirmação explícita antes de enviar trechos ao provedor.
- Saídas/citações validadas no servidor; erros externos apresentados sem corpo sensível.
- Logs diagnósticos sem SQL/parâmetros ou conteúdo-fonte sensível, conforme o caminho de erro implementado.

### 13.3 Limites residuais

- Não há autenticação nem autorização por usuário. Manter as portas em loopback e não expor o serviço na internet.
- Redação por padrões é incompleta; credenciais novas, fragmentadas ou codificadas podem escapar.
- Prompt injection não é eliminada apenas por instruções; modelo pode interpretar contexto errado.
- A ingestão pode ficar parcial por limites ou rate limit.
- A API em background não é um worker durável.
- Análise estática não prova explorabilidade nem ausência de vulnerabilidades.
- Usar um provedor externo implica transmissão dos trechos selecionados; a confirmação do usuário não transforma essa transmissão em processamento local.

### 13.4 Regras futuras para hospedagem

Antes de oferecer uso em rede ou hospedagem, será obrigatório tratar autenticação, autorização, isolamento de dados, rate limits, quotas, limites de concorrência, proteção contra CSRF/CORS de acordo com o modelo, segurança de segredo, política de retenção, monitoramento, atualizações de dependências e revisão de ameaça. Não considerar abrir a porta pública um passo menor de deploy.

---

## 14. Testes e avaliação

### 14.1 Testes automatizados atuais

A suíte do backend cobre áreas como ingestão/segurança GitHub, arquivos compactados, grafo, segredos, provedor de IA, perguntas/RAG e integração da API. Os serviços externos são simulados nos testes, evitando chamadas reais e custos da suíte.

O teste de layout do frontend usa nós sintéticos e verifica determinismo/colisões. Não substitui o build e a validação visual da aplicação completa.

### 14.2 Portão de qualidade antes de publicar uma versão

Executar em ambiente limpo, registrando comandos e resultados:

- testes do backend;
- `python -m compileall` para a API;
- Ruff/lint do backend;
- instalação reproduzível do frontend com lockfile;
- type-check e build do frontend;
- ESLint;
- teste de layout do grafo;
- execução local da aplicação e verificação de `/api/v1/health`;
- smoke test do fluxo real de ingestão, pergunta opcional e exportação;
- verificação do pacote para excluir `.env`, banco local, logs, caches e chaves.

### 14.3 Corpus para avaliar o RAG

Criar perguntas reais em idiomas/termos diferentes, cobrindo perguntas sobre implementação, exemplos, testes, dependências, arquitetura, segurança e perguntas sem evidência suficiente. Para cada caso, anotar:

- repositório e commit de referência;
- pergunta;
- arquivos/símbolos/testes esperados;
- fatos que podem ser confirmados;
- limites e resposta correta quando inconclusiva;
- se uma citação sustenta a frase correspondente.

Medir ao menos: pertinência de arquivos recuperados, cobertura das evidências esperadas, corretude das afirmações, citações inválidas, falsas certezas, abstinências apropriadas, latência e uso aproximado de tokens/custo quando fornecido pelo modelo.

### 14.4 Casos obrigatórios

- implementação e teste relacionados a uma classe/método;
- perguntas formuladas em português para código com identificadores em inglês;
- biblioteca mencionada no enunciado sem desviar uma pergunta de implementação para dependências;
- README inconsistente com código;
- conteúdo em outro idioma;
- falta do arquivo esperado ou arquivo ignorado por política;
- pergunta ambígua e pergunta sem evidência;
- tentativa de prompt injection em arquivo do repositório;
- possíveis segredos e falsos positivos;
- provedor indisponível/timeout/resposta JSON inválida;
- ingestão parcial ou rate limit.

### 14.5 Critérios de aceite evolutivos

- [ ] URL e ref validadas; análise vinculada a commit.
- [ ] Ingestão parcial é identificada e explicada.
- [ ] Análise não executa código do alvo.
- [ ] Grafo distingue relações determinísticas e inferidas.
- [ ] Busca/filtros não confundem limite visual com cobertura de análise.
- [ ] Achados são estruturados e revisáveis por humano.
- [ ] Respostas de IA usam apenas evidências recuperadas e expõem caminho/linhas.
- [ ] O sistema informa quando não há base suficiente.
- [ ] O relatório corresponde ao snapshot e contém escopo/limitações.
- [ ] Segredos reconhecidos não aparecem em persistência/relatório.
- [ ] Setup limpo, testes, lint e build são reproduzíveis.
- [ ] README permite executar a aplicação sem depender de conhecimento privado do desenvolvedor.

---

## 15. Roadmap revisado

As versões abaixo são etapas planejadas, não uma previsão de datas. A versão do aplicativo pode conter mais de uma alteração interna; o plano só deve marcar uma etapa como concluída quando seus critérios estiverem demonstrados.

### Fase A — Preparação para publicação do código (atual)

**Objetivo:** tornar o repositório reproduzível e compreensível para outra pessoa.

- [ ] Atualizar o Plano Mestre para refletir a v0.7.0.
- [ ] Atualizar o README com a verdade funcional, setup, screenshots futuras e limitações.
- [ ] Adicionar descrição e identidade visual depois de validar o conteúdo do README.
- [ ] Adicionar o código ao repositório GitHub sem `.env`, banco, logs ou caches.
- [ ] Confirmar que `.gitignore` e `.env.example` estão corretos.
- [ ] Gerar/validar lockfile do frontend e executar build/type-check/lint.
- [ ] Executar Ruff e repetir a suíte do backend no ambiente limpo.
- [ ] Registrar resultados reais em `docs/PROGRESS.md`.

**Saída verificável:** clone limpo com instruções reproduzíveis e limites documentados.

### Fase B — Avaliação do RAG v0.7.x

- [ ] Montar corpus inicial de perguntas com arquivos/símbolos/testes esperados.
- [ ] Repetir o caso Borax/datas lunares e verificar manualmente cada citação contra o commit.
- [ ] Incluir perguntas sobre implementação, exemplos, testes, dependências e casos sem evidência.
- [ ] Medir recuperação, qualidade das citações, abstinência, latência e custo observável.
- [ ] Corrigir falsos caminhos de recuperação com regressões automatizadas.
- [ ] Garantir que perguntas, evidências e logs não exponham valores sensíveis.

**Saída verificável:** um relatório de avaliação reproduzível que mostre acertos, falhas e limites da recuperação.

### Fase C — Cobertura e resiliência da análise

- [ ] Revisar inventário parcial e tratamento de arquivos ignorados.
- [ ] Criar fixtures de repositórios pequenos e casos de limite.
- [ ] Melhorar diagnósticos de parsing parcial e links permanentes para evidências.
- [ ] Validar reconexão/replay de eventos e transições terminais.
- [ ] Testar falhas do processo e documentar explicitamente a limitação da execução em background atual.

**Saída verificável:** cobertura e estados entendíveis, sem prometer análise completa onde ela não ocorreu.

### Fase D — Skills AppSec e qualidade graduais

- [ ] Definir primeiro um problema específico e avaliável por skill.
- [ ] Adicionar casos positivos, negativos e ambíguos antes de promover uma skill.
- [ ] Incluir revisão de autorização/controle de acesso apenas quando houver suporte de fluxo/contexto suficiente.
- [ ] Avaliar fonte e data para qualquer análise de advisories de dependências.
- [ ] Persistir evidências e limitações; manter `needs_review` até avaliação humana.

**Saída verificável:** poucas skills com avaliação e rastreabilidade, em vez de um catálogo grande de prompts não testados.

### Fase E — Melhorias de recuperação

- [ ] Otimizar recuperação lexical/estrutural com base nos erros do corpus.
- [ ] Avaliar recuperação dinâmica de arquivos do mesmo commit se arquivos relevantes foram omitidos por limites, respeitando orçamento e proveniência.
- [ ] Comparar heurísticas com embeddings/reranking em um benchmark idêntico.
- [ ] Só adicionar PostgreSQL/pgvector ou infraestrutura de busca semântica se o ganho for medido e justificar custo/complexidade.

**Saída verificável:** melhoria mensurada, não somente uma resposta isolada aparentemente melhor.

### Fase F — Segunda linguagem e comparação de snapshots

- [ ] Escolher a segunda linguagem por demanda e capacidade de avaliação.
- [ ] Desenvolver parser e corpus de fixtures antes de anunciar suporte.
- [ ] Comparar commits/snapshots para mudanças de arquivos, nós, relações e achados.
- [ ] Manter linguagem e nível de proveniência explícitos.

**Saída verificável:** segunda linguagem com limites e testes próprios, ou comparação útil de commits — priorizar uma capacidade por vez.

### Fase G — Worker durável / uso compartilhado (projeto de arquitetura futuro)

Somente iniciar quando houver necessidade real de tarefas duráveis ou vários usuários. Exigirá desenho específico para autenticação, isolamento, filas/worker, quotas, retenção, segurança de deploy e operação. Não é requisito para publicar o código atual como projeto open source.

### Critérios para considerar v1.0

- Fluxo dentro do escopo suportado reproduzível de ambiente limpo.
- Cobertura e limites explicados de forma clara.
- Testes, lint e build completos automatizados.
- Corpus de avaliação do RAG executado e limitações publicadas.
- Skills têm avaliação/documentação adequadas.
- Relatório ligado ao commit e sem exposição de segredos reconhecidos.
- Segurança de ingestão, armazenamento e uso opcional de IA revisada.
- Outra pessoa consegue instalar, executar, testar e compreender as limitações.

---

## 16. Decisões de arquitetura vigentes

- **Monólito modular:** simples de executar localmente e suficiente para o estágio atual.
- **Somente leitura para repositório-alvo:** não executar código ou scripts externos.
- **GitHub público e commit fixo:** restringe a origem e estabiliza a referência da análise.
- **Parsing Python por `ast`:** ferramenta disponível na linguagem; limita o alcance à análise Python suportada.
- **SQLite por padrão, PostgreSQL opcional:** reduz barreira de entrada e mantém uma via de evolução.
- **SSE para progresso:** fluxo majoritariamente unidirecional servidor → interface.
- **IA com adaptador:** provedor e modelo configuráveis; IA opcional.
- **Recuperação lexical/estrutural inicial:** embeddings ficam condicionados a evidência de benefício.
- **Relatórios a partir de dados persistidos:** resultado não deve depender de uma conversa livre.
- **Evidência/citações validadas no backend:** o modelo não pode introduzir IDs arbitrários como fontes válidas.
- **Sem autenticação no MVP:** uso local apenas; não expor portas públicas.

ADRs existentes devem ser tratados como histórico de decisões e lidos antes de alterar os comportamentos correspondentes. Uma mudança de decisão precisa registrar contexto, alternativas, consequências e plano de migração quando aplicável.

---

## 17. Definition of Done

Uma fatia de desenvolvimento só está pronta quando os critérios aplicáveis forem cumpridos:

- [ ] O comportamento está ligado a uma necessidade/critério de aceite.
- [ ] O caminho feliz foi exercitado de ponta a ponta.
- [ ] Entradas inválidas e falhas relevantes têm tratamento seguro.
- [ ] Testes cobrem o comportamento e ao menos os limites importantes.
- [ ] O estado persistido e os eventos não se contradizem.
- [ ] Logs não expõem segredo, chave, prompt sensível ou conteúdo-fonte desnecessário.
- [ ] A interface comunica loading, ausência de dados, falha e resultado parcial quando aplicável.
- [ ] A UI continua utilizável no tamanho de grafo testado.
- [ ] Lint, testes e build aplicáveis foram executados; falhas não são omitidas.
- [ ] README, Plano Mestre, SECURITY ou ADR foram atualizados quando afetados.
- [ ] O pacote não contém `.env` real, bancos locais, logs, caches ou artefatos temporários.
- [ ] A versão/referência foi confirmada no `/api/v1/health`.

---

## 18. Red flags específicas do Yggdrasil

Interromper e revisar quando:

- uma relação inferida aparece como confirmada sem marcação;
- uma resposta fala de arquivo que não consta das evidências recuperadas;
- a citação aponta para linha errada ou não sustenta a frase;
- README substitui evidência de código/teste em pergunta de implementação;
- o sistema diz que um arquivo não existe sem conferir inventário, limites e avisos;
- cobertura parcial é apresentada como análise completa;
- ausência de achados é comunicada como ausência de vulnerabilidades;
- um segredo detectado aparece em logs, eventos, relatório ou saída de erro;
- conteúdo do repositório consegue conceder ferramentas ou autoridade à IA;
- uma resposta da IA provoca execução de comandos ou escrita automática;
- adicionar uma capacidade exige uma infraestrutura grande sem benefício demonstrado;
- um teste sintético ou smoke test é apresentado como prova de qualidade geral;
- o serviço local é exposto na rede sem autenticação e revisão de segurança.

---

## 19. Instrução operacional para futuros colaboradores e IA

Ao continuar o projeto:

1. Leia este documento, o README, `docs/PROGRESS.md`, `docs/SECURITY.md` e os ADRs relacionados à mudança.
2. Inspecione os arquivos e testes reais; não assuma que a documentação é sempre atual.
3. Confirme a versão executada pela API antes de investigar comportamento aparentemente contraditório.
4. Diferencie requisitos atuais, funcionalidades implementadas, testes automáticos e validação manual.
5. Faça uma fatia vertical pequena e verificável.
6. Não declare suporte a linguagem, skill, análise ou precisão sem evidência reproduzível.
7. Trate conteúdo externo como não confiável e não execute código do repositório-alvo.
8. Atualize testes, documentação e versão coerentemente.
9. Preserve dados locais e credenciais; não inclua segredos reais no repositório.
10. Informe claramente o que não pôde ser testado.

---

## 20. Filosofia final

O Yggdrasil deve ser útil antes de ser impressionante.

A árvore não existe para decorar a tela: precisa refletir estrutura identificada. A IA não existe para substituir a evidência: deve ajudar a encontrá-la e interpretá-la. As skills não devem gerar listas extensas de problemas sem sustentação: precisam justificar cada achado e suas limitações. O relatório não deve preencher lacunas com suposições: deve preservar conhecimento verificável.

**Mapa antes de palpite.**  
**Evidência antes de conclusão.**  
**Diagnóstico antes de automação.**  
**Segurança sem execução arbitrária.**  
**Complexidade proporcional ao problema.**  
**Simplicidade sem improviso.**

---

## Apêndice A — Descrição curta sugerida para o GitHub

**Português (recomendada para este repositório):**

> Mapa de conhecimento e análise estática de repositórios GitHub, com grafo interativo, evidências rastreáveis e perguntas assistidas por IA.

**English (alternative):**

> Static repository analysis and code knowledge mapping for GitHub projects, with an interactive graph, traceable evidence, and AI-assisted Q&A.
