from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import DriveConnectRequest, DriveSourceCreate
from app.services.drive import build_oauth_url, connect_google_drive, register_drive_source

router = APIRouter(prefix="/drive", tags=["drive"])


@router.get("/connect/url")
def connect_url(tenant_id: int = Query(...)) -> dict:
    return {"authorization_url": build_oauth_url(tenant_id)}


@router.post("/connect")
async def connect(payload: DriveConnectRequest, db: Session = Depends(get_db)) -> dict:
    connection = await connect_google_drive(db, payload)
    return {"connection_id": connection.id, "account_email": connection.account_email}


@router.post("/sources")
def add_source(payload: DriveSourceCreate, db: Session = Depends(get_db)) -> dict:
    source = register_drive_source(db, payload)
    return {"drive_source_id": source.id, "google_file_name": source.google_file_name}
