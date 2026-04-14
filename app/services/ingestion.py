from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
from pandas.errors import ParserError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import utcnow
from app.models import Customer, CustomerProfile, DriveSource, ImportSnapshot, ReceivableCase
from app.schemas import ReceivableImportRow

EXCEL_HEADER_SCAN_LIMIT = 25
REQUIRED_IMPORT_FIELDS = {"customer_name", "amount_outstanding"}
IGNORED_ROW_LABELS = {
    "total",
    "grand total",
    "opening balance",
    "closing balance",
    "balance carried forward",
}


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


RAW_COLUMN_ALIASES = {
    "customer_name": [
        "customer",
        "customer name",
        "party",
        "party_name",
        "party name",
        "party's name",
        "debtor_name",
        "debtor name",
        "particulars",
        "account name",
        "name",
    ],
    "amount_outstanding": [
        "amount",
        "balance",
        "outstanding",
        "outstanding amount",
        "closing_balance",
        "closing balance",
        "pending amount",
        "pending",
        "net outstanding",
        "receivable amount",
    ],
    "due_date": ["due", "due_dt", "due date", "due on", "due on date"],
    "invoice_reference": [
        "invoice",
        "invoice_no",
        "invoice_number",
        "bill_no",
        "bill no",
        "voucher no",
        "document no",
        "ref no",
        "ref no.",
        "reference",
        "bill reference",
    ],
    "invoice_date": ["invoice_dt", "bill_date", "date", "voucher date", "document date"],
    "overdue_days": [
        "days_overdue",
        "age_days",
        "overdue",
        "overdue days",
        "overdue by days",
        "days overdue",
        "ageing days",
    ],
    "phone_number": ["phone", "mobile", "mobile no", "mobile number", "phone number"],
    "salesperson": ["sales_person", "owner", "sales person", "salesperson", "sales executive"],
    "notes": ["remarks", "comment", "comments", "narration", "notes"],
    "external_customer_code": [
        "customer_code",
        "customer code",
        "party_code",
        "party code",
        "ledger_code",
        "ledger code",
        "account code",
    ],
}

COLUMN_ALIASES = {
    field: {normalize_name(alias) for alias in aliases}
    for field, aliases in RAW_COLUMN_ALIASES.items()
}


def _normalize_columns(columns: list[str]) -> dict[str, str]:
    return {column: normalize_name(column) for column in columns}


def _pick_source_column(canonical_field: str, normalized_columns: dict[str, str], mapping: dict[str, str]) -> str | None:
    explicit = mapping.get(canonical_field)
    if explicit:
        explicit_normalized = normalize_name(explicit)
        for original, normalized in normalized_columns.items():
            if normalized == explicit_normalized:
                return original

    candidate_names = {normalize_name(canonical_field), *COLUMN_ALIASES.get(canonical_field, set())}
    for original, normalized in normalized_columns.items():
        if normalized in candidate_names:
            return original
    return None


def _read_csv_dataframe(content: bytes) -> pd.DataFrame:
    raw_text = content.decode("utf-8-sig", errors="replace")
    preview = raw_text[:500].lower()
    if "<html" in preview or "<!doctype html" in preview:
        raise ValueError("Uploaded file looks like an HTML page, not a CSV export. Download the raw CSV file and upload it again.")

    sample = "\n".join(raw_text.splitlines()[:5])
    candidate_delimiters: list[str] = []
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        candidate_delimiters.append(dialect.delimiter)
    except csv.Error:
        pass

    for delimiter in [",", ";", "\t", "|"]:
        if delimiter not in candidate_delimiters:
            candidate_delimiters.append(delimiter)

    last_error: Exception | None = None
    for delimiter in candidate_delimiters:
        try:
            dataframe = pd.read_csv(io.StringIO(raw_text), sep=delimiter, engine="python")
            if len(dataframe.columns) > 1:
                return dataframe
        except (ParserError, UnicodeDecodeError, ValueError) as exc:
            last_error = exc

    raise ValueError(f"Could not parse CSV upload. {last_error}")


