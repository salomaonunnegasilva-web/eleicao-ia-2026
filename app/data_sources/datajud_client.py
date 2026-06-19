from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

import requests


BASE_URL = "https://api-publica.datajud.cnj.jus.br"
SOURCE_URL = "https://datajud-wiki.cnj.jus.br/api-publica/"
DEFAULT_API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
DEFAULT_TIMEOUT = 30


class DataJudAPIError(RuntimeError):
    pass


COURT_ALIAS_BY_SEGMENT_AND_CODE = {
    ("1", "00"): "api_publica_stf",
    ("2", "00"): "api_publica_cnj",
    ("3", "00"): "api_publica_stj",
    ("4", "01"): "api_publica_trf1",
    ("4", "02"): "api_publica_trf2",
    ("4", "03"): "api_publica_trf3",
    ("4", "04"): "api_publica_trf4",
    ("4", "05"): "api_publica_trf5",
    ("4", "06"): "api_publica_trf6",
    ("5", "01"): "api_publica_trt1",
    ("5", "02"): "api_publica_trt2",
    ("5", "03"): "api_publica_trt3",
    ("5", "04"): "api_publica_trt4",
    ("5", "05"): "api_publica_trt5",
    ("5", "06"): "api_publica_trt6",
    ("5", "07"): "api_publica_trt7",
    ("5", "08"): "api_publica_trt8",
    ("5", "09"): "api_publica_trt9",
    ("5", "10"): "api_publica_trt10",
    ("5", "11"): "api_publica_trt11",
    ("5", "12"): "api_publica_trt12",
    ("5", "13"): "api_publica_trt13",
    ("5", "14"): "api_publica_trt14",
    ("5", "15"): "api_publica_trt15",
    ("5", "16"): "api_publica_trt16",
    ("5", "17"): "api_publica_trt17",
    ("5", "18"): "api_publica_trt18",
    ("5", "19"): "api_publica_trt19",
    ("5", "20"): "api_publica_trt20",
    ("5", "21"): "api_publica_trt21",
    ("5", "22"): "api_publica_trt22",
    ("5", "23"): "api_publica_trt23",
    ("5", "24"): "api_publica_trt24",
    ("6", "00"): "api_publica_tse",
    ("6", "01"): "api_publica_tre-ac",
    ("6", "02"): "api_publica_tre-al",
    ("6", "03"): "api_publica_tre-am",
    ("6", "04"): "api_publica_tre-ap",
    ("6", "05"): "api_publica_tre-ba",
    ("6", "06"): "api_publica_tre-ce",
    ("6", "07"): "api_publica_tre-dft",
    ("6", "08"): "api_publica_tre-es",
    ("6", "09"): "api_publica_tre-go",
    ("6", "10"): "api_publica_tre-ma",
    ("6", "11"): "api_publica_tre-mg",
    ("6", "12"): "api_publica_tre-ms",
    ("6", "13"): "api_publica_tre-mt",
    ("6", "14"): "api_publica_tre-pa",
    ("6", "15"): "api_publica_tre-pb",
    ("6", "16"): "api_publica_tre-pe",
    ("6", "17"): "api_publica_tre-pi",
    ("6", "18"): "api_publica_tre-pr",
    ("6", "19"): "api_publica_tre-rj",
    ("6", "20"): "api_publica_tre-rn",
    ("6", "21"): "api_publica_tre-ro",
    ("6", "22"): "api_publica_tre-rr",
    ("6", "23"): "api_publica_tre-rs",
    ("6", "24"): "api_publica_tre-sc",
    ("6", "25"): "api_publica_tre-se",
    ("6", "26"): "api_publica_tre-sp",
    ("6", "27"): "api_publica_tre-to",
    ("8", "01"): "api_publica_tjac",
    ("8", "02"): "api_publica_tjal",
    ("8", "03"): "api_publica_tjam",
    ("8", "04"): "api_publica_tjap",
    ("8", "05"): "api_publica_tjba",
    ("8", "06"): "api_publica_tjce",
    ("8", "07"): "api_publica_tjdft",
    ("8", "08"): "api_publica_tjes",
    ("8", "09"): "api_publica_tjgo",
    ("8", "10"): "api_publica_tjma",
    ("8", "11"): "api_publica_tjmg",
    ("8", "12"): "api_publica_tjms",
    ("8", "13"): "api_publica_tjmt",
    ("8", "14"): "api_publica_tjpa",
    ("8", "15"): "api_publica_tjpb",
    ("8", "16"): "api_publica_tjpe",
    ("8", "17"): "api_publica_tjpi",
    ("8", "18"): "api_publica_tjpr",
    ("8", "19"): "api_publica_tjrj",
    ("8", "20"): "api_publica_tjrn",
    ("8", "21"): "api_publica_tjro",
    ("8", "22"): "api_publica_tjrr",
    ("8", "23"): "api_publica_tjrs",
    ("8", "24"): "api_publica_tjsc",
    ("8", "25"): "api_publica_tjse",
    ("8", "26"): "api_publica_tjsp",
    ("8", "27"): "api_publica_tjto",
}

