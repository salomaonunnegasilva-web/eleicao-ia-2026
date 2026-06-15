from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.main import get_db
from app.db.models import Candidate, Party, Poll, Document
from app.db.seed_data import seed_all
from app.config import settings

router = APIRouter()

@router.get("/sources/candidates")
def list_candidates(db: Session = Depends(get_db)):
    res = db.query(Candidate).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "party": c.party.abbreviation if c.party else None,
            "coalition": c.coalition,
            "status": c.status,
            "congress_expenses": c.congress_expenses,
            "session_attendance": c.session_attendance,
            "bills_proposed": c.bills_proposed
        }
        for c in res
    ]

@router.get("/sources/parties")
def list_parties(db: Session = Depends(get_db)):
    res = db.query(Party).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "abbreviation": p.abbreviation,
            "number": p.number
        }
        for p in res
    ]

@router.get("/sources/polls")
def list_polls(db: Session = Depends(get_db)):
    res = db.query(Poll).all()
    return [
        {
            "id": p.id,
            "pollster": p.pollster,
            "registration_id": p.registration_id,
            "publication_date": str(p.publication_date),
            "sample_size": p.sample_size,
            "geography": p.geography,
            "methodology": p.methodology,
            "results_count": len(p.results)
        }
        for p in res
    ]

@router.get("/sources/documents")
def list_documents(db: Session = Depends(get_db)):
    res = db.query(Document).all()
    return [
        {
            "id": d.id,
            "title": d.title,
            "source_type": d.source_type,
            "publication_date": str(d.publication_date) if d.publication_date else None,
            "candidate": d.candidate.name if d.candidate else None,
            "author": d.author,
            "source_url": d.source_url
        }
        for d in res
    ]

@router.post("/sources/seed")
def trigger_seed(db: Session = Depends(get_db)):
    if not settings.admin_enabled:
        raise HTTPException(status_code=403, detail="Seeding is disabled in public demo mode.")
    try:
        seed_all(db)
        return {"status": "success", "message": "Database seeded successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database seeding failed: {str(e)}")
