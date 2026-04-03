from datetime import date

from app.models import Customer, ReceivableCase
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


def test_ingest_source_file_accepts_tally_style_receivables_headers(db_session, seeded_tenant):
    tenant, source = seeded_tenant
    tally_csv = b"Date,Ref No.,Party's Name,Opening Amount,Pending Amount,Due On,Overdue by days,Mobile,Sales Person,Remarks,Party Code\n2026-01-05,INV-1001,Gupta Traders,\"48,500\",\"48,500\",2026-02-04,58,9876543210,Rohit Sharma,Follow up after dispatch,CUST-001\n"

    snapshot = ingest_source_file(db_session, tenant.id, source, "tally-bills-receivable.csv", tally_csv, None)

    assert snapshot.imported_rows == 1
    case = db_session.query(ReceivableCase).one()
    customer = db_session.query(Customer).one()

    assert case.invoice_reference == "INV-1001"
    assert case.invoice_date == date(2026, 1, 5)
    assert case.due_date == date(2026, 2, 4)
    assert str(case.amount_outstanding) == "48500.00"
    assert case.overdue_days == 58
    assert case.metadata_json["salesperson"] == "Rohit Sharma"
    assert case.metadata_json["notes"] == "Follow up after dispatch"
    assert case.metadata_json["external_customer_code"] == "CUST-001"
    assert customer.customer_name == "Gupta Traders"
    assert customer.phone_number == "9876543210"
    assert customer.external_customer_code == "CUST-001"
