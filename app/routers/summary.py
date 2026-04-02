from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.ai import AIOrchestrator
from app.services.briefing import build_morning_brief, render_brief_text
from app.services.verification import verify_summary_numbers

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("/today")
def today_summary(tenant_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    brief = build_morning_brief(db, tenant_id)
    ai = AIOrchestrator()
    ai_text = ai.compose_brief(brief)
    suggestion = ai.suggest_next_action(brief)
    brief.draft_reply_suggestion = suggestion
    return {
        "verified": verify_summary_numbers(brief.total_outstanding, brief.ageing_buckets),
        "text": ai_text or render_brief_text(brief),
        "brief": brief.model_dump(mode="json"),
    }