def _clean_excel_header_cell(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text or text.lower().startswith("unnamed:"):
        return ""
    return text


def _dedupe_headers(headers: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: dict[str, int] = {}
    for index, header in enumerate(headers, start=1):
        base = header or f"unnamed_{index}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        deduped.append(base if count == 1 else f"{base}_{count}")
    return deduped


def _score_candidate_header(columns: list[str], mapping: dict[str, str]) -> tuple[int, int, int]:
    normalized_columns = _normalize_columns(columns)
    matched_fields = {
        field
        for field in ReceivableImportRow.model_fields
        if _pick_source_column(field, normalized_columns, mapping)
    }
    required_matches = sum(1 for field in REQUIRED_IMPORT_FIELDS if field in matched_fields)
    named_columns = sum(1 for column in columns if column and not column.startswith("unnamed_"))
    return required_matches, len(matched_fields), named_columns


def _read_excel_dataframe(content: bytes, mapping: dict[str, str], sheet_name: str | None) -> pd.DataFrame:
    workbook = pd.read_excel(pd.io.common.BytesIO(content), sheet_name=sheet_name or None, header=None)
    if not isinstance(workbook, dict):
        workbook = {sheet_name or "Sheet1": workbook}

    if sheet_name and sheet_name not in workbook:
        raise ValueError(f"Sheet '{sheet_name}' was not found in the uploaded workbook.")

    best_score = (-1, -1, -1, 0)
    best_dataframe: pd.DataFrame | None = None

    candidate_sheets = [(sheet_name, workbook[sheet_name])] if sheet_name else list(workbook.items())
    for _, sheet_frame in candidate_sheets:
        trimmed = sheet_frame.dropna(axis=0, how="all").dropna(axis=1, how="all").reset_index(drop=True)
        if trimmed.empty:
            continue

        scan_limit = min(EXCEL_HEADER_SCAN_LIMIT, len(trimmed))
        for header_row_index in range(scan_limit):
            raw_headers = [_clean_excel_header_cell(value) for value in trimmed.iloc[header_row_index].tolist()]
            deduped_headers = _dedupe_headers(raw_headers)
            prepared = trimmed.iloc[header_row_index + 1 :].copy()
            prepared.columns = deduped_headers
            prepared = prepared.dropna(axis=0, how="all").dropna(axis=1, how="all")
            if prepared.empty:
                continue

            score = (*_score_candidate_header(deduped_headers, mapping), -header_row_index)
            if score > best_score:
                best_score = score
                best_dataframe = prepared

    if best_dataframe is None or best_score[0] == 0:
        raise ValueError(
            "Could not locate a usable header row in the Excel workbook. "
            "Make sure the sheet includes customer and amount columns."
        )

    return best_dataframe


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


def _should_skip_row(customer_name: str) -> bool:
    normalized = normalize_name(customer_name)
    return normalized in IGNORED_ROW_LABELS


def load_rows(file_name: str, content: bytes, mapping: dict[str, str], sheet_name: str | None) -> list[ReceivableImportRow]:
    if file_name.lower().endswith(".csv"):
        dataframe = _read_csv_dataframe(content)
    else:
        dataframe = _read_excel_dataframe(content, mapping, sheet_name)

    normalized_columns = _normalize_columns(list(dataframe.columns))
    rows: list[ReceivableImportRow] = []
    for _, series in dataframe.iterrows():
        payload = {}
        for field in ReceivableImportRow.model_fields:
            source_column = _pick_source_column(field, normalized_columns, mapping)
            payload[field] = series[source_column] if source_column in series else None

        customer_name = str(payload.get("customer_name") or "").strip()
        if not customer_name or payload.get("amount_outstanding") in (None, ""):
            continue
        if _should_skip_row(customer_name):
            continue

        row = ReceivableImportRow(
            customer_name=customer_name,
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
