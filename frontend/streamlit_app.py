import os
import datetime
import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# 1. Page Configuration
st.set_page_config(
    page_title="Eleição IA 2026",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 2. Theme Toggle State
if "theme" not in st.session_state:
    st.session_state.theme = "dark"

def toggle_theme():
    st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"

IS_DARK = st.session_state.theme == "dark"

# 3. CSS Design System
# zinc colors (dark mode vs light mode)
css = f"""
<style>
:root {{
    --bg: { '#09090b' if IS_DARK else '#ffffff' };
    --bg-subtle: { '#0c0c0f' if IS_DARK else '#f9fafb' };
    --card: { '#0c0c0f' if IS_DARK else '#ffffff' };
    --card-hover: { '#131316' if IS_DARK else '#f4f4f5' };
    --border: { '#1e1e24' if IS_DARK else '#e4e4e7' };
    --border-subtle: { '#16161a' if IS_DARK else '#f0f0f2' };
    --text: { '#fafafa' if IS_DARK else '#09090b' };
    --text-muted: #71717a;
    --text-dim: { '#52525b' if IS_DARK else '#a1a1aa' };
    --accent: #2563eb;
    --accent-muted: #1d4ed8;
    --green: { '#22c55e' if IS_DARK else '#16a34a' };
    --green-muted: { 'rgba(34,197,94,0.12)' if IS_DARK else 'rgba(22,163,74,0.08)' };
    --red: { '#ef4444' if IS_DARK else '#dc2626' };
    --red-muted: { 'rgba(239,68,68,0.12)' if IS_DARK else 'rgba(220,38,38,0.08)' };
    --amber: { '#f59e0b' if IS_DARK else '#d97706' };
    --amber-muted: { 'rgba(245,158,11,0.12)' if IS_DARK else 'rgba(217,119,6,0.08)' };
    --shadow: { 'none' if IS_DARK else '0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.03)' };
    --radius: 10px;
}}

/* Hide Streamlit default components */
header[data-testid="stHeader"], #MainMenu, footer, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"], .stDeployButton,
div[data-testid="stSidebarCollapsedControl"] {{
    display: none !important;
}}

/* Global app styling */
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"], .main, .block-container, section[data-testid="stMain"] {{
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'DM Sans', -apple-system, sans-serif !important;
}}

.block-container {{
    padding: 2rem 2.5rem 3rem !important;
    max-width: 1360px !important;
}}

/* Metric Cards */
.metric-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem 1.4rem;
    box-shadow: var(--shadow);
    margin-bottom: 1rem;
}}
.metric-label {{
    font-size: 0.78rem;
    color: var(--text-muted);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
.metric-value {{
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.03em;
    margin-top: 0.2rem;
}}
.metric-delta {{
    font-size: 0.75rem;
    font-weight: 500;
    margin-top: 0.4rem;
    padding: 2px 8px;
    border-radius: 6px;
    display: inline-flex;
    align-items: center;
    gap: 3px;
}}
.delta-up {{ color: var(--green); background: var(--green-muted); }}
.delta-down {{ color: var(--red); background: var(--red-muted); }}
.delta-warn {{ color: var(--amber); background: var(--amber-muted); }}

/* Chart Wrapper */
.chart-wrap {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.2rem;
    box-shadow: var(--shadow);
    margin-bottom: 1rem;
}}
.chart-title {{
    font-size: 0.88rem;
    font-weight: 600;
    color: var(--text);
}}
.chart-subtitle {{
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-bottom: 1rem;
}}

/* Data Tables */
.data-table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 0.85rem;
    margin: 1rem 0;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
}}
.data-table th {{
    text-align: left;
    padding: 0.75rem 1rem;
    color: var(--text-muted);
    font-weight: 600;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid var(--border);
    background: var(--bg-subtle);
}}
.data-table td {{
    padding: 0.75rem 1rem;
    color: var(--text);
    border-bottom: 1px solid var(--border-subtle);
}}
.data-table tr:last-child td {{
    border-bottom: none;
}}

/* Pill styled tabs override */
button[data-baseweb="tab"] {{
    background: transparent !important;
    color: var(--text-muted) !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    padding: 0.55rem 1.1rem !important;
    border: 1px solid transparent !important;
    border-radius: 7px !important;
    transition: all 0.2s ease !important;
}}
button[data-baseweb="tab"][aria-selected="true"] {{
    color: var(--text) !important;
    background: var(--card) !important;
    border-color: var(--border) !important;
}}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {{
    display: none !important;
}}
[data-baseweb="tab-list"] {{
    gap: 6px !important;
    background: var(--bg-subtle) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    padding: 4px !important;
    margin-bottom: 1.5rem !important;
}}

/* Column spacing */
[data-testid="stHorizontalBlock"] {{
    gap: 1.25rem !important;
}}

/* Brand elements */
.brand {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 1.5rem;
}}
.brand-name {{
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.03em;
}}
.brand-badge {{
    font-size: 0.7rem;
    font-weight: 600;
    background: var(--accent);
    color: #ffffff;
    padding: 2px 8px;
    border-radius: 20px;
    text-transform: uppercase;
}}

/* Badges */
.badge {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 600;
}}
.badge-green {{ color: var(--green); background: var(--green-muted); }}
.badge-red {{ color: var(--red); background: var(--red-muted); }}
.badge-amber {{ color: var(--amber); background: var(--amber-muted); }}
.badge-blue {{ color: var(--accent); background: rgba(37,99,235,0.1); }}

/* Chat UI customizations */
.stChatMessage {{
    background-color: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1rem !important;
    margin-bottom: 0.75rem !important;
}}
</style>
"""
st.markdown(css, unsafe_allow_html=True)

# 4. Helper UI Functions
def metric_card(label, value, delta=None, delta_type="up"):
    cls = f"delta-{delta_type}"
    arrow = "↑" if delta_type == "up" else ("↓" if delta_type == "down" else "→")
    delta_html = f'<div class="metric-delta {cls}">{arrow} {delta}</div>' if delta else ""
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)

