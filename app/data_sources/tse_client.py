from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.text_utils import normalize_text


CALENDAR_URL = (
    "https://www.tse.jus.br/eleicoes/calendario-eleitoral/calendario-eleitoral"
)
SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "official"
    / "tse_calendar_2026.json"
)
DEFAULT_TIMEOUT = 30
CACHE_TTL_SECONDS = 15 * 60
HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "User-Agent": "eleicao-ia-portfolio/2.0 (official-public-data demo)",
}

_cache: dict[str, Any] = {"expires_at": 0.0, "payload": None}


class TSEDataError(RuntimeError):
    pass


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _is_date_heading(value: str) -> bool:
    normalized = normalize_text(value).upper()
    return bool(
        re.match(
            r"^(?:\d{1,2}(?:O)?(?:\s+A\s+\d{1,2})?|ULTIMO DIA)"
            r"\s+DE\s+[A-Z]+",
            normalized,
        )
    )


def _entry_checksum(entries: list[dict]) -> str:
    stable_payload = json.dumps(
        entries,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(stable_payload.encode("utf-8")).hexdigest()


def parse_calendar_html(html: str, year: int = 2026) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    year_heading = next(
        (
            heading
            for heading in soup.find_all(["h2", "h3"])
            if _clean_text(heading.get_text(" ", strip=True)) == str(year)
        ),
        None,
    )
    if year_heading is None:
        raise TSEDataError(f"The TSE calendar page has no {year} section.")

    year_container = year_heading.find_parent(
        "div",
        class_=lambda classes: classes and "panel__linha" in classes,
    )
    if year_container is None:
        raise TSEDataError("The TSE calendar page structure is unsupported.")

    entries: list[dict] = []
    for card in year_container.select(".accordion__card"):
        title_node = card.select_one(".accordion__card-title")
        body = card.select_one(".accordion__card-body")
        if title_node is None or body is None:
            continue

        month = _clean_text(title_node.get_text(" ", strip=True))
        current: dict[str, Any] | None = None
        for node in body.find_all(["p", "li"]):
            if node.name == "p" and node.find_parent("li") is not None:
                continue
            text_value = _clean_text(node.get_text(" ", strip=True))
            if not text_value:
                continue

            if _is_date_heading(text_value):
                if current and current["details"]:
                    entries.append(
                        {
                            "month": current["month"],
                            "date_label": current["date_label"],
                            "text": " ".join(current["details"]),
                        }
                    )
                current = {
                    "month": month,
                    "date_label": text_value,
                    "details": [],
                }
            elif current is not None:
                current["details"].append(text_value)

        if current and current["details"]:
            entries.append(
                {
                    "month": current["month"],
                    "date_label": current["date_label"],
                    "text": " ".join(current["details"]),
                }
            )

    if not entries:
        raise TSEDataError("No dated entries were parsed from the TSE calendar.")
    return entries


def fetch_live_calendar(year: int = 2026) -> dict:
    try:
        response = requests.get(
            CALENDAR_URL,
            headers=HEADERS,
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise TSEDataError("The official TSE calendar is unavailable.") from exc

    entries = parse_calendar_html(response.text, year=year)
    return {
        "year": year,
        "source": "Tribunal Superior Eleitoral - Calendário Eleitoral",
        "source_url": CALENDAR_URL,
        "source_type": "official_tse_calendar",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "live_data": True,
        "checksum": _entry_checksum(entries),
        "entries": entries,
    }


def load_calendar_snapshot(year: int = 2026) -> dict:
    try:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TSEDataError("No valid TSE calendar snapshot is available.") from exc

    if payload.get("year") != year or not payload.get("entries"):
        raise TSEDataError(f"The local TSE snapshot does not contain {year}.")

    result = dict(payload)
    result["live_data"] = False
    result["fallback_reason"] = "Live TSE request failed; using versioned snapshot."
    return result


def get_calendar(year: int = 2026, force_live: bool = False) -> dict:
    now = time.monotonic()
    cached = _cache.get("payload")
    if (
        not force_live
        and cached is not None
        and cached.get("year") == year
        and now < float(_cache.get("expires_at", 0.0))
    ):
        return cached

    try:
        payload = fetch_live_calendar(year=year)
    except TSEDataError:
        payload = load_calendar_snapshot(year=year)

    _cache["payload"] = payload
    _cache["expires_at"] = now + CACHE_TTL_SECONDS
    return payload


_STOPWORDS = {
    "a",
    "as",
    "ate",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "o",
    "os",
    "para",
    "por",
    "qual",
    "quais",
    "quando",
    "que",
    "um",
    "uma",
}


def search_calendar(query: str, limit: int = 4) -> tuple[dict, list[dict]]:
    payload = get_calendar(year=2026)
    query_normalized = normalize_text(query)
    query_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", query_normalized)
        if len(token) > 2 and token not in _STOPWORDS
    }

    phrase_boosts = {
        "primeiro turno": {"primeiro", "turno", "eleicoes"},
        "segundo turno": {"segundo", "turno", "eleicoes"},
        "registro de candidatura": {"registro", "candidatura", "candidatos"},
        "registro de candidaturas": {"registro", "candidaturas", "candidatos"},
        "convencoes": {"convencoes", "partidarias"},
        "pesquisa eleitoral": {"pesquisas", "registro", "divulgacao"},
        "pesquisas eleitorais": {"pesquisas", "registro", "divulgacao"},
        "propaganda eleitoral": {"propaganda", "eleitoral"},
    }
    expanded_tokens = set(query_tokens)
    for phrase, tokens in phrase_boosts.items():
        if phrase in query_normalized:
            expanded_tokens.update(tokens)

    ranked: list[tuple[float, dict]] = []
    for entry in payload["entries"]:
        searchable = normalize_text(
            f"{entry['month']} {entry['date_label']} {entry['text']}"
        )
        entry_tokens = set(re.findall(r"[a-z0-9]+", searchable))
        overlap = expanded_tokens & entry_tokens
        if not overlap:
            continue

        score = float(len(overlap))
        for phrase in phrase_boosts:
            if phrase in query_normalized and phrase in searchable:
                score += 4.0
        if "eleicao" in expanded_tokens or "eleicoes" in expanded_tokens:
            if "eleicoes" in searchable:
                score += 1.0

        intent_boost = 0.0
        if "primeiro turno" in query_normalized:
            if "dia das eleicoes (1o turno)" in searchable:
                intent_boost += 30.0
            elif "data em que se realizara a votacao" in searchable:
                intent_boost += 15.0
        if "segundo turno" in query_normalized:
            if "dia das eleicoes (2o turno)" in searchable:
                intent_boost += 30.0
        if (
            "registro de candidatura" in query_normalized
            or "registro das candidaturas" in query_normalized
            or "registro de candidaturas" in query_normalized
        ):
            if "requererem o registro de candidatas e candidatos" in searchable:
                intent_boost += 30.0
        if "convenc" in query_normalized:
            if "data a partir da qual" in searchable and "realizar convencoes" in searchable:
                intent_boost += 25.0
            if (
                any(term in query_normalized for term in ("ultimo", "fim", "termin"))
                and "ultimo dia" in searchable
                and "realizem convencoes" in searchable
            ):
                intent_boost += 30.0
        if "pesquis" in query_normalized and "registr" in query_normalized:
            if "pesqele" in searchable and "5 (cinco) dias antes" in searchable:
                intent_boost += 30.0
        score += intent_boost
        ranked.append((score, entry))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return payload, [entry for _, entry in ranked[: max(1, limit)]]
