from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import utcnow
from app.models import Customer, CustomerProfile, DriveSource, ImportSnapshot, ReceivableCase
from app.schemas import ReceivableImportRow

COLUMN_ALIASES = {
    "customer_name": ["customer", "party_name", "debtor_name", "name"],
    "amount_outstanding": ["amount", "balance", "outstanding", "closing_balance"],
    "due_date": ["due", "due_dt"],
    "invoice_reference": ["invoice", "invoice_no", "invoice_number", "bill_no"],
    "invoice_date": ["invoice_dt", "bill_date"],
    "overdue_days": ["days_overdue", "age_days"],
    "phone_number": ["phone", "mobile"],
    "salesperson": ["sales_person", "owner"],
    "notes": ["remarks", "comment"],
    "external_customer_code": ["customer_code", "party_code", "ledger_code"],
}


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _normalize_columns(columns: list[str]) -> dict[str, str]:
    return {column: normalize_name(column) for column in columns}


def _pick_source_column(canonical_field: str, normalized_columns: dict[str, str], mapping: dict[str, str]) -> str | None:
    explicit = mapping.get(canonical_field)
    if explicit:
        explicit_normalized = normalize_name(explicit)
        for original, normalized in normalized_columns.items():
            if normalized == explicit_normalized:
                return original
    for original, normalized in normalized_columns.items():
        if normalized == canonical_field:
            return original
        if normalized in COLUMN_ALIASES.get(canonical_field, []):
            return original
    return None


def _as_decimal(value: object) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    text = str(value).replace(",", "").replace("Rs", "").replace("INR", "").strip()
    return Decimal(text)


def _as_date(value: object) -> date | None:
    if value in (None, "", "NaT"):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def load_rows(file_name: str, content: bytes, mapping: dict[str, str], sheet_name: str | None) -> list[ReceivableImportRow]:
    if file_name.lower().endswith(".csv"):
        dataframe = pd.read_csv(pd.io.common.BytesIO(content))
    else:
        dataframe = pd.read_excel(pd.io.common.BytesIO(content), sheet_name=sheet_name or 0)

    normalized_columns = _normalize_columns(list(dataframe.columns))
    rows: list[ReceivableImportRow] = []
    for _, series in dataframe.iterrows():
        payload = {}
        for field in ReceivableImportRow.model_fields:
            source_column = _pick_source_column(field, normalized_columns, mapping)
            payload[field] = series[source_column] if source_column in series else None
        if not payload.get("customer_name") or payload.get("amount_outstanding") in (None, ""):
            continue
        row = ReceivableImportRow(
            customer_name=str(payload["customer_name"]).strip(),
            amount_outstanding=_as_decimal(payload["amount_outstanding"]),
            due_date=_as_date(payload.get("due_date")),
            invoice_reference=str(payload["invoice_reference"]).strip() if payload.get("invoice_reference") not in (None, "") else None,
            invoice_date=_as_date(payload.get("invoice_date")),
            overdue_days=int(payload["overdue_days"]) if payload.get("overdue_days") not in (None, "") else None,
            phone_number=str(payload["phone_number"]).strip() if payload.get("phone_number") not in (None, "") else None,
            salesperson=str(payload["salesperson"]).strip() if payload.get("salesperson") not in (None, "") else None,
            notes=str(payload["notes"]).strip() if payload.get("notes") not in (None, "") else None,
            external_customer_code=str(payload["external_customer_code"]).strip() if payload.get("external_customer_code") not in (None, "") else None,
        )
        rows.append(row)
    return rows


def _row_key(row: ReceivableImportRow) -> str:
    invoice = row.invoice_reference or "no-invoice"
    due = row.due_date.isoformat() if row.due_date else "no-due-date"
    return "|".join([normalize_name(row.customer_name), invoice, due])


def _next_snapshot_version(db: Session, tenant_id: int, drive_source_id: int) -> int:
    latest = db.scalar(
        select(func.max(ImportSnapshot.snapshot_version)).where(
            ImportSnapshot.tenant_id == tenant_id,
            ImportSnapshot.drive_source_id == drive_source_id,
        )
    )
    return int(latest or 0) + 1


def _find_or_create_customer(db: Session, tenant_id: int, row: ReceivableImportRow) -> Customer:
    if row.external_customer_code:
        customer = db.scalar(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.external_customer_code == row.external_customer_code,
            )
        )
        if customer is not None:
            customer.customer_name = row.customer_name
            customer.normalized_name = normalize_name(row.customer_name)
            return customer

    normalized = normalize_name(row.customer_name)
    customer = db.scalar(
        select(Customer).where(Customer.tenant_id == tenant_id, Customer.normalized_name == normalized)
    )
    if customer is None:
        customer = Customer(
            tenant_id=tenant_id,
            customer_name=row.customer_name,
            normalized_name=normalized,
            phone_number=row.phone_number,
            external_customer_code=row.external_customer_code,
        )
        db.add(customer)
        db.flush()
    else:
        customer.customer_name = row.customer_name
        customer.phone_number = row.phone_number or customer.phone_number
        customer.external_customer_code = row.external_customer_code or customer.external_customer_code
    return customer


