"""Run the lightweight retrieval benchmark and write a transparent report."""

import os
import sys
from datetime import date
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.seed_data import seed_all
from app.evals.evaluator import evaluate_retrieval


def run_evaluation() -> dict:
    database_url = os.getenv("DATABASE_URL", "sqlite:///./eleicoes2026.db")
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        seed_all(db)
        result = evaluate_retrieval(db)
    finally:
        db.close()
        engine.dispose()

    report_lines = [
        "# Retrieval Evaluation Report — Eleição IA 2026",
        f"Generated on: {date.today()}",
        "",
        "## Metric",
        f"- **Expected-source retrieval recall:** {result['score']}% "
        f"({result['successful']}/{result['total']})",
        f"- **Limitation:** {result['limitations']}",
        "",
        "## Results",
        "",
        "| ID | Question | Route | Expected source | Status |",
        "| :-- | :-- | :-- | :-- | :--: |",
    ]
    for item in result["results"]:
        status = "PASS" if item["success"] else "FAIL"
        report_lines.append(
            f"| {item['id']} | {item['query']} | {item['route']} | "
            f"{item['expected_source']} | {status} |"
        )

    report_path = Path(__file__).with_name("eval_report.md")
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    evaluation = run_evaluation()
    print(
        f"Retrieval recall: {evaluation['score']}% "
        f"({evaluation['successful']}/{evaluation['total']})"
    )
