# YGGDRASIL — Plano Mestre de Engenharia

> **Documento:** Plano Mestre / Fonte de Verdade do Projeto  
> **Versão do plano:** 0.5.0
>
> **Atualizado em:** 28/10/2026
>
> **Versão do aplicativo de referência:** 0.7.0
>
> **Status geral:** núcleo funcional validado em clone limpo; entregas de engenharia publicadas em branch de trabalho; desktop experimental escolhido como candidato de release, ainda com bugs e validação final pendente.
> **Idioma principal:** português (pt-BR)  
> **Princípio de engenharia:** simplicidade sem improviso  
> **Nome:** Yggdrasil — a árvore que representa visualmente a rede de relações de um software

---

## 0. Como usar este documento

Este documento é a fonte de verdade do projeto para retomar o desenvolvimento, registrar decisões e distinguir resultados comprovados de intenções. Ele substitui o status desatualizado do plano 0.4.0, mas **não transforma pendências em funcionalidades concluídas**.

Use estes estados:

- **Implementado:** existe código na referência indicada.
- **Testado automaticamente:** o comando foi executado e terminou sem falhas no ambiente descrito.
- **Validado manualmente:** uma pessoa executou o fluxo; isso não equivale a validação exaustiva.
- **Parcial:** o núcleo está implementado, mas há limites, bugs conhecidos ou aceite incompleto.
- **Pendente:** ainda não foi demonstrado ou desenvolvido.

Em caso de conflito, conferir o código e os testes da referência correta. O README explica como utilizar o código distribuído; `docs/PROGRESS.md` deve ser o diário cronológico de progresso; `docs/SECURITY.md` registra controles e limites de segurança; ADRs mantêm o histórico de decisões arquiteturais.

### 0.1 Estado de retomada — 28/10/2026

Esta subseção existe para que outro chat ou colaborador possa continuar sem reconstruir todo o contexto.

| Item | Estado confirmado |
|---|---|
| Repositório | `GabrielJalmeida/yggdrasil` |
| Branch de trabalho | `test/env-file-detection` |
| Commit publicado na branch | `3d07627` — `feat: add desktop packaging and quality evaluation` |
| Push | Aceito pelo GitHub; não foi usado bypass de secret scanning |
| `main` | A entrega **não foi integrada à `main`** durante esta sessão |
| Clone limpo de validação | `C:\Users\Gabriel\Desktop\yggdrasil-clone-test-20261028` |
| Estado do clone ao final | `git status --short --branch` mostrou branch sincronizada e sem alterações locais |
| Plano mestre original | `docs/MASTER-PLAN.md` tinha alterações locais não commitadas e ficou fora do commit publicado |
| Documento atualizado desta sessão | Gerado como artefato separado; ainda precisa ser colocado em `docs/MASTER-PLAN.md` no repositório original após conferência |
| Executável candidato de release | Build de 27/10/2026, por volta de 23:40; selecionado manualmente pelo usuário como a melhor versão disponível |
| Estado do executável candidato | Abre rapidamente e o usuário informou que consegue configurar a API e usar o chatbot melhor que na versão anterior; ainda há bugs visuais/de UX a registrar e revisar |
| Publicação da release | Ainda não foi feita; executável deve ser distribuído separadamente via GitHub Releases, não no commit do código-fonte |

**Importante:** os testes do clone validam o commit `3d07627`; não validam automaticamente cada ZIP de desktop. A versão de 23:03 foi descartada pelo usuário porque o fluxo de chatbot não funcionava como esperado. A versão por volta de 23:40 é a candidata escolhida, mas o ZIP exato, o SHA-256 do pacote final e um smoke test repetido sobre exatamente esse ZIP ainda precisam ser registrados. Uma verificação anterior de um pacote extraído mostrou um erro de sessão não autorizada em uma chamada de IA; a retestagem manual posterior foi melhor, portanto a aceitação end-to-end deve ser repetida no pacote final exato antes de anunciar uma release estável.

### 0.2 Estratégia de execução

O desenvolvimento está organizado em quatro entregas consolidadas. Elas agrupam as antigas Fases A–E e incluem a etapa de produto desktop. Uma entrega pode envolver vários commits, mas só pode ser declarada concluída quando seus critérios de aceite forem demonstrados.

Preservar alterações locais, dados e credenciais. Não usar `git reset --hard`, `git clean -fd`, substituição indiscriminada de pastas ou `git add .` como procedimento padrão. Antes de cada commit, revisar `git status`, `git diff --check` e o conjunto exato do staging. Para pacotes/patches, declarar arquivos afetados e verificar pré-condições.

### 0.3 Próxima sessão — ordem recomendada

1. Aplicar/revisar este plano atualizado em `C:\Users\Gabriel\Desktop\yggdrasil\docs\MASTER-PLAN.md`, sem sobrescrever às cegas o estado local e sem incluir no commit algo que não tenha sido revisado.
2. Conferir `git diff --check`, `git diff -- docs/MASTER-PLAN.md` e `git status --short --branch` no repositório original.
3. Registrar o plano atualizado em um commit separado na branch `test/env-file-detection`, após revisar o diff. O push anterior da entrega de código já foi aceito; não é necessário repetir os passos de build/lint/test do clone sem mudança de código.
4. Decidir se abre/atualiza um Pull Request para integrar a branch em `main`. Não afirmar que `main` está atualizada antes de verificar o merge.
5. Retomar a release do desktop: localizar e identificar o ZIP correspondente ao build das 23:40, calcular SHA-256 desse ZIP, testar o pacote exato, registrar bugs visuais e confirmar o fluxo de IA/persistência. Não reutilizar automaticamente o nome/hash de um ZIP mais antigo das 23:03.
6. Só então publicar GitHub Release com pacote ZIP separado do código, instruções e hash; se bugs relevantes persistirem, marcar como experimental/pré-release ou adiar o anúncio de versão estável.

---

## 1. Resumo executivo

**Yggdrasil** é uma ferramenta local de análise estática e compreensão de repositórios de software. Recebe a URL de um repositório público do GitHub, fixa a análise a um commit, inspeciona arquivos elegíveis sem executar o código-alvo e transforma os resultados em inventário, grafo consultável, achados candidatos e relatório Markdown. Quando configurada e autorizada pelo usuário, a IA responde perguntas com base em evidências recuperadas.

O núcleo da versão 0.7.0 combina:

- ingestão limitada de repositórios públicos do GitHub;
- parsing estático de Python com `ast`;
- grafo persistido de arquivos, símbolos e relações;
- duas skills determinísticas iniciais: detecção de possíveis segredos e inventário de testes;
- API FastAPI e UI React/TypeScript/Vite;
- navegação do grafo com consultas/filtros no servidor e limites de visualização;
- perguntas assistidas por IA com recuperação lexical/estrutural e citações validadas pelo backend;
- harnesses de avaliação para skills determinísticas, recuperação RAG e revisão de qualidade de respostas;
- empacotamento experimental para desktop Windows, com inicializador local, SQLite e armazenamento protegido da chave para o usuário Windows.

O Yggdrasil **não é apenas um chatbot que resume README**. O diferencial pretendido é ajudar a explorar um software desconhecido por meio de relações e evidências vinculadas a um commit, explicitando o que foi extraído, inferido, omitido ou não comprovado.

### Proposta de valor

> Entender um repositório desconhecido por meio de um mapa consultável, fazer perguntas orientadas por evidências e obter um relatório técnico que permita verificar as conclusões.

### Estado honesto do produto

O núcleo publicado na branch `test/env-file-detection` foi testado a partir de um clone limpo. A suíte completa do backend passou; o frontend instalou dependências, passou no lint e no build de produção; o teste de layout passou com 420 nós sem sobreposições. O benchmark de skills passou em 6/6 casos sem chamadas de IA. A avaliação RAG real, sobre o mesmo snapshot de Borax usado na baseline, mostrou melhora nas métricas de recuperação. A validação do corpus de qualidade de respostas foi executada em simulação e não enviou perguntas ao modelo.

O desktop tem um candidato de release escolhido pelo usuário, mas a distribuição ainda é experimental: o usuário reportou alguns bugs na interface, a máquina limpa sem Python/Node/Docker ainda não foi usada para aceite final, e o teste end-to-end deve ser repetido no ZIP exato selecionado. A release ainda não foi publicada, e a branch não foi integrada à `main`.

---

## 2. Identidade, visão e problema

### 2.1 Significado do nome

Yggdrasil faz referência à árvore mitológica que conecta diferentes mundos. No produto, a árvore representa componentes identificáveis do software e suas relações. A metáfora visual ajuda a navegar; não define a verdade técnica do grafo.

O modelo primário é um **grafo de conhecimento do código**. Relações determinísticas extraídas por parser/API e relações inferidas por heurísticas devem permanecer distinguíveis. A IA interpreta evidências disponíveis; não substitui a origem nem transforma uma hipótese em fato confirmado.

### 2.2 Visão

Permitir que uma pessoa investigue um repositório desconhecido, compreenda sua estrutura e encontre evidências relevantes sem depender somente da leitura manual de centenas de arquivos.

### 2.3 Problema

