# Receivables Copilot

Receivables Copilot is an LLM-forward MVP for WhatsApp-first collections operations. This repo now contains the first application scaffold: a FastAPI backend, SQLAlchemy data model, Google Drive source registration, CSV/XLSX ingestion, WhatsApp webhook handling, morning brief generation, and a minimal web onboarding console.

## What is implemented

- FastAPI app with server-rendered onboarding dashboard
- PostgreSQL-friendly SQLAlchemy models and Alembic bootstrap migration
- Google Drive connection + source registration service seams
- CSV/XLSX normalization and snapshot-based reconciliation
- Structured customer timeline and morning brief generation
- OpenRouter-backed message parsing, summarization, and recommendation
- Deterministic verification before financial writes
- WhatsApp webhook flow for drilldowns, updates, clarifications, and confirmations
- Direct API endpoints for AI extraction and manual case-event append
- Celery wiring for scheduled sync/brief jobs
- Service-level pytest coverage for ingestion, briefing, and verification logic

## Quick start

1. Copy `.env.example` to `.env` and fill the credentials.
2. Install dependencies: `pip install -e .[dev]`
3. Run migrations or let local development use `init_db()` on boot.
4. Start the API: `uvicorn app.main:app --reload`
5. Open `http://localhost:8000` for the onboarding console.

## Model switching

The LLM layer is wired through OpenRouter using the OpenAI-compatible SDK.

- Set `OPENROUTER_API_KEY`
- Change `OPENROUTER_MODEL` to switch providers or model families
- Optionally set `OPENROUTER_HTTP_REFERER` and `OPENROUTER_APP_NAME`

No code changes should be required to move between OpenRouter-hosted models unless a specific model has different response-format behavior.

## Main endpoints

- `GET /` - onboarding dashboard
- `GET /healthz` - health check
- `GET /drive/connect/url` - Google OAuth launch URL
- `POST /drive/connect` - store Drive tokens for a tenant
- `POST /drive/sources` - register the receivables source file
- `POST /imports/run` - trigger a Drive-backed import
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
