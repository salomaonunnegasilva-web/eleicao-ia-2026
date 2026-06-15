from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.main import get_db
from app.evals.evaluator import evaluate_retrieval

router = APIRouter()


@router.get("/evaluations/retrieval")
def get_retrieval_evaluation(db: Session = Depends(get_db)):
    return evaluate_retrieval(db)