Entender uma base de código exige localizar pontos de entrada, seguir imports e chamadas, reconhecer regras de negócio, correlacionar implementação e testes e conferir configurações/dependências. A documentação pode estar ausente ou desatualizada. A análise assistida deve reduzir o esforço inicial sem prometer compreensão perfeita.

### 2.4 Perguntas que queremos ajudar a responder

- Como o repositório está organizado?
- Quais arquivos, módulos, classes e funções foram identificados?
- Onde estão definidas certas regras ou interfaces?
- Quais testes parecem relacionados a uma funcionalidade?
- Quais relações foram extraídas diretamente e quais são inferências?
- Quais possíveis segredos aparecem em arquivos elegíveis?
- Que evidência sustenta uma resposta ou recomendação?
- Quais arquivos ficaram fora da análise e por quê?
- O que ainda precisa ser verificado manualmente?

### 2.5 Público inicial

Desenvolvedores que precisam compreender bases existentes, estudantes que aprendem lendo código real, mantenedores, revisores técnicos e profissionais que fazem triagem estática inicial de AppSec. O sistema apoia o trabalho; não substitui revisão humana, testes, scanners especializados ou análise dinâmica.

---

## 3. Princípios obrigatórios

### 3.1 Evidência antes de conclusão

README, comentários e documentação são fontes úteis, mas não provam que a implementação atual se comporte como descrito. Respostas devem preferir código, testes, configuração e relações efetivamente recuperadas, citando caminho e linhas quando disponíveis.

### 3.2 Fato, inferência, hipótese e recomendação não são sinônimos

- **Determinístico/extraído:** produzido por parser, API ou regra reprodutível.
- **Inferido:** sugerido com base em correspondências/contexto, sem prova completa de execução.
- **Hipótese:** possibilidade que ainda exige validação.
- **Recomendação:** ação sugerida; não comprova que exista um defeito.

Não atribuir confiança numérica artificial sem calibração. Uma resposta isolada não valida a qualidade do modelo. Priorizar recuperação, evidências, testes determinísticos, citações e abstinência em vez de depender de um modelo perfeito.

### 3.3 Segurança por padrão

O analisador não executa, importa, compila, instala nem testa o código do repositório-alvo. Código externo é conteúdo não confiável. URLs, arquivos, caminhos, conteúdo compactado e respostas de IA permanecem sob limites explícitos.

### 3.4 Arquitetura proporcional

Manter o monólito modular enquanto atender ao uso atual. Não adicionar filas distribuídas, microsserviços, vetor store, cluster de agentes ou infraestrutura comercial por antecipação.

### 3.5 Fatias verticais verificáveis

Priorizar fluxos completos pequenos em vez de acumular telas/camadas incompletas. Declarar uma funcionalidade pronta somente quando o comportamento relevante foi exercitado e suas limitações documentadas.

### 3.6 Não confundir visibilidade com cobertura

Um nó fora da visão inicial pode continuar presente no grafo persistido. Um arquivo inventariado pode não ter conteúdo lido ou sintaxe analisada. A UI precisa separar cobertura de ingestão, parsing e visualização.

### 3.7 A IA não possui autoridade operacional

A IA não recebe terminal, filesystem, ferramentas livres ou permissão de escrita no repositório. Conteúdo encontrado no README, comentários ou código é dado não confiável e não substitui as instruções do sistema.

### 3.8 Não otimizar métricas fora do contexto

Uma melhoria em um corpus pequeno significa melhoria naquele corpus e snapshot, não uma garantia universal. Toda métrica deve vir acompanhada de escopo, casos pontuáveis, versão do corpus, commit analisado e limitações.

---

## 4. Estado real da versão 0.7.0

### 4.1 Implementado na referência publicada

#### Ingestão e inventário

- Aceita URL canônica de repositório público do GitHub.
- Valida a origem e resolve a referência solicitada para um commit identificável.
- Tenta ingestão por arquivo compactado sob limites; quando necessário, usa árvore do commit e busca seletiva de arquivos elegíveis.
- Aplica limites para tamanho compactado, número de entradas, tamanho individual e orçamento agregado de texto.
- Mantém avisos e razões para itens ignorados ou falhas de leitura.
- Não segue links arbitrários descobertos no conteúdo do repositório.

#### Parsing e grafo

- Usa a biblioteca padrão `ast` para parsing estático de Python.
- Extrai módulos, classes, funções/métodos, imports internos e alguns decorators que aparentam declarar endpoints.
- Distingue relações determinísticas de inferidas, como chamadas possíveis por correspondência local.
- Persiste nós e arestas relacionados ao snapshot analisado.
- Suporta inspeção de nós e consultas por tipo/nome/caminho.
- Expõe contadores de cobertura da ingestão e do parsing Python.
- Adiciona paginação e filtros do grafo no servidor, evitando depender da transferência do grafo inteiro para a UI.
- A visualização pode destacar caminhos a partir de eventos observáveis da análise/evidência. Isso é um traço de comportamento observável, **não** acesso a raciocínio privado do modelo.
- A visão geral sintetiza o grafo; o layout e os filtros têm limites explícitos para preservar legibilidade.

#### Skills iniciais

- `appsec.secrets-detection`: deteção por padrões de possíveis segredos, com redação dos padrões reconhecidos antes da persistência/uso previsto pelo pipeline.
- `engineering.test-inventory`: inventário simples de arquivos de teste Python.

As skills são determinísticas e limitadas. O inventário não executa testes nem mede cobertura. A deteção não encontra todos os formatos e não valida credenciais.

#### Perguntas assistidas por IA

- Endpoint de perguntas para análise concluída.
- A recuperação classifica a intenção, expande termos e prioriza fontes de código, testes/exemplos, documentação e relações do grafo conforme a pergunta.
- A recuperação é lexical e estrutural, com limites de evidências e contexto; não usa embeddings nem reranking semântico aprendido.
- O backend valida que as referências retornadas pelo modelo pertençam ao conjunto de evidências recuperadas. Isso reduz citações inventadas, mas não garante que toda conclusão seja semanticamente correta.
- O adaptador pode usar endpoints compatíveis com OpenAI Chat Completions e caminho nativo Gemini implementado no projeto.
- IA opcional e desabilitada por padrão.
- A interface pede confirmação antes de enviar a pergunta e trechos de evidência redigidos ao provedor.
- A conversa não é um histórico persistido nesta versão.

#### Avaliação de qualidade

- `services/api/scripts/evaluate_skills.py` executa o corpus determinístico de skills sem provedor.
- `services/api/scripts/evaluate_rag.py` mede recuperação lexical/estrutural sobre uma análise persistida e um corpus rotulado, sem chamar IA.
- `services/api/scripts/evaluate_answers.py` suporta simulação sem provedor e modo explícito de chamadas reais via `--run-provider`. A validação realizada nesta sessão foi apenas simulação.
- Os corpora de avaliação e o protocolo de revisão humana estão versionados em `services/api/evaluation/corpora/` e `docs/evaluations/`.
- A avaliação não prova qualidade universal; a resposta semântica ainda exige revisão humana.

#### Persistência, eventos e relatório

- SQLAlchemy e migrations Alembic.
- SQLite é o padrão local; PostgreSQL pode ser configurado.
- Persistência de repositórios, snapshots, execuções, arquivos, nós, arestas, eventos, achados e exportações.
- Execuções de análise em background no processo da API.
- Eventos persistidos e stream SSE para acompanhar progresso/replay recente.
- Exportação do relatório Markdown a partir de dados persistidos.
- Revisão humana persistida de achados, incluindo confirmação, falso positivo, risco aceito e estados relacionados.

#### Interface web

- React, TypeScript, Vite, `@xyflow/react` e `lucide-react`.
- Canvas, pesquisa/filtros, inspetor contextual, painéis de avisos/achados, perguntas e exportação.
- Lockfile do npm versionado (`apps/web/package-lock.json`) e declaração de tipos Vite.
- A visão geral é resumida; pesquisa/filtros do servidor permitem alcançar itens fora da primeira janela, quando presentes na análise/indexação.

#### Desktop Windows experimental

- Inicializador empacotado via PyInstaller e scripts para gerar/testar a distribuição Windows.
- SQLite persistente em diretório de dados do usuário, fora da pasta do programa.
- Configurações de IA separadas da chave; chave protegida pelo Windows DPAPI para o usuário atual.
- Serviço local configurado para loopback; interface aberta no navegador padrão.
- Scripts de build e smoke test para o pacote.
- A distribuição é planejada como ZIP separado do repositório de código; o ZIP não foi adicionado ao commit.

### 4.2 Testes e validações executados após publicação

**Referência dos testes:** clone limpo da branch `test/env-file-detection`, commit `3d07627`, em `C:\Users\Gabriel\Desktop\yggdrasil-clone-test-20261028`. Após as verificações, `git status --short --branch` mostrou branch sincronizada e sem alterações locais. Os resultados abaixo não são provas de uma máquina Windows completamente limpa para a distribuição desktop.

