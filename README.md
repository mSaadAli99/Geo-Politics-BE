# GeoPolitics AI — Backend

FastAPI backend that **collects**, **cleans**, **analyses**, and **serves** geopolitical news for the GeoPolitics AI dashboard.

Two processes, one database:

| Process | Role | Loads HF models? |
|---|---|---|
| **API** (`api`) | REST reads for the frontend | No |
| **Worker** (`worker`) | Ingest + NLP + trending + clustering (APScheduler) | Yes |

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## What it does

1. **Ingest** news on a schedule from RSS feeds + NewsAPI / GNews / The Guardian.
2. **Clean** text with Pandas and **dedupe** with URL hashing + TF-IDF cosine similarity.
3. Run the **NLP pipeline** per article:
   - Summarisation (DistilBART; T5 supported via env)
   - Category classification (scikit-learn TF-IDF + logistic regression)
   - Sentiment (RoBERTa)
   - NER → country mapping
   - Keyword extraction → trending topics
   - Event clustering (same story across sources)
   - Credibility score (0–100, explainable)
4. **Store** everything in PostgreSQL (Neon in production / local Postgres optional).
5. **Serve** JSON over `/api/v1` for the React frontend.

---

## Tech stack

| Area | Used |
|---|---|
| Language | Python 3.11+ |
| API | FastAPI + Uvicorn |
| Config / schemas | Pydantic v2, pydantic-settings |
| ORM / migrations | SQLAlchemy 2 + Alembic |
| Database | PostgreSQL 15+ (`psycopg` v3) — Neon or local |
| Scheduling | APScheduler (worker only) |
| HTTP / RSS | Requests, feedparser |
| Data processing | Pandas, NumPy |
| Classical ML | scikit-learn, joblib |
| NLP | Hugging Face Transformers + torch (CPU) |
| Models | DistilBART summary, RoBERTa sentiment, BERT NER |
| Countries | pycountry + alias JSON |
| Evaluation | sklearn metrics, rouge-score |
| Tests | pytest, Postman collection |

---

## Architecture

```
NewsAPI / GNews / Guardian / RSS
            │
            ▼
     Worker (APScheduler)
      ├─ ingest_job      every INGEST_INTERVAL_MINUTES (default 30)
      ├─ process_job     every 2 min  → NLP pipeline
      ├─ cluster_job     every 15 min → event grouping
      └─ trending_job    every 30 min → topic scores
            │
            ▼
        PostgreSQL
            │
            ▼
     API (FastAPI)  ──►  React frontend (CORS)
```

The API never loads Transformer weights. Keep `ENABLE_SCHEDULER=false` on the API and `true` only on the worker.

---

## Folder layout

```
backend/
├── app/
│   ├── main.py                 # FastAPI app, CORS, routers
│   ├── core/                   # config, database, logging
│   ├── models/                 # SQLAlchemy tables
│   ├── schemas/                # Pydantic request/response
│   ├── api/v1/                 # HTTP routes (no raw SQL)
│   ├── services/               # query / serialisation logic
│   ├── ingestion/              # fetch, clean, dedupe
│   ├── nlp/                    # summary, classify, sentiment, NER, …
│   ├── scheduler/              # APScheduler jobs + entrypoint
│   └── data/                   # country aliases, centroids, reliability
├── ml/                         # datasets, train, evaluate, artifacts
├── alembic/                    # migrations
├── scripts/                    # seed, backfill, requeue, drain
├── tests/                      # unit + integration
├── postman/                    # GeoPoliticsAI.postman_collection.json
├── Dockerfile.api
├── Dockerfile.worker
├── docker-compose.yml
├── requirements-api.txt
├── requirements-worker.txt
└── .env.example
```

---

## Environment

