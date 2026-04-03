from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RawMessage, ReceivableCase
from app.schemas import CustomerEventCreate, ParsedMessage, VerificationResult
from app.services.collections import apply_case_update

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("/{case_id}/events")
def append_case_event(
    case_id: int,
    payload: CustomerEventCreate,
    tenant_id: int = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    case = db.scalar(select(ReceivableCase).where(ReceivableCase.id == case_id, ReceivableCase.tenant_id == tenant_id))
    if case is None:
        return {"status": "error", "message": "Case not found"}

    raw_message = RawMessage(
        tenant_id=tenant_id,
        direction="manual",
        text_body=payload.note,
        parsed_payload_json=payload.model_dump(mode="json"),
        raw_payload_json={},
    )
    db.add(raw_message)
    db.commit()
    db.refresh(raw_message)

    parsed = ParsedMessage(
        intent="update_case",
        confidence=1.0,
        outcome_type=payload.outcome_type,
        amount_paid=payload.amount_paid,
        promised_date=payload.promised_date,
        follow_up_date=payload.follow_up_date,
        note=payload.note,
    )
    verification = VerificationResult(
        is_valid=True,
        customer_id=case.customer_id,
        case_id=case.id,
        confidence=1.0,
    )
    updated_case, event = apply_case_update(db, tenant_id, parsed, verification, raw_message)
    return {
        "status": "ok",
        "case_id": updated_case.id,
        "event_id": event.id,
        "amount_outstanding": str(updated_case.amount_outstanding),
    }
