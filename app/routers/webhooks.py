from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RawMessage
from app.schemas import ParsedMessage, VerificationResult, WhatsAppWebhookPayload
from app.services.ai import AIOrchestrator
from app.services.briefing import build_morning_brief, render_brief_text
from app.services.collections import apply_case_update, build_customer_timeline, create_pending_confirmation, find_customer_candidates, get_pending_confirmation
from app.services.verification import verify_case_update

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _save_raw_message(db: Session, payload: WhatsAppWebhookPayload, parsed: ParsedMessage | None = None) -> RawMessage:
    raw = RawMessage(
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        whatsapp_message_id=payload.whatsapp_message_id,
        direction="inbound",
        text_body=payload.text,
        parsed_payload_json=parsed.model_dump(mode="json") if parsed else {},
        raw_payload_json=payload.raw_payload,
    )
    db.add(raw)
    db.commit()
    db.refresh(raw)
    return raw


@router.post("/whatsapp")
def whatsapp_webhook(payload: WhatsAppWebhookPayload, db: Session = Depends(get_db)) -> dict:
    ai = AIOrchestrator()
    parsed = ai.parse_message(payload.text)
    raw_message = _save_raw_message(db, payload, parsed)

    if parsed.intent == "confirm_action" and parsed.confirmation_token:
        pending = get_pending_confirmation(db, payload.tenant_id, parsed.confirmation_token)
        if pending is None:
            return {"status": "expired", "reply_text": "That confirmation token is missing or expired."}
        parsed = ParsedMessage.model_validate(pending.action_payload_json["parsed"])
        verification = VerificationResult.model_validate(pending.action_payload_json["verification"])
        case, event = apply_case_update(db, payload.tenant_id, parsed, verification, raw_message)
        pending.resolved_at = event.event_timestamp
        db.add(pending)
        db.commit()
        return {"status": "updated", "reply_text": f"Logged {parsed.outcome_type} for case {case.invoice_reference or case.id}."}

    if parsed.intent == "customer_timeline" and parsed.customer_name:
        matches = find_customer_candidates(db, payload.tenant_id, parsed.customer_name)
        if not matches:
            return {"status": "clarification_required", "reply_text": f"I could not find '{parsed.customer_name}'."}
        if len(matches) > 1:
            options = ", ".join(match.customer_name for match in matches[:3])
            return {"status": "clarification_required", "reply_text": f"I found multiple matches: {options}. Please reply with the exact customer name."}
        timeline = build_customer_timeline(db, payload.tenant_id, matches[0].id)
        return {"status": "ok", "reply_text": ai.summarize_timeline(timeline) or timeline.model_dump(mode="json")}

    if parsed.intent in {"top_overdue", "promises_due", "bucket_query"}:
        brief = build_morning_brief(db, payload.tenant_id)
        return {"status": "ok", "reply_text": ai.compose_brief(brief) or render_brief_text(brief)}

    if parsed.intent == "update_case":
        verification = verify_case_update(db, payload.tenant_id, parsed)
        if not verification.is_valid:
            return {"status": "clarification_required", "reply_text": verification.clarification_question}
        if verification.needs_confirmation and not payload.confirmed:
            confirmation = create_pending_confirmation(db, payload.tenant_id, raw_message.id, parsed, verification)
            return {
                "status": "confirmation_required",
                "reply_text": f"{verification.clarification_question} Reply 'confirm {confirmation.confirmation_token}' to proceed.",
            }
        case, _event = apply_case_update(db, payload.tenant_id, parsed, verification, raw_message)
        return {
            "status": "updated",
            "reply_text": f"Updated {case.invoice_reference or case.id} for {parsed.outcome_type}. Remaining outstanding: Rs {case.amount_outstanding}.",
        }

    return {
        "status": "unknown",
        "reply_text": "I could not confidently understand that. Try 'show Gupta', 'top overdue', or 'Mehta paid 20000'.",
    }