```powershell
cd backend
copy .env.example .env
```

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL URL (`postgres://` is rewritten to `postgresql+psycopg://`) |
| `CORS_ORIGINS` | Comma-separated frontend origins |
| `NEWSAPI_KEY` | [newsapi.org](https://newsapi.org/register) |
| `GNEWS_API_KEY` | [gnews.io](https://gnews.io/) |
| `GUARDIAN_API_KEY` | [open-platform.theguardian.com](https://open-platform.theguardian.com/access/) |
| `ADMIN_API_KEY` | Header `X-Admin-Key` for `/api/v1/admin/*` |
| `INGEST_INTERVAL_MINUTES` | Fetch cadence (default `30`) |
| `PROCESS_BATCH_SIZE` | Articles per NLP batch (default `20`) |
| `SUMMARY_MODEL` | Primary BART-family summariser (default DistilBART) |
| `SUMMARY_MODEL_T5` | Secondary T5 summariser (default `t5-small`); used if BART fails |
| `SENTIMENT_MODEL` | Default `cardiffnlp/twitter-roberta-base-sentiment-latest` |
| `NER_MODEL` | Default `dslim/bert-base-NER` |
| `ENABLE_SCHEDULER` | `false` on API, `true` on worker |
| `HF_HOME` | Hugging Face cache dir |

RSS sources need no keys. Empty API keys are skipped and logged as a failed ingestion run.

---

## Quick start (Docker — recommended)

Requires Docker Desktop. Point `.env` at Neon **or** enable the local Postgres profile.

```powershell
cd backend

# API + worker (uses DATABASE_URL from .env, e.g. Neon)
docker compose up -d --build api worker

# Optional local Postgres instead of Neon
docker compose --profile local-db up -d
```

Then:

```powershell
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed_sources.py
```

- API: [http://localhost:8000](http://localhost:8000)
- Health: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
- Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)

Worker first boot downloads DistilBART / RoBERTa / NER into the `hf_cache` volume (several minutes on CPU).

### Useful Compose commands

```powershell
docker compose logs -f worker
docker compose logs -f api
docker compose restart worker
docker compose ps
```

---

## Local Python (without Docker images)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu

alembic upgrade head
python scripts/seed_sources.py

# Terminal 1 — API
uvicorn app.main:app --reload

# Terminal 2 — worker
$env:ENABLE_SCHEDULER = "true"
python -m app.scheduler.run_scheduler
```

Run every scheduled job once and exit:

```powershell
$env:ENABLE_SCHEDULER = "true"
python -m app.scheduler.run_scheduler --once
```

---

## NLP pipeline (per article)

Order in `app/nlp/pipeline.py`:

1. **Summarise** — DistilBART (or T5 if configured); short texts returned as-is
2. **Classify** — scikit-learn joblib model → one of five categories
3. **Sentiment** — RoBERTa → positive / negative / neutral + score
4. **NER** — BERT token classification → people / orgs / locations
5. **Countries** — entity labels + aliases → ISO2
6. **Keywords** — TF-IDF terms (+ entity names)
7. **Credibility** — 0–100 from source tier, corroboration, etc.

Statuses: `pending` → `processing` → `done` (or `failed`). Lists hide near-duplicates (`is_duplicate_of`). Incomplete NLP fields stay `null` until the worker finishes.

### Models

| Task | Live default | Notes |
|---|---|---|
| Summary | DistilBART → T5-small | Both load on the worker; BART first, T5 fallback |
| Sentiment | `cardiffnlp/twitter-roberta-base-sentiment-latest` | |
| NER | `dslim/bert-base-NER` | |
| Category | `ml/artifacts/classifier.joblib` | TF-IDF + LogisticRegression |

---

## API surface

Base path: `/api/v1`. Timestamps are UTC. Errors: `{"detail": ...}`.

| Method | Path | Description |
|---|---|---|
| GET | `/health` or `/api/v1/health` | DB + pending queue |
| GET | `/articles` | Filtered, paginated list |
| GET | `/articles/{id}` | Full article + entities / keywords |
| GET | `/countries` | Map markers / counts |
| GET | `/countries/{iso2}` | Country detail |
| GET | `/trending` | Trending topics (`window`, `limit`) |
| GET | `/stats/overview` | Totals, category & sentiment breakdown |
| GET | `/stats/sentiment` | Sentiment time series / groups |
| GET | `/stats/categories` | Category stats |
| GET | `/events` | Clustered stories |
| GET | `/events/{id}` | Event detail + linked articles |
| GET | `/timeline` | Timeline feed |
| GET | `/categories` | Category list + counts |
| GET | `/sources` | Configured outlets |
| POST | `/admin/ingest` | Trigger fetch (`202`, needs `X-Admin-Key`) |
| POST | `/admin/reprocess/{id}` | Requeue one article |
| GET | `/admin/runs` | Recent ingestion runs |

Postman: `postman/GeoPoliticsAI.postman_collection.json`

---

## Scripts

```powershell
# Seed RSS + API source rows
python scripts/seed_sources.py

# Requeue failed / incomplete NLP
python scripts/requeue_incomplete.py
python scripts/backfill.py --status failed --limit 200

# Drain NLP backlog with fast extractive summaries (CPU catch-up)
python scripts/drain_nlp.py
```

New articles after a normal worker start still use the configured HF summariser (DistilBART / T5). `drain_nlp.py` is only for clearing a large backlog quickly.

---

## Train and evaluate

Bootstrap CSVs in `ml/datasets/` let the harness run before hand-labelled data exists. Replace them before citing metrics in a report.

```powershell
python -m ml.build_datasets
python -m ml.train_classifier
python -m ml.evaluate_classifier
python -m ml.evaluate_sentiment
python -m ml.evaluate_summaries

# Score live HF models (downloads weights)
python -m ml.evaluate_sentiment --use-hf
python -m ml.evaluate_summaries --use-hf
```

Artifacts land in `ml/artifacts/` (joblib model, JSON reports, confusion matrix PNG).

---

## Tests

```powershell
pytest --cov=app --cov-report=term-missing
```

Unit tests mock models (no HF download). Integration tests expect Postgres and skip if unavailable.

---

## Deployment notes

- **Web service**: `Dockerfile.api`, `ENABLE_SCHEDULER=false`, no torch/transformers required for serving.
- **Background worker**: `Dockerfile.worker`, `ENABLE_SCHEDULER=true`, needs enough RAM for CPU HF models.
- `render.yaml` describes the web + worker split.
- Do not run the scheduler inside Uvicorn workers.
- Stored content: URL, source, capped description/excerpt, and generated summary — full HTML pages are not scraped by default.

---

## Summarisation models (BART + T5)

The worker loads **both**:

- `SUMMARY_MODEL` — DistilBART (`sshleifer/distilbart-cnn-12-6`) by default
- `SUMMARY_MODEL_T5` — `t5-small` by default

Each article is summarised with DistilBART first; if that call fails, T5 runs; only then does an extractive lead fallback apply. Rebuild/restart the **worker** after changing either model name.