# 5. Header setup
head_left, head_right = st.columns([8, 2])
with head_left:
    st.markdown("""
    <div class="brand">
        <span class="brand-name">Eleição IA 2026</span>
        <span class="brand-badge">RAG + Forecasting</span>
    </div>
    """, unsafe_allow_html=True)
with head_right:
    theme_label = "☀️ Modo Claro" if IS_DARK else "🌙 Modo Escuro"
    st.button(theme_label, on_click=toggle_theme, width="stretch")

# Plotly Theme Setup
PLOT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans, sans-serif", color="#71717a" if not IS_DARK else "#a1a1aa", size=11),
    margin=dict(l=40, r=20, t=10, b=40),
    xaxis=dict(
        gridcolor="rgba(0,0,0,0.05)" if not IS_DARK else "rgba(255,255,255,0.05)",
        zerolinecolor="rgba(0,0,0,0.05)" if not IS_DARK else "rgba(255,255,255,0.05)",
        tickfont=dict(size=10, color="#71717a"),
    ),
    yaxis=dict(
        gridcolor="rgba(0,0,0,0.05)" if not IS_DARK else "rgba(255,255,255,0.05)",
        zerolinecolor="rgba(0,0,0,0.05)" if not IS_DARK else "rgba(255,255,255,0.05)",
        tickfont=dict(size=10, color="#71717a"),
    ),
)

# Backend connection settings
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def api_request(method: str, path: str, **kwargs):
    response = requests.request(
        method,
        f"{BACKEND_URL}{path}",
        timeout=kwargs.pop("timeout", 30),
        **kwargs,
    )
    response.raise_for_status()
    return response.json()


# Verify connection
@st.cache_data(ttl=5)
def get_backend_info():
    try:
        return api_request("GET", "/", timeout=5)
    except requests.RequestException:
        return None

backend_info = get_backend_info()

