import os

# Must be set before the app is imported: tests are deterministic (no model) and use their own database.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite://")
os.environ["LOCAL_LLM_ENABLED"] = "false"
os.environ["EXTERNAL_LLM_URL"] = ""
os.environ["REVIEW_DATE"] = "2026-10-27"
os.environ["SEED_ON_STARTUP"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402
from app.services.review import ledger  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    seed(session)
    yield session
    session.close()


@pytest.fixture()
def lg(db):
    return ledger(db)


@pytest.fixture()
def client(db):
    with TestClient(app) as c:
        yield c


def login(client, who: str) -> dict:
    emails = {"priya": "priya@nimbuspay.example", "arjun": "arjun@bluefin.example",
              "meera": "meera@nimbuspay.example", "rahul": "rahul@nimbuspay.example"}
    r = client.post("/api/auth/login", json={"email": emails[who], "password": "demo1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
