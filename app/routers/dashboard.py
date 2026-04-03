from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DriveSource, ImportSnapshot, Tenant
from app.schemas import TenantCreate

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    tenants = db.scalars(select(Tenant).order_by(Tenant.created_at.desc())).all()
    sources = db.scalars(select(DriveSource).order_by(DriveSource.created_at.desc())).all()
    snapshots = db.scalars(select(ImportSnapshot).order_by(desc(ImportSnapshot.created_at)).limit(10)).all()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "tenants": tenants,
            "sources": sources,
            "snapshots": snapshots,
        },
    )


@router.post("/tenants")
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)) -> dict:
    tenant = Tenant(
        business_name=payload.business_name,
        timezone=payload.timezone,
        morning_brief_time=payload.morning_brief_time,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return {
        "business_id": tenant.id,
        "tenant_id": tenant.id,
        "business_name": tenant.business_name,
    }
