import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_tmp = tempfile.mkdtemp(prefix="cove2e_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'test.db').replace(os.sep, '/')}"
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["DEMO_MODE"] = "true"
os.environ["APP_ENV"] = "test"
os.environ["SARVAM_API_KEY"] = ""
os.environ["COGNEE_ENABLED"] = "false"
os.environ["N8N_BASE_URL"] = "http://127.0.0.1:1"  # unreachable → demo fallback path

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import demo_service  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def demo_user(db):
    demo_service.ensure_products(db)
    user = demo_service.ensure_demo_user(db, "demo")
    db.commit()
    return user


@pytest.fixture()
def demo_data(db, demo_user):
    ids = demo_service.load_recovery_demo(db, demo_user)
    return ids


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_client(client):
    resp = client.post("/api/auth/demo-login", json={"demo_code": "demo"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
