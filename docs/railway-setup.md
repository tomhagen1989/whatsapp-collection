# Railway Setup

This guide is for deploying the current MVP to Railway with one web service, one PostgreSQL service, and one Redis service.

## What Railway handles

- Public HTTPS hosting for the FastAPI app
- Managed PostgreSQL and Redis inside the same project
- Build and deploy lifecycle using `railway.json`
- Pre-deploy migrations with `alembic upgrade head`
- Health checks against `/healthz`

## Web service

The included `railway.json` config is intentionally web-service-first.

- Builder: `RAILPACK`
- Pre-deploy command: `alembic upgrade head`
- Start command: `python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers`
- Healthcheck path: `/healthz`

## Railway variables

### Required infra references

Set these on the web service by referencing variables from the attached Railway databases:

- `DATABASE_URL` from PostgreSQL
- `REDIS_URL` from Redis

### Required app secrets

Set these on the web service:

- `ENCRYPTION_SECRET`
- `OPENROUTER_API_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`

### Useful optional variables

- `OPENROUTER_MODEL`
- `OPENROUTER_BASE_URL`
- `OPENROUTER_HTTP_REFERER`
- `OPENROUTER_APP_NAME`
- `APP_BASE_URL`
- `DEFAULT_TIMEZONE`

## External callback URLs

After you generate a public Railway domain, configure:

- Google OAuth redirect URI to `https://<your-domain>/drive/connect/callback`
- WhatsApp webhook callback URL to `https://<your-domain>/webhooks/whatsapp`

## Separate worker service

If you add a worker service later, create a second Railway service from the same repo and set its start command manually in the dashboard to:

`celery -A app.celery_app.celery_app worker --loglevel=info`

Use the same `DATABASE_URL`, `REDIS_URL`, and app secrets on the worker service.

## Current runtime caveats

- The app is deployment-ready, but the Google Drive and WhatsApp integrations still need real credentials and end-to-end validation.
- The worker process is scaffolded but not yet required for the initial web deployment.
- The current repo includes a Drive connect POST flow, but a fully interactive OAuth callback UX still needs live testing after deployment.