if not backend_info:
    st.error("⚠️ Não foi possível conectar ao FastAPI backend. Certifique-se de que o backend Docker está rodando ou use a porta correta.")
    st.info(f"Tentando acessar: `{BACKEND_URL}`. Se estiver rodando localmente, tente rodar `docker compose up --build` ou `uvicorn app.api.main:app` na pasta raiz.")
    if st.button("Tentar Conectar Novamente"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

st.warning(
    "**Demo de portfólio:** pesquisas, candidatos e propostas eleitorais são "
    "sintéticos. A aba Dados Oficiais consulta diretamente as APIs públicas "
    "da Câmara dos Deputados e do Senado Federal."
)

# Load DB counts
db_status = {"documents_indexed": 0, "chunks_indexed": 0}
try:
    db_status = api_request("GET", "/api/ingest/status", timeout=5)
except Exception as e:
    st.warning(f"Aviso: Não foi possível carregar o status do banco de dados: {str(e)}")


# Tabs
tab_chat, tab_polls, tab_sims, tab_official, tab_ingest, tab_evals = st.tabs([
    "💬 Assistente Inteligente",
    "📊 Pesquisas Sintéticas",
    "🎲 Simulação Sintética",
    "🏛️ Dados Oficiais",
    "📂 Base RAG",
    "🧪 Avaliação do Sistema"
])

# -----------------
# TAB 1: Chat Assistant
# -----------------
with tab_chat:
    st.caption(
        "Explore o roteamento RAG e o forecasting com um cenário eleitoral "
        "sintético, claramente separado dos dados legislativos oficiais."
    )

    # Session chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("Visualizar Fontes Citadas"):
                    for idx, s in enumerate(msg["sources"]):
                        st.markdown(f"**[{idx+1}] {s['title']}**")
                        if s.get('author'):
                            st.caption(f"Autor: {s['author']} | URL: {s.get('url') or 'N/A'}")
                        else:
                            st.caption(f"URL: {s.get('url') or 'N/A'}")

    if prompt := st.chat_input("Ex: Quais as propostas de Tarcísio e Lula sobre reforma tributária?"):
        # Display user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analisando fontes e rodando modelos..."):
                try:
                    res = api_request("POST", "/api/chat", json={"query": prompt}, timeout=45)
                    answer = res["answer"]
                    sources = res.get("sources", [])
                    route = res.get("route", "rag")

                    st.markdown(answer)

                    # If forecast-heavy query, display info badge
                    if route in ("forecast", "hybrid"):
                        st.markdown(f'<span class="badge badge-blue"> Rota: Forecasting Estatístico Ponderado</span>', unsafe_allow_html=True)
                    elif route == "candidate_profile":
                        st.markdown(
                            '<span class="badge badge-amber"> Rota: Cadastro Estruturado</span>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(f'<span class="badge badge-green"> Rota: RAG Grounded</span>', unsafe_allow_html=True)

                    if sources:
                        with st.expander("Visualizar Fontes Citadas"):
                            for idx, s in enumerate(sources):
                                st.markdown(f"**[{idx+1}] {s['title']}**")
                                st.caption(f"Autor: {s.get('author') or 'Desconhecido'} | URL: {s.get('url') or 'N/A'}")

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer,
                        "sources": sources
                    })
                except requests.RequestException as e:
                    st.error(f"Erro ao gerar resposta do assistente: {str(e)}")

