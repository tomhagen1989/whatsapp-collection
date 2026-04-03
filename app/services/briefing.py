from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Customer, ImportSnapshot, ReceivableCase
from app.schemas import AttentionItem, MorningBriefView

DEFAULT_BUCKETS = [30, 60, 90]


def _bucket_label(days: int | None, buckets: list[int]) -> str:
    overdue = max(days or 0, 0)
    if overdue <= buckets[0]:
        return f"0-{buckets[0]}"
    if overdue <= buckets[1]:
        return f"{buckets[0] + 1}-{buckets[1]}"
    if overdue <= buckets[2]:
        return f"{buckets[1] + 1}-{buckets[2]}"
    return f"{buckets[2]}+"


def _attention_item(case: ReceivableCase, customer_name: str, reason: str) -> AttentionItem:
    return AttentionItem(
        customer_id=case.customer_id,
        case_id=case.id,
        customer_name=customer_name,
        amount_outstanding=case.amount_outstanding,
        reason=reason,
        overdue_days=case.overdue_days,
        action_hint=f"show {customer_name}",
    )


def build_morning_brief(db: Session, tenant_id: int, limit: int = 5) -> MorningBriefView:
    cases = db.scalars(
        select(ReceivableCase)
        .where(ReceivableCase.tenant_id == tenant_id, ReceivableCase.status.not_in(["paid", "closed"]))
        .order_by(desc(ReceivableCase.amount_outstanding))
    ).all()
    customers = {
        customer.id: customer.customer_name
        for customer in db.scalars(select(Customer).where(Customer.tenant_id == tenant_id)).all()
    }
    latest_snapshot = db.scalar(
        select(ImportSnapshot)
        .where(ImportSnapshot.tenant_id == tenant_id, ImportSnapshot.sync_status == "success")
        .order_by(desc(ImportSnapshot.snapshot_version))
    )

    buckets = {"0-30": Decimal("0"), "31-60": Decimal("0"), "61-90": Decimal("0"), "90+": Decimal("0")}
    promises_due: list[AttentionItem] = []
    stale_cases: list[AttentionItem] = []
    biggest_overdues: list[AttentionItem] = []

    for case in cases:
        label = _bucket_label(case.overdue_days, DEFAULT_BUCKETS)
        buckets[label] = buckets.get(label, Decimal("0")) + case.amount_outstanding
        name = customers.get(case.customer_id, "Unknown customer")
        if case.latest_promise_date and case.latest_promise_date <= datetime.now(timezone.utc).date():
            promises_due.append(_attention_item(case, name, "Promise due or missed"))
        if case.next_follow_up_date and case.next_follow_up_date <= datetime.now(timezone.utc).date():
            stale_cases.append(_attention_item(case, name, "Follow-up overdue"))
        biggest_overdues.append(_attention_item(case, name, f"{case.overdue_days} days overdue"))

    attention = (promises_due + stale_cases + biggest_overdues)[:limit]
    total = sum((case.amount_outstanding for case in cases), start=Decimal("0"))
    freshness = None
    if latest_snapshot is None:
        freshness = "No successful import yet. Results are based on current operational state only."

    return MorningBriefView(
        total_outstanding=total,
        ageing_buckets=buckets,
        attention_items=attention,
        promises_due=promises_due[:limit],
        stale_cases=stale_cases[:limit],
        generated_at=datetime.now(timezone.utc),
        snapshot_version=latest_snapshot.snapshot_version if latest_snapshot else None,
        freshness_note=freshness,
    )


def render_brief_text(brief: MorningBriefView) -> str:
    bucket_text = " | ".join(f"{label}: Rs {amount}" for label, amount in brief.ageing_buckets.items())
    lines = [
        "Receivables as of today",
        f"Total outstanding: Rs {brief.total_outstanding}",
        bucket_text,
    ]
    if brief.attention_items:
        lines.append("Needs attention:")
        for idx, item in enumerate(brief.attention_items, start=1):
            lines.append(
                f"{idx}. {item.customer_name} - Rs {item.amount_outstanding} - {item.reason}"
            )
    if brief.freshness_note:
        lines.append(brief.freshness_note)
    return "\n".join(lines)
