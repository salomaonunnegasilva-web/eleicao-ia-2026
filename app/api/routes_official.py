from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.data_sources.camara_client import (
    CamaraAPIError,
    get_deputy_metrics,
    list_deputies,
)
from app.data_sources.datajud_client import DataJudAPIError, fetch_process_by_number
from app.data_sources.portal_transparencia_client import (
    PortalTransparenciaAPIError,
    fetch_server_remuneration,
    search_ceis_by_name,
    search_cnep_by_name,
)
from app.data_sources.senado_client import SenadoAPIError, list_senators
from app.data_sources.tse_client import TSEDataError, get_calendar

router = APIRouter()


@router.get("/official/tse/calendar")
def get_official_tse_calendar():
    try:
        return get_calendar(year=2026)
    except TSEDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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


@router.get("/official/datajud/process/{process_number}")
def get_official_datajud_process(
    process_number: str,
    alias: list[str] | None = Query(None),
):
    try:
        return {
            "items": fetch_process_by_number(process_number, aliases=alias),
            "source": "CNJ DataJud - API Publica",
            "source_url": "https://datajud-wiki.cnj.jus.br/api-publica/",
            "live_data": True,
        }
    except DataJudAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/official/transparency/sanctions")
def get_official_transparency_sanctions(
    name: str = Query(min_length=3),
):
    try:
        return {
            "items": {
                "ceis": search_ceis_by_name(name),
                "cnep": search_cnep_by_name(name),
            },
            "source": "Portal da Transparencia / CGU",
            "source_url": "https://api.portaldatransparencia.gov.br/swagger-ui/index.html",
            "live_data": True,
        }
    except PortalTransparenciaAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/official/transparency/remuneration")
def get_official_transparency_remuneration(
    cpf: str | None = None,
    server_id: int | None = Query(None, alias="id"),
    mes_ano: int | None = Query(None, alias="mesAno"),
):
    try:
        return {
            "items": fetch_server_remuneration(
                cpf=cpf,
                server_id=server_id,
                mes_ano=mes_ano,
            ),
            "source": "Portal da Transparencia / CGU",
            "source_url": "https://api.portaldatransparencia.gov.br/swagger-ui/index.html",
            "live_data": True,
        }
    except PortalTransparenciaAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
