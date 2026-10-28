from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.domain.secrets import redact_secrets
from app.domain.skills import run_initial_skills
from app.infrastructure.archive import ArchiveArtifact

DEFAULT_CORPUS = Path(__file__).resolve().parents[1] / "evaluation" / "corpora" / "skill-quality-cases.json"


def _artifact(file_row: dict[str, Any]) -> ArchiveArtifact:
    raw = str(file_row["content"])
    path = str(file_row["path"])
    extension = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    language = {"py": "Python", "pyi": "Python", "toml": "TOML", "json": "JSON", "yml": "YAML", "yaml": "YAML"}.get(extension)
    return ArchiveArtifact(
        path=path,
        size_bytes=len(raw.encode("utf-8")),
        language=language,
        eligibility_status="eligible",
        parse_status="parsed" if language == "Python" else "unsupported",
        redacted_content=redact_secrets(raw),
        raw_content=raw,
    )


def evaluate_case(case: dict[str, Any], commit_sha: str = "a" * 40) -> dict[str, Any]:
    artifacts = [_artifact(item) for item in case.get("files", [])]
    skill_ids = list(case.get("skill_ids", []))
    findings, warnings = run_initial_skills(artifacts, commit_sha, skill_ids)
    expected = str(case.get("expected"))
    finding_skills = sorted({item.skill_id for item in findings})
    limitations = [line for item in findings for line in item.limitations]
    titles = [item.title for item in findings]
    if expected == "finding":
        passed = bool(findings) and any(item.skill_id.startswith("appsec.") for item in findings)
    elif expected == "clean":
        passed = not findings
    elif expected == "review_only":
        passed = bool(findings) and all(item.status == "needs_review" for item in findings) and any("falsos positivos" in item.casefold() or "não prova" in item.casefold() for item in limitations)
    elif expected == "tests_recognized":
        passed = not any("Nenhum arquivo de teste reconhecido" in title for title in titles)
    elif expected == "test_inventory_review":
        passed = any("Nenhum arquivo de teste reconhecido" in title for title in titles) and any(item.confidence_label == "low" for item in findings) and any("não prova que o projeto não possui testes" in item.casefold() for item in limitations)
    else:
        passed = False
    return {
        "id": str(case.get("id", "unknown")),
        "skill_ids": skill_ids,
        "expected": expected,
        "passed": passed,
        "findings_count": len(findings),
        "finding_skills": finding_skills,
        "warnings_count": len(warnings),
        "review_only_findings": sum(item.status == "needs_review" for item in findings),
        "limitation_count": len(limitations),
    }


def evaluate_corpus(corpus_path: Path = DEFAULT_CORPUS) -> dict[str, Any]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = [evaluate_case(item) for item in corpus.get("cases", [])]
    passed = sum(bool(item["passed"]) for item in cases)
    return {
        "corpus_id": corpus.get("corpus_id"),
        "version": corpus.get("version"),
        "cases_total": len(cases),
        "cases_passed": passed,
        "cases_failed": len(cases) - passed,
        "quality_score": round(passed / len(cases), 4) if cases else None,
        "provider_calls": 0,
        "semantic_limitations": [
            "O benchmark mede contratos determinísticos das skills, não segurança absoluta do alvo.",
            "Casos ambíguos aprovados significam encaminhamento conservador para revisão humana.",
            "O inventário de testes não executa testes nem mede cobertura.",
        ],
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Avalia as skills determinísticas do Yggdrasil sem chamadas de IA.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_corpus(args.corpus)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    print(f"\nAvaliação de skills: {result['cases_passed']}/{result['cases_total']} casos aprovados; chamadas ao provedor: 0")
    return 0 if result["cases_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
