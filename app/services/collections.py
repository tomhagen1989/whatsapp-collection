from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.database import utcnow
from app.models import CaseEvent, Customer, CustomerProfile, PendingConfirmation, RawMessage, ReceivableCase, Reminder
from app.schemas import CustomerTimelineView, ParsedMessage, TimelineCase, TimelineEvent, VerificationResult
from app.services.ingestion import normalize_name, refresh_customer_profiles


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def find_customer_candidates(db: Session, tenant_id: int, query: str) -> list[Customer]:
    normalized = normalize_name(query)
    exact = db.scalars(
        select(Customer).where(Customer.tenant_id == tenant_id, Customer.normalized_name == normalized)
    ).all()
    if exact:
        return exact
    return db.scalars(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            or_(Customer.normalized_name.contains(normalized), Customer.customer_name.ilike(f"%{query}%")),
        )
    ).all()


def build_customer_timeline(db: Session, tenant_id: int, customer_id: int) -> CustomerTimelineView:
    customer = db.scalar(select(Customer).where(Customer.tenant_id == tenant_id, Customer.id == customer_id))
    if customer is None:
        raise ValueError("Customer not found")
    profile = db.scalar(
        select(CustomerProfile).where(CustomerProfile.tenant_id == tenant_id, CustomerProfile.customer_id == customer_id)
    )
    cases = db.scalars(
        select(ReceivableCase)
        .where(ReceivableCase.tenant_id == tenant_id, ReceivableCase.customer_id == customer_id)
        .order_by(desc(ReceivableCase.amount_outstanding))
    ).all()
    events = db.scalars(
        select(CaseEvent)
        .where(CaseEvent.tenant_id == tenant_id, CaseEvent.customer_id == customer_id)
        .order_by(desc(CaseEvent.event_timestamp))
        .limit(10)
    ).all()
    return CustomerTimelineView(
        customer_id=customer.id,
        customer_name=customer.customer_name,
        total_outstanding=profile.total_outstanding if profile else Decimal("0"),
        active_case_count=profile.active_case_count if profile else 0,
        risk_flags=profile.risk_flags_json if profile else {},
        latest_summary=profile.latest_summary if profile else None,
        cases=[
            TimelineCase(
                case_id=case.id,
                invoice_reference=case.invoice_reference,
                due_date=case.due_date,
                amount_outstanding=case.amount_outstanding,
                status=case.status,
                next_follow_up_date=case.next_follow_up_date,
                latest_promise_date=case.latest_promise_date,
            )
            for case in cases
        ],
        events=[
            TimelineEvent(
                event_type=event.event_type,
                event_timestamp=event.event_timestamp,
                payload=event.structured_payload_json,
            )
            for event in events
        ],
    )


def create_pending_confirmation(
    db: Session,
    tenant_id: int,
    raw_message_id: int | None,
    parsed: ParsedMessage,
    verification: VerificationResult,
) -> PendingConfirmation:
    confirmation = PendingConfirmation(
        tenant_id=tenant_id,
        raw_message_id=raw_message_id,
        action_type="case_update",
        confirmation_token=secrets.token_hex(4),
        action_payload_json={
            "parsed": parsed.model_dump(mode="json"),
            "verification": verification.model_dump(mode="json"),
        },
        clarification_question=verification.clarification_question,
        expires_at=datetime.now(UTC) + timedelta(minutes=20),
    )
    db.add(confirmation)
    db.commit()
    db.refresh(confirmation)
    return confirmation


def get_pending_confirmation(db: Session, tenant_id: int, token: str) -> PendingConfirmation | None:
    confirmation = db.scalar(
        select(PendingConfirmation).where(
            PendingConfirmation.tenant_id == tenant_id,
            PendingConfirmation.confirmation_token == token,
            PendingConfirmation.resolved_at.is_(None),
        )
    )
    if confirmation and _as_utc(confirmation.expires_at) < datetime.now(UTC):
        return None
    return confirmation


def apply_case_update(
    db: Session,
    tenant_id: int,
    parsed: ParsedMessage,
    verification: VerificationResult,
    raw_message: RawMessage | None,
) -> tuple[ReceivableCase, CaseEvent]:
    case = db.scalar(select(ReceivableCase).where(ReceivableCase.tenant_id == tenant_id, ReceivableCase.id == verification.case_id))
    if case is None:
        raise ValueError("Verified case not found")

    payload = {
        "outcome_type": parsed.outcome_type,
        "note": parsed.note,
        "amount_paid": str(parsed.amount_paid) if parsed.amount_paid is not None else None,
        "promised_date": parsed.promised_date.isoformat() if parsed.promised_date else None,
        "follow_up_date": parsed.follow_up_date.isoformat() if parsed.follow_up_date else None,
    }

    if parsed.outcome_type == "paid_partial" and parsed.amount_paid:
        case.amount_outstanding = max(Decimal("0"), case.amount_outstanding - parsed.amount_paid)
        case.status = "paid" if case.amount_outstanding == 0 else "open"
    elif parsed.outcome_type == "paid_full":
        case.amount_outstanding = Decimal("0")
        case.status = "paid"
        case.closed_at = utcnow()
        case.closed_reason = "fully_paid"
    elif parsed.outcome_type == "promise_to_pay":
        case.latest_promise_date = parsed.promised_date
        case.next_follow_up_date = parsed.promised_date
        case.status = "promised"
    elif parsed.outcome_type == "asked_to_call_later":
        case.next_follow_up_date = parsed.follow_up_date or date.today() + timedelta(days=2)
    elif parsed.outcome_type == "dispute_raised":
        case.status = "disputed"
        case.next_follow_up_date = parsed.follow_up_date or date.today() + timedelta(days=3)
    elif parsed.outcome_type in {"unreachable", "no_response"}:
        case.next_follow_up_date = parsed.follow_up_date or date.today() + timedelta(days=2)
    elif parsed.outcome_type == "wrong_contact":
        case.status = "wrong_contact"

    case.last_contact_at = utcnow()
    event = CaseEvent(
        tenant_id=tenant_id,
        receivable_case_id=case.id,
        customer_id=case.customer_id,
        raw_message_id=raw_message.id if raw_message else None,
        event_type=parsed.outcome_type or "note",
        event_timestamp=utcnow(),
        structured_payload_json=payload,
        created_by="whatsapp_user",
    )
    db.add(case)
    db.add(event)

    if case.next_follow_up_date:
        reminder = Reminder(
            tenant_id=tenant_id,
            customer_id=case.customer_id,
            receivable_case_id=case.id,
            reminder_type="follow_up",
            scheduled_for=datetime.combine(case.next_follow_up_date, datetime.min.time(), tzinfo=UTC),
            payload_json={"reason": parsed.outcome_type},
        )
        db.add(reminder)

    db.flush()
    refresh_customer_profiles(db, tenant_id)
    db.commit()
    db.refresh(case)
    db.refresh(event)
    return case, event
