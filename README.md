# Receivables Copilot

Receivables Copilot is an LLM-forward MVP for WhatsApp-first collections operations. This repo now contains the first application scaffold: a FastAPI backend, SQLAlchemy data model, Google Drive source registration, CSV/XLSX ingestion, WhatsApp webhook handling, morning brief generation, and a minimal web onboarding console.

## What is implemented

- FastAPI app with server-rendered onboarding dashboard
- PostgreSQL-friendly SQLAlchemy models and Alembic bootstrap migration
- Google Drive connection + source registration service seams
- Manual CSV/XLSX upload for first-pilot onboarding
- CSV/XLSX normalization and snapshot-based reconciliation
- Structured customer timeline and morning brief generation
- OpenRouter-backed message parsing, summarization, and recommendation
- Deterministic verification before financial writes
- WhatsApp webhook flow for drilldowns, updates, clarifications, and confirmations
- Direct API endpoints for AI extraction and manual case-event append
- Import history visibility with latest status and error details
- Celery wiring for scheduled sync/brief jobs
- Railway deployment config with healthcheck and pre-deploy migrations
- Service-level pytest coverage for ingestion, briefing, and verification logic

## Quick start

1. Copy `.env.example` to `.env` and fill the credentials.
2. Install dependencies: `pip install -e .[dev]`
3. Run migrations or let local development use `init_db()` on boot.
4. Start the API: `uvicorn app.main:app --reload`
5. Open `http://localhost:8000` for the onboarding console.

## Sample receivables file

The repo includes a realistic Tally-style starter export at [sample_data/tally_bills_receivable_sample.csv](/sample_data/tally_bills_receivable_sample.csv).

Use [docs/tally-receivables-source.md](/docs/tally-receivables-source.md) for the recommended Tally report and the expected export shape.

The fastest pilot path is now:

1. Create a business
2. Upload the CSV/XLSX directly from the console with `POST /imports/upload`
3. Review `GET /summary/today`
4. Start testing WhatsApp-style queries and updates

If an import fails, check `GET /imports/history?tenant_id=<business_id>` or the `Recent imports` section on the dashboard for the latest error message.

## Model switching

The LLM layer is wired through OpenRouter using the OpenAI-compatible SDK.

- Set `OPENROUTER_API_KEY`
- Change `OPENROUTER_MODEL` to switch providers or model families
- Optionally set `OPENROUTER_HTTP_REFERER` and `OPENROUTER_APP_NAME`

No code changes should be required to move between OpenRouter-hosted models unless a specific model has different response-format behavior.

## Railway deploy

This repo now includes a `railway.json` that uses Railway config-as-code with:

- `DOCKERFILE` as the builder
- `alembic upgrade head` as the pre-deploy command
- `python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers` as the web start command
- `/healthz` as the healthcheck path

### Recommended Railway setup

1. Create a web service from this GitHub repo.
2. Add a PostgreSQL service to the same Railway project.
3. Add a Redis service to the same Railway project.
4. In the web service variables, reference:
   - `DATABASE_URL` from the PostgreSQL service
   - `REDIS_URL` from the Redis service
5. Set the remaining app variables:
   - `ENCRYPTION_SECRET`
   - `OPENROUTER_API_KEY`
   - `OPENROUTER_MODEL`
   - `OPENROUTER_BASE_URL` if you want to override the default
   - `OPENROUTER_HTTP_REFERER`
   - `OPENROUTER_APP_NAME`
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI`
   - `WHATSAPP_VERIFY_TOKEN`
   - `WHATSAPP_ACCESS_TOKEN`
   - `WHATSAPP_PHONE_NUMBER_ID`
6. Generate a public Railway domain for the web service.
7. Use that public domain for:
   - Google OAuth redirect URI
   - WhatsApp webhook callback URL

### Worker service

The repo already contains Celery wiring. If you later add a dedicated worker service in Railway, use this start command for that separate service:

`celery -A app.celery_app.celery_app worker --loglevel=info`

Because Railway config-as-code applies per deployment, it is usually simplest to keep `railway.json` focused on the web service and set the worker start command in the Railway dashboard when you add the worker.

## Main endpoints

- `GET /` - onboarding dashboard
- `GET /healthz` - health check
- `GET /drive/connect/url` - Google OAuth launch URL
- `POST /drive/connect` - store Drive tokens for a tenant
- `POST /drive/sources` - register the receivables source file
- `POST /imports/run` - trigger a Drive-backed import
- `POST /imports/upload` - upload and import a local CSV/XLSX file
- `GET /imports/history` - inspect recent import statuses and errors for a business
- `GET /summary/today` - deterministic morning brief + suggested actions
- `GET /customers/{customer_id}/timeline` - customer memory view
- `POST /cases/{case_id}/events` - append a structured event directly
- `POST /ai/extract` - inspect LLM extraction output
- `POST /webhooks/whatsapp` - inbound query/update handling

## Design notes

- Invoice-level storage, customer-level UX
- OpenRouter is the default LLM gateway for parsing, summarization, and recommendation
- Deterministic validation remains the gate for financial facts and writes
- Voice notes are deliberately out of scope for this first MVP
