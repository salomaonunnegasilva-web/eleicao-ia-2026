import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.rag.retrieval import retrieve_hybrid_chunks


QUESTIONS_PATH = Path(__file__).with_name("test_questions.json")


def evaluate_retrieval(db: Session) -> dict:
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    results = []
    successful = 0

    for question in questions:
        chunks = retrieve_hybrid_chunks(
            db,
            question["query"],
            limit=4,
            source_types=("demo_calendar", "demo_policy_scenario"),
        )
        titles = list(dict.fromkeys(chunk["title"] for chunk in chunks))
        success = any(
            question["expected_source"].casefold() in title.casefold()
            for title in titles
        )
        successful += int(success)
        results.append(
            {
                "id": question["id"],
                "query": question["query"],
                "expected_source": question["expected_source"],
                "retrieved_sources": titles,
                "route": "demo_retrieval",
                "success": success,
            }
        )

    total = len(results)
    return {
        "metric": "expected-source retrieval recall",
        "successful": successful,
        "total": total,
        "score": round((successful / total) * 100, 2) if total else 0.0,
        "results": results,
        "limitations": (
            "This benchmark validates routing and retrieval against a small synthetic "
            "dataset. It is not a RAGAS evaluation and does not measure factual accuracy."
        ),
    }
