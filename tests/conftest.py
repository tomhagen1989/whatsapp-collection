from datetime import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import DriveSource, Tenant


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture()
def seeded_tenant(db_session):
    tenant = Tenant(business_name="Acme Traders", timezone="Asia/Kolkata", morning_brief_time=time(9, 0))
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)

    source = DriveSource(
        tenant_id=tenant.id,
        google_file_id="file-1",
        google_file_name="receivables.csv",
        schema_mapping_json={},
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return tenant, source
