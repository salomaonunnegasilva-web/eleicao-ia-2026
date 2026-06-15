from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.data_sources.camara_client import (
    CamaraAPIError,
    get_deputy_metrics,
    list_deputies,
)
from app.data_sources.senado_client import SenadoAPIError, list_senators

router = APIRouter()


@router.get("/official/deputies")
def get_official_deputies(
    name: str | None = None,
    party: str | None = None,
    state: str | None = Query(None, min_length=2, max_length=2),
    limit: int = Query(30, ge=1, le=100),
):
    try:
        return {
            "items": list_deputies(name=name, party=party, state=state, limit=limit),
            "source": "Câmara dos Deputados - Dados Abertos",
            "source_url": "https://dadosabertos.camara.leg.br/",
            "live_data": True,
        }
    except CamaraAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/official/deputies/{deputy_id}/metrics")
def get_official_deputy_metrics(
    deputy_id: int,
    year: int = Query(default_factory=lambda: date.today().year, ge=2009, le=2100),
):
    try:
        return get_deputy_metrics(deputy_id, year)
    except CamaraAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/official/senators")
def get_official_senators(
    name: str | None = None,
    limit: int = Query(30, ge=1, le=100),
):
    try:
        return {
            "items": list_senators(name=name, limit=limit),
            "source": "Senado Federal - Dados Abertos",
            "source_url": "https://www12.senado.leg.br/dados-abertos",
            "live_data": True,
        }
    except SenadoAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
