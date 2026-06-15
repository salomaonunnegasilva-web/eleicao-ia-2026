import os
import re
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.models import Document, DocumentChunk
from app.rag.ingest import get_embedding
from app.text_utils import normalize_text

def classify_query(query_text: str) -> str:
    """
    Classifies the user query into:
    - 'forecast': if it asks about poll averages, trend lines, who is leading, probabilities.
    - 'candidate_profile': if it's a simple lookup for candidate parties/coalitions.
    - 'rag': if it's about policy positions, speeches, laws, proposals, etc. (Default)
    - 'hybrid': if it asks to compare candidates or combines multiple topics.
    """
    query_lower = normalize_text(query_text)

    document_research_phrases = [
        "registro de pesquisa",
        "pesquisas devem ser registradas",
        "prazo para pesquisa",
        "divulgacao de pesquisa",
        "calendario eleitoral",
        "data da eleicao",
        "dia da eleicao",
    ]
    if any(phrase in query_lower for phrase in document_research_phrases):
        return "rag"

    forecast_keywords = [
        "liderando", "na frente", "intencao de voto", "votos validos", "porcentagem",
        "probabilidade", "segundo turno", "cenario atual", "simulacao", "forecast",
        "media das pesquisas", "tendencia", "subiu", "caiu", "levantamentos"
    ]

    profile_keywords = [
        "quem e", "partido de", "partido do", "coligacao", "candidato do", "vice"
    ]

    is_forecast = any(k in query_lower for k in forecast_keywords)
    is_profile = any(k in query_lower for k in profile_keywords)

    if is_forecast and (
        "posicionamento" in query_lower
        or "proposta" in query_lower
        or "defende" in query_lower
        or "diz" in query_lower
        or "fala" in query_lower
    ):
        return "hybrid"
    elif is_forecast:
        return "forecast"
    elif is_profile and not ("proposta" in query_lower or "defende" in query_lower):
        return "candidate_profile"

    return "rag"

def get_vector_results(db: Session, embedding: list[float], limit: int = 10) -> list[dict]:
    """Retrieves top chunks based on vector distance using pgvector <=> (cosine distance)."""
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        query_vector = np.asarray(embedding, dtype=float)
        query_norm = np.linalg.norm(query_vector)
        if query_norm == 0:
            return []

        ranked = []
        rows = db.query(DocumentChunk).filter(DocumentChunk.embedding.isnot(None)).all()
        for chunk in rows:
            candidate_vector = np.asarray(chunk.embedding, dtype=float)
            candidate_norm = np.linalg.norm(candidate_vector)
            if candidate_norm == 0 or candidate_vector.shape != query_vector.shape:
                continue
            score = float(np.dot(query_vector, candidate_vector) / (query_norm * candidate_norm))
            ranked.append(
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "chunk_text": chunk.chunk_text,
                    "chunk_index": chunk.chunk_index,
                    "metadata": chunk.metadata_json,
                    "score": score,
                }
            )
        return sorted(ranked, key=lambda item: item["score"], reverse=True)[:limit]

    # Convert list[float] to string format for postgres vector: '[0.1, 0.2, ...]'
    emb_str = "[" + ",".join(map(str, embedding)) + "]"

    # We query document_chunks table. Since we might run in environments without pgvector
    # during dev tests, we use text() to execute the query safely.
    sql = text("""
        SELECT c.id, c.document_id, c.chunk_text, c.chunk_index, c.metadata_json,
               (c.embedding <=> CAST(:emb_str AS vector)) as distance
        FROM document_chunks c
        ORDER BY distance ASC
        LIMIT :limit
    """)
    try:
        res = db.execute(sql, {"emb_str": emb_str, "limit": limit}).all()
        return [
            {
                "chunk_id": r[0],
                "document_id": r[1],
                "chunk_text": r[2],
                "chunk_index": r[3],
                "metadata": r[4],
                "score": 1.0 - float(r[5]) # Convert cosine distance to cosine similarity
            }
            for r in res
        ]
    except Exception:
        # Fallback to no-vector search or return empty if pgvector not yet loaded
        # print("Vector search exception:", e)
        return []

