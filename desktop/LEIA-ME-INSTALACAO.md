# Yggdrasil Desktop para Windows

## Iniciar

1. Extraia o ZIP completo para uma pasta gravável.
2. Execute `Yggdrasil.exe`.
3. Aguarde o estado **Servidor local pronto**. A interface abre no navegador padrão.
4. Mantenha a janela do Yggdrasil aberta enquanto utiliza a interface. Fechar a janela encerra o servidor local de forma controlada.

Não é necessário instalar Python, Node.js ou Docker. O aplicativo vincula a API somente a `127.0.0.1`; ele não foi feito para ser acessado pela rede local.

## IA opcional

Clique em **Configurar IA** na janela do inicializador. Informe a URL base, o identificador exato do modelo e, quando exigida, a chave da API. A chave é protegida pelo Windows DPAPI para o usuário atual e não é colocada no ZIP, na interface web, no JSON de preferências ou no log. Deixe o campo de chave vazio para conservar a chave já salva. Use **Remover chave salva** para apagá-la explicitamente.

A IA vem desabilitada quando não há configuração. O mapa estático, as referências e as skills determinísticas continuam disponíveis sem IA. Ao salvar as opções de IA, o inicializador reinicia a API para aplicar as mudanças.

O botão **Testar conexão** faz uma solicitação curta ao endpoint de listagem de modelos, sem enviar pergunta/prompt. Ele confirma conectividade/autenticação quando o provedor oferece esse endpoint; não garante que toda geração de resposta funcionará nem verifica semanticamente o identificador do modelo.

Para endpoints remotos, use HTTPS. HTTP só é aceito para serviços locais em loopback. Não use uma URL que carregue a chave em query string.

## Dados, backup e remoção

Os dados do usuário ficam fora da pasta do programa:

`%LOCALAPPDATA%\Yggdrasil\`

- `data\yggdrasil.db`: banco SQLite persistente;
- `settings.json`: opções de IA sem a chave;
- `ai-key.dpapi`: chave protegida pelo Windows para o usuário atual;
- `logs\runtime.log`: mensagens operacionais para diagnóstico, sem prompts ou chaves planejados nos registros;
- `desktop-port.txt`: porta local temporária, removida ao encerrar normalmente.

Para backup consistente, feche o Yggdrasil antes de copiar o banco e as preferências. A cópia da chave DPAPI funciona apenas no contexto do usuário Windows que a protegeu e não deve ser tratada como portável para outra conta/máquina. Para transferir a instalação, configure a chave novamente no destino.

Para remover os dados do usuário, feche o aplicativo e exclua `%LOCALAPPDATA%\Yggdrasil\` somente depois de confirmar que o backup está correto. Apagar essa pasta elimina análises, preferências e a chave protegida.

## Diagnóstico rápido

- **Servidor não iniciou:** abra a pasta de dados pelo inicializador e confira `logs\runtime.log`. Verifique se um antivírus/política local impediu a execução.
- **A porta está ocupada:** o inicializador escolhe uma porta de loopback livre ao abrir; feche instâncias antigas e tente novamente.
- **Banco inacessível:** confirme que o usuário tem permissão de escrita em `%LOCALAPPDATA%\Yggdrasil\data\` e que não existe outro processo mantendo o arquivo bloqueado.
- **Erro 401/403 na IA:** confira a chave e as permissões no painel do provedor.
- **Erro 429/503 na IA:** pode ser limitação ou indisponibilidade do provedor. Aguarde antes de tentar novamente.
- **Não aparece a interface:** mantenha o inicializador aberto, clique em **Abrir Yggdrasil** e verifique se o navegador está bloqueando `127.0.0.1`.

## Limitações da distribuição inicial

A aplicação é local e de usuário único, sem autenticação multiusuário, serviço Windows ou atualização automática. A análise permanece estática e focada no escopo descrito no README do projeto; não executa código do repositório analisado. A IA é opcional e envia apenas os trechos/evidências recuperados para o endpoint configurado quando o usuário faz uma pergunta e confirma o compartilhamento na interface.