| Verificação | Resultado observado | Interpretação |
|---|---|---|
| Clone Git | `3d07627` presente; branch acompanha `origin/test/env-file-detection` | O código testado corresponde ao commit publicado na branch de trabalho |
| Migrações Alembic | Migradas para schema inicial e `report exports` | Banco SQLite do clone preparado com sucesso |
| Health API | `status=ok`, `database=ok`, versão `0.7.0`, `ai_enabled=False`, provider `disabled` | API e banco local responderam; IA permaneceu desativada |
| Backend `pytest -q` | Suíte completa terminou em 100%, sem falhas de coleta/teste | A saída do pytest em modo quiet não foi usada para afirmar um total numérico exato nesta sessão |
| Aviso backend | `StarletteDeprecationWarning`: uso de `httpx` com `starlette.testclient` depreciado | Não bloqueou a suíte; avaliar correção em manutenção futura |
| `npm ci` | 196 pacotes instalados; auditoria reportou 0 vulnerabilidades | Instalação frontend reproduzível no clone |
| Avisos npm | ESLint `9.39.5` sinalizado como fora de suporte; script de instalação do `esbuild@0.28.2` bloqueado pela configuração de allowScripts | Apesar dos avisos, lint e build foram executados com sucesso; não aprovar scripts de instalação sem revisão deliberada |
| ESLint frontend | `npm.cmd run lint` terminou sem erros | Passou |
| Build frontend | `npm.cmd run build`, `tsc -b` e Vite passaram; Vite `7.3.7`, 1743 módulos transformados | Build de produção gerado sem erros |
| Layout do grafo | `Graph layout OK: 420 nodes, no overlaps; overview=180; filtered modules=20` | Teste de layout sintético passou |
| Benchmark skills | 6/6 casos, `quality_score=1.0`, `provider_calls=0` | Todos os contratos determinísticos incluídos no corpus passaram; não é prova de segurança absoluta |
| Avaliação RAG | 6 de 7 casos pontuáveis no snapshot esperado; sem anotações inválidas/avisos; `provider_calls=0` | Métricas de recuperação melhoraram no corpus específico; um caso de insuficiência de evidência não é pontuado para recall |
| Avaliação de respostas | `evaluate_answers.py --latest` em simulação; 4 perguntas declaradas; análise e SHA compatíveis; nenhuma pergunta enviada ao provedor | Validação do corpus/snapshot passou, não foi avaliação de geração da IA |
| Desktop | Usuário testou o build das ~23:40, considerou-o melhor que o build ~23:03 e disse que abre rapidamente, permite configurar a API e funciona melhor com chatbot | Validação manual positiva para o candidato, mas o usuário relatou bugs; aceite final do ZIP exato e máquina limpa ainda pendentes |

#### Métricas RAG observadas em 28/10/2026

- Corpus: `borax-lunar-rag` v`0.1.0`.
- Repositório: `kinegratii/borax`.
- Referência solicitada: `master`.
- Commit analisado: `01cbbbf7ce33ee22d23c462c525d07e1320e67a7`.
- ID da análise local no banco do clone: `a6a28262b8584071bd0a6095224faa5e`.
- Casos totais: 7; casos pontuáveis: 6; anotações inválidas: 0; avisos: 0; chamadas de provedor: 0.

| Métrica | Baseline anterior | Atual (28/10) | Diferença aproximada |
|---|---:|---:|---:|
| Intent accuracy | 1.0000 | 1.0000 | sem mudança |
| MRR | 0.7208 | 0.7833 | +0.0625 |
| Hit@1 | 0.6667 | 0.6667 | sem mudança |
| Hit@3 | 0.6667 | 0.8333 | +0.1666 |
| Hit@5 | 0.8333 | 1.0000 | +0.1667 |
| Recall@1 | 0.5000 | 0.5000 | sem mudança |
| Recall@3 | 0.5833 | 0.7500 | +0.1667 |
| Recall@5 | 0.7500 | 1.0000 | +0.2500 |

A comparação é válida para este corpus e o mesmo SHA analisado. Hit@5 e Recall@5 em 1.0 significam que todos os caminhos esperados dos seis casos pontuáveis foram encontrados até k=5, conforme os rótulos humanos. Isso **não** significa que todo arquivo relevante do projeto seja recuperado, que os rótulos sejam exaustivos ou que as respostas geradas estejam semanticamente corretas.

Falha residual identificada no caso sobre metadados de empacotamento: `setup.py` aparece em quinta posição. A pergunta sobre testes é correta em intenção, mas `tests/test_lunardate.py` aparece em segundo lugar, não primeiro. A melhoria elevou os indicadores globais daquele corpus, mas não elimina todas as oportunidades de ranking.

#### Benchmark determinístico das skills

Corpus `yggdrasil-skill-quality` v`0.1.0`, 6 casos aprovados de 6, score `1.0`, zero chamadas ao provedor. Os casos cobrem segredo literal, referência a variável de ambiente, placeholder, valor ambíguo semelhante a placeholder, reconhecimento convencional de arquivo de teste e caminho de teste não convencional. Casos ambíguos são encaminhados para revisão humana. Esse score avalia contratos determinísticos pequenos; não demonstra cobertura abrangente de AppSec nem confirma que o alvo esteja seguro.

#### Validação do corpus de qualidade de respostas

O comando `scripts/evaluate_answers.py --latest` foi executado sem `--run-provider`. A saída explicitou `SIMULAÇÃO`, quatro perguntas que seriam executadas, análise `a6a28262b8584071bd0a6095224faa5e` e o SHA esperado. Nenhuma pergunta foi enviada à IA. Logo, esse teste confirma a validade da seleção de análise/snapshot, não qualidade de respostas ao vivo, latência ou custo.

### 4.3 Histórico operacional relevante desta sessão

- As alterações de entrega foram organizadas e commitadas em `a5e75eb`, mas o primeiro push foi bloqueado por GitHub Push Protection porque um teste continha uma sequência literal que correspondia ao formato de token Slack.
- A fixture em `services/api/tests/test_secrets.py` foi alterada para montar o token sintético por concatenação (`"xoxb-" + ("1" * 12) + "-" + ("a" * 16)`). A suíte específica de segredos passou com 16 testes, e `git show HEAD:services/api/tests/test_secrets.py` não encontrou a sequência completa identificada.
- O commit foi amendado para `3d07627`, mantendo a mensagem `feat: add desktop packaging and quality evaluation`, e o push foi aceito. Não foi usado link para liberar o segredo nem bypass do scanner.
- A referência `README.pt-BR.md` foi corrigida para a convenção real do repositório: `README.md` em português e `README-EN.md` em inglês.
- Referências antigas a `banner.png` e `yggdrasil-icon.png` foram removidas dos documentos verificados; as imagens PNG antigas foram removidas e o novo `docs/assets/banner.svg` foi adicionado.
- `.gitignore` recebeu `*.egg-info/` para ignorar metadados gerados pelo pacote Python; `.env` já era ignorado e foi verificado localmente.
- Artefatos temporários que poluíam a raiz do projeto foram movidos, sem exclusão, para `C:\Users\Gabriel\Desktop\yggdrasil-local-artifacts-backup-20261028`. A lista incluía payloads e scripts de entregas antigas/avaliações; esse backup fica fora do repositório e não deve ser apagado sem revisão do usuário.
- `docker compose down` foi executado sem `-v`; os containers/rede foram removidos e os volumes foram preservados.
- O plano mestre não entrou no commit `3d07627`; havia alteração local em `docs/MASTER-PLAN.md`. Este arquivo atualizado precisa ser copiado/revisado antes de qualquer commit próprio do plano.

### 4.4 Não implementado, parcial ou não validado

- Suporte estrutural amplo a TypeScript/Java/outras linguagens.
- Fluxo de chamadas completo e preciso entre todas as camadas e chamadas dinâmicas.
- Embeddings, base vetorial e reranking semântico.
- Avaliação real e automatizada da qualidade semântica de respostas de IA.
- Correção semântica de todas as citações/conclusões: IDs válidos não garantem que a afirmação esteja correta.
- Catálogo amplo de skills de arquitetura, autorização, validação de entradas, dependências e DevSecOps.
- Advisories de dependências com fonte/data e validação de atualidade.
- OAuth e análise de repositórios privados.
- Histórico de conversas persistido.
- Análise incremental e comparação de commits/snapshots.
- Worker durável que sobreviva a reinicialização; tarefas continuam no processo da API.
- Login, permissões multiusuário, isolamento comercial e hardening de hospedagem pública.
- Execução do código, scanners dinâmicos ou execução de testes do repositório-alvo.
- Aceite definitivo do desktop em máquina limpa sem Python/Node/Docker.
- Teste end-to-end da API de IA após configuração no ZIP exato de 23:40, incluindo autorização de sessão, reinício, persistência e tratamento de erro.
- Identificação inequívoca do caminho/nome/SHA-256 do ZIP final das 23:40.
- Publicação do pacote como GitHub Release.
- Integração da branch `test/env-file-detection` à `main`.

---

## 5. Escopo do produto

### 5.1 Escopo atual do MVP local

