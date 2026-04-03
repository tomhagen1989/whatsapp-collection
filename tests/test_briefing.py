from app.services.briefing import build_morning_brief
from app.services.ingestion import ingest_source_file
from app.services.verification import verify_summary_numbers


def test_build_morning_brief_returns_verified_numbers(db_session, seeded_tenant):
    tenant, source = seeded_tenant
    csv_data = b"customer_name,amount_outstanding,due_date,invoice_reference,overdue_days\nGupta Traders,48500,2026-01-25,INV-1,67\nMehta Agencies,120000,2026-02-10,INV-2,12\n"
    ingest_source_file(db_session, tenant.id, source, "receivables.csv", csv_data, None)

    brief = build_morning_brief(db_session, tenant.id)
    assert brief.total_outstanding > 0
    assert len(brief.attention_items) >= 1
    assert verify_summary_numbers(brief.total_outstanding, brief.ageing_buckets)
