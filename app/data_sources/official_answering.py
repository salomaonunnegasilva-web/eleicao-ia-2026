from __future__ import annotations

import re
from datetime import UTC, date, datetime

from app.data_sources.camara_client import (
    CamaraAPIError,
    fetch_deputy_expenses,
    fetch_deputy_recent_propositions,
    list_all_deputies,
)
from app.data_sources.datajud_client import (
    DataJudAPIError,
    SOURCE_URL as DATAJUD_SOURCE_URL,
    extract_process_numbers,
    fetch_process_by_number,
    summarize_process,
)
from app.data_sources.portal_transparencia_client import (
    PortalTransparenciaAPIError,
    SOURCE_URL as PORTAL_TRANSPARENCIA_SOURCE_URL,
    extract_cpf,
    fetch_server_remuneration,
    has_api_key as portal_transparencia_has_api_key,
    search_ceis_by_name,
    search_cnep_by_name,
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
    "processo",
    "processos",
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


def _datajud_process_chunk(record: dict) -> dict:
    summary = summarize_process(record)
    text = (
        "Registro de metadados processuais do CNJ DataJud. "
        f"Numero do processo: {summary.get('process_number') or 'N/A'}. "
        f"Tribunal: {summary.get('tribunal') or summary.get('index') or 'N/A'}. "
        f"Classe: {summary.get('class_name') or 'N/A'}. "
        f"Data de ajuizamento: {summary.get('filing_date') or 'N/A'}. "
        f"Grau: {summary.get('degree') or 'N/A'}. "
        f"Nivel de sigilo: {summary.get('secrecy_level')}. "
        f"Orgao julgador: {summary.get('judging_body') or 'N/A'}. "
        f"Assuntos: {summary.get('subjects') or 'N/A'}. "
        f"Movimentos recentes: {summary.get('latest_movements') or 'N/A'}. "
        "Este metadado nao implica culpa, condenacao ou irregularidade."
    )
    return {
        "document_id": (
            f"datajud-{summary.get('index') or 'unknown'}-"
            f"{summary.get('process_number') or 'process'}"
        ),
        "text": text,
        "score": 1.0,
        "title": (
            "Metadados processuais CNJ DataJud - "
            f"{summary.get('process_number') or 'processo'}"
        ),
        "source_type": "official_datajud_process",
        "source_url": DATAJUD_SOURCE_URL,
        "author": "CNJ DataJud - API Publica",
        "publication_date": summary.get("filing_date"),
        "official": True,
        "live_data": True,
        "retrieved_at": summary.get("retrieved_at"),
    }


def _portal_sanction_chunk(record: dict, registry: str) -> dict:
    sanctioned = (
        record.get("sancionado")
        or record.get("pessoa")
        or record.get("nomeSancionado")
        or record.get("razaoSocial")
        or {}
    )
    sanction = record.get("sancao") or record.get("tipoSancao") or {}
    agency = record.get("orgaoSancionador") or record.get("orgao") or {}
    process = record.get("processo") or record.get("numeroProcesso")
    name = (
        sanctioned.get("nome")
        if isinstance(sanctioned, dict)
        else sanctioned
    ) or record.get("nomeSancionado") or "N/A"
    sanction_name = (
        sanction.get("descricao")
        if isinstance(sanction, dict)
        else sanction
    ) or "N/A"
    agency_name = (
        agency.get("nome")
        if isinstance(agency, dict)
        else agency
    ) or "N/A"
    start_date = (
        record.get("dataInicioSancao")
        or record.get("dataPublicacaoSancao")
        or record.get("dataReferencia")
    )
    end_date = record.get("dataFimSancao")
    text = (
        f"Registro {registry} no Portal da Transparencia. "
        f"Sancionado: {name}. "
        f"Sancao: {sanction_name}. "
        f"Orgao sancionador: {agency_name}. "
        f"Processo: {process or 'N/A'}. "
        f"Inicio: {start_date or 'N/A'}. "
        f"Fim: {end_date or 'N/A'}."
    )
    return {
        "document_id": f"portal-{registry.lower()}-{record.get('id') or name}",
        "text": text,
        "score": 1.0,
        "title": f"Registro {registry} - {name}",
        "source_type": f"official_portal_{registry.lower()}_sanction",
        "source_url": PORTAL_TRANSPARENCIA_SOURCE_URL,
        "author": "Portal da Transparencia / CGU",
        "publication_date": start_date,
        "official": True,
        "live_data": True,
        "retrieved_at": datetime.now(UTC).isoformat(),
    }


def _portal_remuneration_chunk(record: dict) -> dict:
    person = record.get("servidor") or record.get("pessoa") or {}
    name = (
        person.get("nome")
        if isinstance(person, dict)
        else person
    ) or record.get("nome") or "servidor"
    amount_keys = (
        "remuneracaoBasicaBruta",
        "remuneracaoPosDeducoesObrigatorias",
        "valorTotalRemuneracaoAposDeducoes",
        "valorTotalRemuneracao",
    )
    values = []
    for key in amount_keys:
        if key in record:
            values.append(f"{key}: {record[key]}")
    text = (
        "Registro de remuneracao do Poder Executivo Federal no Portal da "
        f"Transparencia. Pessoa: {name}. "
        f"Mes/ano: {record.get('mesAno') or record.get('mesAnoReferencia') or 'N/A'}. "
        f"Valores retornados: {'; '.join(values) if values else 'ver JSON oficial'}."
    )
    return {
        "document_id": f"portal-remuneration-{record.get('id') or name}",
        "text": text,
        "score": 1.0,
        "title": f"Remuneracao Portal da Transparencia - {name}",
        "source_type": "official_portal_transparency_remuneration",
        "source_url": PORTAL_TRANSPARENCIA_SOURCE_URL,
        "author": "Portal da Transparencia / CGU",
        "publication_date": str(record.get("mesAno") or ""),
        "official": True,
        "live_data": True,
        "retrieved_at": datetime.now(UTC).isoformat(),
    }


def _transparency_scope_chunk(query: str, people: list[dict]) -> dict:
    names = ", ".join(person["name"] for person in people) if people else "a pessoa consultada"
    text = (
        "Escopo de transparencia conectado: a aplicacao consulta despesas e "
        "proposicoes legislativas da Camara, processos legislativos do Senado, "
        "metadados processuais do CNJ DataJud quando o numero do processo e "
        "informado, e registros CEIS/CNEP do Portal da Transparencia quando a "
        "chave da API esta configurada. Remuneracao nominal pelo Portal da "
        "Transparencia exige CPF ou id de servidor do Poder Executivo Federal; "
        "para deputados e senadores, a remuneracao deve ser integrada por fontes "
        "proprias da Camara/Senado antes de ser apresentada como valor factual. "
        f"Consulta preservada: {query}. Pessoa(s) identificada(s): {names}."
    )
    return {
        "document_id": "official-transparency-scope",
        "text": text,
        "score": 1.0,
        "title": "Escopo atual de transparencia oficial",
        "source_type": "official_transparency_scope",
        "source_url": PORTAL_TRANSPARENCIA_SOURCE_URL,
        "author": "Eleicao IA 2026 / fontes oficiais conectadas",
        "publication_date": None,
        "official": True,
        "live_data": False,
        "retrieved_at": datetime.now(UTC).isoformat(),
    }


def build_integrity_chunks(query: str, limit_people: int = 3) -> list[dict]:
    normalized_query = normalize_text(query)
    chunks: list[dict] = []

    process_numbers = extract_process_numbers(query)
    for process_number in process_numbers:
        try:
            records = fetch_process_by_number(process_number, limit=5)
        except DataJudAPIError:
            records = []
        chunks.extend(_datajud_process_chunk(record) for record in records)

    people = resolve_current_officeholders(query, limit=limit_people)
    wants_sanctions = any(
        term in normalized_query
        for term in (
            "ceis",
            "cnep",
            "sancao",
            "sancoes",
            "sancionado",
            "inidoneo",
            "inidoneidade",
            "punicao",
            "portal da transparencia",
        )
    )
    wants_compensation = any(
        term in normalized_query
        for term in (
            "salario",
            "remuneracao",
            "contracheque",
            "subsidio",
            "subsidios",
            "quanto ganha",
        )
    )

    if wants_sanctions and people and portal_transparencia_has_api_key():
        for person in people:
            for registry, search in (
                ("CEIS", search_ceis_by_name),
                ("CNEP", search_cnep_by_name),
            ):
                try:
                    records = search(person["name"], limit=3)
                except PortalTransparenciaAPIError:
                    records = []
                chunks.extend(
                    _portal_sanction_chunk(record, registry)
                    for record in records
                )

    cpf = extract_cpf(query)
    if wants_compensation and cpf and portal_transparencia_has_api_key():
        try:
            records = fetch_server_remuneration(cpf=cpf)
        except PortalTransparenciaAPIError:
            records = []
        chunks.extend(_portal_remuneration_chunk(record) for record in records[:3])

    if wants_compensation or (
        any(term in normalized_query for term in ("judicial", "processo", "processos", "criminal"))
        and not process_numbers
    ) or (wants_sanctions and not chunks):
        chunks.append(_transparency_scope_chunk(query, people))

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


def legal_integrity_unavailable_result(query: str) -> dict:
    return {
        "answer": (
            "### Evidencia oficial juridica/transparencia insuficiente\n\n"
            "A pergunta foi reconhecida como consulta juridica, de integridade "
            "ou remuneracao, mas a aplicacao nao encontrou registros oficiais "
            "suficientes para responder com seguranca.\n\n"
            "Para processos judiciais, esta versao consulta o CNJ DataJud por "
            "numero unico de processo; ela nao faz busca ampla por nome de pessoa "
            "para evitar falsos positivos. Para remuneracao no Portal da "
            "Transparencia, a API exige CPF ou id de servidor e chave "
            "`PORTAL_TRANSPARENCIA_API_KEY`. Para deputados e senadores, valores "
            "de remuneracao devem vir de fonte propria da Camara ou do Senado "
            "antes de serem apresentados como fato.\n\n"
            "A existencia de metadados processuais, sancoes ou registros publicos "
            "nao implica culpa, condenacao ou irregularidade sem decisao final "
            "explicitamente citada.\n\n"
            f"**Pergunta preservada para auditoria:** {query}"
        ),
        "provider": "official-evidence-gate",
        "model": "deterministic-legal-integrity-gate",
        "sources_used": [],
        "fallback_reason": "No official legal/transparency record supports the query.",
    }
