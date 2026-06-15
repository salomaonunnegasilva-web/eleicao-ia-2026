from __future__ import annotations

from datetime import date
import time
from typing import Any

import requests

BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
SOURCE_URL = "https://dadosabertos.camara.leg.br/"
DEFAULT_TIMEOUT = 20
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "eleicao-ia-portfolio/1.1 (public-data educational demo)",
}
OFFICEHOLDER_CACHE_TTL_SECONDS = 10 * 60
_all_deputies_cache: dict[str, Any] = {"expires_at": 0.0, "items": None}


class CamaraAPIError(RuntimeError):
    pass


def _get(path_or_url: str, params: dict[str, Any] | None = None) -> dict:
    url = path_or_url if path_or_url.startswith("http") else f"{BASE_URL}{path_or_url}"
    try:
        response = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CamaraAPIError("The Chamber of Deputies API is unavailable.") from exc


def _get_all(path: str, params: dict[str, Any], max_pages: int = 50) -> list[dict]:
    payload = _get(path, params)
    records = list(payload.get("dados", []))
    pages = 1

    while pages < max_pages:
        next_url = next(
            (
                link.get("href")
                for link in payload.get("links", [])
                if link.get("rel") == "next"
            ),
            None,
        )
        if not next_url:
            break
        payload = _get(next_url)
        records.extend(payload.get("dados", []))
        pages += 1
    return records


def list_deputies(
    name: str | None = None,
    party: str | None = None,
    state: str | None = None,
    limit: int = 30,
) -> list[dict]:
    params: dict[str, Any] = {
        "itens": max(1, min(limit, 100)),
        "ordem": "ASC",
        "ordenarPor": "nome",
    }
    if name:
        params["nome"] = name
    if party:
        params["siglaPartido"] = party.upper()
    if state:
        params["siglaUf"] = state.upper()

    records = _get("/deputados", params).get("dados", [])
    return [_normalize_deputy(record) for record in records]


def _normalize_deputy(record: dict) -> dict:
    return {
        "id": record["id"],
        "name": record["nome"],
        "party": record.get("siglaPartido"),
        "state": record.get("siglaUf"),
        "photo_url": record.get("urlFoto"),
        "email": record.get("email"),
        "profile_url": record.get("uri"),
        "source": "Câmara dos Deputados - Dados Abertos",
        "source_url": SOURCE_URL,
        "office": "deputy",
    }


def list_all_deputies() -> list[dict]:
    now = time.monotonic()
    cached = _all_deputies_cache.get("items")
    if cached is not None and now < float(_all_deputies_cache["expires_at"]):
        return cached

    records = _get_all(
        "/deputados",
        {
            "itens": 100,
            "ordem": "ASC",
            "ordenarPor": "nome",
        },
        max_pages=10,
    )
    items = [_normalize_deputy(record) for record in records]
    _all_deputies_cache["items"] = items
    _all_deputies_cache["expires_at"] = now + OFFICEHOLDER_CACHE_TTL_SECONDS
    return items


def fetch_deputy_recent_propositions(
    deputy_id: int,
    limit: int = 8,
) -> list[dict]:
    records = _get(
        "/proposicoes",
        {
            "idDeputadoAutor": deputy_id,
            "itens": max(1, min(limit, 20)),
            "ordem": "DESC",
            "ordenarPor": "id",
        },
    ).get("dados", [])
    return [
        {
            "id": record.get("id"),
            "identifier": " ".join(
                str(value)
                for value in (
                    record.get("siglaTipo"),
                    record.get("numero"),
                    record.get("ano"),
                )
                if value not in (None, "")
            ),
            "summary": record.get("ementa"),
            "api_url": record.get("uri"),
        }
        for record in records
    ]


def get_deputy(deputy_id: int) -> dict:
    record = _get(f"/deputados/{deputy_id}").get("dados", {})
    latest_status = record.get("ultimoStatus", {})
    return {
        "id": record.get("id"),
        "civil_name": record.get("nomeCivil"),
        "name": latest_status.get("nomeEleitoral") or record.get("nomeCivil"),
        "party": latest_status.get("siglaPartido"),
        "state": latest_status.get("siglaUf"),
        "photo_url": latest_status.get("urlFoto"),
        "email": latest_status.get("email"),
        "status": latest_status.get("situacao"),
        "source": "Câmara dos Deputados - Dados Abertos",
        "source_url": SOURCE_URL,
    }


def fetch_deputy_expenses(deputy_id: int, year: int | None = None) -> dict:
    target_year = year or date.today().year
    records = _get_all(
        f"/deputados/{deputy_id}/despesas",
        {
            "ano": target_year,
            "itens": 100,
            "ordem": "ASC",
            "ordenarPor": "dataDocumento",
        },
    )
    total = round(sum(float(item.get("valorLiquido") or 0.0) for item in records), 2)
    return {
        "year": target_year,
        "total_brl": total,
        "expense_records": len(records),
    }


def fetch_deputy_propositions_count(deputy_id: int) -> int:
    records = _get_all(
        "/proposicoes",
        {
            "idDeputadoAutor": deputy_id,
            "itens": 100,
            "ordem": "DESC",
            "ordenarPor": "id",
        },
    )
    return len(records)


def get_deputy_metrics(deputy_id: int, year: int | None = None) -> dict:
    deputy = get_deputy(deputy_id)
    return {
        **deputy,
        "expenses": fetch_deputy_expenses(deputy_id, year),
        "authored_propositions": fetch_deputy_propositions_count(deputy_id),
        "attendance": None,
        "attendance_note": (
            "Attendance is intentionally omitted because this demo does not yet "
            "implement a verified roll-call attendance calculation."
        ),
        "retrieved_at": date.today().isoformat(),
    }
