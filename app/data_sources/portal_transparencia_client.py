from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

import requests


BASE_URL = "https://api.portaldatransparencia.gov.br/api-de-dados"
SOURCE_URL = "https://api.portaldatransparencia.gov.br/swagger-ui/index.html"
DEFAULT_TIMEOUT = 20


class PortalTransparenciaAPIError(RuntimeError):
    pass


def has_api_key() -> bool:
    return bool(os.getenv("PORTAL_TRANSPARENCIA_API_KEY", "").strip())


def normalize_cpf(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 11:
        raise PortalTransparenciaAPIError("CPF must contain 11 digits.")
    return digits


def extract_cpf(text: str) -> str | None:
    match = re.search(r"\b\d{3}[.]?\d{3}[.]?\d{3}[-]?\d{2}\b", text)
    if not match:
        return None
    return normalize_cpf(match.group(0))


def latest_reference_month() -> int:
    now = datetime.now(UTC)
    month = now.month - 1
    year = now.year
    if month == 0:
        month = 12
        year -= 1
    return int(f"{year}{month:02d}")


def _headers() -> dict[str, str]:
    api_key = os.getenv("PORTAL_TRANSPARENCIA_API_KEY", "").strip()
    if not api_key:
        raise PortalTransparenciaAPIError(
            "PORTAL_TRANSPARENCIA_API_KEY is not configured."
        )
    return {
        "Accept": "application/json",
        "chave-api-dados": api_key,
        "User-Agent": "eleicao-ia-portfolio/1.2 (official-public-data demo)",
    }


def _get(path: str, params: dict[str, Any]) -> list[dict] | dict:
    try:
        response = requests.get(
            f"{BASE_URL}{path}",
            params=params,
            headers=_headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise PortalTransparenciaAPIError(
            "The Portal da Transparencia API is unavailable."
        ) from exc


def search_ceis_by_name(name: str, limit: int = 5) -> list[dict]:
    records = _get("/ceis", {"nomeSancionado": name, "pagina": 1})
    if not isinstance(records, list):
        return []
    return records[: max(1, limit)]


def search_cnep_by_name(name: str, limit: int = 5) -> list[dict]:
    records = _get("/cnep", {"nomeSancionado": name, "pagina": 1})
    if not isinstance(records, list):
        return []
    return records[: max(1, limit)]


def fetch_server_remuneration(
    cpf: str | None = None,
    server_id: int | None = None,
    mes_ano: int | None = None,
) -> list[dict]:
    if not cpf and server_id is None:
        raise PortalTransparenciaAPIError(
            "A CPF or server id is required for remuneration lookup."
        )
    params: dict[str, Any] = {
        "mesAno": mes_ano or latest_reference_month(),
        "pagina": 1,
    }
    if cpf:
        params["cpf"] = normalize_cpf(cpf)
    if server_id is not None:
        params["id"] = server_id
    records = _get("/servidores/remuneracao", params)
    if not isinstance(records, list):
        return []
    return records
