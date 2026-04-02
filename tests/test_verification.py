from app.schemas import ParsedMessage
from app.services.ingestion import ingest_source_file
from app.services.verification import verify_case_update


def test_verify_case_update_requires_confirmation_for_index_reference(db_session, seeded_tenant):
    tenant, source = seeded_tenant
    csv_data = b"customer_name,amount_outstanding,due_date,invoice_reference,overdue_days\nGupta Traders,48500,2026-01-25,INV-1,67\n"
    ingest_source_file(db_session, tenant.id, source, "receivables.csv", csv_data, None)

    result = verify_case_update(
        db_session,
        tenant.id,
        ParsedMessage(intent="update_case", customer_reference="1", outcome_type="promise_to_pay"),
    )
    assert result.is_valid
    assert result.needs_confirmation


def test_verify_case_update_finds_exact_customer(db_session, seeded_tenant):
    tenant, source = seeded_tenant
    csv_data = b"customer_name,amount_outstanding,due_date,invoice_reference\nGupta Traders,48500,2026-01-25,INV-1\n"
    ingest_source_file(db_session, tenant.id, source, "receivables.csv", csv_data, None)

    result = verify_case_update(
        db_session,
        tenant.id,
        ParsedMessage(intent="update_case", customer_name="Gupta Traders", outcome_type="paid_partial"),
    )
    assert result.is_valid
    assert result.case_id is not None
