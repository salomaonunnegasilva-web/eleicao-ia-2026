from __future__ import annotations

import re
from datetime import UTC, date, datetime

from app.data_sources.camara_client import (
    CamaraAPIError,
    fetch_deputy_expenses,
    fetch_deputy_recent_propositions,
    list_all_deputies,
)
from app.data_sources.senado_client import (
    SenadoAPIError,
    fetch_senator_recent_processes,
    list_senators,
)
from app.data_sources.tse_client import TSEDataError, search_calendar
from app.text_utils import normalize_text


_QUERY_STOPWORDS = {
    "a",
    "as",
    "ate",
    "com",
    "como",
    "da",
    "das",
    "de",
    "deputado",
    "deputada",
    "do",
    "dos",
    "e",
    "em",
    "estado",
    "federal",
    "gastos",
    "lei",
    "leis",
    "mandato",
    "o",
    "os",
    "parlamentar",
    "partido",
    "por",
    "projeto",
    "projetos",
    "proposicao",
    "proposicoes",
    "qual",
    "quais",
    "senador",
    "senadora",
    "sobre",
}


def _query_tokens(query: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalize_text(query))
        if len(token) > 2 and token not in _QUERY_STOPWORDS
    }


def _match_score(query: str, person_name: str) -> float:
    normalized_query = normalize_text(query)
    normalized_name = normalize_text(person_name)
    if normalized_name in normalized_query:
        return 100.0

    query_tokens = _query_tokens(query)
    name_tokens = {
        token
        for token in normalized_name.split()
        if len(token) > 2 and token not in {"da", "das", "de", "do", "dos"}
    }
    overlap = query_tokens & name_tokens
    if not overlap:
        return 0.0
    if len(query_tokens) >= 2 and len(overlap) == 1:
        return 0.0
    return float(len(overlap) * 10) + (len(overlap) / max(len(name_tokens), 1))


def resolve_current_officeholders(query: str, limit: int = 3) -> list[dict]:
    people: list[dict] = []
    try:
        people.extend(list_all_deputies())
    except CamaraAPIError:
        pass
    try:
        people.extend(list_senators(limit=100))
    except SenadoAPIError:
        pass

    ranked = [
        (_match_score(query, person["name"]), person)
        for person in people
    ]
    ranked = [item for item in ranked if item[0] >= 10.0]
    ranked.sort(key=lambda item: item[0], reverse=True)

    if not ranked:
        return []
    best_score = ranked[0][0]
    return [
        person
        for score, person in ranked
        if score >= best_score - 0.5
    ][: max(1, limit)]


def build_calendar_chunks(query: str, limit: int = 4) -> list[dict]:
    payload, entries = search_calendar(query, limit=limit)
    chunks = []
    for entry in entries:
        chunks.append(
            {
                "document_id": (
                    f"tse-calendar-{payload['year']}-"
                    f"{normalize_text(entry['date_label']).replace(' ', '-')}"
                ),
                "text": f"{entry['date_label']}: {entry['text']}",
                "score": 1.0,
                "title": (
                    f"Calendário Eleitoral {payload['year']} - "
                    f"{entry['date_label']}"
                ),
                "source_type": payload["source_type"],
                "source_url": payload["source_url"],
                "author": "Tribunal Superior Eleitoral",
                "publication_date": None,
                "official": True,
                "live_data": payload["live_data"],
                "retrieved_at": payload.get("retrieved_at"),
            }
        )
    return chunks


def _profile_chunk(person: dict) -> dict:
    office_label = (
        "Deputado(a) federal"
        if person["office"] == "deputy"
        else "Senador(a)"
    )
    text = (
        f"{office_label}: {person['name']}. "
        f"Partido: {person.get('party') or 'não informado'}. "
        f"Unidade da Federação: {person.get('state') or 'não informada'}."
    )
    return {
        "document_id": f"{person['office']}-{person['id']}-profile",
        "text": text,
        "score": 1.0,
        "title": f"Perfil oficial - {person['name']}",
        "source_type": f"official_{person['office']}_profile",
        "source_url": person.get("profile_url") or person["source_url"],
        "author": person["source"],
        "publication_date": None,
        "official": True,
        "live_data": True,
        "retrieved_at": datetime.now(UTC).isoformat(),
    }


