"""Markdown export generated from persisted analysis facts, not free-form model output."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.config import settings


def _github_file_url(repository_url: str, commit_sha: str, path: str, start: int | None, end: int | None) -> str:
    url = f"{repository_url}/blob/{commit_sha}/{path}"
    if start:
        url += f"#L{start}"
        if end and end != start:
            url += f"-L{end}"
    return url


def generate_markdown(
    *,
    repository: Any,
    snapshot: Any,
    analysis: Any,
    source_files: list[Any],
    nodes: list[Any],
    edges: list[Any],
    findings: list[Any],
) -> str:
    """Build a report that remains useful when the provider of AI is not configured."""
    node_counts = Counter(node.node_type for node in nodes)
    relation_counts = Counter(edge.relation_type for edge in edges)
    eligible = [item for item in source_files if item.eligibility_status == "eligible"]
    ignored = [item for item in source_files if item.eligibility_status != "eligible"]
    modules = sorted(
        (node for node in nodes if node.node_type == "module"), key=lambda item: item.label.lower()
    )
    endpoints = sorted(
        (node for node in nodes if node.node_type == "endpoint"),
        key=lambda item: (item.source_file_id or "", item.start_line or 0),
    )
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    progress = getattr(analysis, "progress_metadata", {}) or {}
    ingestion_method = progress.get("ingestion_method", "archive")
    ingestion_label = (
        "árvore GitHub com leitura seletiva"
        if ingestion_method == "github_tree"
        else "arquivo compactado"
    )
    warnings = getattr(analysis, "warning_summary", []) or []
    lines: list[str] = [
        "# Yggdrasil Repository Map",
        "",
        "> Mapa estático de conhecimento do repositório. Este documento não certifica ausência de vulnerabilidades.",
        "",
        "## 1. Metadados da análise",
        "",
        f"- **Gerado em:** {now}",
        f"- **Versão do Yggdrasil:** {settings.app_version}",
        f"- **ID da análise:** `{analysis.id}`",
        f"- **Estado:** `{analysis.status}`",
        f"- **Etapa final:** `{analysis.stage}`",
        f"- **Commit fixado:** `{snapshot.commit_sha}`",
        f"- **Referência solicitada:** `{snapshot.requested_ref}`",
        f"- **Estratégia de ingestão:** {ingestion_label}",
        "- **Execução do código-alvo:** não realizada",
        "- **IA externa:** não utilizada neste MVP",
        "",
        "## 2. Resumo executivo",
        "",
        f"O inventário contém **{len(source_files)} arquivos**, dos quais **{len(eligible)}** foram elegíveis para leitura textual dentro dos limites configurados. Foram criados **{len(nodes)} nós**, **{len(edges)} relações** e registrados **{len(findings)} achados para revisão**.",
        "",
        "Este resultado é uma visão inicial baseada em inventário e parsing estático de Python. Uma relação inferida é uma pista, e não uma observação de execução.",
        "",
        "## 3. Escopo e limitações",
        "",
        "- Somente repositórios públicos do GitHub são aceitos nesta versão.",
        "- O commit analisado é fixo; uma branch pode mudar depois da análise sem alterar este relatório.",
        "- Nenhum script, pacote, build, hook ou teste do repositório-alvo foi executado.",
        "- A análise Python usa `ast` e cobre definições, imports internos simples, decorators de endpoint e chamadas locais com resolução limitada.",
        "- Arquivos binários, arquivos acima dos limites e diretórios gerados/vendor podem ser ignorados.",
        "- Detecção estática não confirma que uma credencial é válida nem que um padrão é explorável.",
        "- Perguntas com IA/RAG não estão habilitadas neste MVP.",
        "",
    ]
    if warnings:
        lines.extend(["### Avisos da análise", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
    lines.extend([
        "## 4. Repositório e commit analisado",
        "",
        f"- **Repositório:** [{repository.owner}/{repository.name}]({repository.canonical_url})",
        f"- **Commit:** [`{snapshot.commit_sha}`]({repository.canonical_url}/commit/{snapshot.commit_sha})",
        f"- **Branch padrão observada:** `{snapshot.default_branch or 'não informada'}`",
        f"- **Descrição:** {repository.description or 'não informada'}",
        f"- **Mensagem do commit:** {snapshot.metadata_json.get('commit_message') or 'não informada'}",
        "",
        "## 5. Inventário e linguagens",
        "",
        "| Item | Quantidade |",
        "|---|---:|",
        f"| Arquivos inventariados | {len(source_files)} |",
        f"| Arquivos elegíveis para leitura | {len(eligible)} |",
        f"| Arquivos ignorados/não suportados | {len(ignored)} |",
        f"| Arquivos Python parseados | {sum(1 for item in source_files if item.language == 'Python' and item.parse_status == 'parsed')} |",
        f"| Nós do grafo | {len(nodes)} |",
        f"| Relações do grafo | {len(edges)} |",
        "",
        "### Tipos de nós",
        "",
    ])
    if node_counts:
        lines.extend(f"- `{kind}`: {count}" for kind, count in sorted(node_counts.items()))
    else:
        lines.append("Nenhum nó foi produzido.")
    lines.extend(["", "## 6. Estrutura e módulos Python", ""])
    if modules:
        lines.extend(
            f"- [`{node.label}`]({_github_file_url(repository.canonical_url, snapshot.commit_sha, node.properties.get('path', ''), None, None)})"
            for node in modules[:200]
        )
        if len(modules) > 200:
            lines.append(f"- … mais {len(modules) - 200} módulos omitidos desta lista resumida.")
    else:
        lines.append("Nenhum módulo Python elegível foi analisado.")

    lines.extend(["", "## 7. Endpoints reconhecidos por decorators", ""])
    if endpoints:
        for endpoint in endpoints[:200]:
            related_file = next((item for item in source_files if item.id == endpoint.source_file_id), None)
            path = related_file.path if related_file else ""
            link = _github_file_url(repository.canonical_url, snapshot.commit_sha, path, endpoint.start_line, endpoint.end_line)
            lines.append(f"- [`{endpoint.label}`]({link}) — `{path}:{endpoint.start_line or '?'}`")
    else:
        lines.append("Nenhum decorator de rota reconhecido no escopo analisado.")

    lines.extend(["", "## 8. Tipos de relações", ""])
    if relation_counts:
        lines.extend(f"- `{kind}`: {count}" for kind, count in sorted(relation_counts.items()))
    else:
        lines.append("Nenhuma relação foi produzida.")
    lines.extend([
        "",
        "Relações `deterministic` vêm de uma estrutura sintática ou declaração explícita. Relações `inferred` são aproximações estáticas; neste MVP, chamadas resolvidas apenas pelo nome do símbolo são sempre marcadas como inferidas.",
        "",
        "## 9. Achados priorizados",
        "",
    ])
    severity_order = {"BLOCKER": 0, "CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4, "IMPROVEMENT": 5}
    for finding in sorted(findings, key=lambda item: (severity_order.get(item.severity, 99), item.title.lower())):
        lines.extend([
            f"### {finding.severity} — {finding.title}",
            "",
            f"- **Skill:** `{finding.skill_id}` v`{finding.skill_version}`",
            f"- **Estado:** `{finding.status}`",
            f"- **Confiança qualitativa:** `{finding.confidence_label}`",
            f"- **Categoria:** `{finding.category}`",
            "",
            finding.summary,
            "",
            f"**Impacto potencial:** {finding.impact}",
            "",
            f"**Recomendação:** {finding.recommendation}",
            "",
        ])
        if finding.evidence:
            lines.append("**Evidências:**")
            for evidence in finding.evidence:
                path = evidence.get("path")
                start = evidence.get("start_line")
                end = evidence.get("end_line")
                sha = evidence.get("commit_sha") or snapshot.commit_sha
                if path:
                    link = _github_file_url(repository.canonical_url, sha, str(path), start, end)
                    location = f"[{path}{':' + str(start) if start else ''}]({link})"
                else:
                    location = "Resumo do inventário"
                lines.append(f"- {location} — `{evidence.get('evidence_type', 'evidence')}`; valores sensíveis omitidos.")
            lines.append("")
        if finding.limitations:
            lines.append("**Limitações:**")
            lines.extend(f"- {limitation}" for limitation in finding.limitations)
            lines.append("")
    if not findings:
        lines.append("Nenhum achado foi produzido pelas skills habilitadas. Isso não significa ausência de defeitos ou vulnerabilidades.")

    lines.extend(["", "## 10. Arquivos ignorados ou não interpretados", ""])
    if ignored:
        lines.extend(
            f"- `{item.path}` — `{item.eligibility_status}/{item.parse_status}`; {item.metadata_json.get('ignored_reason', 'fora do escopo textual inicial')}"
            for item in ignored[:300]
        )
        if len(ignored) > 300:
            lines.append(f"- … mais {len(ignored) - 300} itens omitidos desta listagem.")
    else:
        lines.append("Nenhum arquivo foi marcado como ignorado pelo filtro de elegibilidade.")

    lines.extend([
        "",
        "## 11. Metodologia, versões e fontes",
        "",
        "- **Parser Python:** biblioteca padrão `ast`; análise sintática, sem importação/execução do alvo.",
        "- **Higiene de segredos:** padrões estáticos conservadores; valores prováveis são redigidos antes de persistir o conteúdo textual.",
        "- **Skills:** `appsec.secrets-detection` v0.2.0 e `engineering.test-inventory` v0.1.0, conforme configuração da análise.",
        "- **Relatório:** gerado a partir de dados persistidos nesta análise.",
        "- **Limites:** inventário, arquivo compactado, tamanho por arquivo e conteúdo textual são limitados; arquivos grandes podem usar leitura seletiva pela árvore GitHub.",
        "",
        "## 12. Glossário",
        "",
        "- **Determinístico:** resultado diretamente reproduzível a partir de estrutura ou conteúdo identificado.",
        "- **Inferido:** relação estática provável que precisa de validação, especialmente em linguagens dinâmicas.",
        "- **Achado:** item para revisão, não necessariamente defeito confirmado.",
        "- **Snapshot:** visão do repositório associada a um commit SHA imutável.",
        "",
        "---",
        "",
        "Relatório gerado pelo Yggdrasil. Verifique os links e revise achados antes de tomar decisões de engenharia ou segurança.",
        "",
    ])
    return "\n".join(lines)
