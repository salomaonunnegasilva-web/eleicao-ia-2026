---
title: Eleição IA 2026
emoji: 📊
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
---

# Eleição IA 2026 — RAG, Public Data, and Forecasting Portfolio Demo

[Open the live demo](https://nunnega-eleicao-ia-2026.hf.space)

This portfolio project combines an **official-first question-answering
assistant**, Brazilian government open-data APIs, Retrieval-Augmented
Generation (RAG), and a separately labeled synthetic forecasting demonstration.

The assistant currently answers from:

- **TSE:** live 2026 election-calendar entries, with a versioned snapshot
  fallback.
- **Câmara dos Deputados:** current deputy profiles, current-year expenses, and
  authored propositions.
- **Senado Federal:** current senator profiles and recent associated legislative
  processes.
- **CNJ DataJud:** official judicial-process metadata when the user provides a
  CNJ process number.
- **Portal da Transparencia / CGU:** optional CEIS/CNEP sanctions and federal
  executive remuneration lookups when `PORTAL_TRANSPARENCIA_API_KEY` is
  configured.

Candidate programs and policy comparisons are answered only when an official
program or statement has been indexed. Otherwise, the assistant refuses rather
than substituting synthetic content. Polling and Monte Carlo tabs remain
synthetic and must not be interpreted as real electoral information.

---

## Technical Stack
- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL with `pgvector`, with SQLite support for local/demo use
- **Retrieval**: source-constrained hybrid vector + keyword search with
  relevance filtering and reciprocal-rank fusion
- **LLM**: optional Gemini free tier, with deterministic local fallback
- **Frontend**: Streamlit with custom zinc-grade layout and Plotly charts
- **Deployment**: Docker Compose locally; Docker Space on Hugging Face publicly
- **CI/CD**: GitHub Actions
- **Official-data refresh**: scheduled TSE snapshot refresh through GitHub
  Actions

## Current Question Coverage

Examples supported with official sources:

```text
When is the first round of the 2026 election?
When is the candidate-registration deadline?
What are the current expenses of deputy Tabata Amaral?
Which recent bills are associated with senator Flávio Bolsonaro?
Search CNJ process 0000832-35.2018.4.01.3202.
Does this public official appear in CEIS or CNEP sanctions records?
What remuneration appears in official transparency sources?
```

Example intentionally refused:

```text
Compare Lula and Flávio's 2026 government programs.
```

As of June 15, 2026, registered 2026 candidacies and government programs are not
yet complete. The official convention period is July 20 through August 5, and
the candidacy-registration deadline is August 15. The project does not present
pre-candidate speculation as an official program.

Judicial and integrity answers use stricter guardrails. The app does not search
for lawsuits by broad person-name matching because that can create false
positives. CNJ DataJud lookup is process-number based. Portal da Transparencia
lookups require an API key, and federal payroll/remuneration records generally
require CPF or a server id. Deputy and senator remuneration should be integrated
from Chamber/Senate-specific transparency sources before being presented as a
factual salary value.

---

## Project Structure
```text
eleicao-ia-2026/
│
├── app/
│   ├── api/
│   │   ├── main.py
│   │   ├── routes_evaluations.py
│   │   ├── routes_chat.py
│   │   ├── routes_ingestion.py
│   │   ├── routes_forecast.py
│   │   ├── routes_official.py
│   │   └── routes_sources.py
│   │
│   ├── db/
│   │   ├── models.py
│   │   └── seed_data.py
│   │
│   ├── forecasting/
│   │   ├── polling_average.py
│   │   └── simulations.py
│   │
│   ├── rag/
│   │   ├── ingest.py
│   │   ├── retrieval.py
│   │   └── answer_generation.py
│   │
│   └── evals/
│       ├── evaluator.py
│       ├── test_questions.json
│       ├── ragas_eval.py
│       └── eval_report.md
│
├── frontend/
│   └── streamlit_app.py
│
├── data/official/
│   └── tse_calendar_2026.json
├── scripts/
│   └── refresh_official_data.py
├── .github/workflows/
├── deploy/start-space.sh
├── tests/
├── docker-compose.yml
├── Dockerfile
├── Dockerfile.backend
├── Dockerfile.frontend
├── requirements-dev.txt
├── requirements.txt
├── .env.example
├── .env
└── architecture.md
```

---

## Run with Docker Compose

1. **Clone the Repository** and navigate to the project root:
   ```bash
   cd eleicao-ia-2026
   ```

2. **Configure the environment**:

   The application works without an API key. To enable Gemini, create `.env`
   from `.env.example` and set:

   ```env
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=your-api-key-here
   LLM_MODEL=gemini-2.5-flash-lite
   PORTAL_TRANSPARENCIA_API_KEY=optional-cgu-api-key
   ```

3. **Spin up Docker Containers**:
   ```bash
   docker compose up --build -d
   ```

4. **Access the Applications**:
   - **Frontend Dashboard (Streamlit)**: [http://localhost:8501](http://localhost:8501)
   - **Backend API Documentation (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Verify

Run the regression suite:

```bash
python -m unittest discover -s tests -v
```

Run the transparent retrieval benchmark:

```bash
docker compose exec backend python app/evals/ragas_eval.py
```

## Public Deployment

The root `Dockerfile` runs FastAPI internally and exposes Streamlit on port
`7860`, matching Hugging Face Docker Spaces.

1. Create a Docker Space on Hugging Face.
2. Add `GEMINI_API_KEY` and `LLM_PROVIDER=gemini` as Space secrets.
3. Add GitHub repository secrets:
   - `HF_TOKEN`
   - `HF_SPACE` in `username/space-name` format
4. Run the **Deploy Hugging Face Space** workflow.

GitHub Actions performs CI/CD; it does not host the persistent web application.

The `Refresh Official Data` workflow runs daily. It fetches the official TSE
calendar, compares a content checksum, and commits a new snapshot only when the
source changes. Runtime requests prefer the live TSE page and use the snapshot
only when that request fails.

## API Routes

- `POST /api/chat`: official-first question answering
- `GET /api/official/tse/calendar`: live TSE calendar plus provenance
- `GET /api/official/deputies`: live Chamber search
- `GET /api/official/deputies/{id}/metrics`: live expenses and proposition count
- `GET /api/official/senators`: live Senate directory
- `GET /api/official/datajud/process/{process_number}`: CNJ DataJud metadata
- `GET /api/official/transparency/sanctions`: Portal da Transparencia CEIS/CNEP
- `GET /api/official/transparency/remuneration`: Portal da Transparencia payroll
- `GET /api/forecast/*`: explicitly synthetic statistical demonstration

## Data Sources

- [Câmara dos Deputados — Dados Abertos](https://dadosabertos.camara.leg.br/)
- [Senado Federal — Dados Abertos](https://www12.senado.leg.br/dados-abertos)
- [TSE — Calendário Eleitoral](https://www.tse.jus.br/eleicoes/calendario-eleitoral/calendario-eleitoral)
- [CNJ DataJud — API Publica](https://datajud-wiki.cnj.jus.br/api-publica/)
- [Portal da Transparencia — API](https://api.portaldatransparencia.gov.br/swagger-ui/index.html)

The interface concept was inspired by
[Custo Político](https://www.custopolitico.com.br/en-US), but the application
does not scrape or depend on that service.

An LLM is optional. Gemini only synthesizes the official evidence supplied by
the source adapters; it is not used as an unverified web-search substitute.
