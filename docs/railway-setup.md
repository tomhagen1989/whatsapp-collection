# Railway Setup

This guide is for deploying the current MVP to Railway with one web service, one PostgreSQL service, and one Redis service.

## Why Dockerfile instead of Railpack

If Railway shows "Error creating build plan with Railpack", the fastest fix is to bypass automatic build-plan detection and deploy from the included `Dockerfile`.

The branch now includes:

- `Dockerfile`
- `.dockerignore`
- `railway.json`

## Web service

Railway should deploy this repo as a Dockerfile-based web service.

- Builder: `DOCKERFILE`
- Pre-deploy command: `alembic upgrade head`
- Container command: defined in `Dockerfile`
- Healthcheck path: `/healthz`

## Railway variables

Set these on the web service:

- `DATABASE_URL`
- `REDIS_URL`
- `ENCRYPTION_SECRET`
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`
- `OPENROUTER_BASE_URL`
- `OPENROUTER_HTTP_REFERER`
- `OPENROUTER_APP_NAME`
- `APP_BASE_URL`
- `DEFAULT_TIMEZONE`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`

## External callbacks

After Railway gives you a public domain, configure:

- Google OAuth redirect URI to `https://<your-domain>/drive/connect/callback`
- WhatsApp webhook callback URL to `https://<your-domain>/webhooks/whatsapp`

## Worker service later

If you later add a separate worker service in Railway, use this start command there:

`celery -A app.celery_app.celery_app worker --loglevel=info`