- Analisar repositórios públicos do GitHub.
- Vincular cada execução a um commit resolvido.
- Inventariar arquivos elegíveis sob limites configuráveis.
- Extrair estrutura Python por parsing estático.
- Construir um grafo navegável e inspecionável.
- Rodar skills determinísticas habilitadas.
- Fazer perguntas assistidas por IA com recuperação de evidências, quando explicitamente configurada.
- Revisar achados, exportar Markdown e exibir avisos/limitações.
- Trabalhar localmente sem autenticação multiusuário.
- Oferecer distribuição desktop Windows experimental, cuja release definitiva ainda requer os testes desta seção.

### 5.2 Fora do escopo atual

- Repositórios privados/permissões GitHub por usuário.
- Executar código ou instalar dependências do alvo.
- Provar que o sistema analisado é seguro ou livre de vulnerabilidades.
- Cobrir todas as linguagens/frameworks.
- Fuzzing, exploração ativa ou teste em sistemas implantados.
- Alteração automática do código, criação automática de commit ou pull request.
- Acesso irrestrito da IA a terminal, rede, banco ou filesystem.
- SaaS multiusuário, faturamento e isolamento comercial completo.
- Prometer entendimento exaustivo de sistemas dinâmicos grandes.

### 5.3 Evolução possível

Após avaliar o MVP, considerar melhoria incremental da recuperação, corpus de avaliação mais representativo, skills AppSec adicionais, advisories com fonte/data, busca semântica se os benchmarks justificarem, suporte a outra linguagem, comparação de commits e execução isolada em sandbox como projeto futuro separado.

---

## 6. Fluxo principal do usuário

1. O usuário cola uma URL canônica de repositório público.
2. O backend valida a URL e resolve a referência para um commit.
3. A análise é registrada e retorna estado inicial.
4. O backend inventaria arquivos e aplica limites de ingestão.
5. O parser extrai a estrutura Python suportada e o grafo é persistido.
6. As skills determinísticas habilitadas produzem achados candidatos.
7. A interface acompanha progresso/avisos e permite explorar o grafo.
8. O usuário abre um nó para examinar detalhes/evidências.
9. Se a IA estiver habilitada, o usuário confirma o envio dos trechos redigidos e faz perguntas.
10. O usuário confere as referências e registra sua decisão humana sobre achados.
11. O usuário exporta relatório Markdown.

Uma análise pode terminar com avisos ou cobertura parcial. O status terminal não significa que todos os arquivos tenham sido analisados estruturalmente nem que todos os riscos tenham sido encontrados.

### 6.1 Estados da execução

Os estados exatos seguem o contrato da implementação. Conceitualmente, distinguir fila/início, ingestão, parsing/construção, skills, finalização, conclusão normal, conclusão com avisos, falha e cancelamento quando suportado. A UI não deve mostrar percentuais inventados.

### 6.2 Estados de cobertura de arquivo

Registrar, quando aplicável, se o item foi descoberto, lido, elegível, ignorado por política, não suportado ou falhou. Não confundir arquivo presente no inventário com conteúdo lido/redigido/interpretado pelo parser.

---

## 7. Interface e grafo

### 7.1 Regiões funcionais

1. **Canvas:** mostra o grafo e destaca relações selecionadas.
2. **Atividade/avisos:** informa etapa, contadores, avisos e falhas.
3. **Inspetor:** mostra detalhes, origem, linhas, evidências e achados.
4. **Perguntas/relatório:** permite consultar a análise e exportar resultados.

A linha do tempo deve refletir eventos persistidos/SSE e caminhos observáveis. Não apresentar um traço do sistema como se fosse raciocínio interno privado do modelo.

### 7.2 Limites de visualização conhecidos

A visão geral é resumida a aproximadamente 180 nós; consultas/filtros do grafo usam paginação e limites da API; a validação sintética demonstrou 420 nós sem sobreposições e uma visão geral de 180 nós. No teste executado, os módulos filtrados foram 20. Esses resultados provam o comportamento do fixture, não a usabilidade para qualquer repositório.

A UI e o backend devem explicar a diferença entre:

- itens descobertos no inventário;
- itens cujo conteúdo foi lido;
- itens analisados pelo parser;
- nós/arestas persistidos;
- itens retornados pela consulta;
- itens efetivamente desenhados no canvas;
- itens omitidos por filtro/limite.

O limite visual não significa que itens omitidos desapareceram da análise. A experiência de busca precisa continuar clara e responsiva em grafos maiores.

### 7.3 Tipos de nós

O conjunto real depende do parser/pipeline: repositório/snapshot, diretórios/arquivos, módulos/classes/funções/métodos Python e entidades para testes/dependências/achados quando suportadas. Não inventar tipos para preencher o canvas.

### 7.4 Relações

As relações podem incluir contenção, imports/definições, relações com testes, dependências e chamadas inferidas. Cada tipo precisa de semântica clara. Chamada inferida por nome não é prova de execução em runtime.

### 7.5 UX e acessibilidade

Priorizar leitura, contraste, rótulos explícitos, estados loading/empty/error/partial e navegação utilizável. Cor não deve ser o único sinal de proveniência. O usuário reportou que o desktop selecionado ainda tem alguns bugs; descrevê-los concretamente em uma sessão de reteste antes da release, sem presumir que todos sejam bugs do frontend web.

---

## 8. Pipeline de análise

### 8.1 Validar origem e fixar commit

- Aceitar apenas a origem canônica `https://github.com/{owner}/{repo}` no MVP.
- Rejeitar hosts alternativos, credenciais na URL, parâmetros inesperados e formato ambíguo.
- Resolver referência para SHA antes de obter arquivos.
- Usar endpoints de host fixo; não tratar a URL do usuário ou links encontrados como destinos HTTP arbitrários.
- Tratar rate limit, repositório inexistente/indisponível e falhas de rede com mensagens seguras.

### 8.2 Inventário e limites

- Recuperar a árvore do commit ou arquivo compactado sob o limite configurado.
- Filtrar conteúdo binário, artefatos gerados, dependências vendorizadas, caches, arquivos excessivos e itens não elegíveis.
- Aplicar limites configuráveis de arquivo, quantidade e conteúdo total.
- Registrar avisos, omissões e cobertura parcial.
- Nunca presumir que um arquivo excluído está seguro ou revisado.

### 8.3 Parsing estático

- Parser atual: `ast` da biblioteca padrão Python.
- Extrair estrutura e localizações onde suportado.
- Não executar arquivos para descobrir definições.
- Tolerar falhas parciais sem interromper todo o repositório, salvo erro global relevante.
- Registrar claramente os casos não interpretados.
- Tree-sitter e parsers adicionais são opções futuras, não parte funcional da v0.7.0.

### 8.4 Construção e persistência do grafo

- Criar identificadores estáveis dentro do snapshot.
- Manter caminho/linhas quando disponíveis.
- Separar relações determinísticas de inferidas.
- Impedir relações que cruzem snapshots incompatíveis.
- Persistir resultados para navegação, consulta e relatório.
- Manter filtros/paginação do servidor coerentes com a UX e o layout.

### 8.5 Indexação e recuperação para perguntas

A v0.7.0 usa recuperação lexical/estrutural. A pergunta é classificada por intenção; termos em português podem ser expandidos para identificadores reconhecíveis em código. A seleção prioriza fontes apropriadas à intenção: definições/código, testes/exemplos, documentação e relações do grafo.

Limitações: seleção heurística, sinônimos, nomes dinâmicos, documentação divergente e arquivos não ingeridos podem causar omissões. Não há embeddings nem ranking semântico aprendido. Se as evidências forem insuficientes, a resposta deve ser inconclusiva e indicar a lacuna.

A avaliação atual do corpus Borax demonstra melhoria no ranking/recall nesse snapshot específico em comparação com a baseline. Próxima evolução: ampliar o corpus e testar regressões; não adotar embeddings apenas por popularidade.

### 8.6 Skills e achados

- Executar apenas skills habilitadas e com entrada disponível.
- Priorizar regras determinísticas para verificações que não dependam de interpretação probabilística.
- Guardar categoria, severidade, estado, evidências, recomendação e limitações quando disponíveis.
- Tratar resultados como candidatos à revisão humana.
- Não registrar ausência de achados como prova de ausência de vulnerabilidades.

### 8.7 Relatórios

Gerar Markdown a partir dos dados persistidos, incluindo repositório/commit, escopo, inventário/cobertura, estrutura, achados, referências, limitações e versão/metodologia. A exportação não deve inventar conclusões para lacunas sem dados.

---

## 9. Skills especializadas

### 9.1 Catálogo ativo

| ID | Modo | Objetivo | Limite principal |
|---|---|---|---|
| `appsec.secrets-detection` | Determinístico | Identificar padrões conhecidos de possíveis credenciais e redigir o valor reconhecido | Falsos positivos/falsos negativos; não valida credenciais |
| `engineering.test-inventory` | Determinístico | Reconhecer arquivos de teste Python por convenções simples | Não executa testes nem mede cobertura |

Versões e metadados exatos devem ser consultados no código quando alterados; não fixar no plano uma versão que não foi conferida na referência.

### 9.2 Categorias futuras

