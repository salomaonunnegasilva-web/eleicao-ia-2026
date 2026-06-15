from __future__ import annotations

import time
from datetime import date, timedelta

import requests

BASE_URL = "https://legis.senado.leg.br/dadosabertos"
SOURCE_URL = "https://www12.senado.leg.br/dados-abertos"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "eleicao-ia-portfolio/1.1 (public-data educational demo)",
}
OFFICEHOLDER_CACHE_TTL_SECONDS = 10 * 60
_senator_cache: dict[str, object] = {"expires_at": 0.0, "items": None}


class SenadoAPIError(RuntimeError):
    pass


def list_senators(name: str | None = None, limit: int = 30) -> list[dict]:
    records = _get_current_senator_records()
    normalized_query = (name or "").casefold()
    result = []
    for record in records:
        identification = record.get("IdentificacaoParlamentar", {})
        senator_name = identification.get("NomeParlamentar", "")
        civil_name = identification.get("NomeCompletoParlamentar", "")
        if normalized_query and normalized_query not in senator_name.casefold() and normalized_query not in civil_name.casefold():
            continue
        result.append(
            {
                "id": identification.get("CodigoParlamentar"),
                "name": senator_name,
                "civil_name": civil_name,
                "party": identification.get("SiglaPartidoParlamentar"),
                "state": identification.get("UfParlamentar"),
                "photo_url": identification.get("UrlFotoParlamentar"),
                "profile_url": str(
                    identification.get("UrlPaginaParlamentar") or ""
                ).replace("http://", "https://"),
                "source": "Senado Federal - Dados Abertos",
                "source_url": SOURCE_URL,
                "office": "senator",
            }
        )
        if len(result) >= max(1, min(limit, 100)):
            break
    return result


def _get_current_senator_records() -> list[dict]:
    now = time.monotonic()
    cached = _senator_cache.get("items")
    if cached is not None and now < float(_senator_cache["expires_at"]):
        return cached  # type: ignore[return-value]

    try:
        response = requests.get(
            f"{BASE_URL}/senador/lista/atual",
            headers=HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise SenadoAPIError("The Federal Senate API is unavailable.") from exc

    records = (
        payload.get("ListaParlamentarEmExercicio", {})
        .get("Parlamentares", {})
        .get("Parlamentar", [])
    )
    _senator_cache["items"] = records
    _senator_cache["expires_at"] = now + OFFICEHOLDER_CACHE_TTL_SECONDS
    return records


def fetch_senator_recent_processes(
    senator_id: int,
    limit: int = 8,
    lookback_days: int = 3 * 365,
) -> list[dict]:
    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)
    try:
        response = requests.get(
            f"{BASE_URL}/processo",
            params={
                "codigoParlamentarAutor": senator_id,
                "dataInicioApresentacao": start_date.isoformat(),
                "dataFimApresentacao": end_date.isoformat(),
            },
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        records = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise SenadoAPIError(
            "The Federal Senate legislative-process API is unavailable."
        ) from exc

    if not isinstance(records, list):
        return []

    proposal_prefixes = (
        "PEC ",
        "PL ",
        "PLP ",
        "PDL ",
        "PRS ",
        "PLC ",
        "PLS ",
    )
    proposals = [
        {
            "id": record.get("id"),
            "identifier": record.get("identificacao"),
            "summary": record.get("ementa"),
            "presented_at": record.get("dataApresentacao"),
            "status": record.get("situacaoAtual"),
            "document_url": record.get("urlDocumento"),
            "authorship": record.get("autoria"),
        }
        for record in records
        if str(record.get("identificacao") or "").startswith(proposal_prefixes)
    ]
    proposals.sort(
        key=lambda item: item.get("presented_at") or "",
        reverse=True,
    )
    return proposals[: max(1, limit)]
