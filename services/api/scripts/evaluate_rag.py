#!/usr/bin/env python3
"""Evaluate Yggdrasil evidence retrieval against a local labelled corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from sqlalchemy import select  # noqa: E402

from app.application.rag_evaluation import (
    evaluate_corpus,
    find_latest_completed_analysis,
    load_corpus,
)  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import AnalysisRun  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Avalia a recuperação lexical/estrutural sem chamar um provedor de IA."
    )
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--analysis-id", help="ID de uma análise persistida e concluída.")
    selector.add_argument("--latest", action="store_true", help="Seleciona a análise concluída mais recente do repositório declarado no corpus.")
    parser.add_argument(
        "--cases",
        default=str(API_ROOT / "evaluation" / "corpora" / "borax.json"),
        help="Caminho para o corpus JSON (padrão: corpus inicial de Borax).",
    )
    parser.add_argument("--output", help="Arquivo JSON opcional para salvar o relatório sem trechos de código.")
    parser.add_argument("--top-k", default="1,3,5", help="Valores k separados por vírgula (padrão: 1,3,5).")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        k_values = tuple(sorted({int(value.strip()) for value in args.top_k.split(",") if value.strip()}))
        if not k_values or any(value < 1 for value in k_values):
            raise ValueError("--top-k deve conter inteiros positivos separados por vírgula.")
        corpus = load_corpus(args.cases)
    except ValueError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        if args.latest:
            try:
                run = find_latest_completed_analysis(db, corpus)
            except ValueError as exc:
                print(f"Erro de configuração: {exc}", file=sys.stderr)
                return 2
            if run is None:
                print(
                    f"Erro: nenhuma análise concluída encontrada para {corpus.target_repository!r} no banco configurado.",
                    file=sys.stderr,
                )
                return 2
            print(f"Análise selecionada por --latest: {run.id}")
        else:
            run = db.scalar(select(AnalysisRun).where(AnalysisRun.id == args.analysis_id))
        if run is None:
            print("Erro: análise não encontrada no banco configurado.", file=sys.stderr)
            return 2
        if run.status not in {"completed", "completed_with_warnings"}:
            print(f"Erro: a análise precisa estar concluída (estado atual: {run.status}).", file=sys.stderr)
            return 2
        try:
            report = evaluate_corpus(db, run, corpus, k_values=k_values)
        except ValueError as exc:
            print(f"Erro na avaliação: {exc}", file=sys.stderr)
            return 2

    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(encoded + "\n", encoding="utf-8")
        print(f"Relatório salvo em: {output_path}")

    metrics = report["metrics"]
    print(f"Corpus: {report['corpus']['id']} v{report['corpus']['version']}")
    print(f"Snapshot: {report['analysis']['repository']} @ {report['analysis']['commit_sha']}")
    print(f"Casos pontuados: {metrics['scored_cases']}/{metrics['cases_total']}")
    for name in ("intent_accuracy", "mrr", "hit_at_1", "hit_at_3", "hit_at_5", "recall_at_1", "recall_at_3", "recall_at_5"):
        if name in metrics:
            print(f"{name}: {metrics[name]}")
    if metrics["invalid_annotations"]:
        print(f"Aviso: {metrics['invalid_annotations']} caso(s) possuem caminhos esperados ausentes e foram excluídos das métricas de recuperação.")
    if report["warnings"]:
        for warning in report["warnings"]:
            print(f"Aviso: {warning}")
    if not args.output:
        print("\nRelatório detalhado (JSON):")
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
