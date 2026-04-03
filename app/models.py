import enum
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class CaseStatus(str, enum.Enum):
    open = "open"
    promised = "promised"
    disputed = "disputed"
    paid = "paid"
    closed = "closed"
    wrong_contact = "wrong_contact"


class ReminderStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    cancelled = "cancelled"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    morning_brief_time: Mapped[time | None] = mapped_column(Time())
    ageing_config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    whatsapp_phone: Mapped[str | None] = mapped_column(String(32), index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(50), default="collector")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DriveConnection(Base):
    __tablename__ = "drive_connections"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_drive_connection_tenant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    provider: Mapped[str] = mapped_column(String(50), default="google_drive")
    account_email: Mapped[str | None] = mapped_column(String(255))
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DriveSource(Base):
    __tablename__ = "drive_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    provider: Mapped[str] = mapped_column(String(50), default="google_drive")
    google_file_id: Mapped[str] = mapped_column(String(255), index=True)
    google_file_name: Mapped[str] = mapped_column(String(255))
    source_sheet_name: Mapped[str | None] = mapped_column(String(255))
    schema_mapping_json: Mapped[dict] = mapped_column(JSON, default=dict)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImportSnapshot(Base):
    __tablename__ = "import_snapshots"
    __table_args__ = (UniqueConstraint("tenant_id", "drive_source_id", "snapshot_version", name="uq_snapshot_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    drive_source_id: Mapped[int] = mapped_column(ForeignKey("drive_sources.id"), index=True)
    snapshot_version: Mapped[int] = mapped_column(nullable=False)
    sync_status: Mapped[str] = mapped_column(String(50), default="processing")
    source_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_rows: Mapped[int] = mapped_column(default=0)
    summary_stats_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "normalized_name", name="uq_customer_normalized_name"),
        Index("ix_customer_external_code", "tenant_id", "external_customer_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    customer_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    phone_number: Mapped[str | None] = mapped_column(String(32))
    external_customer_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReceivableCase(Base):
    __tablename__ = "receivable_cases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "drive_source_id", "source_row_key", name="uq_case_source_row"),
        Index("ix_case_tenant_customer_status", "tenant_id", "customer_id", "status"),
        Index("ix_case_tenant_promise", "tenant_id", "latest_promise_date"),
        Index("ix_case_tenant_follow_up", "tenant_id", "next_follow_up_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    drive_source_id: Mapped[int] = mapped_column(ForeignKey("drive_sources.id"), index=True)
    import_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("import_snapshots.id"), index=True)
    source_row_key: Mapped[str] = mapped_column(String(255))
    invoice_reference: Mapped[str | None] = mapped_column(String(255), index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date())
    due_date: Mapped[date | None] = mapped_column(Date())
    amount_outstanding: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[str] = mapped_column(String(32), default=CaseStatus.open.value)
    overdue_days: Mapped[int] = mapped_column(default=0)
    next_follow_up_date: Mapped[date | None] = mapped_column(Date())
    latest_promise_date: Mapped[date | None] = mapped_column(Date())
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_reason: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RawMessage(Base):
    __tablename__ = "raw_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    whatsapp_message_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    direction: Mapped[str] = mapped_column(String(20))
    text_body: Mapped[str | None] = mapped_column(Text)
    transcript_text: Mapped[str | None] = mapped_column(Text)
    parsed_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CaseEvent(Base):
    __tablename__ = "case_events"
    __table_args__ = (Index("ix_case_events_customer_time", "customer_id", "event_timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    receivable_case_id: Mapped[int | None] = mapped_column(ForeignKey("receivable_cases.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    raw_message_id: Mapped[int | None] = mapped_column(ForeignKey("raw_messages.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    structured_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    receivable_case_id: Mapped[int | None] = mapped_column(ForeignKey("receivable_cases.id"), index=True)
    reminder_type: Mapped[str] = mapped_column(String(64))
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), default=ReminderStatus.pending.value)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerProfile(Base):
    __tablename__ = "customer_profiles"
    __table_args__ = (UniqueConstraint("tenant_id", "customer_id", name="uq_customer_profile"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    total_outstanding: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    active_case_count: Mapped[int] = mapped_column(default=0)
    promise_break_count: Mapped[int] = mapped_column(default=0)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_summary: Mapped[str | None] = mapped_column(Text)
    risk_flags_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PendingConfirmation(Base):
    __tablename__ = "pending_confirmations"
    __table_args__ = (UniqueConstraint("confirmation_token", name="uq_confirmation_token"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    raw_message_id: Mapped[int | None] = mapped_column(ForeignKey("raw_messages.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(64))
    confirmation_token: Mapped[str] = mapped_column(String(32), index=True)
    action_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    clarification_question: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
