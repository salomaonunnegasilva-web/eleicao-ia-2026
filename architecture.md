# System Architecture

This document describes the implemented architecture of **Eleição IA 2026**.
The public portfolio build is designed to run at no infrastructure cost while
keeping a clear path to PostgreSQL and a hosted LLM.

## 1. Data Boundaries

The application keeps two data categories separate:

- **Official live data:** current deputy and senator records fetched from the
  Câmara dos Deputados and Senado Federal open-data APIs.
- **Synthetic demonstration data:** hypothetical candidates, policy documents,
  polls, polling averages, and simulations used to demonstrate engineering
  techniques. These records are visibly labeled as synthetic.

Custo Político inspired the product concept, but it is neither scraped nor used
as a runtime dependency.

## 2. Runtime Flow

```text
Browser
  |
  v
Streamlit UI :7860
  |
  v
FastAPI :8000
  |---------------------> Official Câmara/Senado APIs
  |
  +-- Query classifier
  |     +-- structured candidate lookup
  |     +-- synthetic forecast endpoint
  |     +-- RAG retrieval
  |
  +-- SQLite (public demo/local default)
  |     +-- relational demo records
  |     +-- 384-dimensional hash vectors
  |
  +-- PostgreSQL + pgvector (optional production backend)
  |
  +-- deterministic local answer generator
        +-- optional Gemini generation when configured
```

The Docker Space image runs FastAPI on the container's internal port `8000` and
publishes Streamlit on port `7860`.

## 3. Persistence and Retrieval

SQLite is the default because a public portfolio demo must start without an
external database. PostgreSQL with `pgvector` remains supported through
`DATABASE_URL`.

Documents are split into overlapping chunks and represented by deterministic
384-dimensional hashing vectors. The retrieval pipeline combines:

1. Cosine similarity over stored vectors.
2. Keyword matching: PostgreSQL Portuguese full-text search, or a SQLite
   keyword fallback.
3. Reciprocal Rank Fusion with `k = 60`.

The hash-vector implementation is dependency-free and reproducible. A local
Sentence Transformers model can be selected with environment configuration,
and the database schema is compatible with `pgvector`.

## 4. Answer Generation

Retrieved chunks are always returned with their document metadata and dynamic
citations. Generation has two modes:

- **Local fallback:** deterministic, no API key, suitable for CI and the public
  demo.
- **Gemini:** optional provider configured with `GEMINI_API_KEY`.

Provider failures fall back to the local generator instead of breaking the
request. The LLM does not create official legislative metrics; those values
come directly from the government APIs.

## 5. Forecasting

Forecasting runs only on the synthetic demonstration polls.

For candidate `c`, the polling average is:

```text
average(c) = sum(weight(i) * result(i,c)) / sum(weight(i))
weight(i) = exp(-ln(2) * age_days(i) / half_life) * sqrt(sample_size(i))
```

Blank, null, and undecided responses are excluded when calculating valid-vote
shares.

The Monte Carlo simulation draws support from normal distributions using each
poll's margin of error, clips negative values, renormalizes each poll, applies
the same poll weights, and reports 95% intervals plus first-round and runoff
probabilities. `MONTE_CARLO_SEED` makes demo and test results reproducible.

These outputs illustrate statistical implementation; they are not real 2026
election forecasts.

## 6. Security and Operations

- Public builds set `PUBLIC_DEMO=true` and `ADMIN_ENABLED=false`.
- Upload size is limited by `MAX_UPLOAD_BYTES`.
- CORS uses an explicit allowlist.
- The API exposes `/health` for container health checks.
- GitHub Actions runs compilation, tests, and a Docker build.
- A separate workflow uploads the repository to a Hugging Face Docker Space.

GitHub Actions provides CI/CD, not persistent application hosting.

## 7. Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe app\evals\ragas_eval.py
docker compose config --quiet
docker build -t eleicao-ia-2026:portfolio .
docker run --rm -p 7860:7860 eleicao-ia-2026:portfolio
```

The retrieval report measures expected-source recall on a small synthetic
benchmark. It is deliberately not presented as factual-accuracy evaluation.
