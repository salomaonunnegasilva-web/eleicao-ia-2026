import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.main import get_db
from app.config import settings
from app.db.models import Candidate, ChatLog
from app.rag.retrieval import classify_query, retrieve_hybrid_chunks
from app.rag.answer_generation import generate_grounded_answer
from app.forecasting.polling_average import calculate_polling_average
from app.forecasting.simulations import run_monte_carlo_simulation
from app.text_utils import normalize_text

router = APIRouter()

class ChatRequest(BaseModel):
    query: str

class ChatResponse(BaseModel):
    query: str
    route: str
    answer: str
    provider: str
    model: str
    sources: list[dict]
    polling_summary: dict | None = None
    simulation_summary: dict | None = None


def _candidate_profile_answer(db: Session, query_text: str) -> dict | None:
    normalized_query = normalize_text(query_text)
    candidates = db.query(Candidate).all()
    matched = next(
        (
            candidate
            for candidate in candidates
            if normalize_text(candidate.name) in normalized_query
            or any(
                len(token) > 3 and token in normalized_query
                for token in normalize_text(candidate.name).split()
            )
        ),
        None,
    )
    if matched is None or matched.status == "Categoria de resposta":
        return None

    party = matched.party.abbreviation if matched.party else "sem partido informado"
    answer = (
        f"**{matched.name}** está associado ao partido **{party}** neste cenário "
        f"demonstrativo. Status no dataset: **{matched.status}**. "
        "Esses dados servem apenas para demonstrar o fluxo técnico do portfólio."
    )
    return {
        "answer": answer,
        "provider": "local",
        "model": "candidate-registry",
        "sources_used": [
            {
                "title": "Cadastro de cenário eleitoral demonstrativo",
                "url": None,
                "publication_date": None,
                "author": "Eleição IA 2026",
                "synthetic": True,
            }
        ],
    }


@router.post("/chat", response_model=ChatResponse)
def handle_chat_query(req: ChatRequest, db: Session = Depends(get_db)):
    query_text = req.query.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Query text cannot be empty.")

    # 1. Query Router
    route = classify_query(query_text)

    # 2. Retrieve resources based on route
    context_chunks = []
    polling_context = None
    simulation_context = None

    if route == "candidate_profile":
        profile_result = _candidate_profile_answer(db, query_text)
        if profile_result is None:
            raise HTTPException(
                status_code=404,
                detail="Candidate not found in the demonstration registry.",
            )
        generation_result = profile_result
    else:
        if route in ("rag", "hybrid"):
            context_chunks = retrieve_hybrid_chunks(db, query_text, limit=4)

        if route in ("forecast", "hybrid"):
            polling_context = calculate_polling_average(
                db,
                scenario_name="Estimulada Turno 1",
                round_num=1,
            )
            simulation_context = run_monte_carlo_simulation(
                db,
                scenario_name="Estimulada Turno 1",
                round_num=1,
            )

        generation_result = generate_grounded_answer(
            db=db,
            query_text=query_text,
            context_chunks=context_chunks,
            polling_context=polling_context,
            simulation_context=simulation_context,
        )

    # 4. Save chat logs for transparency and auditability
    log = ChatLog(
        user_question=query_text,
        retrieved_sources_json=generation_result.get("sources_used", []),
        answer=generation_result["answer"],
        model_used=f"{generation_result.get('provider')}/{generation_result.get('model')}"
    )
    db.add(log)
    db.commit()

    return ChatResponse(
        query=query_text,
        route=route,
        answer=generation_result["answer"],
        provider=generation_result.get("provider", "mock"),
        model=generation_result.get("model", "local"),
        sources=generation_result.get("sources_used", []),
        polling_summary=polling_context,
        simulation_summary=simulation_context
    )