def _format_brl(value: float) -> str:
    formatted = f"{value:,.2f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def build_legislative_chunks(query: str, limit_people: int = 3) -> list[dict]:
    people = resolve_current_officeholders(query, limit=limit_people)
    if not people:
        return []

    normalized_query = normalize_text(query)
    wants_expenses = any(
        term in normalized_query
        for term in ("gasto", "gastos", "despesa", "despesas", "cota parlamentar")
    )
    wants_proposals = any(
        term in normalized_query
        for term in (
            "projeto",
            "projetos",
            "projeto de lei",
            "projetos de lei",
            "proposta legislativa",
            "propostas legislativas",
            "proposicao",
            "proposicoes",
            "materias de autoria",
        )
    )

    chunks: list[dict] = []
    for person in people:
        chunks.append(_profile_chunk(person))

        if wants_expenses and person["office"] == "deputy":
            try:
                expenses = fetch_deputy_expenses(person["id"], date.today().year)
            except CamaraAPIError:
                expenses = None
            if expenses is not None:
                chunks.append(
                    {
                        "document_id": f"deputy-{person['id']}-expenses",
                        "text": (
                            f"Em {expenses['year']}, a API oficial registra "
                            f"R$ {_format_brl(expenses['total_brl'])} em despesas líquidas "
                            f"para {person['name']}, distribuídas em "
                            f"{expenses['expense_records']} registros."
                        ),
                        "score": 1.0,
                        "title": f"Despesas oficiais - {person['name']}",
                        "source_type": "official_deputy_expenses",
                        "source_url": person["source_url"],
                        "author": "Câmara dos Deputados - Dados Abertos",
                        "publication_date": str(date.today()),
                        "official": True,
                        "live_data": True,
                        "retrieved_at": datetime.now(UTC).isoformat(),
                    }
                )

        if wants_proposals and person["office"] == "deputy":
            try:
                proposals = fetch_deputy_recent_propositions(person["id"], limit=5)
            except CamaraAPIError:
                proposals = []
            for proposal in proposals:
                chunks.append(
                    {
                        "document_id": (
                            f"deputy-{person['id']}-proposal-{proposal['id']}"
                        ),
                        "text": (
                            f"{proposal['identifier']}: "
                            f"{proposal.get('summary') or 'Ementa não informada.'}"
                        ),
                        "score": 1.0,
                        "title": (
                            f"Proposição de autoria de {person['name']} - "
                            f"{proposal['identifier']}"
                        ),
                        "source_type": "official_deputy_proposition",
                        "source_url": proposal.get("api_url") or person["source_url"],
                        "author": "Câmara dos Deputados - Dados Abertos",
                        "publication_date": None,
                        "official": True,
                        "live_data": True,
                        "retrieved_at": datetime.now(UTC).isoformat(),
                    }
                )

        if wants_proposals and person["office"] == "senator":
            try:
                proposals = fetch_senator_recent_processes(person["id"], limit=5)
            except SenadoAPIError:
                proposals = []
            for proposal in proposals:
                chunks.append(
                    {
                        "document_id": (
                            f"senator-{person['id']}-process-{proposal['id']}"
                        ),
                        "text": (
                            f"{proposal['identifier']}: "
                            f"{proposal.get('summary') or 'Ementa não informada.'} "
                            f"Apresentação: {proposal.get('presented_at') or 'N/A'}. "
                            f"Situação: {proposal.get('status') or 'não informada'}."
                        ),
                        "score": 1.0,
                        "title": (
                            f"Processo legislativo associado a {person['name']} - "
                            f"{proposal['identifier']}"
                        ),
                        "source_type": "official_senator_process",
                        "source_url": (
                            proposal.get("document_url")
                            or person.get("profile_url")
                            or person["source_url"]
                        ),
                        "author": "Senado Federal - Dados Abertos",
                        "publication_date": proposal.get("presented_at"),
                        "official": True,
                        "live_data": True,
                        "retrieved_at": datetime.now(UTC).isoformat(),
                    }
                )
    return chunks


def policy_evidence_unavailable_result(query: str) -> dict:
    try:
        calendar_chunks = build_calendar_chunks(
            "convenções partidárias e registro de candidaturas",
            limit=3,
        )
    except TSEDataError:
        calendar_chunks = []

    today = date.today()
    if today < date(2026, 7, 20):
        timing_note = (
            "O calendário oficial prevê as convenções partidárias entre "
            "20 de julho e 5 de agosto e o prazo de registro de candidaturas "
            "até 15 de agosto de 2026."
        )
    elif today <= date(2026, 8, 15):
        timing_note = (
            "O processo de convenções e registro de candidaturas ainda está "
            "em andamento; o prazo oficial termina em 15 de agosto de 2026."
        )
    else:
        timing_note = (
            "O prazo de registro de candidaturas terminou em 15 de agosto de "
            "2026, mas a aplicação ainda não possui um programa oficial "
            "indexado que sustente esta resposta."
        )

    answer = (
        "### Evidência oficial ainda insuficiente\n\n"
        "A aplicação não encontrou, no corpus oficial atual, programas de governo "
        "registrados que sustentem uma comparação factual para esta pergunta. "
        "Por isso, os cenários sintéticos do portfólio não foram usados como se "
        "fossem propostas reais.\n\n"
        f"{timing_note} Programas oficiais devem ser associados "
        "às candidaturas registradas e publicados com sua proveniência antes de "
        "serem usados pelo assistente.\n\n"
        f"**Pergunta preservada para auditoria:** {query}"
    )
    return {
        "answer": answer,
        "provider": "official-evidence-gate",
        "model": "deterministic-policy-gate",
        "sources_used": [
            {
                "title": chunk["title"],
                "url": chunk["source_url"],
                "publication_date": chunk.get("publication_date"),
                "author": chunk["author"],
                "synthetic": False,
                "official": True,
                "live_data": chunk.get("live_data", False),
                "retrieved_at": chunk.get("retrieved_at"),
            }
            for chunk in calendar_chunks
        ],
        "fallback_reason": "No indexed official candidate program supports the query.",
    }


def official_evidence_unavailable_result(query: str) -> dict:
    return {
        "answer": (
            "### Evidência oficial insuficiente\n\n"
            "Não encontrei uma fonte oficial compatível com esta pergunta no "
            "conjunto atualmente conectado. Para evitar inferências ou conteúdo "
            "fabricado, nenhuma resposta factual foi gerada.\n\n"
            "A base atual cobre o calendário do TSE e dados legislativos ao vivo "
            "da Câmara dos Deputados e do Senado Federal. Perguntas sobre outros "
            "temas exigem uma fonte oficial adicional e versionada.\n\n"
            f"**Pergunta preservada para auditoria:** {query}"
        ),
        "provider": "official-evidence-gate",
        "model": "deterministic-evidence-gate",
        "sources_used": [],
        "fallback_reason": "No connected official source supports the query.",
    }
