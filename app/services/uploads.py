from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import DriveSource, ImportSnapshot
from app.services.ingestion import ingest_source_file


def ingest_manual_upload(
    db: Session,
    tenant_id: int,
    file_name: str,
    content: bytes,
    sheet_name: str | None,
    modified_at: datetime | None = None,
) -> tuple[ImportSnapshot, DriveSource]:
    source = DriveSource(
        tenant_id=tenant_id,
        provider="manual_upload",
        google_file_id=f"manual-upload-{uuid4().hex}",
        google_file_name=file_name,
        source_sheet_name=sheet_name,
        schema_mapping_json={},
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    try:
        snapshot = ingest_source_file(db, tenant_id, source, file_name, content, modified_at)
        return snapshot, source
    except Exception:
        db.refresh(source)
        raise
