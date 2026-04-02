from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ReceivableCase
from app.schemas import ParsedMessage, VerificationResult
from app.services.briefing import build_morning_brief
from app.services.collections import find_customer_candidates


def verify_summary_numbers(total: Decimal, buckets: dict[str, Decimal]) -> bool:
    return total == sum(buckets.values(), start=Decimal("0"))


def verify_case_update(db: Session, tenant_id: int, parsed: ParsedMessage) -> VerificationResult:
    if parsed.customer_reference and parsed.customer_reference.isdigit():
        attention = build_morning_brief(db, tenant_id, limit=10).attention_items
        index = int(parsed.customer_reference) - 1
        if 0 <= index < len(attention):
            item = attention[index]
            return VerificationResult(
                is_valid=True,
                customer_id=item.customer_id,
                case_id=item.case_id,
                confidence=0.8,
                needs_confirmation=True,
                clarification_question=f"Reply 'confirm {index + 1}' only if you want me to update {item.customer_name}.",
            )
        return VerificationResult(is_valid=False, clarification_question="That list reference does not exist in the latest brief.")

    if not parsed.customer_name:
        return VerificationResult(is_valid=False, clarification_question="Which customer should I apply this update to?")

    candidates = find_customer_candidates(db, tenant_id, parsed.customer_name)
    if not candidates:
        return VerificationResult(
            is_valid=False,
            clarification_question=f"I could not find '{parsed.customer_name}'. Which customer did you mean?",
        )
    if len(candidates) > 1:
        return VerificationResult(
            is_valid=False,
            ambiguity_reason="multiple_customers",
            clarification_question="I found multiple matching customers. Please reply with the exact customer name.",
        )

    customer = candidates[0]
    cases = db.scalars(
        select(ReceivableCase).where(
            ReceivableCase.tenant_id == tenant_id,
            ReceivableCase.customer_id == customer.id,
            ReceivableCase.status.not_in(["closed", "paid"]),
        )
    ).all()
    if parsed.invoice_reference:
        cases = [case for case in cases if case.invoice_reference == parsed.invoice_reference]
    if not cases:
        return VerificationResult(
            is_valid=False,
            customer_id=customer.id,
            clarification_question="I found the customer but not an open case that matches this update.",
        )
    if len(cases) > 1 and not parsed.invoice_reference:
        chosen = sorted(cases, key=lambda case: case.amount_outstanding, reverse=True)[0]
        return VerificationResult(
            is_valid=True,
            customer_id=customer.id,
            case_id=chosen.id,
            confidence=0.72,
            needs_confirmation=True,
            clarification_question="I matched the largest open invoice for that customer. Please confirm before I update it.",
        )
    chosen = cases[0]
    return VerificationResult(is_valid=True, customer_id=customer.id, case_id=chosen.id, confidence=0.96)
