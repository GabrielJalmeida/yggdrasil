# Skill — Inventário de arquivos de teste

- **ID:** `engineering.test-inventory`
- **Versão:** `0.1.0`
- **Modo:** regra determinística
- **Estado:** habilitada no MVP

## Objetivo

Identificar arquivos Python que seguem convenções simples de nome/localização de testes, sem executá-los e sem inferir cobertura.

## Critério

Considera arquivos `.py`/`.pyi` sob `tests/`, subdiretórios `tests/` ou nomes que começam por `test_`. Se houver arquivos Python elegíveis e nenhum teste for reconhecido, cria um achado de melhoria com baixa confiança e limitações explícitas.

## Não faz

Não mede cobertura, não prova que os testes faltam, não executa pytest e não garante que o arquivo encontrado contenha testes válidos.
