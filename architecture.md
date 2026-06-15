# System Architecture

This document describes the implemented architecture of **Eleição IA 2026**.
The public build is official-first: it answers only from connected government
sources and keeps synthetic modeling in separate, clearly labeled screens.

## 1. Runtime Flow

```text
Browser
  |
  v
Streamlit UI :7860
  |
  v
FastAPI :8000
  |
  +-- Query classifier
  |     +-- official_calendar
  |     +-- official_legislative
  |     +-- official_policy
  |     +-- forecast (synthetic demo)
  |     +-- official_evidence
  |
  +-- Official source adapters
  |     +-- TSE election calendar (live + snapshot fallback)
  |     +-- Câmara profiles, expenses, propositions
  |     +-- Senado profiles and legislative processes
  |
  +-- Source-constrained RAG
  |     +-- official program/statement document types only
  |     +-- exact term-overlap safeguard
  |     +-- vector + keyword retrieval
  |     +-- Reciprocal Rank Fusion
  |
  +-- SQLite (public demo) / PostgreSQL + pgvector (optional)
  |
  +-- deterministic grounded generator
        +-- optional Gemini synthesis
```

FastAPI runs internally on port `8000`. Streamlit is the public process on port
`7860`, matching the Hugging Face Docker Space contract.

## 2. Source Boundaries

### Official live sources

- TSE 2026 election calendar
- Current Chamber of Deputies directory
- Current-year deputy expenses
- Authored Chamber propositions
- Current Federal Senate directory
- Recent Senate legislative processes associated with a senator

### Versioned fallback

`data/official/tse_calendar_2026.json` is generated from the official TSE page.
Runtime requests prefer the live page. The snapshot is used only if TSE is
temporarily unavailable.

### Synthetic demonstration

- Hypothetical candidate registry
- Fictional poll institutes and poll results
- Hypothetical policy documents
- Polling averages and Monte Carlo simulations

Synthetic documents remain available for the retrieval benchmark but are not
eligible evidence for official chat answers.

## 3. Query Routing

The router uses normalized Portuguese concepts rather than an LLM classifier:

- Election dates, conventions, registration, propaganda, and PesqEle questions
  route to `official_calendar`.
- Explicit deputy/senator, expense, bill, proposition, and roll-call questions
  route to `official_legislative`.
- Government-program and candidate-policy comparisons route to
  `official_policy`.
- Poll averages and simulation requests route to the synthetic forecast module.
- Other questions route to the general official evidence gate.

If no compatible official source exists, the application refuses to answer.

## 4. TSE Retrieval

The TSE client:

1. Fetches the official calendar page.
2. Locates the 2026 page section.
3. Parses month cards into dated entries.
4. Ranks entries using query-term overlap and election-specific intent boosts.
5. Returns provenance, retrieval time, live/snapshot state, and source URL.

A daily GitHub Actions workflow refreshes the snapshot. It compares a stable
content checksum and commits only substantive source changes.

## 5. Legislative Retrieval

Current officeholders are cached for ten minutes to avoid unnecessary upstream
requests.

The Chamber adapter supports:

- Profile resolution
- Current-year net expense aggregation
- Recent authored proposition summaries

The Senate adapter supports:

- Profile resolution
- Recent `PL`, `PLP`, `PEC`, `PDL`, `PRS`, `PLC`, and `PLS` processes associated
  with the senator

Legislative proposals are not described as election programs.

## 6. Database RAG

The document database supports SQLite JSON vectors locally and PostgreSQL
`pgvector` in the Compose architecture.

Documents are split into overlapping chunks. Retrieval combines:

1. Cosine vector similarity
2. Portuguese full-text search on PostgreSQL, or keyword fallback on SQLite
3. Reciprocal Rank Fusion with `k = 60`
4. Allowed-source-type filtering
5. Meaningful query-term overlap

The last two controls prevent unrelated synthetic documents from filling an
answer merely because the database is small.

## 7. Generation

The deterministic generator works without an API key. Optional Gemini synthesis
receives only the evidence selected by the source adapters.

Every returned source includes:

- Title
- Authoring institution
- URL
- Official/synthetic classification
- Live/snapshot state
- Retrieval timestamp when available

Provider failures fall back locally. They do not fall back to unsupported facts.

## 8. Forecasting

Forecasting is intentionally isolated from official chat answers. It uses the
synthetic polls to demonstrate:

```text
average(c) = sum(weight(i) * result(i,c)) / sum(weight(i))
weight(i) = exp(-ln(2) * age_days(i) / half_life) * sqrt(sample_size(i))
```

The Monte Carlo module reports uncertainty intervals and runoff frequencies,
but these outputs are not real 2026 forecasts.

## 9. Deployment and Operations

- The public Docker image runs as non-root UID `1000`.
- Public ingestion is disabled.
- SQLite lives under `/tmp` and is recreated on Space restart.
- Official TSE fallback data is committed to the image.
- GitHub Actions runs tests, compilation, and Docker build verification.
- A deployment workflow uploads `main` to the Hugging Face Docker Space.
- A scheduled workflow refreshes the TSE snapshot.

## 10. Current Limitation

As of June 15, 2026, final registered candidacies and government programs are
not complete. The official convention window is July 20 through August 5, and
the registration deadline is August 15.

The next source expansion is a versioned DivulgaCandContas/TSE candidate-program
ingestion pipeline after those documents are officially published.
