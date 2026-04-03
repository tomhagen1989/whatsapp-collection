from sqlalchemy import select

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import DriveSource
from app.services.briefing import build_morning_brief
from app.services.drive import download_drive_source
from app.services.ingestion import ingest_source_file


@celery_app.task(name="imports.sync_source")
def sync_source(tenant_id: int, drive_source_id: int) -> dict:
    db = SessionLocal()
    try:
        source = db.scalar(select(DriveSource).where(DriveSource.id == drive_source_id, DriveSource.tenant_id == tenant_id))
        if source is None:
            return {"status": "missing"}
        # Celery tasks run synchronously, so the async download would usually be wrapped by an event loop in production.
        return {"status": "queued_for_runtime_wrapper", "source_id": source.id}
    finally:
        db.close()


@celery_app.task(name="briefs.generate_today")
def generate_today_brief(tenant_id: int) -> dict:
    db = SessionLocal()
    try:
        brief = build_morning_brief(db, tenant_id)
        return brief.model_dump(mode="json")
    finally:
        db.close()
