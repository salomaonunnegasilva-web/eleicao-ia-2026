import os
import json
import requests
from sqlalchemy.orm import Session
from app.config import settings
from app.text_utils import normalize_text


class LLMProviderError(RuntimeError):
    pass


def call_gemini_api(prompt: str, api_key: str, model_name: str = "gemini-2.5-flash-lite") -> str:
    """Calls Gemini API directly using requests HTTP endpoint to prevent dependency issues."""
    if not model_name.startswith("gemini-"):
        model_name = "gemini-2.5-flash-lite"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048
        }
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        res_data = response.json()
        return res_data["candidates"][0]["content"]["parts"][0]["text"]
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        raise LLMProviderError("Gemini generation failed.") from exc


def call_openai_api(
    prompt: str,
    api_key: str,
    api_base: str | None = None,
    model_name: str = "gpt-4o-mini",
) -> str:
    """Calls OpenAI API or compatible provider."""
    base_url = api_base or "https://api.openai.com/v1"
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "Você é um assistente analítico, neutro e apartidário para a eleição brasileira de 2026."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 1500
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        res_data = response.json()
        return res_data["choices"][0]["message"]["content"]
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        raise LLMProviderError("OpenAI generation failed.") from exc


def _unique_contexts(context_chunks: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for chunk in context_chunks:
        key = chunk["document_id"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return unique


def generate_local_fallback_answer(
    query_text: str,
    context_chunks: list[dict],
    polling_context: dict | None = None,
) -> str:
    """
    Generates a structured, neutral analytical answer using local heuristics.
    Used in mock mode or when API keys are missing.
    """
    query_lower = normalize_text(query_text)

    # 1. Handle polling queries
    if polling_context and "raw_averages" in polling_context and polling_context["raw_averages"]:
        raw = polling_context["raw_averages"]
        valid = polling_context.get("valid_vote_averages", {})
        total_polls = polling_context.get("total_polls", 0)

        # Sort candidates
        sorted_raw = sorted(raw.items(), key=lambda x: x[1], reverse=True)

        ans = []
        ans.append("### Simulação de média ponderada")
        ans.append(
            "**Aviso:** os levantamentos deste módulo são sintéticos e existem "
            "apenas para demonstrar modelagem estatística."
        )
        ans.append(
            "A análise usa pesos de recência e tamanho da amostra "
            f"(data de corte: {polling_context.get('target_date', 'data atual')})."
        )
        ans.append(f"**Total de pesquisas consideradas:** {total_polls}\n")

        ans.append("| Candidato | Intenção de Voto Geral (Média Ponderada) | Votos Válidos Estimados |")
        ans.append("| :--- | :---: | :---: |")
        for cand, val in sorted_raw:
            valid_val = f"{valid.get(cand, 0.0)}%" if cand in valid else "N/A"
            ans.append(f"| {cand} | {val}% | {valid_val} |")

        ans.append("\n**Levantamentos sintéticos considerados:**")
        for p in polling_context.get("polls_used", []):
            ans.append(f"- {p['pollster']} (Publicada em {p['pub_date']}, Peso Calculado: {round(p['weight'], 2)})")

        ans.append("\n> [!NOTE]")
        ans.append(
            "> **Limitações:** o resultado não representa uma previsão real. "
            "Ele demonstra ponderação, normalização e simulação de incerteza."
        )

        return "\n".join(ans)

    # 2. Handle proposal queries
    if not context_chunks:
        return (
            "A base de dados atual não possui documentos suficientes para responder a esta pergunta.\n"
            "**Nota:** Por questões de neutralidade e conformidade regulatória, não emitimos respostas fatuais "
            "sem fontes citadas comprovadas no banco de dados."
        )

    unique_contexts = _unique_contexts(context_chunks)
    ans = [
        "### Resposta baseada no conjunto recuperado",
        f"**Aviso de dados:** {settings.data_notice}\n",
    ]

    for idx, chunk in enumerate(unique_contexts):
        title = chunk["title"]
        author = chunk.get("author", "Desconhecido")
        pub_date = chunk.get("publication_date", "N/A")
        text_snippet = chunk["text"]
        excerpt = text_snippet[:500].strip()

        ans.append(f"#### [{idx + 1}] {title}")
        ans.append(f"- **Autor:** {author} | **Data:** {pub_date}")
        ans.append(f"- **Trecho recuperado:** {excerpt}\n")

    if "tribut" in query_lower:
        ans.append(
            "Os cenários recuperados apresentam abordagens diferentes para "
            "progressividade, desoneração e simplificação tributária. Consulte "
            "os itens numerados acima para manter cada afirmação vinculada ao "
            "documento efetivamente recuperado."
        )
    elif any(term in query_lower for term in ("calendario", "data", "dia", "prazo")):
        ans.append(
            "As datas e os prazos acima vêm do resumo demonstrativo. "
            "Use o link do TSE associado ao documento para confirmação oficial."
        )
    else:
        ans.append(
            "A resposta local apresenta os trechos mais relevantes sem inventar "
            "uma síntese que não esteja sustentada pelo conjunto recuperado."
        )

    return "\n".join(ans)

def generate_grounded_answer(
    db: Session,
    query_text: str,
    context_chunks: list[dict],
    polling_context: dict = None,
    simulation_context: dict = None
) -> dict:
    """
    Main entry point for generating source-grounded answers.
    Combines context, builds system prompts, and routes to appropriate models.
    """
    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    default_model = "gemini-2.5-flash-lite" if provider == "gemini" else "gpt-4o-mini"
    model_name = os.getenv("LLM_MODEL", default_model)

    # If mock is selected or keys are missing, run local fallback generator
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")

    fallback_reason = None
    if provider == "gemini" and not gemini_key:
        fallback_reason = "Gemini API key is not configured."
        provider = "mock"
    elif provider == "openai" and not openai_key:
        fallback_reason = "OpenAI API key is not configured."
        provider = "mock"

    # Build context string
    docs_context_str = ""
    for idx, chunk in enumerate(context_chunks):
        docs_context_str += f"--- DOCUMENTO [{idx + 1}] ---\n"
        docs_context_str += f"Título: {chunk['title']}\n"
        docs_context_str += f"Autor/Candidato: {chunk.get('author') or 'N/A'}\n"
        docs_context_str += f"Data de Publicação: {chunk.get('publication_date') or 'N/A'}\n"
        docs_context_str += f"URL: {chunk.get('source_url') or 'N/A'}\n"
        docs_context_str += f"Texto: {chunk['text']}\n\n"

    polls_context_str = ""
    if polling_context and "raw_averages" in polling_context:
        polls_context_str = f"--- DADOS ESTATÍSTICOS DAS PESQUISAS ELEITORAIS ---\n"
        polls_context_str += f"Pesquisa de Média Ponderada (Data de corte: {polling_context.get('target_date')}):\n"
        polls_context_str += json.dumps(polling_context.get("raw_averages"), indent=2, ensure_ascii=False) + "\n"
        polls_context_str += f"Votos Válidos Estimados:\n"
        polls_context_str += json.dumps(polling_context.get("valid_vote_averages"), indent=2, ensure_ascii=False) + "\n"

    sims_context_str = ""
    if simulation_context and "runoff_probability" in simulation_context:
        sims_context_str = (
            "--- RESULTADOS DA SIMULAÇÃO MONTE CARLO "
            f"({simulation_context.get('iterations')} ITERAÇÕES) ---\n"
        )
        sims_context_str += f"Probabilidade de haver 2º Turno: {simulation_context.get('runoff_probability')}%\n"
        sims_context_str += "Intervalos de Confiança (95% CI) e Médias:\n"
        sims_context_str += json.dumps(simulation_context.get("candidate_summary"), indent=2, ensure_ascii=False) + "\n"
        sims_context_str += "Probabilidade de Vitória no 1º Turno (Valid Votes > 50%):\n"
        sims_context_str += json.dumps(simulation_context.get("win_probabilities"), indent=2, ensure_ascii=False) + "\n"

    # Construct Prompt
    prompt = f"""Você é o Eleição IA 2026, um assistente analítico, neutro e apartidário para uma demonstração técnica de portfólio.

Instruções Cruciais:
1. Responda a pergunta do usuário com base APENAS nas fontes e dados fornecidos abaixo. Não tente extrapolar ou adivinhar informações.
2. Seja objetivo, analítico e não-partidário. Nunca use termos subjetivos ou adjetivos fortes sobre os candidatos.
3. Se os documentos forem insuficientes para responder a pergunta factualmente, recuse-se a inventar. Responda explicitamente: "As fontes e diretrizes documentais fornecidas no banco de dados são insuficientes para responder a esta questão." e justifique brevemente o que está faltando.
4. Nunca faça previsões subjetivas. Use o termo "estatístico" ou "probabilístico" baseado nos dados de simulação, destacando a incerteza e margens de erro.
5. Cite os documentos usando [1], [2], etc.
6. Declare claramente que pesquisas e propostas marcadas como DEMO são sintéticas.

--- DADOS DISPONÍVEIS ---
{docs_context_str}
{polls_context_str}
{sims_context_str}
-------------------------

Pergunta do Usuário: {query_text}

Resposta em Português:"""

    try:
        if provider == "mock":
            answer = generate_local_fallback_answer(query_text, context_chunks, polling_context)
            model_name = "deterministic-local"
        elif provider == "gemini":
            answer = call_gemini_api(prompt, gemini_key, model_name)
        elif provider == "openai":
            api_base = os.getenv("OPENAI_API_BASE", None)
            answer = call_openai_api(prompt, openai_key, api_base, model_name)
        else:
            fallback_reason = f"Unsupported provider: {provider}"
            provider = "mock"
            model_name = "deterministic-local"
            answer = generate_local_fallback_answer(query_text, context_chunks, polling_context)
    except LLMProviderError as exc:
        fallback_reason = str(exc)
        provider = "local-fallback"
        model_name = "deterministic-local"
        answer = generate_local_fallback_answer(query_text, context_chunks, polling_context)

    return {
        "query": query_text,
        "answer": answer,
        "provider": provider,
        "model": model_name,
        "sources_used": [
            {
                "title": c["title"],
                "url": c.get("source_url"),
                "publication_date": c.get("publication_date"),
                "author": c.get("author"),
                "synthetic": str(c.get("source_type", "")).startswith("demo_"),
            }
            for c in _unique_contexts(context_chunks)
        ],
        "fallback_reason": fallback_reason,
    }
