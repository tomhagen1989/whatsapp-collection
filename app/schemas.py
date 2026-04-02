from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    business_name: str
    timezone: str = "Asia/Kolkata"
    morning_brief_time: time | None = None


class DriveConnectRequest(BaseModel):
    tenant_id: int
    authorization_code: str
    account_email: str | None = None
    redirect_uri: str | None = None


class DriveSourceCreate(BaseModel):
    tenant_id: int
    google_file_id: str
    google_file_name: str
    source_sheet_name: str | None = None
    schema_mapping_json: dict[str, str] = Field(default_factory=dict)


class ManualImportRequest(BaseModel):
    tenant_id: int
    drive_source_id: int


class ReceivableImportRow(BaseModel):
    customer_name: str
    amount_outstanding: Decimal
    due_date: date | None = None
    invoice_reference: str | None = None
    invoice_date: date | None = None
    overdue_days: int | None = None
    phone_number: str | None = None
    salesperson: str | None = None
    notes: str | None = None
    external_customer_code: str | None = None


class AttentionItem(BaseModel):
    customer_id: int
    case_id: int | None
    customer_name: str
    amount_outstanding: Decimal
    reason: str
    overdue_days: int = 0
    action_hint: str | None = None


class MorningBriefView(BaseModel):
    total_outstanding: Decimal
    ageing_buckets: dict[str, Decimal]
    attention_items: list[AttentionItem]
    promises_due: list[AttentionItem] = Field(default_factory=list)
    stale_cases: list[AttentionItem] = Field(default_factory=list)
    generated_at: datetime
    snapshot_version: int | None = None
    freshness_note: str | None = None
    draft_reply_suggestion: str | None = None


class ParsedMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    intent: Literal[
        "customer_timeline",
        "bucket_query",
        "top_overdue",
        "promises_due",
        "update_case",
        "confirm_action",
        "unknown",
    ] = "unknown"
    confidence: float = 0.0
    customer_name: str | None = None
    customer_reference: str | None = None
    invoice_reference: str | None = None
    bucket_query: str | None = None
    outcome_type: str | None = None
    amount_paid: Decimal | None = None
    promised_date: date | None = None
    follow_up_date: date | None = None
    note: str | None = None
    requires_confirmation: bool = False
    confirmation_token: str | None = None
    raw_extraction: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    is_valid: bool
    customer_id: int | None = None
    case_id: int | None = None
    confidence: float = 0.0
    needs_confirmation: bool = False
    ambiguity_reason: str | None = None
    clarification_question: str | None = None


class CustomerEventCreate(BaseModel):
    outcome_type: str
    note: str | None = None
    amount_paid: Decimal | None = None
    promised_date: date | None = None
    follow_up_date: date | None = None


class TimelineEvent(BaseModel):
    event_type: str
    event_timestamp: datetime
    payload: dict[str, Any]


class TimelineCase(BaseModel):
    case_id: int
    invoice_reference: str | None
    due_date: date | None
    amount_outstanding: Decimal
    status: str
    next_follow_up_date: date | None
    latest_promise_date: date | None


class CustomerTimelineView(BaseModel):
    customer_id: int
    customer_name: str
    total_outstanding: Decimal
    active_case_count: int
    risk_flags: dict[str, Any] = Field(default_factory=dict)
    latest_summary: str | None = None
    cases: list[TimelineCase]
    events: list[TimelineEvent]


class WhatsAppWebhookPayload(BaseModel):
    tenant_id: int
    user_id: int | None = None
    whatsapp_message_id: str | None = None
    text: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False
