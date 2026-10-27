# Modelo de segurança do Yggdrasil MVP

## Ativos e fronteiras

O backend recebe código público de terceiros, processa arquivos compactados ou uma árvore de arquivos por commit e grava resultados em um banco local. O conteúdo analisado é não confiável, mesmo que venha de um repositório conhecido. O browser conversa apenas com a API do próprio Yggdrasil e não recebe chave de IA.

## Controles presentes

- URL allowlist: `https://github.com/{owner}/{repo}`; não permite host alternativo, credenciais na URL, parâmetros, caminhos de branch/arquivo ou porta explícita.
- O cliente usa hosts fixos `api.github.com`, `codeload.github.com` e `raw.githubusercontent.com`; não segue redirecionamentos. O token opcional da API não é enviado aos outros hosts.
- A referência é validada e resolvida para um SHA de 40 caracteres antes do download.
- Quando o ZIP ultrapassa o limite, a análise pode obter a árvore recursiva do commit e baixar somente blobs elegíveis, usando paths validados e limites individuais/agregados. O SHA do blob Git é verificado quando o formato é SHA-1 conhecido.
- O ZIP é lido em memória sem extração. Entradas com traversal, symlinks, conteúdo binário, arquivos grandes e diretórios de dependência/artefato gerado são ignorados conforme política.
- Limites configuráveis de bytes compactados, quantidade de entradas/arquivos, bytes declarados, tamanho individual e conteúdo textual agregado. Se a resposta recursiva for truncada, a ingestão tenta reconstruir o inventário lendo subárvores individualmente; `MAX_TREE_DIRECTORIES` limita a quantidade de consultas e a cobertura parcial é sinalizada quando necessário.
- Não há subprocess, `eval`, importação dinâmica do alvo, instalação de pacote, execução de build/teste ou uso de ferramentas fornecidas por arquivos.
- Relações que dependem apenas de correspondência de nome de chamada são marcadas como inferidas.
- Valores que correspondem aos padrões de segredo implementados são redigidos antes de persistir texto e são omitidos de achados/eventos/relatórios. A skill v0.2.0 cobre atribuições e chaves JSON comuns, credenciais em URLs HTTP(S)/banco, tokens Bearer/JWT e alguns formatos de provedores (AWS, Google, GitHub, Slack e Stripe).
- Erros de integração retornam códigos e mensagens seguras; falhas inesperadas não retornam stack trace ao usuário.
- CORS é limitado a origens configuradas, sem credenciais cross-origin.
- Perguntas por IA são desativadas por padrão; o backend só habilita o adaptador compatível quando provedor/modelo e credenciais necessárias estão configurados.
- Ao enviar uma pergunta, a interface exige confirmação de que trechos redigidos serão transmitidos ao provedor selecionado. O backend recupera contexto limitado, não envia o repositório inteiro e não expõe chave ao frontend.
- O prompt instrui o modelo a tratar código, README, comentários e strings como dados não confiáveis; nenhum terminal/ferramenta é disponibilizado. O backend descarta referências fora do conjunto recuperado e se abstém se a resposta não tiver citações verificáveis.
- Mensagens do usuário e trechos recuperados são enviados ao endpoint configurado quando a IA é usada. O projeto não persiste perguntas/respostas nesta versão. A redação baseada em padrões pode falhar e não constitui garantia de anonimização.

## Limites e riscos residuais

- Redaction por regex não cobre todos os formatos de credencial; o texto bruto existe transitoriamente em memória durante a skill. Padrões não reconhecidos, formatos novos, credenciais fragmentadas ou valores codificados podem escapar da detecção.
- A API não tem autenticação. Não a exponha em redes compartilhadas ou na internet.
- O ZIP inteiro fica temporariamente em memória dentro do limite compactado. A árvore recursiva é recebida como resposta JSON; se o GitHub truncá-la, o cliente percorre subárvores dentro de um limite de consultas. Repositórios que excedem esses limites geram uma análise parcial explicitamente sinalizada. Arquivos especialmente malformados podem atingir comportamentos de parser não previstos; mantenha dependências atualizadas.
- O algoritmo não valida credenciais, não consulta advisories e não mede explorabilidade de achados.
- Rate limits do GitHub podem interromper ingestão. Configurar `GITHUB_TOKEN` reduz o risco de rate limit, mas não habilita repositórios privados.
- `BackgroundTasks` roda dentro do processo API e não dá durabilidade após reinício.
- A mitigação de prompt injection é por instrução e arquitetura mínima, não garantia formal. O modelo ainda pode interpretar incorretamente contexto ou produzir conclusão errada; respostas devem ser verificadas nos links do commit. O provedor externo recebe os trechos recuperados redigidos, portanto não envie código cujo compartilhamento não seja autorizado.

## Uso seguro

Execute localmente e mantenha as portas vinculadas ao loopback. Não use credenciais de produção no arquivo `.env`. Trate achados como pendentes de revisão. Não conclua que arquivos ignorados foram revisados ou que a ausência de achados prova ausência de vulnerabilidades.
