import os
import re
import hashlib
import numpy as np
from datetime import date
from sqlalchemy.orm import Session
from app.db.models import Document, DocumentChunk

# Dynamic importing for embedding model
_sentence_transformer_model = None

def get_embedding(text: str) -> list[float]:
    """
    Generates a 384-dimensional embedding vector for the given text.
    First tries to use sentence-transformers local model,
    then falls back to a deterministic hashing-vectorizer implementation.
    """
    global _sentence_transformer_model

    # Check env variables
    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "local").lower()
    model_name = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    # Cloud providers could be added here, but for MVP we focus on local and its fallback
    if embedding_provider == "local":
        try:
            from sentence_transformers import SentenceTransformer
            if _sentence_transformer_model is None:
                # Suppress warnings
                os.environ["TOKENIZERS_PARALLELISM"] = "false"
                _sentence_transformer_model = SentenceTransformer(model_name)

            vector = _sentence_transformer_model.encode(text)
            return vector.tolist()
        except Exception as e:
            # Fall back to the dependency-free local vectorizer.
            pass

    return generate_hashing_vector(text, 384)


def generate_hashing_vector(text: str, dim: int = 384) -> list[float]:
    """Builds a dependency-free, deterministic bag-of-words hashing vector."""
    from app.text_utils import normalize_text

    tokens = re.findall(r"[a-z0-9]+", normalize_text(text))
    vector = np.zeros(dim, dtype=float)
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, byteorder="big", signed=False)
        index = value % dim
        sign = 1.0 if (value >> 1) % 2 == 0 else -1.0
        vector[index] += sign

    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    return vector.tolist()

def chunk_text(text: str, chunk_size: int = 600, overlap: int = 120) -> list[str]:
    """
    Splits text into chunks of roughly chunk_size characters with overlap,
    respecting sentence boundaries.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        sentence_len = len(sentence)
        if current_length + sentence_len > chunk_size:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
            # Keep last few sentences for overlap
            overlap_chunk = []
            overlap_len = 0
            for s in reversed(current_chunk):
                if overlap_len + len(s) < overlap:
                    overlap_chunk.insert(0, s)
                    overlap_len += len(s)
                else:
                    break
            current_chunk = overlap_chunk
            current_length = overlap_len

        current_chunk.append(sentence)
        current_length += sentence_len

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks

def ingest_document(
    db: Session,
    title: str,
    raw_text: str,
    source_type: str,
    source_url: str = None,
    author: str = None,
    publication_date: date = None,
    candidate_id: int = None,
    party_id: int = None,
    jurisdiction: str = "Federal"
) -> Document:
    """Chunks, embeds, and saves a document and its chunks to the database."""
    # Compute simple checksum to prevent duplicate documents
    checksum = hashlib.sha256(raw_text.encode('utf-8')).hexdigest()

    # Check if document already exists
    existing = db.query(Document).filter(Document.checksum == checksum).first()
    if existing:
        return existing

    doc = Document(
        title=title,
        source_type=source_type,
        source_url=source_url,
        author=author,
        publication_date=publication_date,
        candidate_id=candidate_id,
        party_id=party_id,
        jurisdiction=jurisdiction,
        raw_text=raw_text,
        checksum=checksum
    )
    db.add(doc)
    db.flush()  # get doc.id

    chunks = chunk_text(raw_text)
    for idx, text in enumerate(chunks):
        embedding = get_embedding(text)
        metadata = {
            "title": title,
            "source_type": source_type,
            "publication_date": str(publication_date) if publication_date else None,
            "chunk_index": idx
        }
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_text=text,
            chunk_index=idx,
            embedding=embedding,
            metadata_json=metadata
        )
        db.add(chunk)

    db.commit()
    return doc
