from datetime import UTC, datetime, timedelta

from app.models import PendingConfirmation
from app.services.collections import get_pending_confirmation


def test_get_pending_confirmation_accepts_naive_future_timestamp(db_session, seeded_tenant):
    tenant, _ = seeded_tenant
    confirmation = PendingConfirmation(
        tenant_id=tenant.id,
        action_type="case_update",
        confirmation_token="deadbeef",
        action_payload_json={"parsed": {}, "verification": {}},
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    db_session.add(confirmation)
    db_session.commit()

    found = get_pending_confirmation(db_session, tenant.id, "deadbeef")

    assert found is not None
    assert found.confirmation_token == "deadbeef"


def test_get_pending_confirmation_rejects_naive_expired_timestamp(db_session, seeded_tenant):
    tenant, _ = seeded_tenant
    confirmation = PendingConfirmation(
        tenant_id=tenant.id,
        action_type="case_update",
        confirmation_token="feedcafe",
        action_payload_json={"parsed": {}, "verification": {}},
        expires_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db_session.add(confirmation)
    db_session.commit()

    found = get_pending_confirmation(db_session, tenant.id, "feedcafe")

    assert found is None