DEFAULT_ALIASES = (
    "api_publica_stf",
    "api_publica_stj",
    "api_publica_tse",
    "api_publica_trf1",
    "api_publica_trf2",
    "api_publica_trf3",
    "api_publica_trf4",
    "api_publica_trf5",
    "api_publica_trf6",
    "api_publica_tjsp",
    "api_publica_tjrj",
    "api_publica_tjmg",
    "api_publica_tjrs",
    "api_publica_tjpr",
    "api_publica_tjdft",
)


def normalize_process_number(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 20:
        raise DataJudAPIError("A CNJ process number must contain 20 digits.")
    return digits


def extract_process_numbers(text: str) -> list[str]:
    candidates = re.findall(
        r"\b\d{7}[-.]?\d{2}[.]?\d{4}[.]?\d[.]?\d{2}[.]?\d{4}\b",
        text,
    )
    normalized: list[str] = []
    for candidate in candidates:
        try:
            number = normalize_process_number(candidate)
        except DataJudAPIError:
            continue
        if number not in normalized:
            normalized.append(number)
    return normalized


def infer_aliases(process_number: str) -> list[str]:
    digits = normalize_process_number(process_number)
    segment = digits[13]
    court_code = digits[14:16]
    alias = COURT_ALIAS_BY_SEGMENT_AND_CODE.get((segment, court_code))
    if alias:
        return [alias]
    return list(DEFAULT_ALIASES)


def _headers() -> dict[str, str]:
    api_key = os.getenv("DATAJUD_API_KEY", DEFAULT_API_KEY).strip()
    return {
        "Authorization": f"APIKey {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "eleicao-ia-portfolio/1.2 (official-public-data demo)",
    }


def _search_alias(alias: str, process_number: str, limit: int) -> list[dict]:
    url = f"{BASE_URL}/{alias}/_search"
    payload = {
        "size": max(1, min(limit, 10)),
        "query": {
            "match": {
                "numeroProcesso": process_number,
            }
        },
    }
    try:
        response = requests.post(
            url,
            headers=_headers(),
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise DataJudAPIError("The CNJ DataJud API is unavailable.") from exc

    hits = data.get("hits", {}).get("hits", [])
    records = []
    for hit in hits:
        source = hit.get("_source") or {}
        source["_datajud_index"] = hit.get("_index") or alias
        source["_datajud_score"] = hit.get("_score")
        records.append(source)
    return records


def _format_datajud_datetime(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    if re.fullmatch(r"\d{14}", text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}T{text[8:10]}:{text[10:12]}:{text[12:14]}"
    if re.fullmatch(r"\d{8}", text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text


def fetch_process_by_number(
    process_number: str,
    aliases: list[str] | None = None,
    limit: int = 5,
) -> list[dict]:
    number = normalize_process_number(process_number)
    search_aliases = aliases or infer_aliases(number)
    records: list[dict] = []
    errors = 0

    for alias in search_aliases:
        try:
            records.extend(_search_alias(alias, number, limit=limit))
        except DataJudAPIError:
            errors += 1
            continue
        if len(records) >= limit:
            break

    if not records and errors == len(search_aliases):
        raise DataJudAPIError("The CNJ DataJud API is unavailable.")

    return records[: max(1, limit)]


def summarize_process(record: dict[str, Any]) -> dict:
    latest_movements = sorted(
        record.get("movimentos") or [],
        key=lambda item: item.get("dataHora") or "",
        reverse=True,
    )[:3]
    subjects = ", ".join(
        subject.get("nome", "")
        for subject in record.get("assuntos") or []
        if subject.get("nome")
    )
    movements = "; ".join(
        " - ".join(
            value
            for value in (
                _format_datajud_datetime(movement.get("dataHora")),
                movement.get("nome"),
            )
            if value
        )
        for movement in latest_movements
    )
    return {
        "process_number": record.get("numeroProcesso"),
        "tribunal": record.get("tribunal"),
        "index": record.get("_datajud_index"),
        "class_name": (record.get("classe") or {}).get("nome"),
        "filing_date": _format_datajud_datetime(record.get("dataAjuizamento")),
        "degree": record.get("grau"),
        "secrecy_level": record.get("nivelSigilo"),
        "judging_body": (record.get("orgaoJulgador") or {}).get("nome"),
        "subjects": subjects or None,
        "latest_movements": movements or None,
        "retrieved_at": datetime.now(UTC).isoformat(),
    }
