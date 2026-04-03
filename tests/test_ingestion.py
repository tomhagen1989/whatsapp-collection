from app.models import ReceivableCase
from app.services.ingestion import ingest_source_file


def test_ingest_source_file_upserts_and_closes_missing_rows(db_session, seeded_tenant):
    tenant, source = seeded_tenant
    csv_v1 = b"customer_name,amount_outstanding,due_date,invoice_reference\nGupta Traders,48500,2026-01-25,INV-1\nMehta Agencies,120000,2026-02-10,INV-2\n"
    snapshot_one = ingest_source_file(db_session, tenant.id, source, "receivables.csv", csv_v1, None)
    assert snapshot_one.imported_rows == 2

    csv_v2 = b"customer_name,amount_outstanding,due_date,invoice_reference\nGupta Traders,30000,2026-01-25,INV-1\n"
    snapshot_two = ingest_source_file(db_session, tenant.id, source, "receivables.csv", csv_v2, None)
    assert snapshot_two.snapshot_version == 2

    cases = db_session.query(ReceivableCase).order_by(ReceivableCase.invoice_reference).all()
    assert len(cases) == 2
    assert str(cases[0].amount_outstanding) == "30000.00"
    assert cases[1].status == "closed"
    assert cases[1].closed_reason == "missing_from_latest_import"
