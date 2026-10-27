# Yggdrasil — Progresso verificado

**Versão do aplicativo:** 0.7.0 — recuperação source-first e preferências de leitura
**Data:** 27/10/2026
**Fonte de verdade:** Plano Mestre v0.3.0 (`docs/MASTER-PLAN.md`) e código/testes presentes neste repositório.

## Estado atual

A base de análise estática está funcional na máquina do usuário. A v0.7.0 corrige a classificação de perguntas que pedem implementação e também mencionam uma biblioteca, amplia a recuperação para definições por símbolo, testes/exemplos, trechos relevantes da documentação e relações do grafo; adiciona expansão lexical português→identificadores em inglês; recolhe as referências por padrão; e inclui preferências locais de fonte/tamanho. A IA continua opcional e desligada por padrão. Não foi feita chamada real a um provedor nesta fatia.

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
