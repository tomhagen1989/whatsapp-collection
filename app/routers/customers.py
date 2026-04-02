from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.ai import AIOrchestrator
from app.services.collections import build_customer_timeline

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/{customer_id}/timeline")
def customer_timeline(customer_id: int, tenant_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    timeline = build_customer_timeline(db, tenant_id, customer_id)
    ai = AIOrchestrator()
    summary = ai.summarize_timeline(timeline)
    payload = timeline.model_dump(mode="json")
    payload["llm_summary"] = summary
    return payload