- **AppSec:** autorização, validação de entrada, sinks perigosos/fluxos de dados, configuração insegura e revisão de logs/erros.
- **Dependências/DevSecOps:** inventário de versões, advisories com fonte/data, workflows/permissões, proteção de segredos e pipeline.
- **Qualidade/confiabilidade:** tratamento de erro, lacunas de testes, contratos, casos de borda e riscos de regressão.
- **Arquitetura/desempenho:** dependências circulares, acoplamento e consultas ineficientes como hipóteses; diferenciar risco estático de gargalo medido.

### 9.3 Contrato mínimo de uma skill

Cada skill deve declarar ID/versão, categoria/objetivo, modo, linguagem/pré-condições, entradas/saídas, esquema do achado, fontes e procedimento de avaliação, ferramentas autorizadas/efeitos colaterais, limitações, casos positivos/negativos/ambíguos e orçamento de recursos quando aplicável.

### 9.4 Severidade e estado

Manter severidade separada de confiança. Achados não confirmados permanecem `needs_review` até revisão. `confirmed` significa que um revisor aceitou a evidência disponível, não que houve exploração automática. `fixed_in_revision` registra decisão de revisão, não prova por si só que a correção foi verificada pelo Yggdrasil.

### 9.5 Resultado do benchmark atual

O corpus `yggdrasil-skill-quality` v0.1.0 passou em 6/6 casos com `provider_calls=0`. Essa evidência serve como gate de regressão para os contratos testados; não deve ser usada para declarar cobertura AppSec completa. Manter o benchmark e adicionar casos apenas com anotações claras e justificadas.

---

## 10. IA, RAG e privacidade

### 10.1 Contrato da IA

O adaptador de IA é infraestrutura substituível. Chamadas precisam de timeout, limites de contexto/saída, tratamento de falhas transitórias e validação da resposta. Falha do provedor não deve apagar inventário/grafo já construído. A configuração de IA não deve ser requisito para análise estática ou avaliação RAG.

### 10.2 Conteúdo enviado a provedor externo

Quando a IA é utilizada:

- a pergunta e os trechos selecionados para contexto são enviados ao endpoint configurado;
- os trechos passam pelas redações implementadas antes do uso previsto pelo pipeline;
- o repositório inteiro não é enviado como um único payload;
- a interface exige confirmação antes do envio;
- a chave permanece no backend ou no armazenamento protegido do desktop;
- a conversa não é persistida como histórico nesta versão.

A redação por padrões reduz risco, mas não garante anonimização nem detecta todos os dados confidenciais. Não enviar código cujo compartilhamento não esteja autorizado. Em código sensível, avaliar provedor local confiável ou manter a IA desabilitada.

### 10.3 Prompt injection e conteúdo não confiável

Código, README, comentários, nomes de arquivos e strings podem conter instruções hostis. Esses conteúdos são dados delimitados, não instruções de controle. O modelo não deve possuir ferramentas, terminal, escrita, rede arbitrária nem permissão para executar texto retornado.

### 10.4 Integridade das citações

O backend aceita apenas IDs de citação pertencentes às evidências recuperadas. A UI deve expor caminho/linhas e incentivar a conferência da fonte. Uma citação válida pode não sustentar a conclusão mais ampla; a precisão semântica precisa de testes próprios.

### 10.5 Avaliação da qualidade de respostas

Existem casos humanos versionados em `docs/evaluations/borax-answer-quality-cases.json` e protocolo em `docs/evaluations/RESPONSE-REVIEW-PROTOCOL.md`. O modo de simulação do `evaluate_answers.py` valida corpus/snapshot e não chama IA. As avaliações reais exigem `--run-provider`, configuração válida e aceitação consciente de consumo de cota/custo. Não executar esse modo automaticamente em retomadas sem confirmar a intenção do usuário.

A avaliação humana deve verificar afirmações, citações, interpretação de testes, cobertura de evidências, falsa certeza, abstinência, latência e custo aproximado quando mensurável.

### 10.6 Busca semântica

Não implementar embeddings/pgvector só por popularidade. Primeiro ampliar o corpus e medir recuperação/qualidade de respostas. Incorporar busca semântica somente se houver ganho repetível que compense latência, custo e complexidade.

---

## 11. Modelo de dados e persistência

As entidades SQLAlchemy da versão incluem conceitos equivalentes a:

- `Repository` — identidade do repositório;
- `RepositorySnapshot` — referência/commit analisado;
- `AnalysisRun` — estado/metadados da execução;
- `SourceFile` — arquivo, metadados, status e conteúdo redigido quando elegível;
- `GraphNode` — nó do grafo;
- `GraphEdge` — relação do grafo;
- `AnalysisEvent` — evento persistido;
- `Finding` — achado estruturado/estado de revisão;
- `ReportExport` — exportação Markdown.

SQLite é o padrão local; PostgreSQL é suportado pela conexão e Compose. Migrations evoluem o esquema. A persistência deve manter-se limitada ao necessário e evitar guardar valores reconhecidos como segredos.

### 11.1 Integridade esperada

- Relações de grafo pertencem ao mesmo snapshot.
- Chaves estrangeiras/constraints preservam a ordem válida de gravação.
- Eventos têm sequência/identidade suficiente para replay e deduplicação razoável.
- Mudanças de contrato vêm com migrations e testes.
- Logs não armazenam segredos, chave, corpo sensível do provedor nem fonte completa desnecessária.

### 11.2 Retenção e dados locais

