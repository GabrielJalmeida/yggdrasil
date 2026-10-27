# Skill — Detecção inicial de possíveis segredos

- **ID:** `appsec.secrets-detection`
- **Versão:** `0.2.0`
- **Modo:** análise estática determinística, nível de autoridade A (leitura/diagnóstico)
- **Estado:** habilitada no MVP

## Objetivo

Encontrar candidatos a credenciais que correspondam a padrões estreitos em arquivos textuais elegíveis, registrar localização/commit e evitar incluir o valor provável no achado.

## Entradas

Texto temporário do arquivo; caminho; commit SHA; política de elegibilidade.

## Procedimento

1. Inspecionar atribuições com nomes comuns (`API_KEY`, `PASSWORD`, `TOKEN`, `SECRET`, entre outros) e alguns formatos conhecidos de token/chave.
2. Ignorar placeholders óbvios reconhecidos pela regra inicial.
3. Retornar categoria e intervalo de linha, nunca o valor.
4. Redigir padrões reconhecidos antes de persistir o texto e antes de exportar relatório.
5. Cobrir valores citados e não citados em configurações, chaves JSON, credenciais embutidas em URLs, tokens Bearer/JWT e formatos comuns de provedores (AWS, Google, GitHub, Slack e Stripe).
6. Criar achado `needs_review`, com severidade potencial e confiança qualitativa; não afirmar que a credencial funciona.

## Saída

Achado com categoria, severidade potencial, confiança `moderate`, evidência (path/linhas/commit), impacto, recomendação e limitações.

## Limitações

- Falsos positivos e falsos negativos são esperados.
- Não há verificação externa nem tentativa de uso da credencial.
- A redação não cobre todos os formatos de segredo; não use como única barreira de proteção.
- Placeholders comuns como `user:password` em URLs de exemplo são ignorados pela triagem; isso não equivale a validação semântica do contexto.
- A severidade representa impacto potencial, não confirmação de exploração.

## Testes

Inclui testes para padrões positivos e negativos, variáveis de ambiente, URLs com credenciais, tokens de provedores e preservação das linhas durante redaction. A integração confirma que o valor de teste não chega à base, ao endpoint de nó, aos achados ou ao Markdown.
