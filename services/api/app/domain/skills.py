"""Small, deterministic MVP skills. These routines inspect text; they never execute the target."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.domain.secrets import SecretCandidate, detect_secret_candidates
from app.infrastructure.archive import ArchiveArtifact


@dataclass(slots=True)
class FindingData:
    skill_id: str
    skill_version: str
    finding_key: str
    category: str
    severity: str
    status: str
    confidence_label: str
    title: str
    summary: str
    impact: str
    recommendation: str
    limitations: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)


def _finding_key(skill_id: str, path: str, line: int, category: str) -> str:
    digest = hashlib.sha256(f"{skill_id}:{path}:{line}:{category}".encode()).hexdigest()[:16]
    return f"{skill_id}:{digest}"


_ENVIRONMENT_SAMPLE_NAMES = {
    ".env.example", ".env.sample", ".env.template", ".env.dist",
}


def _is_versioned_environment_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    if any(
        name == sample or name.startswith(f"{sample}.")
        for sample in _ENVIRONMENT_SAMPLE_NAMES
    ):
        return False
    return name == ".env" or name.startswith(".env.")


def _environment_file_finding(path: str, commit_sha: str) -> FindingData:
    return FindingData(
        skill_id="appsec.secrets-detection",
        skill_version="0.2.0",
        finding_key=_finding_key(
            "appsec.secrets-detection", path, 0, "environment_file_present"
        ),
        category="security",
        severity="MEDIUM",
        status="needs_review",
        confidence_label="high",
        title="Arquivo de ambiente versionado",
        summary=(
            "Um arquivo de ambiente está presente no snapshot do repositório. Isso não confirma "
            "que exista uma credencial real, mas o arquivo merece revisão porque pode conter "
            "configurações privadas ou segredos."
        ),
        impact=(
            "Se o arquivo contiver valores sensíveis, eles podem ficar acessíveis a qualquer pessoa "
            "com acesso ao repositório e ao histórico da revisão."
        ),
        recommendation=(
            "Revise o arquivo localmente. Se contiver credenciais reais, revogue/rotacione os valores "
            "expostos, retire o arquivo do versionamento e use variáveis de ambiente ou um gerenciador "
            "de segredos. Mantenha arquivos de exemplo apenas com placeholders."
        ),
        limitations=[
            "Este achado é baseado na presença e no nome do arquivo; não prova que contenha um segredo.",
            "A análise não valida credenciais nem tenta utilizá-las.",
        ],
        evidence=[{
            "path": path,
            "start_line": None,
            "end_line": None,
            "commit_sha": commit_sha,
            "evidence_type": "environment_file_presence",
            "redacted": True,
        }],
    )

def _secret_finding(path: str, candidate: SecretCandidate, commit_sha: str) -> FindingData:
    high_impact = candidate.category in {
        "private_key_block", "private_key_candidate", "cloud_access_key_candidate",
        "source_control_token_candidate", "cloud_api_key_candidate", "messaging_token_candidate",
        "messaging_webhook_candidate", "payment_provider_key_candidate", "bearer_token_candidate",
        "jwt_candidate", "url_credential_candidate", "token_candidate",
    }
    human_category = candidate.category.replace("_", " ")
    return FindingData(
        skill_id="appsec.secrets-detection",
        skill_version="0.2.0",
        finding_key=_finding_key("appsec.secrets-detection", path, candidate.start_line, candidate.category),
        category="security",
        severity="HIGH" if high_impact else "MEDIUM",
        status="needs_review",
        confidence_label="moderate",
        title="Possível credencial literal no código",
        summary=(
            f"Um padrão compatível com {human_category} foi identificado no arquivo, mas o valor foi "
            "omitido do resultado. Isso é um candidato a revisão, não uma confirmação de segredo válido."
        ),
        impact=(
            "Se o valor for uma credencial real e estiver ativo, alguém com acesso ao repositório pode "
            "conseguir usar a conta, serviço ou recurso associado."
        ),
        recommendation=(
            "Verifique o valor localmente sem copiá-lo para logs ou tickets. Se for real, revogue/rotacione, "
            "remova-o do código e do histórico conforme a política da organização e use variáveis de ambiente "
            "ou um gerenciador de segredos."
        ),
        limitations=[
            "Detecção estática por padrões; falsos positivos são possíveis.",
            "O Yggdrasil não validou a credencial nem tentou utilizá-la.",
            "O valor encontrado não é incluído no achado, nos logs ou no relatório.",
        ],
        evidence=[
            {
                "path": path,
                "start_line": candidate.start_line,
                "end_line": candidate.end_line,
                "commit_sha": commit_sha,
                "evidence_type": candidate.evidence_type,
                "redacted": True,
            }
        ],
    )


def run_initial_skills(
    files: list[ArchiveArtifact],
    commit_sha: str,
    requested_skill_ids: list[str] | None = None,
    *,
    on_file_scanned: Callable[[str, str], None] | None = None,
) -> tuple[list[FindingData], list[str]]:
    """Execute only registered MVP skills and return structured findings plus warnings."""
    supported = {"appsec.secrets-detection", "engineering.test-inventory"}
    requested = set(supported if requested_skill_ids is None else requested_skill_ids)
    unknown = sorted(requested - supported)
    warnings = [f"Skill não habilitada no MVP e ignorada: {skill_id}" for skill_id in unknown]
    enabled = requested & supported
    findings: list[FindingData] = []

    if "appsec.secrets-detection" in enabled:
        for artifact in files:
            if _is_versioned_environment_file(artifact.path):
                findings.append(_environment_file_finding(artifact.path, commit_sha))
            if artifact.raw_content is None or artifact.eligibility_status != "eligible":
                continue
            if on_file_scanned is not None:
                on_file_scanned(artifact.path, "appsec.secrets-detection")
            for candidate in detect_secret_candidates(artifact.raw_content):
                findings.append(_secret_finding(artifact.path, candidate, commit_sha))

    if "engineering.test-inventory" in enabled:
        if on_file_scanned is not None:
            for artifact in files:
                if artifact.eligibility_status == "eligible" and artifact.path.endswith((".py", ".pyi")):
                    on_file_scanned(artifact.path, "engineering.test-inventory")
        test_files = [
            artifact.path for artifact in files
            if artifact.eligibility_status == "eligible"
            and artifact.path.endswith((".py", ".pyi"))
            and (
                artifact.path.startswith("tests/")
                or "/tests/" in artifact.path
                or artifact.path.rsplit("/", 1)[-1].startswith("test_")
            )
        ]
        python_files = [
            artifact.path for artifact in files
            if artifact.eligibility_status == "eligible" and artifact.path.endswith((".py", ".pyi"))
        ]
        if python_files and not test_files:
            findings.append(
                FindingData(
                    skill_id="engineering.test-inventory",
                    skill_version="0.1.0",
                    finding_key=_finding_key("engineering.test-inventory", "<repository>", 0, "tests_not_identified"),
                    category="quality",
                    severity="IMPROVEMENT",
                    status="needs_review",
                    confidence_label="low",
                    title="Nenhum arquivo de teste reconhecido no escopo",
                    summary=(
                        "A análise não identificou arquivos Python com as convenções de nome/localização "
                        "mais comuns para testes no conjunto de arquivos analisado."
                    ),
                    impact="Sem testes identificáveis, mudanças podem ter menos proteção automatizada visível.",
                    recommendation=(
                        "Confirme onde os testes ficam no projeto e se usam convenções não reconhecidas. "
                        "Considere adicionar testes para os fluxos críticos; este achado não mede cobertura."
                    ),
                    limitations=[
                        "O resultado não prova que o projeto não possui testes.",
                        "A skill procura convenções simples de arquivos Python e não executa testes.",
                        "Arquivos ignorados por política não foram considerados.",
                    ],
                    evidence=[
                        {
                            "path": path,
                            "start_line": None,
                            "end_line": None,
                            "commit_sha": commit_sha,
                            "evidence_type": "inventory_summary",
                        }
                        for path in python_files[:10]
                    ],
                )
            )
    # Finding keys intentionally group detections by skill, file, line and category. A line can
    # contain more than one matching literal (for example, two assignments separated by `;`).
    # Coalesce those into one line-level finding so persistence constraints stay deterministic.
    deduplicated: dict[str, FindingData] = {}
    for finding in findings:
        existing = deduplicated.get(finding.finding_key)
        if existing is None:
            deduplicated[finding.finding_key] = finding
            continue
        evidence_seen = {
            (
                evidence.get("path"), evidence.get("start_line"), evidence.get("end_line"),
                evidence.get("commit_sha"), evidence.get("evidence_type"),
            )
            for evidence in existing.evidence
        }
        for evidence in finding.evidence:
            signature = (
                evidence.get("path"), evidence.get("start_line"), evidence.get("end_line"),
                evidence.get("commit_sha"), evidence.get("evidence_type"),
            )
            if signature not in evidence_seen:
                existing.evidence.append(evidence)
                evidence_seen.add(signature)
        existing.limitations = list(dict.fromkeys(existing.limitations + finding.limitations))

    return list(deduplicated.values()), warnings
