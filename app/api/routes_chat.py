import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.main import get_db
from app.db.models import ChatLog
from app.rag.retrieval import classify_query, retrieve_hybrid_chunks
from app.rag.answer_generation import generate_grounded_answer
from app.forecasting.polling_average import calculate_polling_average
from app.forecasting.simulations import run_monte_carlo_simulation
from app.data_sources.official_answering import (
    build_calendar_chunks,
    build_integrity_chunks,
    build_legislative_chunks,
    legal_integrity_unavailable_result,
    official_evidence_unavailable_result,
    policy_evidence_unavailable_result,
)
from app.data_sources.tse_client import TSEDataError

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

    if route == "official_calendar":
        try:
            context_chunks = build_calendar_chunks(query_text, limit=4)
        except TSEDataError:
            context_chunks = []
        generation_result = (
            generate_grounded_answer(
                db=db,
                query_text=query_text,
                context_chunks=context_chunks,
            )
            if context_chunks
            else official_evidence_unavailable_result(query_text)
        )
    elif route == "official_legislative":
        context_chunks = build_legislative_chunks(query_text)
        generation_result = (
            generate_grounded_answer(
                db=db,
                query_text=query_text,
                context_chunks=context_chunks,
            )
            if context_chunks
            else official_evidence_unavailable_result(query_text)
        )
    elif route == "official_policy":
        context_chunks = retrieve_hybrid_chunks(
            db,
            query_text,
            limit=4,
            source_types=(
                "official_candidate_program",
                "official_party_program",
                "official_public_statement",
            ),
        )
        generation_result = (
            generate_grounded_answer(
                db=db,
                query_text=query_text,
                context_chunks=context_chunks,
            )
            if context_chunks
            else policy_evidence_unavailable_result(query_text)
        )
    elif route == "official_integrity":
        context_chunks = build_integrity_chunks(query_text)
        generation_result = (
            generate_grounded_answer(
                db=db,
                query_text=query_text,
                context_chunks=context_chunks,
            )
            if context_chunks
            else legal_integrity_unavailable_result(query_text)
        )
    elif route == "forecast":
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
    else:
        context_chunks = retrieve_hybrid_chunks(
            db,
            query_text,
            limit=4,
            source_types=(
                "official_candidate_program",
                "official_party_program",
                "official_public_statement",
                "official_tse_document",
            ),
        )
        generation_result = (
            generate_grounded_answer(
                db=db,
                query_text=query_text,
                context_chunks=context_chunks,
            )
            if context_chunks
            else official_evidence_unavailable_result(query_text)
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
