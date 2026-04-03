from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DriveSource, ImportSnapshot
from app.schemas import CsvPasteImportRequest, ManualImportRequest
from app.services.drive import download_drive_source
from app.services.ingestion import ingest_source_file
from app.services.uploads import ingest_manual_upload

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("/history")
def import_history(tenant_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    snapshots = db.scalars(
        select(ImportSnapshot)
        .where(ImportSnapshot.tenant_id == tenant_id)
        .order_by(desc(ImportSnapshot.created_at))
        .limit(10)
    ).all()
    source_names = {
        source.id: source.google_file_name
        for source in db.scalars(select(DriveSource).where(DriveSource.tenant_id == tenant_id)).all()
    }
    return {
        "imports": [
            {
                "snapshot_id": snapshot.id,
                "drive_source_id": snapshot.drive_source_id,
                "source_name": source_names.get(snapshot.drive_source_id),
                "status": snapshot.sync_status,
                "rows": snapshot.imported_rows,
                "snapshot_version": snapshot.snapshot_version,
                "error_message": snapshot.error_message,
                "created_at": snapshot.created_at,
            }
            for snapshot in snapshots
        ]
    }


@router.post("/run")
async def run_import(payload: ManualImportRequest, db: Session = Depends(get_db)) -> dict:
    source = db.scalar(
        select(DriveSource).where(DriveSource.id == payload.drive_source_id, DriveSource.tenant_id == payload.tenant_id)
    )
    if source is None:
        return {"status": "error", "message": "Drive source not found"}
    try:
        file_bytes, modified_at = await download_drive_source(db, source)
        snapshot = ingest_source_file(db, payload.tenant_id, source, source.google_file_name, file_bytes, modified_at)
    except Exception as exc:
        return {"status": "error", "message": str(exc), "drive_source_id": source.id}
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
    try:
        snapshot, source = ingest_manual_upload(db, tenant_id, file_name, file_bytes, source_sheet_name)
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
            "google_file_name": file_name,
            "provider": "manual_upload",
        }
    return {
        "status": snapshot.sync_status,
        "snapshot_id": snapshot.id,
        "rows": snapshot.imported_rows,
        "drive_source_id": source.id,
        "provider": source.provider,
        "google_file_name": source.google_file_name,
    }


@router.post("/paste")
def paste_import(payload: CsvPasteImportRequest, db: Session = Depends(get_db)) -> dict:
    try:
        snapshot, source = ingest_manual_upload(
            db,
            payload.tenant_id,
            payload.file_name,
            payload.csv_text.encode("utf-8"),
            sheet_name=None,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
            "google_file_name": payload.file_name,
            "provider": "manual_upload",
        }
    return {
        "status": snapshot.sync_status,
        "snapshot_id": snapshot.id,
        "rows": snapshot.imported_rows,
        "drive_source_id": source.id,
        "provider": source.provider,
        "google_file_name": source.google_file_name,
    }
