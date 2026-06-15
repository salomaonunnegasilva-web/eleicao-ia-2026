import io
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.config import settings
from app.api.main import get_db
from app.db.models import Document, DocumentChunk, Candidate, Party
from app.rag.ingest import ingest_document

router = APIRouter()

@router.post("/ingest/file")
async def ingest_uploaded_file(
    file: UploadFile = File(...),
    title: str = Form(...),
    source_url: str = Form(None),
    author: str = Form(None),
    publication_date: str = Form(None),
    candidate_id: int = Form(None),
    party_id: int = Form(None),
    db: Session = Depends(get_db)
):
    if not settings.admin_enabled:
        raise HTTPException(status_code=403, detail="Document ingestion is disabled in public demo mode.")

    # Parse date if provided
    pub_date = None
    if publication_date:
        try:
            import datetime
            pub_date = datetime.datetime.strptime(publication_date, "%Y-%m-%d").date()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD.")

    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds the configured upload limit.")
    filename = (file.filename or "").lower()

    # 1. Parse text based on file type
    raw_text = ""
    try:
        if filename.endswith(".pdf"):
            from pypdf import PdfReader
            pdf_file = io.BytesIO(content)
            reader = PdfReader(pdf_file)
            for page in reader.pages:
                raw_text += (page.extract_text() or "") + "\n"
        elif filename.endswith(".html") or filename.endswith(".htm"):
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content.decode("utf-8", errors="ignore"), "html.parser")
            raw_text = soup.get_text()
        elif filename.endswith(".csv"):
            import pandas as pd
            csv_file = io.StringIO(content.decode("utf-8", errors="ignore"))
            df = pd.read_csv(csv_file)
            # Format nicely as text representation
            raw_text = df.to_string()
        elif filename.endswith(".txt"):
            raw_text = content.decode("utf-8", errors="ignore")
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Upload PDF, HTML, TXT, or CSV.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse file: {str(e)}")

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No readable text extracted from the file.")

    # 2. Ingest document and generate chunks/embeddings
    try:
        doc = ingest_document(
            db=db,
            title=title,
            raw_text=raw_text,
            source_type="user_upload",
            source_url=source_url,
            author=author,
            publication_date=pub_date,
            candidate_id=candidate_id,
            party_id=party_id
        )
        return {
            "status": "success",
            "document_id": doc.id,
            "title": doc.title,
            "chunks_count": len(doc.chunks)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@router.get("/ingest/status")
def get_ingestion_status(db: Session = Depends(get_db)):
    doc_count = db.query(func.count(Document.id)).scalar()
    chunk_count = db.query(func.count(DocumentChunk.id)).scalar()
    return {
        "documents_indexed": doc_count,
        "chunks_indexed": chunk_count
    }