O MVP local guarda histórico das análises e dados derivados no banco. A documentação desktop aponta para `%LOCALAPPDATA%\Yggdrasil\`, incluindo banco SQLite, `settings.json`, `ai-key.dpapi`, logs operacionais e porta temporária. Backup consistente deve ser feito com o programa fechado. A chave DPAPI é vinculada ao usuário Windows que a protegeu e não deve ser considerada portável entre máquinas/contas.

O clone de validação criou seu próprio banco SQLite e ambiente virtual locais; esses dados não entram no Git. O usuário removeu a pasta clone por engano e a restaurou da Lixeira; a pasta foi localizada e os testes continuaram. Não remover o clone nem o backup de artefatos locais sem o usuário confirmar que não são mais necessários.

---

## 12. Arquitetura e stack atuais

### 12.1 Frontend

- React 19;
- TypeScript;
- Vite 7;
- `@xyflow/react` para o canvas;
- `lucide-react` para ícones;
- npm e `package-lock.json` para instalação reproduzível.

### 12.2 Backend

- Python 3.11+;
- FastAPI/Uvicorn;
- Pydantic;
- SQLAlchemy;
- Alembic;
- Pytest;
- Ruff configurado.

### 12.3 Persistência e ingestão

- SQLite por padrão;
- PostgreSQL via URL SQLAlchemy e Docker Compose;
- adaptador GitHub e ingestão por arquivo compactado/fallback seletivo;
- `ast` para estrutura Python;
- SSE para eventos servidor → navegador.

### 12.4 Estrutura resumida do repositório publicado

```text
yggdrasil/
├── apps/
│   └── web/                       # React, TypeScript, Vite e grafo
├── desktop/                       # inicializador, config segura, build e smoke tests Windows
├── services/
│   └── api/
│       ├── app/
│       │   ├── api/               # rotas HTTP
│       │   ├── application/       # runner, perguntas e avaliação RAG
│       │   ├── domain/            # grafo, skills, segredos e relatório
│       │   ├── infrastructure/    # GitHub, arquivos, provedor de IA
│       │   ├── schemas/
│       │   ├── config.py
│       │   ├── db.py
│       │   ├── desktop_runtime.py
│       │   ├── models.py
│       │   └── main.py
│       ├── alembic/               # migrations
│       ├── evaluation/corpora/     # corpora JSON versionados
│       ├── scripts/                # evaluate_answers/rag/skills
│       └── tests/
├── docs/
│   ├── evaluations/               # protocolo, casos e baseline
│   ├── assets/banner.svg
│   ├── MASTER-PLAN.md
│   ├── PROGRESS.md
│   ├── RAG-EVALUATION.md
│   └── SECURITY.md
├── scripts/                        # start-dev e utilitários
├── .env.example
├── docker-compose.yml
├── README.md                       # português
└── README-EN.md                    # inglês
```

A árvore é resumida; conferir o repositório real antes de assumir que uma pasta existe ou que um item futuro foi implementado.

### 12.5 API relevante

Prefixo `/api/v1`. Rotas e contratos reais devem ser conferidos no OpenAPI (`/docs`) antes de alterar.

| Endpoint | Finalidade |
|---|---|
| `GET /health` ou `GET /api/v1/health` conforme montagem atual | Status da API/banco e versão; o caminho utilizado nos testes foi `/api/v1/health` |
| `GET /api/v1/skills` | Catálogo de skills |
| `POST /api/v1/analyses` | Registrar/iniciar análise, respondendo `202` |
| `GET /api/v1/analyses` | Listar análises recentes |
| `GET /api/v1/analyses/{id}` | Estado, commit, contadores e avisos |
| `GET /api/v1/analyses/{id}/events` | SSE/replay de eventos |
| `GET /api/v1/analyses/{id}/graph` | Consultar nós/arestas com busca/filtros/paginação |
| `GET /api/v1/analyses/{id}/nodes/{node_id}` | Detalhes do nó/evidência redigida |
| `GET /api/v1/analyses/{id}/findings` | Listar achados |
| `PATCH /api/v1/analyses/{id}/findings/{finding_id}/status` | Atualizar revisão humana de achado |
| `POST /api/v1/analyses/{id}/questions` | Pergunta assistida por IA com evidências recuperadas |
| `GET /api/v1/analyses/{id}/export/markdown` | Exportar relatório Markdown |
| `POST /api/v1/analyses/{id}/exports/markdown` | Criar exportação persistida |
| `GET /api/v1/exports/{export_id}` | Baixar exportação criada |

O caminho exato de cada rota deve ser confirmado em `services/api/app/api/routes.py` se houver discrepância.

### 12.6 Tarefas longas e eventos

O pipeline usa execução em background no mesmo processo da API e eventos persistidos/SSE. Isso atende ao estágio local, mas não garante durabilidade após reinício do processo. Worker externo só deve ser introduzido quando recuperação pós-crash, volume ou paralelismo justificarem a complexidade.

### 12.7 Ambiente de desenvolvimento limpo

O README orienta Windows com `scripts/start-dev.ps1`, ou setup manual de Python/npm. No clone validado, por causa da Execution Policy do PowerShell, `npm` resolveu para `npm.ps1` bloqueado; usar `npm.cmd` permitiu instalar/lint/build sem alterar a política global do Windows. Esse é um detalhe operacional do ambiente de validação, não uma falha do projeto.

O `npm ci` registrou script de instalação do esbuild bloqueado por allowScripts, mas a compilação de produção passou. Antes de aprovar script de instalação manualmente, conferir o pacote/origem e decidir de forma consciente; não contornar por padrão.

---

## 13. Segurança do próprio Yggdrasil

### 13.1 Ativos e ameaças

O Yggdrasil recebe conteúdo de terceiros, processa arquivos e, se habilitada, envia trechos a um provedor de IA. Riscos relevantes: URL/SSRF ou redirecionamento indevido, traversal/symlink/arquivo compactado abusivo, consumo excessivo, segredo em repositório/log, prompt injection, resposta falsa da IA, exposição de código, abuso de rotas locais e falhas de persistência/eventos.

### 13.2 Controles presentes

- URL de ingestão limitada ao host/formato esperado do GitHub.
- Hosts fixos e recusa de redirecionamentos nas operações relevantes.
- Referência resolvida para commit e limites de arquivos/conteúdo.
- Código-alvo nunca executado/importado.
- Redação de padrões reconhecidos de segredos.
- CORS configurável.
- IA desativada por padrão e chave mantida no backend/armazenamento protegido do desktop.
- Confirmação antes de enviar trechos ao provedor.
- Saídas/citações validadas no servidor.
- Logs de erro planejados sem corpo sensível, SQL/parâmetros ou conteúdo-fonte desnecessário.
- Armazenamento DPAPI no desktop para a chave do usuário Windows, fora do ZIP de distribuição.
- Testes automatizados de segurança de sessão/configuração/env-file no commit publicado.

### 13.3 Limites residuais

- Não há autenticação/autorização multiusuário; manter portas em loopback e não expor serviço na internet.
- Redação por padrões é incompleta; credenciais desconhecidas, divididas ou codificadas podem escapar.
- Prompt injection não é eliminada apenas por instruções.
- Ingestão pode ficar parcial por limites/rate limit.
- Background no processo não é worker durável.
- Análise estática não prova explorabilidade nem ausência de vulnerabilidades.
- Provedor externo recebe trechos selecionados; a confirmação não transforma essa transmissão em processamento local.
- O fluxo de IA no desktop ainda precisa ser repetido de ponta a ponta no ZIP exato escolhido; não declarar resolvido apenas porque o inicializador abre.
- A distribuição desktop ainda não foi aceita em Windows limpo sem Python/Node/Docker.

### 13.4 Push protection e segredos no Git

O GitHub rejeitou o primeiro push porque uma fixture sintética em `services/api/tests/test_secrets.py` continha uma string literal que correspondia a um padrão de token Slack. A fixture foi reformulada por concatenação e o commit foi amendado para `3d07627`; o push foi aceito sem bypass. Manter a regra de nunca liberar o push ignorando um alerta não resolvido.

A verificação de nomes/extensões no staging e uma busca por padrões comuns no diff não encontraram outros resultados, mas essas verificações não garantem ausência de todo tipo de segredo. Continuar verificando conteúdo e manter `.env` real fora do controle de versão.

### 13.5 Regras antes de hospedagem ou distribuição pública

Antes de oferecer uso em rede/hospedagem, tratar autenticação, autorização, isolamento, rate limits, quotas, concorrência, segurança de segredos, retenção, monitoramento, atualizações de dependências e revisão de ameaça. Não considerar abrir a porta pública um passo pequeno de deploy.

---

## 14. Testes e avaliação

### 14.1 Portão de qualidade do código

O clone limpo passou pelos seguintes itens no commit `3d07627`:

- [x] suíte completa do backend via `python -m pytest -q` no venv do clone;
- [x] migrations Alembic para SQLite do clone;
- [x] health API com banco `ok`;
- [x] `npm ci` do frontend;
- [x] ESLint;
- [x] type-check/build (`tsc -b` e `vite build`);
- [x] teste sintético de layout do grafo;
- [x] benchmark de skills sem IA;
- [x] avaliação de recuperação RAG sem IA;
- [x] validação/simulação do corpus de respostas sem IA;
- [x] clone limpo permaneceu sem alterações inesperadas após testes.

Observações: a suíte backend exibiu aviso de depreciação do TestClient/Starlette; o frontend emitiu aviso de ESLint fora de suporte e bloqueio do script de instalação do esbuild, embora o lint/build tenham passado. Manutenção futura deve revisar esses avisos sem converter isso automaticamente em falha do produto.

### 14.2 Portão de qualidade do desktop

- [x] Código/launcher e scripts estão no commit.
- [x] Há pacote compilado e executável candidate identificado por timestamp aproximado.
- [x] O usuário reportou que o candidato das ~23:40 abre rápido, aceita configuração da API e funciona melhor com o chatbot que o candidato anterior.
- [ ] Identificar e arquivar o ZIP exato de 23:40, seu tamanho e SHA-256.
- [ ] Reexecutar `desktop\test-windows-package.ps1` no diretório extraído do ZIP exato candidato.
- [ ] Testar com IA desabilitada.
- [ ] Configurar chave/modelo pelo inicializador e testar uma pergunta real, verificando sessão local/autorização.
- [ ] Fechar e reabrir o aplicativo; confirmar persistência SQLite e configuração esperada.
- [ ] Testar endpoint/conexão inválida, erro 401/403, 429/503 e mensagens de diagnóstico relevantes sem expor a chave.
- [ ] Reproduzir e documentar os bugs de UI observados pelo usuário, classificando bloqueador/não bloqueador.
- [ ] Testar em máquina/perfil Windows limpo sem Python, Node.js nem Docker.
- [ ] Conferir que o pacote não contém `.env`, bancos do desenvolvedor, logs, chave nem cache desnecessário.
- [ ] Registrar hash final do ZIP e preparar notas de release.

### 14.3 Corpus para avaliar RAG

O corpus atual contém perguntas sobre implementação, exemplo, testes, visão geral, API pública, empacotamento/dependências e insuficiência de evidência. Para cada caso, anotar repositório/commit, pergunta, caminhos esperados, intenção, fatos verificáveis, limites e se uma citação sustenta a afirmação.

Medir pertinência/recuperação; não confundir essas métricas com correção semântica de resposta. O corpus é pequeno e os rótulos são humanos; quando o snapshot mudar, revisar os caminhos esperados antes de comparar.

### 14.4 Casos obrigatórios para expansão

- implementação e teste relacionados a uma classe/método;
- português para identificadores em inglês;
- biblioteca mencionada sem desviar pergunta de implementação para dependências;
- README inconsistente com implementação;
- conteúdo em outro idioma;
- arquivo esperado ausente ou ignorado por política;
- pergunta ambígua/sem evidência;
- prompt injection no conteúdo do alvo;
- segredos e falsos positivos;
- timeout/indisponibilidade/resposta inválida do provedor;
- ingestão parcial/rate limit;
- interpretação correta de assertions/testes;
- citações válidas mas semanticamente insuficientes;
- configuração/reinício/sessão local no desktop.

### 14.5 Critérios de aceite contínuos

- [x] A referência da branch publicada está vinculada a um commit identificável.
- [x] Ingestão estática não executa código do alvo.
- [x] Grafo e layout passam no fixture sintético atual.
- [x] Skills têm um corpus inicial executável sem IA.
- [x] Recuperação RAG tem corpus e métricas reproduzíveis.
- [x] A seleção de análise para o corpus de respostas valida o snapshot correto sem chamada de IA.
- [ ] Corpus de resposta é executado com provedor e avaliado humanamente em um conjunto representativo.
- [ ] Setup e desktop são aceitos em Windows limpo sem ferramentas de desenvolvimento.
- [ ] Bugs visuais do candidato desktop são documentados e priorizados.
- [ ] A release é gerada a partir do build escolhido, tem hash e instruções e não inclui segredos/dados locais.

---

## 15. Roadmap — quatro entregas consolidadas

### Entrega 1 — Fundação, configuração e avaliação

**Status:** núcleo implementado e validado no clone; qualidade semântica de respostas e alguns itens de release permanecem abertos.

Concluído nesta rodada:

- [x] Atualizar `.env.example`, com IA desabilitada por padrão e exemplo opcional de configuração sem chave real.
- [x] Corrigir a referência ao README em português/inglês: `README.md` e `README-EN.md`.
- [x] Versionar `apps/web/package-lock.json` e a declaração `vite-env.d.ts`.
- [x] Manter `.env` ignorado e adicionar `*.egg-info/` ao `.gitignore`.
- [x] Atualizar os READMEs, `docs/PROGRESS.md`, `docs/SECURITY.md` e documentação de RAG/avaliação na entrega publicada.
- [x] Adicionar corpus de qualidade de resposta e protocolo de revisão humana.
- [x] Criar script/relatório automatizado de avaliação de respostas, com simulação por padrão e chamadas reais explícitas via flag.
- [x] Testar a suíte completa backend e o frontend (lint/build/layout) num clone limpo.
- [x] Rodar benchmark de skills e avaliação RAG no snapshot esperado sem chamadas de provedor.
- [x] Comparar métricas RAG com a baseline e registrar que os resultados são específicos do corpus.
- [ ] Executar revisão humana de um conjunto de respostas ao vivo, com provedor e snapshot fixo, incluindo assertivas de teste e abstinência.
- [ ] Revisar avisos de depreciação/dependências em manutenção futura sem bloquear o que já passou, salvo se uma avaliação de risco demonstrar problema relevante.

**Aceite:** a preparação, suite e métricas de recuperação são reproduzíveis; a conclusão semântica do modelo não está declarada como resolvida.

### Entrega 2 — Cobertura, confiabilidade e grafo

**Status:** paginação/filtros e melhoras do grafo implementados; parte de cobertura, UX e resiliência segue como evolução.

Concluído/validado:

- [x] Consulta/filtros server-side e paginação do grafo.
- [x] Melhorias de layout/teste para grafo sintético de 420 nós sem sobreposições.
- [x] Overview de 180 nós e filtragem sintética de módulos para 20 nós demonstrados no teste.
- [x] Traço/realce de caminhos derivado de eventos/evidências observáveis, não de raciocínio privado.
- [x] Testes publicados associados a mudanças de API/grafo/UI passaram no clone completo.

Pendente/evolução:

- [ ] Fazer inspeção visual manual em diferentes tamanhos de janela e em um repositório real maior.
- [ ] Melhorar ainda mais a explicação de inventário vs parsing vs visibilidade do canvas.
- [ ] Fixtures específicas para arquivos inválidos, grandes, binários, ignorados e ingestão parcial, caso ainda não cubram todos esses estados.
- [ ] Testar reconexão/replay SSE, eventos duplicados e estados terminais em falhas/inicialização reiniciada.
- [ ] Não introduzir worker durável até necessidade real justificar sua complexidade.

### Entrega 3 — Inteligência, skills e recuperação

**Status:** harness de avaliação, melhorias de recuperação e benchmark determinístico publicados; avaliação semântica de respostas continua em revisão humana.

Concluído/validado:

- [x] Harness de avaliação de skills com 6/6 casos aprovados e 0 provider calls.
- [x] Harness de avaliação de recuperação RAG com corpus versionado.
- [x] Resultado pós-melhoria do Borax registrado: MRR 0.7833; Hit@3 0.8333; Hit@5 1.0; Recall@5 1.0.
- [x] Caso de ausência de prova de segurança excluído das métricas de recall por não medir geração/abstinência.
- [x] Harness de avaliação de respostas e protocolo de revisão manual.
- [ ] Ampliar corpus além do Borax/lunardate e validar casos em mais projetos/línguas.
- [ ] Reexecutar avaliação semântica com IA com autorização explícita e revisão humana das quatro questões ou seleção representativa.
- [ ] Melhorar seleção de arquivo `setup.py` no caso sobre metadados de empacotamento, se continuar relevante nos corpora expandidos.
- [ ] Considerar embeddings/reranking apenas após benchmark comparativo com baseline atual.
- [ ] Adicionar skills novas somente com casos positivos, negativos, ambíguos e aceitação humana.

### Entrega 4 — Interface final e distribuição Windows

**Status:** candidato de executável escolhido; release pública ainda não liberada.

Decisões e fatos:

- O executável por volta de **27/10/2026 23:03:30** (16.554.409 bytes) foi a primeira opção e o usuário informou que o chatbot não funcionava como esperado; não deve ser o candidato escolhido.
- O executável por volta de **27/10/2026 23:40:00** (16.554.430 bytes) é o segundo, mais recente por 21 bytes; o usuário o abriu e informou que funciona melhor, abre rápido, permite configurar a própria API e o chatbot funciona melhor. Há bugs na interface e o usuário decidiu usá-lo como candidato para a release.
- O timestamp/tamanho identificam o candidato, mas não substituem o caminho, o ZIP final e o SHA-256 da distribuição exata.
- O ZIP conhecido `Yggdrasil-Desktop-v0.7.0-20261027-230335.zip` e seu hash histórico referem-se a um artefato mais antigo; não reutilizar esse hash como se fosse o pacote escolhido das 23:40.

Próximos passos:

- [x] Código do launcher, armazenamento/configuração protegidos, scripts de build e smoke test estão versionados.
- [x] O usuário experimentou manualmente o candidato de 23:40 e o selecionou em relação ao de 23:03.
- [ ] Encontrar o caminho exato do executável escolhido e reconstruir/identificar o ZIP que contém exatamente esse build.
- [ ] Calcular e guardar SHA-256 do ZIP de release, além de tamanho/data.
- [ ] Executar o script de smoke test no ZIP exato e registrar stdout/resultado.
- [ ] Verificar funcionamento sem IA, com IA configurada, erro de sessão/autorização e reinício.
- [ ] Reproduzir bugs de UI e decidir o que corrigir antes da release.
- [ ] Testar em ambiente Windows limpo sem Python/Node/Docker.
- [ ] Preparar GitHub Release com ZIP separado do código, instruções de instalação, limites e checksum.
- [ ] Só marcar como estável se os critérios de aceite forem cumpridos; caso contrário, identificar explicitamente como experimental/pré-release.

### Evoluções posteriores — fora das quatro entregas iniciais

- **Segunda linguagem e comparação de snapshots:** selecionar por demanda e avaliar parser/fixtures antes de anunciar suporte.
- **Worker durável/uso compartilhado:** considerar apenas quando a necessidade existir; exige filas/workers, autenticação, autorização, isolamento, quotas, retenção e monitoramento.
- **Privados/sincronização/colaboração:** exigem revisão própria de permissões e privacidade.
- **Embeddings/reranking:** somente por ganho mensurado.
- **Histórico persistido de chat:** só depois de definir retenção, privacidade e minimização de dados.

### Critérios para v1.0 desktop

- [ ] Fluxo de análise suportado reproduzível a partir de instalação limpa.
- [x] Núcleo do código (branch atual) tem suite e builds básicos validados em clone limpo.
- [x] Corpus de recuperação versionado e executado; resultados e limites documentados.
- [ ] Qualidade semântica de respostas avaliada num conjunto representativo.
- [ ] ZIP aceito em Windows limpo sem Python/Node/Docker.
- [ ] Configuração e remoção da chave testadas, sem chave em frontend/log/pacote.
- [ ] Sessão local, reinício, persistência e encerramento controlado aceitos.
- [ ] Bugs visuais restantes classificados e resolvidos ou declarados com clareza.
- [ ] Release tem checksum SHA-256, instruções, changelog e limitações.
- [ ] Main/versão oficial está alinhada ao código que será distribuído.

### Mapa entre fases antigas e entregas

| Fase antiga | Destino |
|---|---|
| A — Preparação para publicação | Entrega 1 |
| B — Avaliação RAG | Entrega 1 |
| C — Cobertura e resiliência | Entrega 2 |
| D — Skills AppSec e qualidade | Entrega 3 |
| E — Melhorias de recuperação | Entrega 3 |
| F — Segunda linguagem/comparação de snapshots | Evolução posterior |
| G — Worker durável/uso compartilhado | Evolução posterior |
| Interface desktop e empacotamento | Entrega 4 |

---

## 16. Decisões de arquitetura e produto vigentes

1. **Monólito modular:** simples de executar localmente e suficiente para o estágio atual.
2. **Somente leitura para o repositório-alvo:** não executar código ou scripts externos.
3. **GitHub público e commit fixo:** restringe a origem e estabiliza a referência.
4. **Parsing Python com `ast`:** ferramenta disponível; limita o alcance à análise Python suportada.
5. **SQLite por padrão, PostgreSQL opcional:** reduz barreira de entrada e mantém via de evolução.
6. **SSE para progresso:** fluxo servidor → interface.
7. **IA por adaptador:** provider/modelo configuráveis e IA opcional.
8. **Recuperação lexical/estrutural inicial:** embeddings condicionados a evidência de benefício.
9. **Relatórios a partir de dados persistidos:** resultado não deve depender de conversa livre.
10. **Citações validadas no backend:** o modelo não introduz IDs arbitrários como fontes válidas.
11. **Sem autenticação no MVP:** uso local apenas; não expor portas públicas.
12. **Desktop como conveniência local:** `Yggdrasil.exe` é um launcher/orquestrador; o código continua no repositório e o pacote executável vai como asset de GitHub Release, não como binário dentro do commit.
13. **Não esconder problemas de release:** versão que abre rapidamente ainda precisa passar no roteiro de aceite de persistência, IA, sessão e máquina limpa.
14. **Não liberar segredo para passar no push:** corrigir fixtures/dados falsos que disparem secret scanning; não usar bypass sem investigação apropriada.

ADRs existentes são histórico de decisões. Ao alterar uma decisão, registrar contexto, alternativas, consequências e migração.

---

## 17. Definition of Done

Uma fatia de desenvolvimento só está pronta quando os critérios aplicáveis forem cumpridos:

- [ ] comportamento ligado a uma necessidade/critério de aceite;
- [ ] caminho feliz exercitado de ponta a ponta;
- [ ] entradas inválidas/falhas relevantes tratadas com segurança;
- [ ] testes cobrem o comportamento e limites importantes;
- [ ] estado persistido/eventos não se contradizem;
- [ ] logs não expõem segredo/chave/prompt sensível/conteúdo-fonte desnecessário;
- [ ] UI comunica loading, ausência de dados, falha e resultado parcial;
- [ ] UI permanece utilizável no tamanho de grafo testado;
- [ ] lint, testes e build aplicáveis executados e resultados registrados;
- [ ] README/Plano Mestre/PROGRESS/SECURITY/ADR atualizados quando afetados;
- [ ] pacote não contém `.env` real, bancos locais, logs, caches ou artefatos temporários;
- [ ] referência e versão confirmadas em `/api/v1/health`;
- [ ] entrega informa arquivos, comandos e resultados;
- [ ] alterações locais preexistentes não são sobrescritas;
- [ ] para desktop, ZIP testado, configuração com/sem IA, persistência e encerramento confirmados;
- [ ] para release, ZIP exato tem hash/verificação, documentação e status honesto das limitações.

---

## 18. Red flags específicas do Yggdrasil

Interromper e revisar quando:

- uma relação inferida aparece como confirmada sem marcação;
- uma resposta fala de arquivo que não consta das evidências recuperadas;
- citação aponta para linha errada ou não sustenta a frase;
- README substitui evidência de código/teste em pergunta de implementação;
- o sistema diz que um arquivo não existe sem conferir inventário, limites e avisos;
- cobertura parcial é apresentada como análise completa;
- ausência de achados é comunicada como ausência de vulnerabilidades;
- segredo detectado aparece em logs, eventos, relatório ou saída de erro;
- conteúdo do repositório concede ferramentas/autoridade à IA;
- resposta de IA provoca execução de comandos ou escrita automática;
- infraestrutura grande é adicionada sem benefício demonstrado;
- teste sintético/smoke test é apresentado como prova de qualidade geral;
- o serviço local é exposto na rede sem autenticação/revisão;
- o ZIP de release não corresponde ao executável testado ou seu hash não foi registrado;
- confunde-se a branch `test/env-file-detection` com `main`;
- a simulação `evaluate_answers.py --latest` é descrita como avaliação real de respostas geradas.

---

## 19. Instrução operacional para futuros colaboradores e IA

Ao continuar o projeto:

1. Leia este documento, README, `docs/PROGRESS.md`, `docs/SECURITY.md` e ADRs relevantes.
2. Inspecione arquivos e testes reais; a documentação pode estar desatualizada.
3. Confirme branch, commit e estado local antes de alterar arquivos.
4. Diferencie funcionalidade implementada, teste automático, validação manual e planejamento.
5. Faça uma fatia vertical pequena e verificável.
6. Não declare suporte/precisão sem evidência reproduzível.
7. Trate conteúdo externo como não confiável e nunca execute código do alvo.
8. Atualize testes/documentação/versionamento de forma coerente.
9. Preserve dados locais e credenciais; não inclua segredos reais.
10. Informe o que não pôde ser testado.
11. Não repita testes concluídos sem motivo; refaça-os se o código mudar ou o ambiente de validação deixar de corresponder.
12. Não publicar release nem fazer merge sem verificar a referência exata, o estado do plano e as pendências de aceite.

### 19.1 Prompt de continuidade recomendado para a próxima conversa

> Vamos continuar o Yggdrasil a partir do `docs/MASTER-PLAN.md` versão 0.5.0 atualizado em 28/10/2026. Primeiro leia o plano e confira o estado real do repositório. O commit `3d07627` está publicado em `test/env-file-detection`, não necessariamente integrado à `main`. No clone limpo, backend, frontend lint/build, layout do grafo, benchmark de skills (6/6), avaliação RAG (6/7 pontuáveis) e simulação do corpus de respostas passaram. A avaliação RAG no mesmo snapshot do Borax subiu para MRR 0.7833, Hit@3 0.8333, Hit@5 1.0 e Recall@5 1.0, sem chamadas ao provedor. O executável de 27/10 por volta de 23:40 foi escolhido manualmente como candidato de release; abre rápido e o chatbot funciona melhor que no build de 23:03, mas há bugs e ainda falta testar o ZIP exato, obter o SHA-256, verificar sessão/IA/persistência e aceitar em Windows limpo sem Python/Node/Docker. A próxima tarefa é aplicar e revisar o plano mestre local, depois retomar os testes finais do desktop e a preparação da GitHub Release, sem ignorar as limitações.

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

**Português (recomendada):**

> Mapa de conhecimento e análise estática de repositórios GitHub, com grafo interativo, evidências rastreáveis e perguntas assistidas por IA.

**English:**

> Static repository analysis and code knowledge mapping for GitHub projects, with an interactive graph, traceable evidence, and AI-assisted Q&A.

## Apêndice B — Evidências e comandos relevantes para a retomada

Os comandos abaixo foram usados e passaram durante a sessão no clone limpo, salvo onde indicado:

```powershell
# Versão do clone
 git -C ..\yggdrasil-clone-test-20261028 log -1 --oneline
