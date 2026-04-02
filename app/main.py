import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import ai, cases, customers, dashboard, drive, imports, summary, webhooks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Receivables Copilot")
    init_db()
    yield
    logger.info("Stopping Receivables Copilot")


app = FastAPI(title="Receivables Copilot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(dashboard.router)
app.include_router(drive.router)
app.include_router(imports.router)
app.include_router(summary.router)
app.include_router(customers.router)
app.include_router(cases.router)
app.include_router(ai.router)
app.include_router(webhooks.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
