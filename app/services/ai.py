from __future__ import annotations

import json
import re
from datetime import date, timedelta
from decimal import Decimal

from openai import OpenAI

from app.config import get_settings
from app.schemas import CustomerTimelineView, MorningBriefView, ParsedMessage


def _heuristic_parse(text: str) -> ParsedMessage:
    cleaned = text.strip()
    lower = cleaned.lower()
    if lower.startswith("confirm "):
        return ParsedMessage(intent="confirm_action", confidence=0.99, confirmation_token=cleaned.split(maxsplit=1)[1])
    if lower.startswith("show 90") or lower.startswith("show 61"):
        return ParsedMessage(intent="bucket_query", confidence=0.91, bucket_query="90+")
    if lower.startswith("show "):
        return ParsedMessage(intent="customer_timeline", confidence=0.9, customer_name=cleaned[5:].strip())
    if "top overdue" in lower:
        return ParsedMessage(intent="top_overdue", confidence=0.9)
    if "who promised" in lower or "promised this week" in lower:
        return ParsedMessage(intent="promises_due", confidence=0.88)

    promise_match = re.search(r"^(?P<target>.+?)\s+promised\s+(?P<when>.+)$", cleaned, flags=re.IGNORECASE)
    if promise_match:
        when = promise_match.group("when").strip().lower()
        promised_date = date.today() + timedelta(days=1) if when == "tomorrow" else date.today()
        if when == "friday":
            promised_date = date.today() + timedelta(days=(4 - date.today().weekday()) % 7)
        return ParsedMessage(
            intent="update_case",
            confidence=0.78,
            customer_name=promise_match.group("target").strip() if not promise_match.group("target").strip().isdigit() else None,
            customer_reference=promise_match.group("target").strip() if promise_match.group("target").strip().isdigit() else None,
            outcome_type="promise_to_pay",
            promised_date=promised_date,
        )

    paid_match = re.search(r"^(?P<target>.+?)\s+paid\s+(?P<amount>[\d,]+)$", cleaned, flags=re.IGNORECASE)
    if paid_match:
        amount = Decimal(paid_match.group("amount").replace(",", ""))
        target = paid_match.group("target").strip()
        return ParsedMessage(
            intent="update_case",
            confidence=0.8,
            customer_name=target if not target.isdigit() else None,
            customer_reference=target if target.isdigit() else None,
            outcome_type="paid_partial",
            amount_paid=amount,
        )

    if "dispute" in lower:
        target = cleaned.split()[0]
        return ParsedMessage(
            intent="update_case",
            confidence=0.74,
            customer_name=target if not target.isdigit() else None,
            customer_reference=target if target.isdigit() else None,
            outcome_type="dispute_raised",
            note=cleaned,
        )
    return ParsedMessage(intent="unknown", confidence=0.2, note=cleaned)


class AIOrchestrator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.extra_headers = {
            key: value
            for key, value in {
                "HTTP-Referer": self.settings.openrouter_http_referer,
                "X-Title": self.settings.openrouter_app_name,
            }.items()
            if value
        }
        self.client = (
            OpenAI(
                api_key=self.settings.openrouter_api_key,
                base_url=self.settings.openrouter_base_url,
            )
            if self.settings.openrouter_api_key
            else None
        )

    def parse_message(self, text: str) -> ParsedMessage:
        if self.client is None:
            return _heuristic_parse(text)
        schema_prompt = {
            "intent": "customer_timeline | bucket_query | top_overdue | promises_due | update_case | confirm_action | unknown",
            "confidence": 0.0,
            "customer_name": None,
            "customer_reference": None,
            "invoice_reference": None,
            "bucket_query": None,
            "outcome_type": None,
            "amount_paid": None,
            "promised_date": None,
            "follow_up_date": None,
            "note": None,
            "requires_confirmation": False,
            "confirmation_token": None,
        }
        try:
            response = self.client.chat.completions.create(
                model=self.settings.openrouter_model,
                response_format={"type": "json_object"},
                extra_headers=self.extra_headers or None,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You extract structured intent from collections WhatsApp messages. "
                            "Use today's date when resolving relative dates. Return only JSON with keys exactly matching this shape: "
                            f"{json.dumps(schema_prompt)}"
                        ),
                    },
                    {"role": "user", "content": f"Today is {date.today().isoformat()}\nMessage: {text}"},
                ],
            )
            payload = json.loads(response.choices[0].message.content)
            return ParsedMessage.model_validate(payload)
        except Exception:
            return _heuristic_parse(text)

    def compose_brief(self, brief: MorningBriefView) -> str | None:
        if self.client is None:
            return None
        try:
            response = self.client.chat.completions.create(
                model=self.settings.openrouter_model,
                extra_headers=self.extra_headers or None,
                messages=[
                    {
                        "role": "system",
                        "content": "Write a short WhatsApp morning brief for a collections operator. Do not change any numbers.",
                    },
                    {"role": "user", "content": brief.model_dump_json()},
                ],
            )
            return response.choices[0].message.content
        except Exception:
            return None

    def summarize_timeline(self, timeline: CustomerTimelineView) -> str | None:
        if self.client is None:
            return None
        try:
            response = self.client.chat.completions.create(
                model=self.settings.openrouter_model,
                extra_headers=self.extra_headers or None,
                messages=[
                    {
                        "role": "system",
                        "content": "Summarize this customer timeline for a collector in 4 bullet lines max. Stay grounded in the provided data.",
                    },
                    {"role": "user", "content": timeline.model_dump_json()},
                ],
            )
            return response.choices[0].message.content
        except Exception:
            return None

    def suggest_next_action(self, brief: MorningBriefView) -> str | None:
        if self.client is None:
            return None
        try:
            response = self.client.chat.completions.create(
                model=self.settings.openrouter_model,
                extra_headers=self.extra_headers or None,
                messages=[
                    {
                        "role": "system",
                        "content": "Recommend one next best follow-up message for the collector. Be concise and do not invent any numbers.",
                    },
                    {"role": "user", "content": brief.model_dump_json()},
                ],
            )
            return response.choices[0].message.content
        except Exception:
            return None
