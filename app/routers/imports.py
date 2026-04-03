from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DriveSource
from app.schemas import ManualImportRequest
from app.services.drive import download_drive_source
from app.services.ingestion import ingest_source_file
from app.services.uploads import ingest_manual_upload

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


@router.post("/upload")
async def upload_import(
    tenant_id: int = Form(...),
    source_sheet_name: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    file_name = file.filename or "receivables-upload.csv"
    file_bytes = await file.read()
    snapshot, source = ingest_manual_upload(db, tenant_id, file_name, file_bytes, source_sheet_name)
    return {
        "status": snapshot.sync_status,
        "snapshot_id": snapshot.id,
        "rows": snapshot.imported_rows,
        "drive_source_id": source.id,
        "provider": source.provider,
        "google_file_name": source.google_file_name,
    }
