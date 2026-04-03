from app.models import DriveSource, ReceivableCase
from app.services.ingestion import ingest_source_file
from app.services.uploads import ingest_manual_upload


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

    assert case.invoice_reference == "INV-1001"
    assert str(case.amount_outstanding) == "48500.00"
    assert case.overdue_days == 58
    assert case.metadata_json["salesperson"] == "Rohit Sharma"
    assert case.metadata_json["notes"] == "Follow up after dispatch"
    assert case.metadata_json["external_customer_code"] == "CUST-001"


def test_ingest_manual_upload_creates_manual_source_and_snapshot(db_session, seeded_tenant):
    tenant, _ = seeded_tenant
    csv_payload = b"customer_name,amount_outstanding,due_date,invoice_reference\nKaveri Super Stores,42000,2026-03-31,INV-2403-021\n"

    snapshot, source = ingest_manual_upload(
        db_session,
        tenant.id,
        "pilot-upload.csv",
        csv_payload,
        sheet_name=None,
    )

    stored_source = db_session.query(DriveSource).filter(DriveSource.id == source.id).one()
    case = db_session.query(ReceivableCase).filter(ReceivableCase.drive_source_id == source.id).one()

    assert stored_source.provider == "manual_upload"
    assert stored_source.google_file_name == "pilot-upload.csv"
    assert snapshot.imported_rows == 1
    assert snapshot.drive_source_id == source.id
    assert case.invoice_reference == "INV-2403-021"
    assert str(case.amount_outstanding) == "42000.00"


def test_ingest_source_file_accepts_semicolon_delimited_csv(db_session, seeded_tenant):
    tenant, source = seeded_tenant
    csv_payload = b"Date;Ref No.;Party's Name;Pending Amount;Due On;Overdue by days\n2026-01-05;INV-1001;Gupta Traders;48500;2026-02-04;58\n"

    snapshot = ingest_source_file(db_session, tenant.id, source, "semicolon-upload.csv", csv_payload, None)

    assert snapshot.imported_rows == 1
    case = db_session.query(ReceivableCase).one()
    assert case.invoice_reference == "INV-1001"
    assert str(case.amount_outstanding) == "48500.00"
