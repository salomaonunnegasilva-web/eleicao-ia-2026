from __future__ import annotations

import requests

BASE_URL = "https://legis.senado.leg.br/dadosabertos"
SOURCE_URL = "https://www12.senado.leg.br/dados-abertos"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "eleicao-ia-portfolio/1.1 (public-data educational demo)",
}


class SenadoAPIError(RuntimeError):
    pass


def list_senators(name: str | None = None, limit: int = 30) -> list[dict]:
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
                "profile_url": identification.get("UrlPaginaParlamentar"),
                "source": "Senado Federal - Dados Abertos",
                "source_url": SOURCE_URL,
            }
        )
        if len(result) >= max(1, min(limit, 100)):
            break
    return result
