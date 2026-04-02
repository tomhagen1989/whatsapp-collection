from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import DriveConnection, DriveSource
from app.schemas import DriveConnectRequest, DriveSourceCreate
from app.services.security import decrypt_text, encrypt_text

GOOGLE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


def build_oauth_url(tenant_id: int) -> str:
    settings = get_settings()
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": str(tenant_id),
        }
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"


async def connect_google_drive(db: Session, payload: DriveConnectRequest) -> DriveConnection:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": payload.authorization_code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": payload.redirect_uri or settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        token_data = response.json()

    connection = db.scalar(select(DriveConnection).where(DriveConnection.tenant_id == payload.tenant_id))
    if connection is None:
        connection = DriveConnection(tenant_id=payload.tenant_id)

    connection.account_email = payload.account_email
    connection.access_token_encrypted = encrypt_text(token_data["access_token"])
    refresh_token = token_data.get("refresh_token")
    if refresh_token:
        connection.refresh_token_encrypted = encrypt_text(refresh_token)
    connection.scope = token_data.get("scope")
    connection.updated_at = datetime.now(UTC)
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


def register_drive_source(db: Session, payload: DriveSourceCreate) -> DriveSource:
    source = DriveSource(
        tenant_id=payload.tenant_id,
        google_file_id=payload.google_file_id,
        google_file_name=payload.google_file_name,
        source_sheet_name=payload.source_sheet_name,
        schema_mapping_json=payload.schema_mapping_json,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


async def _refresh_access_token(connection: DriveConnection) -> str:
    settings = get_settings()
    if not connection.refresh_token_encrypted:
        return decrypt_text(connection.access_token_encrypted)

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": decrypt_text(connection.refresh_token_encrypted),
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        payload = response.json()
    return payload["access_token"]


async def download_drive_source(db: Session, source: DriveSource) -> tuple[bytes, datetime | None]:
    connection = db.scalar(select(DriveConnection).where(DriveConnection.tenant_id == source.tenant_id))
    if connection is None:
        raise ValueError("No Google Drive connection configured for tenant")

    token = await _refresh_access_token(connection)
    headers = {"Authorization": f"Bearer {token}"}
    metadata_url = f"https://www.googleapis.com/drive/v3/files/{source.google_file_id}?fields=modifiedTime,name"
    media_url = f"https://www.googleapis.com/drive/v3/files/{source.google_file_id}?alt=media"

    async with httpx.AsyncClient(timeout=60) as client:
        metadata_response = await client.get(metadata_url, headers=headers)
        metadata_response.raise_for_status()
        metadata = metadata_response.json()

        media_response = await client.get(media_url, headers=headers)
        media_response.raise_for_status()

    modified = metadata.get("modifiedTime")
    modified_at = datetime.fromisoformat(modified.replace("Z", "+00:00")) if modified else None
    source.google_file_name = metadata.get("name", source.google_file_name)
    return media_response.content, modified_at