# -----------------
# TAB 2: Polling Trends
# -----------------
with tab_polls:
    st.markdown("### Média Ponderada — Cenário Sintético de Primeiro Turno")
    st.info("Os levantamentos desta aba são fictícios e demonstram apenas a implementação estatística.")
    st.caption("A média pondera cada amostra pelo tamanho e por decaimento exponencial de recência.")

    try:
        avg_data = api_request(
            "GET",
            "/api/forecast/average",
            params={"scenario": "Estimulada Turno 1", "round_num": 1},
        )

        # Display Metrics
        c1, c2, c3, c4 = st.columns(4)
        raw_avg = avg_data.get("raw_averages", {})
        valid_avg = avg_data.get("valid_vote_averages", {})

        # Sort candidates to find top candidates
        sorted_cand = sorted(raw_avg.items(), key=lambda x: x[1], reverse=True)

        with c1:
            val = f"{raw_avg.get('Luiz Inácio Lula da Silva', 0.0)}%"
            v_val = f"{valid_avg.get('Luiz Inácio Lula da Silva', 0.0)}% válidos"
            metric_card("Lula (PT)", val, v_val, "up")
        with c2:
            val = f"{raw_avg.get('Tarcísio de Freitas', 0.0)}%"
            v_val = f"{valid_avg.get('Tarcísio de Freitas', 0.0)}% válidos"
            metric_card("Tarcísio de Freitas (Rep/PL)", val, v_val, "up")
        with c3:
            val = f"{raw_avg.get('Ciro Gomes', 0.0)}%"
            metric_card("Ciro Gomes (PDT)", val, "Geral", "warn")
        with c4:
            val = f"{raw_avg.get('Não Sabe/Indeciso', 0.0)}%"
            metric_card("Brancos/Nulos/Indecisos", f"{round(raw_avg.get('Branco/Nulo', 0.0) + raw_avg.get('Não Sabe/Indeciso', 0.0), 2)}%", "Não válidos", "down")

        # Chart
        st.markdown('<div class="chart-wrap"><div class="chart-title">Média Ponderada por Candidato</div><div class="chart-subtitle">Votos Gerais vs Votos Válidos</div>', unsafe_allow_html=True)

        # Format candidate color map
        color_map = {
            "Luiz Inácio Lula da Silva": "#dc2626", # Red
            "Tarcísio de Freitas": "#1d4ed8",      # Navy Blue
            "Ciro Gomes": "#c084fc",               # Rose
            "Romeu Zema": "#f59e0b",               # Amber
            "Simone Tebet": "#a21caf",             # Purple
            "Branco/Nulo": "#71717a",              # Gray
            "Não Sabe/Indeciso": "#a1a1aa"         # Light Gray
        }

        # Plotly chart
        fig = go.Figure()

        candidates_plot = list(raw_avg.keys())
        raw_vals = [raw_avg[c] for c in candidates_plot]
        valid_vals = [valid_avg.get(c, 0.0) for c in candidates_plot]
        colors = [color_map.get(c, "#3b82f6") for c in candidates_plot]

        fig.add_trace(go.Bar(
            name='Intenção de Voto Geral',
            x=candidates_plot,
            y=raw_vals,
            marker_color=colors,
            opacity=0.8
        ))

        fig.add_trace(go.Bar(
            name='Votos Válidos Estimados',
            x=candidates_plot,
            y=valid_vals,
            marker_color=colors,
            opacity=0.4,
            visible='legendonly'
        ))

        fig.update_layout(
            barmode='group',
            height=350,
            **PLOT_LAYOUT
        )

        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

        # Details Table
        st.markdown("#### Tabela de Intenções de Voto Ponderada")
        rows = ""
        for name, val in sorted_cand:
            valid_val = f"{valid_avg.get(name, 0.0)}%" if name in valid_avg else "N/A"
            rows += f"<tr><td>{name}</td><td>{val}%</td><td>{valid_val}</td></tr>"

        st.markdown(f"""
        <table class="data-table">
            <thead>
                <tr>
                    <th>Candidato</th>
                    <th>Média Ponderada Geral</th>
                    <th>Votos Válidos Ponderados</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        """, unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Erro ao renderizar dados das pesquisas: {str(e)}")

# -----------------
# TAB 3: Simulations
# -----------------
with tab_sims:
    st.markdown("### Simulação Monte Carlo — Cenário Sintético")
    st.info("O resultado não é uma previsão eleitoral. Ele demonstra modelagem de incerteza.")
    st.caption("A simulação calcula intervalos com base nas margens de erro do dataset demonstrativo.")

    try:
        sim_data = api_request(
            "GET",
            "/api/forecast/simulation",
            params={"scenario": "Estimulada Turno 1", "round_num": 1},
            timeout=45,
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            metric_card("Probabilidade de Segundo Turno", f"{sim_data.get('runoff_probability')}%", "Modelagem", "warn" if sim_data.get('runoff_probability', 0) > 50 else "up")
        with c2:
            win_probs = sim_data.get("win_probabilities", {})
            top_winner = max(win_probs.items(), key=lambda x: x[1]) if win_probs else ("Nenhum", 0.0)
            metric_card(f"Vitória 1º Turno: {top_winner[0]}", f"{top_winner[1]}%", "Frequência Simulada", "up")
        with c3:
            total_it = sim_data.get("iterations", 10000)
            metric_card("Iterações Simuladas", f"{total_it:,}", "Monte Carlo Run", "up")

        # IC Plotly plot
        st.markdown('<div class="chart-wrap"><div class="chart-title">Intervalos de Confiança (95% CI) para Votos Válidos</div><div class="chart-subtitle">Ponto representa a mediana simulada</div>', unsafe_allow_html=True)

        cand_summary = sim_data.get("candidate_summary", {})
        valid_cands = [c for c in cand_summary if "valid_median" in cand_summary[c]]

        medians = [cand_summary[c]["valid_median"] for c in valid_cands]
        lowers = [cand_summary[c]["valid_ci_lower"] for c in valid_cands]
        uppers = [cand_summary[c]["valid_ci_upper"] for c in valid_cands]

        color_map = {
            "Luiz Inácio Lula da Silva": "#dc2626",
            "Tarcísio de Freitas": "#1d4ed8",
            "Ciro Gomes": "#c084fc",
            "Romeu Zema": "#f59e0b",
            "Simone Tebet": "#a21caf"
        }
        cand_colors = [color_map.get(c, "#3b82f6") for c in valid_cands]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=valid_cands,
            y=medians,
            mode='markers',
            marker=dict(size=12, color=cand_colors, symbol='square'),
            error_y=dict(
                type='data',
                symmetric=False,
                array=[u - m for m, u in zip(medians, uppers)],
                arrayminus=[m - l for m, l in zip(medians, lowers)],
                color='#71717a',
                thickness=2,
                width=10
            )
        ))

        fig.update_layout(
            yaxis_title="Votos Válidos (%)",
            height=300,
            **PLOT_LAYOUT
        )

        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

        # Details Simulation Table
        st.markdown("#### Detalhes de Simulação e Probabilidades")
        rows = ""
        for name in valid_cands:
            stats = cand_summary[name]
            ci = f"{round(stats['valid_ci_lower'], 1)}% – {round(stats['valid_ci_upper'], 1)}%"
            prob_top2 = sim_data.get("top_two_probabilities", {}).get(name, 0.0)
            rows += f"<tr><td>{name}</td><td>{round(stats['valid_median'], 1)}%</td><td>{ci}</td><td>{prob_top2}%</td></tr>"

        st.markdown(f"""
        <table class="data-table">
            <thead>
                <tr>
                    <th>Candidato</th>
                    <th>Mediana (Votos Válidos)</th>
                    <th>Intervalo de Confiança 95%</th>
                    <th>Probabilidade de Ir ao 2º Turno</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        """, unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Erro ao renderizar simulação: {str(e)}")

# -----------------
# TAB 4: Official public data
# -----------------
with tab_official:
    st.markdown("### Dados Legislativos Oficiais ao Vivo")
    st.caption(
        "Consultas diretas às APIs de Dados Abertos da Câmara dos Deputados e "
        "do Senado Federal. O Custo Político é uma referência de produto, não a fonte."
    )

    chamber_tab, senate_tab = st.tabs(["Câmara dos Deputados", "Senado Federal"])

    with chamber_tab:
        deputy_name = st.text_input(
            "Buscar deputado por nome",
            value="Tabata Amaral",
            key="official_deputy_name",
        )
        if st.button("Consultar Câmara", key="search_chamber"):
            st.cache_data.clear()

        try:
            deputy_payload = api_request(
                "GET",
                "/api/official/deputies",
                params={"name": deputy_name, "limit": 20},
                timeout=30,
            )
            deputies = deputy_payload.get("items", [])
            if deputies:
                st.dataframe(
                    pd.DataFrame(deputies)[["name", "party", "state", "email"]],
                    width="stretch",
                    hide_index=True,
                )
                selected = st.selectbox(
                    "Carregar métricas oficiais",
                    deputies,
                    format_func=lambda item: f"{item['name']} ({item['party']}/{item['state']})",
                )
                if st.button("Carregar gastos e proposições", key="load_deputy_metrics"):
                    metrics = api_request(
                        "GET",
                        f"/api/official/deputies/{selected['id']}/metrics",
                        params={"year": datetime.date.today().year},
                        timeout=60,
                    )
                    c1, c2 = st.columns(2)
                    with c1:
                        metric_card(
                            f"Gastos líquidos {metrics['expenses']['year']}",
                            f"R$ {metrics['expenses']['total_brl']:,.2f}",
                            f"{metrics['expenses']['expense_records']} registros",
                            "warn",
                        )
                    with c2:
                        metric_card(
                            "Proposições de autoria",
                            str(metrics["authored_propositions"]),
                            "API oficial",
                            "up",
                        )
                    st.caption(metrics["attendance_note"])
            else:
                st.info("Nenhum deputado encontrado para essa busca.")
            st.link_button("Abrir Dados Abertos da Câmara", deputy_payload["source_url"])
        except requests.RequestException as exc:
            st.error(f"Falha ao consultar a Câmara: {exc}")

    with senate_tab:
        senator_name = st.text_input(
            "Buscar senador por nome",
            value="",
            key="official_senator_name",
        )
        try:
            senator_payload = api_request(
                "GET",
                "/api/official/senators",
                params={"name": senator_name or None, "limit": 30},
                timeout=30,
            )
            senators = senator_payload.get("items", [])
            if senators:
                st.dataframe(
                    pd.DataFrame(senators)[["name", "party", "state", "profile_url"]],
                    width="stretch",
                    hide_index=True,
                )
            st.link_button("Abrir Dados Abertos do Senado", senator_payload["source_url"])
        except requests.RequestException as exc:
            st.error(f"Falha ao consultar o Senado: {exc}")

# -----------------
# TAB 5: RAG base and optional administration
# -----------------
with tab_ingest:
    st.markdown("### Base Documental do RAG")
    st.caption("Os documentos marcados como DEMO são cenários sintéticos para avaliação técnica.")

    c1, c2 = st.columns(2)
    with c1:
        metric_card("Documentos indexados", db_status.get("documents_indexed", 0))
    with c2:
        metric_card("Chunks indexados", db_status.get("chunks_indexed", 0))

    try:
        docs = api_request("GET", "/api/sources/documents")
        st.dataframe(
            pd.DataFrame(docs)[
                ["title", "source_type", "author", "publication_date", "source_url"]
            ],
            width="stretch",
            hide_index=True,
        )
    except requests.RequestException as exc:
        st.error(f"Erro ao carregar documentos: {exc}")

    if backend_info.get("admin_enabled"):
        st.markdown("#### Administração local")
        with st.form("ingest_form"):
            title_input = st.text_input("Título do documento")
            source_url = st.text_input("URL da fonte (opcional)")
            author_input = st.text_input("Autor (opcional)")
            pub_date = st.date_input("Data de publicação", datetime.date.today())
            uploaded_file = st.file_uploader("PDF, HTML, TXT ou CSV")
            submit_btn = st.form_submit_button("Ingerir documento")

            if submit_btn:
                if not title_input.strip() or uploaded_file is None:
                    st.error("Informe um título e selecione um arquivo.")
                else:
                    try:
                        result = api_request(
                            "POST",
                            "/api/ingest/file",
                            files={
                                "file": (
                                    uploaded_file.name,
                                    uploaded_file.getvalue(),
                                    uploaded_file.type,
                                )
                            },
                            data={
                                "title": title_input,
                                "source_url": source_url,
                                "author": author_input,
                                "publication_date": str(pub_date),
                            },
                            timeout=60,
                        )
                        st.success(
                            f"Documento ingerido: {result['chunks_count']} chunks."
                        )
                        st.rerun()
                    except requests.RequestException as exc:
                        st.error(f"Falha na ingestão: {exc}")
    else:
        st.info("Controles de ingestão estão desabilitados no deploy público.")

# -----------------
# TAB 6: Executable evaluation
# -----------------
with tab_evals:
    st.markdown("### Avaliação Executável de Recuperação")
    st.caption(
        "Esta métrica é calculada em tempo real. Ela mede recuperação da fonte "
        "esperada no pequeno benchmark sintético; não é uma avaliação RAGAS."
    )
    try:
        evaluation = api_request("GET", "/api/evaluations/retrieval", timeout=30)
        c1, c2, c3 = st.columns(3)
        with c1:
            metric_card("Recall da fonte esperada", f"{evaluation['score']}%")
        with c2:
            metric_card("Casos aprovados", str(evaluation["successful"]))
        with c3:
            metric_card("Total de casos", str(evaluation["total"]))

        rows = [
            {
                "id": result["id"],
                "question": result["query"],
                "route": result["route"],
                "status": "PASS" if result["success"] else "FAIL",
                "expected_source": result["expected_source"],
            }
            for result in evaluation["results"]
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.info(evaluation["limitations"])
    except requests.RequestException as exc:
        st.error(f"Falha ao executar avaliação: {exc}")