# 3d07627 feat: add desktop packaging and quality evaluation

# Estado limpo do clone
 git -C ..\yggdrasil-clone-test-20261028 status --short --branch
# ## test/env-file-detection...origin/test/env-file-detection

# Backend (executado dentro de services/api com .venv)
 .\.venv\Scripts\python.exe -m pytest -q

# Frontend (executado dentro de apps/web)
 npm.cmd ci
 npm.cmd run lint
 npm.cmd run build
 npm.cmd run test:layout

# Benchmark determinístico (services/api)
 .\.venv\Scripts\python.exe scripts/evaluate_skills.py

# Avaliação RAG no banco local do clone
 .\.venv\Scripts\python.exe scripts/evaluate_rag.py --latest --cases evaluation/corpora/borax.json

# Simulação de avaliação de respostas, sem envio ao provedor
 .\.venv\Scripts\python.exe scripts/evaluate_answers.py --latest
```

O caminho exato do shell pode variar; os comandos relativos acima pressupõem que o terminal está na pasta indicada em cada comentário. No clone, o ambiente virtual está em `services/api/.venv`; os `node_modules`, `dist` e banco são artefatos locais e não devem ser adicionados ao Git.

## Apêndice C — decisões/pendências para não perder na retomada

- A entrega principal de código foi publicada com commit `3d07627` na branch `test/env-file-detection`; ainda não houve merge para `main` registrado nesta sessão.
- `docs/MASTER-PLAN.md` original foi deixado fora do commit. Este arquivo atualizado deve ser revisado e aplicado ao caminho local original, seguido por `git diff --check`, revisão do diff e status.
- A pasta de clone foi restaurada após remoção acidental para a Lixeira e usada nos testes; ela estava limpa ao final. Não apagar até terminar a avaliação/release.
- Artefatos antigos foram movidos sem exclusão para `C:\Users\Gabriel\Desktop\yggdrasil-local-artifacts-backup-20261028`.
- A distribuição oficial será um ZIP anexado a uma GitHub Release, não um binário versionado junto do source commit.
- O build por volta de 23:03 é candidato descartado pelo usuário por problema no chatbot; o build por volta de 23:40 é candidato escolhido. Confirmar o ZIP exato, nome, caminho e hash antes de publicar.
- Há relatos de bugs na UI do desktop. Reproduzir e registrar exemplos concretos em vez de supor ou declarar a interface perfeita.
- A avaliação de respostas realizada no clone foi simulação; nenhuma chamada foi enviada ao provedor. O resultado RAG e o benchmark de skills foram offline.
- Modelo Gemini e chave devem ser configurados localmente pelo usuário. Nunca registrar ou compartilhar a chave no plano, logs ou Git.
