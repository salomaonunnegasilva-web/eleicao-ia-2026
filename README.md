---
title: Eleição IA 2026
emoji: 📊
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
---

# Eleição IA 2026 — RAG, Public Data, and Forecasting Portfolio Demo

This portfolio project combines **Retrieval-Augmented Generation (RAG)**,
official Brazilian legislative open-data APIs, synthetic polling averages, and
transparent forecasting simulations.

The application deliberately separates two data layers:

- **Official live data:** fetched directly from the Chamber of Deputies and
  Federal Senate open-data APIs.
- **Synthetic election demo:** candidates, policy scenarios, polls, and Monte
  Carlo outputs used only to demonstrate engineering and modeling.

The synthetic layer must not be interpreted as real electoral information.

---

## Technical Stack
- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL with `pgvector`, with SQLite support for local/demo use
- **Retrieval**: hybrid vector + keyword search with reciprocal-rank fusion
- **LLM**: optional Gemini free tier, with deterministic local fallback
- **Frontend**: Streamlit with custom zinc-grade layout and Plotly charts
- **Deployment**: Docker Compose locally; Docker Space on Hugging Face publicly
- **CI/CD**: GitHub Actions

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

## Data Sources

- [Câmara dos Deputados — Dados Abertos](https://dadosabertos.camara.leg.br/)
- [Senado Federal — Dados Abertos](https://www12.senado.leg.br/dados-abertos)
- [TSE — Calendário Eleitoral](https://www.tse.jus.br/eleicoes/calendario-eleitoral/calendario-eleitoral)

The interface concept was inspired by
[Custo Político](https://www.custopolitico.com.br/en-US), but the application
does not scrape or depend on that service.
