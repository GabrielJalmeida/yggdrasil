# ADR-003 — Análise somente de leitura e sem execução do alvo

- **Estado:** aceito para o MVP
- **Data:** 26/10/2026

## Contexto

O sistema processa repositórios públicos desconhecidos e pode encontrar arquivos malformados, segredos e instruções hostis.

## Decisão

A análise utiliza metadados, arquivo compactado com fallback para árvore GitHub/leitura individual, parsing estático e regras determinísticas. Não executa scripts, instalações, builds, hooks ou testes do repositório analisado. A ingestão só usa hosts GitHub fixos, recusa redirecionamentos e aplica limites explícitos a arquivos e conteúdo.

## Consequências

- Menor superfície de execução arbitrária.
- Resultados dinâmicos, precisão de chamadas complexas e testes em runtime ficam fora do MVP.
- Arquivos não suportados e relações inferidas precisam ficar visíveis como limitações.
