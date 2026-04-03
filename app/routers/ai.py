from fastapi import APIRouter

from app.services.ai import AIOrchestrator

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/extract")
def extract(payload: dict) -> dict:
    text = payload.get("text", "")
    parsed = AIOrchestrator().parse_message(text)
    return parsed.model_dump(mode="json")
