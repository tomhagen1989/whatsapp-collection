from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DriveSource
from app.schemas import ManualImportRequest
from app.services.drive import download_drive_source
from app.services.ingestion import ingest_source_file

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/run")
async def run_import(payload: ManualImportRequest, db: Session = Depends(get_db)) -> dict:
    source = db.scalar(
        select(DriveSource).where(DriveSource.id == payload.drive_source_id, DriveSource.tenant_id == payload.tenant_id)
    )
    if source is None:
        return {"status": "error", "message": "Drive source not found"}
    file_bytes, modified_at = await download_drive_source(db, source)
    snapshot = ingest_source_file(db, payload.tenant_id, source, source.google_file_name, file_bytes, modified_at)
    return {"status": snapshot.sync_status, "snapshot_id": snapshot.id, "rows": snapshot.imported_rows}