def refresh_customer_profiles(db: Session, tenant_id: int) -> None:
    cases = db.scalars(select(ReceivableCase).where(ReceivableCase.tenant_id == tenant_id)).all()
    grouped: dict[int, list[ReceivableCase]] = defaultdict(list)
    for case in cases:
        grouped[case.customer_id].append(case)

    for customer_id, customer_cases in grouped.items():
        active = [case for case in customer_cases if case.status not in {"closed", "paid"}]
        broken_promises = sum(
            1
            for case in customer_cases
            if case.latest_promise_date and case.latest_promise_date < date.today() and case.status not in {"paid", "closed"}
        )
        profile = db.scalar(
            select(CustomerProfile).where(
                CustomerProfile.tenant_id == tenant_id,
                CustomerProfile.customer_id == customer_id,
            )
        )
        if profile is None:
            profile = CustomerProfile(tenant_id=tenant_id, customer_id=customer_id)
        profile.total_outstanding = sum((case.amount_outstanding for case in active), start=Decimal("0"))
        profile.active_case_count = len(active)
        profile.promise_break_count = broken_promises
        profile.last_contact_at = max((case.last_contact_at for case in customer_cases if case.last_contact_at), default=None)
        profile.risk_flags_json = {
            "has_broken_promises": broken_promises > 0,
            "has_stale_follow_up": any(case.next_follow_up_date and case.next_follow_up_date < date.today() for case in active),
        }
        db.add(profile)
    db.flush()


def ingest_source_file(
    db: Session,
    tenant_id: int,
    source: DriveSource,
    file_name: str,
    content: bytes,
    modified_at: datetime | None,
) -> ImportSnapshot:
    snapshot = ImportSnapshot(
        tenant_id=tenant_id,
        drive_source_id=source.id,
        snapshot_version=_next_snapshot_version(db, tenant_id, source.id),
        sync_status="processing",
        source_modified_at=modified_at,
    )
    db.add(snapshot)
    db.flush()

    try:
        rows = load_rows(file_name, content, source.schema_mapping_json or {}, source.source_sheet_name)
        active_keys: set[str] = set()
        for row in rows:
            customer = _find_or_create_customer(db, tenant_id, row)
            source_key = _row_key(row)
            active_keys.add(source_key)
            case = db.scalar(
                select(ReceivableCase).where(
                    ReceivableCase.tenant_id == tenant_id,
                    ReceivableCase.drive_source_id == source.id,
                    ReceivableCase.source_row_key == source_key,
                )
            )
            if case is None:
                case = ReceivableCase(
                    tenant_id=tenant_id,
                    customer_id=customer.id,
                    drive_source_id=source.id,
                    source_row_key=source_key,
                    opened_at=utcnow(),
                )
            case.customer_id = customer.id
            case.import_snapshot_id = snapshot.id
            case.invoice_reference = row.invoice_reference
            case.invoice_date = row.invoice_date
            case.due_date = row.due_date
            case.amount_outstanding = row.amount_outstanding
            case.overdue_days = row.overdue_days or max((date.today() - row.due_date).days, 0) if row.due_date else 0
            case.status = "open" if row.amount_outstanding > 0 else "paid"
            case.closed_at = None if case.status == "open" else utcnow()
            case.closed_reason = None if case.status == "open" else "zero_balance"
            case.metadata_json = {
                "salesperson": row.salesperson,
                "notes": row.notes,
                "external_customer_code": row.external_customer_code,
            }
            db.add(case)

        existing_cases = db.scalars(
            select(ReceivableCase).where(
                ReceivableCase.tenant_id == tenant_id,
                ReceivableCase.drive_source_id == source.id,
            )
        ).all()
        for case in existing_cases:
            if case.source_row_key not in active_keys and case.status not in {"paid", "closed"}:
                case.status = "closed"
                case.closed_at = utcnow()
                case.closed_reason = "missing_from_latest_import"
                db.add(case)

        source.last_synced_at = utcnow()
        snapshot.imported_rows = len(rows)
        snapshot.sync_status = "success"
        snapshot.summary_stats_json = {
            "imported_rows": len(rows),
            "open_cases": sum(1 for row in rows if row.amount_outstanding > 0),
            "total_outstanding": str(sum((row.amount_outstanding for row in rows), start=Decimal("0"))),
        }
        db.add(source)
        refresh_customer_profiles(db, tenant_id)
        db.commit()
        db.refresh(snapshot)
        return snapshot
    except Exception as exc:  # pragma: no cover - exercised through API only
        snapshot.sync_status = "failed"
        snapshot.error_message = str(exc)
        db.add(snapshot)
        db.commit()
        raise
