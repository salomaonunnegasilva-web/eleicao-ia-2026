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
    - 'official_calendar': election dates, registration, conventions, or deadlines.
    - 'official_legislative': current legislators, expenses, or legislative work.
    - 'official_policy': candidate programs, policy positions, and comparisons.
    - 'forecast': explicitly requested synthetic polling/simulation demonstration.
    - 'official_evidence': default official-source retrieval route.
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
        return "official_calendar"
    if "pesquis" in query_lower and any(
        term in query_lower
        for term in ("registr", "divulg", "pesqele", "prazo")
    ):
        return "official_calendar"

    calendar_keywords = [
        "primeiro turno",
        "segundo turno",
        "registro de candidatura",
        "registro das candidaturas",
        "convencao partidaria",
        "convencoes partidarias",
        "propaganda eleitoral",
        "prazo eleitoral",
    ]
    if any(keyword in query_lower for keyword in calendar_keywords):
        return "official_calendar"

    forecast_keywords = [
        "liderando", "na frente", "intencao de voto", "votos validos", "porcentagem",
        "probabilidade", "segundo turno", "cenario atual", "simulacao", "forecast",
        "media das pesquisas", "tendencia", "subiu", "caiu", "levantamentos"
    ]

    legislative_keywords = [
        "deputado",
        "deputada",
        "senador",
        "senadora",
        "parlamentar",
        "cota parlamentar",
        "gasto parlamentar",
        "gastos parlamentares",
        "despesa parlamentar",
        "despesas parlamentares",
        "projeto de lei",
        "projetos de lei",
        "proposicao legislativa",
        "proposicoes legislativas",
        "materias de autoria",
        "votacao nominal",
        "partido de",
        "partido do",
        "partido da",
        "quem e o deputado",
        "quem e a deputada",
        "quem e o senador",
        "quem e a senadora",
    ]

    is_forecast = any(k in query_lower for k in forecast_keywords)
    if is_forecast:
        return "forecast"

    if any(keyword in query_lower for keyword in legislative_keywords):
        return "official_legislative"

    policy_keywords = [
        "proposta",
        "propostas",
        "programa de governo",
        "plano de governo",
        "posicionamento",
        "posicionamentos",
        "defende",
        "promessa",
        "promessas",
    ]
    if any(keyword in query_lower for keyword in policy_keywords):
        return "official_policy"

    return "official_evidence"

def get_vector_results(
    db: Session,
    embedding: list[float],
    limit: int = 10,
    source_types: tuple[str, ...] | None = None,
) -> list[dict]:
    """Retrieves top chunks based on vector distance using pgvector <=> (cosine distance)."""
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        query_vector = np.asarray(embedding, dtype=float)
        query_norm = np.linalg.norm(query_vector)
        if query_norm == 0:
            return []

        ranked = []
        query = (
            db.query(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(DocumentChunk.embedding.isnot(None))
        )
        if source_types:
            query = query.filter(Document.source_type.in_(source_types))
        rows = query.all()
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
    source_filter = ""
    params: dict[str, object] = {"emb_str": emb_str, "limit": limit}
    if source_types:
        placeholders = []
        for index, source_type in enumerate(source_types):
            key = f"source_type_{index}"
            placeholders.append(f":{key}")
            params[key] = source_type
        source_filter = f"WHERE d.source_type IN ({', '.join(placeholders)})"

    sql = text(f"""
        SELECT c.id, c.document_id, c.chunk_text, c.chunk_index, c.metadata_json,
               (c.embedding <=> CAST(:emb_str AS vector)) as distance
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        {source_filter}
        ORDER BY distance ASC
        LIMIT :limit
    """)
    try:
        res = db.execute(sql, params).all()
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

def get_keyword_results(
    db: Session,
    query_text: str,
    limit: int = 10,
    source_types: tuple[str, ...] | None = None,
) -> list[dict]:
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

    source_filter = ""
    params: dict[str, object] = {
        "keyword_query": keyword_query,
        "limit": limit,
    }
    if source_types:
        placeholders = []
        for index, source_type in enumerate(source_types):
            key = f"source_type_{index}"
            placeholders.append(f":{key}")
            params[key] = source_type
        source_filter = f"AND d.source_type IN ({', '.join(placeholders)})"

    sql = text(f"""
        SELECT c.id, c.document_id, c.chunk_text, c.chunk_index, c.metadata_json,
               ts_rank_cd(to_tsvector('portuguese', c.chunk_text), to_tsquery('portuguese', :keyword_query)) as rank
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE to_tsvector('portuguese', c.chunk_text) @@ to_tsquery('portuguese', :keyword_query)
        {source_filter}
        ORDER BY rank DESC
        LIMIT :limit
    """)
    try:
        res = db.execute(sql, params).all()
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

        params = {f"w{i}": f"%{word.lower()}%" for i, word in enumerate(words)}
        params["limit"] = limit
        source_join_filter = ""
        if source_types:
            placeholders = []
            for index, source_type in enumerate(source_types):
                key = f"source_type_{index}"
                placeholders.append(f":{key}")
                params[key] = source_type
            source_join_filter = (
                f"AND d.source_type IN ({', '.join(placeholders)})"
            )

        sql_like = text(f"""
            SELECT c.id, c.document_id, c.chunk_text, c.chunk_index, c.metadata_json,
                   ({score_expr}) as rank
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE {where_clauses}
            {source_join_filter}
            ORDER BY rank DESC
            LIMIT :limit
        """)

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

_RETRIEVAL_STOPWORDS = {
    "a",
    "as",
    "ate",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "o",
    "os",
    "para",
    "por",
    "qual",
    "quais",
    "que",
    "sobre",
    "um",
    "uma",
}


def retrieve_hybrid_chunks(
    db: Session,
    query_text: str,
    limit: int = 5,
    source_types: tuple[str, ...] | None = None,
    require_term_overlap: bool = True,
) -> list[dict]:
    """
    Executes vector and keyword searches, merges findings using Reciprocal Rank Fusion (RRF),
    and hydrates results with parent document metadata.
    """
    # 1. Get Vector Search results
    emb = get_embedding(query_text)
    search_limit = max(limit * 4, 20)
    vector_results = get_vector_results(
        db,
        emb,
        limit=search_limit,
        source_types=source_types,
    )

    # 2. Get Keyword Search results
    keyword_results = get_keyword_results(
        db,
        query_text,
        limit=search_limit,
        source_types=source_types,
    )

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
    sorted_chunk_ids = sorted(
        rrf_scores.keys(),
        key=lambda x: rrf_scores[x],
        reverse=True,
    )

    # 4. Hydrate metadata with parent Document details
    hydrated_results = []
    query_terms = {
        term
        for term in re.findall(r"[a-z0-9]+", normalize_text(query_text))
        if len(term) > 2 and term not in _RETRIEVAL_STOPWORDS
    }
    for cid in sorted_chunk_ids:
        chunk_data = chunk_cache[cid]
        doc_id = chunk_data["document_id"]

        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            if source_types and doc.source_type not in source_types:
                continue
            searchable = normalize_text(
                f"{doc.title} {chunk_data['chunk_text']}"
            )
            matched_terms = sorted(
                term for term in query_terms if term in searchable
            )
            if require_term_overlap and query_terms and not matched_terms:
                continue
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
                "party_id": doc.party_id,
                "matched_terms": matched_terms,
            })

    return hydrated_results[:limit]