def get_keyword_results(db: Session, query_text: str, limit: int = 10) -> list[dict]:
    """Retrieves top chunks using PostgreSQL Full Text Search (FTS) in Portuguese."""
    # Clean and split query text to generate tsquery syntax
    # e.g., 'reforma tributária' -> 'reforma | tributária'
    words = re.findall(r'\w+', normalize_text(query_text))
    if not words:
        return []

    # Exclude small words
    words = [w for w in words if len(w) > 2]
    if not words:
        words = re.findall(r'\w+', query_text) # Fallback to all words if all are short

    keyword_query = " | ".join(words)

    sql = text("""
        SELECT c.id, c.document_id, c.chunk_text, c.chunk_index, c.metadata_json,
               ts_rank_cd(to_tsvector('portuguese', c.chunk_text), to_tsquery('portuguese', :keyword_query)) as rank
        FROM document_chunks c
        WHERE to_tsvector('portuguese', c.chunk_text) @@ to_tsquery('portuguese', :keyword_query)
        ORDER BY rank DESC
        LIMIT :limit
    """)
    try:
        res = db.execute(sql, {"keyword_query": keyword_query, "limit": limit}).all()
        return [
            {
                "chunk_id": r[0],
                "document_id": r[1],
                "chunk_text": r[2],
                "chunk_index": r[3],
                "metadata": r[4],
                "score": float(r[5])
            }
            for r in res
        ]
    except Exception:
        # Fallback to simple LIKE search if full-text search breaks (e.g. on SQLite)
        # We split query text into keywords and check for any of them
        words = re.findall(r'\w+', normalize_text(query_text))
        # Exclude common stopwords to improve search accuracy
        stopwords = {"para", "como", "mais", "sobre", "qual", "quais", "onde", "quem", "como", "pela", "pelo", "uma", "esta", "este"}
        words = [w for w in words if len(w) > 2 and w.lower() not in stopwords]
        if not words:
            words = re.findall(r'\w+', query_text)

        if not words:
            return []

        # For each word, create a LIKE clause and a ranking score expression
        clauses = []
        score_parts = []
        for i in range(len(words)):
            clauses.append(f"LOWER(c.chunk_text) LIKE :w{i}")
            score_parts.append(f"CASE WHEN LOWER(c.chunk_text) LIKE :w{i} THEN 1 ELSE 0 END")

        where_clauses = " OR ".join(clauses)
        score_expr = " + ".join(score_parts)

        sql_like = text(f"""
            SELECT c.id, c.document_id, c.chunk_text, c.chunk_index, c.metadata_json,
                   ({score_expr}) as rank
            FROM document_chunks c
            WHERE {where_clauses}
            ORDER BY rank DESC
            LIMIT :limit
        """)

        params = {f"w{i}": f"%{word.lower()}%" for i, word in enumerate(words)}
        params["limit"] = limit

        try:
            res = db.execute(sql_like, params).all()
            return [
                {
                    "chunk_id": r[0],
                    "document_id": r[1],
                    "chunk_text": r[2],
                    "chunk_index": r[3],
                    "metadata": r[4],
                    "score": float(r[5])
                }
                for r in res
            ]
        except Exception:
            return []

def retrieve_hybrid_chunks(db: Session, query_text: str, limit: int = 5) -> list[dict]:
    """
    Executes vector and keyword searches, merges findings using Reciprocal Rank Fusion (RRF),
    and hydrates results with parent document metadata.
    """
    # 1. Get Vector Search results
    emb = get_embedding(query_text)
    vector_results = get_vector_results(db, emb, limit=limit*2)

    # 2. Get Keyword Search results
    keyword_results = get_keyword_results(db, query_text, limit=limit*2)

    # 3. Reciprocal Rank Fusion (RRF)
    # RRF score = sum(1 / (k + rank))
    k = 60
    rrf_scores = {}
    chunk_cache = {}

    # Rank mapping (1-indexed)
    for idx, r in enumerate(vector_results):
        cid = r["chunk_id"]
        chunk_cache[cid] = r
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k + (idx + 1)))

    for idx, r in enumerate(keyword_results):
        cid = r["chunk_id"]
        if cid not in chunk_cache:
            chunk_cache[cid] = r
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k + (idx + 1)))

    # Sort by RRF score descending
    sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:limit]

    # 4. Hydrate metadata with parent Document details
    hydrated_results = []
    for cid in sorted_chunk_ids:
        chunk_data = chunk_cache[cid]
        doc_id = chunk_data["document_id"]

        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            hydrated_results.append({
                "chunk_id": cid,
                "document_id": doc_id,
                "text": chunk_data["chunk_text"],
                "score": rrf_scores[cid],
                "title": doc.title,
                "source_type": doc.source_type,
                "source_url": doc.source_url,
                "author": doc.author,
                "publication_date": str(doc.publication_date) if doc.publication_date else None,
                "candidate_id": doc.candidate_id,
                "party_id": doc.party_id
            })

    return hydrated_results
