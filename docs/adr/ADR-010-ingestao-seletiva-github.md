# ADR-010 — Fallback de ingestão por árvore GitHub e blobs individuais

- **Estado:** aceito para o MVP 0.2.0
- **Data:** 26/10/2026

## Contexto

O download compactado evita muitas requisições e continua adequado para repositórios menores, mas repositórios com arquivo compactado acima de `MAX_ARCHIVE_BYTES` não podiam ser analisados. Simplesmente aumentar o limite aumentaria o pico de memória e não resolveria a necessidade de limitar o conteúdo-fonte realmente analisado.

## Decisão

- Manter o arquivo compactado como caminho primário limitado.
- Quando o limite de arquivo compactado for excedido, consultar a árvore do commit imutável usando o SHA da árvore extraído dos metadados do commit.
- Baixar individualmente somente blobs elegíveis para análise textual, sempre por host fixo e no commit analisado.
- Nunca seguir URLs devolvidas pelo conteúdo do repositório nem baixar submódulos automaticamente.
- Verificar caminho, tamanho declarado/recebido e SHA de blob Git SHA-1 quando aplicável.
- Se a resposta recursiva do GitHub for truncada, percorrer subárvores sem recursão, dentro de `MAX_TREE_DIRECTORIES` e `MAX_FILES`.
- Preservar limites de arquivo individual, conteúdo textual agregado e bytes declarados; tornar exclusões/falhas visíveis e nunca executar o alvo.
- Não encaminhar o token opcional de API ao host de conteúdo bruto.

## Alternativas consideradas

1. **Aumentar `MAX_ARCHIVE_BYTES`:** rejeitada como única solução, pois aumenta memória usada e ainda falha para projetos grandes.
2. **Sempre baixar arquivo por arquivo:** rejeitada como padrão, pois produz muitas requisições mesmo para projetos pequenos.
3. **Clonar e extrair o repositório:** rejeitada no MVP; adiciona dependência de Git/processos externos e aumenta a superfície de segurança.

## Consequências

- Projetos cujo ZIP excede o limite podem produzir um mapa útil sem armazenar o ZIP inteiro.
- A alternativa exige uma requisição por arquivo textual elegível e pode ser interrompida por rate limit ou pelos limites de escopo.
- Árvores de diretórios muito amplas ainda podem resultar em cobertura parcial, sempre sinalizada.
- A estratégia escolhida fica registrada no estado da análise e no relatório Markdown.
- Os testes locais cobrem esse caminho com um cliente GitHub simulado; o fallback real precisa ser validado contra a rede GitHub no ambiente de execução.
