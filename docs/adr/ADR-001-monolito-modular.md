# ADR-001 — Monólito modular para o MVP

- **Estado:** aceito para o MVP
- **Data:** 26/10/2026

## Contexto

O primeiro release precisa oferecer um caminho ponta a ponta útil sem introduzir infraestrutura distribuída antes de medir o volume de trabalho.

## Decisão

Usar uma única API FastAPI com camadas separadas para rotas, orquestração, domínio, ingestão, parsing, persistência e relatório. O frontend é um aplicativo React separado por processo de desenvolvimento, mas o produto não é decomposto em serviços backend.

## Consequências

- Menos infraestrutura para instalar e depurar localmente.
- `BackgroundTasks` basta para o primeiro caminho, mas não é uma fila durável.
- Uma fila/worker separado será reavaliado quando houver requisitos de recuperação, paralelismo ou volume medido.
