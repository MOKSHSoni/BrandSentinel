"""Bad input, the same action twice, interrupted work: nothing should break, hang or leave a false state."""

import io
import zipfile

import pytest
from conftest import login
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app.main import app
from app.models import DraftVersion, Rulebook
from app.routers import drafts as drafts_router
from app.services import images, review
from app.services.intake import make_docx

BANNER = images.__file__.rsplit("services", 1)[0] + "samples/festive_banner.png"


def png(w, h):
    b = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(b, "PNG")
    return b.getvalue()


def banner():
    with open(BANNER, "rb") as fh:
        return fh.read()


def create(client, h, **data):
    files = data.pop("files", None)
    r = client.post("/api/drafts", headers=h, data={"title": "t", "goal": "Build trust", **data}, files=files)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def get(client, h, did):
    return client.get(f"/api/drafts/{did}", headers=h).json()


# ---------- oversized and hostile files ----------

def test_huge_image_is_refused_before_decoding(client, monkeypatch):
    priya = login(client, "priya")
    monkeypatch.setattr(images, "MAX_PIXELS", 1_000_000)
    r = client.post("/api/drafts", headers=priya, data={"title": "t"}, files={"file": ("big.png", png(1200, 1000))})
    assert r.status_code == 400 and "too large" in r.json()["detail"] and "1200×1000" in r.json()["detail"]


def test_huge_picture_in_word_file_does_not_fail_the_draft(client, monkeypatch):
    priya = login(client, "priya")
    monkeypatch.setattr(images, "MAX_PIXELS", 1_000_000)
    did = create(client, priya, files={"file": ("p.docx", make_docx("x", "Rated 4.6 on Google Play.", png(1200, 1000)))})
    v = get(client, priya, did)["version"]
    f = next(x for x in v["findings"] if x["check"] == "image")
    assert f["outcome"] == "needs_review" and "too large" in f["explanation"]
    assert any(x["outcome"] == "supported" for x in v["findings"])  # the text was still checked


def test_docx_zip_bomb_is_refused(client, monkeypatch):
    from app.services import intake

    monkeypatch.setattr(intake, "MAX_UNZIPPED", 1000)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", "0" * 100_000)
    r = client.post("/api/drafts", headers=login(client, "priya"), data={"title": "t"}, files={"file": ("x.docx", b.getvalue())})
    assert r.status_code == 400 and "too large" in r.json()["detail"]


def test_scanned_pdf_is_read_by_ocr(client):
    import fitz

    priya = login(client, "priya")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=banner())
    did = create(client, priya, files={"file": ("scan.pdf", doc.tobytes())})
    v = get(client, priya, did)["version"]
    assert v["assets"][0]["source"] == "pdf" and v["assets"][0]["ocr_status"] == "ok"
    assert any(f["outcome"] == "contradicted" and f["meta"].get("in_image") for f in v["findings"])
    assert not any(f["meta"].get("kind") == "alt_text" for f in v["findings"])


def test_pdf_with_nothing_readable_says_so(client):
    import fitz

    doc = fitz.open()
    doc.new_page()
    r = client.post("/api/drafts", headers=login(client, "priya"), data={"title": "t"}, files={"file": ("e.pdf", doc.tobytes())})
    assert r.status_code == 400 and "No readable text" in r.json()["detail"]


def test_corrupt_image_message_is_readable(client):
    r = client.post("/api/drafts", headers=login(client, "priya"), data={"title": "t"}, files={"file": ("x.png", b"nope")})
    assert r.status_code == 400 and r.json()["detail"] == "This file could not be opened as an image."


def test_ocr_crash_during_reading_is_reported_not_fatal(client, monkeypatch):
    class Broken:
        def __call__(self, _img):
            raise MemoryError("no memory")

    monkeypatch.setattr(images, "_ocr_engine", lambda: Broken())
    priya = login(client, "priya")
    did = create(client, priya, files={"file": ("b.png", banner())})
    v = get(client, priya, did)["version"]
    assert v["review_state"] == "done" and v["assets"][0]["ocr_status"] == "failed"
    assert any(f["check"] == "image" for f in v["findings"])


# ---------- reviews can never hang ----------

def test_restart_during_review_is_recovered(client, db):
    priya = login(client, "priya")
    did = create(client, priya, text="Trusted by 50,000 customers.")
    v = db.scalar(select(DraftVersion).where(DraftVersion.draft_id == did))
    v.review_state = "pending"
    db.commit()
    assert get(client, priya, did)["version"]["pending_seconds"] >= 0
    drafts_router.recover_pending_reviews()
    assert get(client, priya, did)["version"]["review_state"] == "done"


def test_failed_review_is_recorded_and_can_be_retried(client, monkeypatch):
    priya = login(client, "priya")
    real = review.run_review

    def boom(*a, **k):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(review, "run_review", boom)
    did = create(client, priya, text="Trusted by 50,000 customers.")
    v = get(client, priya, did)["version"]
    assert v["review_state"] == "failed" and "Retry" in v["ai_status"] and "secret" not in v["ai_status"]
    assert client.post(f"/api/drafts/{did}/signoff", headers=login(client, "meera"), json={}).status_code == 400
    monkeypatch.setattr(review, "run_review", real)
    assert client.post(f"/api/drafts/{did}/review", headers=priya).json()["state"] == "done"


def test_retry_while_a_review_is_running_is_refused(client):
    priya = login(client, "priya")
    did = create(client, priya, text="Hello.")
    version_id = get(client, priya, did)["version"]["id"]
    with review.claim(version_id):
        r = client.post(f"/api/drafts/{did}/review", headers=priya)
    assert r.status_code == 409 and "already running" in r.json()["detail"]


# ---------- the same action twice ----------

def test_rejected_is_final(client):
    priya, meera = login(client, "priya"), login(client, "meera")
    did = create(client, priya, text="Trusted by 50,000 customers.")
    f = get(client, priya, did)["version"]["findings"][0]
    body = {"decision": "rejected", "comment": "No"}
    assert client.post(f"/api/drafts/{did}/decision", headers=meera, json=body).status_code == 200
    assert client.post(f"/api/drafts/{did}/decision", headers=meera, json=body).status_code == 400
    assert client.post(f"/api/drafts/{did}/signoff", headers=meera, json={"overrides": {str(f["id"]): "x"}}).status_code == 400
    assert client.post(f"/api/findings/{f['id']}/decision", headers=priya, json={"action": "accept"}).status_code == 400
    assert client.post(f"/api/drafts/{did}/versions", headers=priya, data={"text": "New"}).status_code == 400
    assert get(client, priya, did)["status"] == "rejected"


def test_one_sign_off_per_version(client):
    priya, meera = login(client, "priya"), login(client, "meera")
    did = create(client, priya, text="Pay at 12,000 merchants.")
    assert client.post(f"/api/drafts/{did}/signoff", headers=meera, json={}).status_code == 200
    r = client.post(f"/api/drafts/{did}/signoff", headers=meera, json={})
    assert r.status_code == 400 and "already signed off" in r.json()["detail"]
    assert len(get(client, meera, did)["signoffs"]) == 1
    r = client.post(f"/api/drafts/{did}/decision", headers=meera, json={"decision": "rejected", "comment": "x"})
    assert r.status_code == 400 and get(client, meera, did)["status"] == "signed_off"


def test_renewing_a_sign_off_closes_the_old_one(client):
    priya, meera, rahul = login(client, "priya"), login(client, "meera"), login(client, "rahul")
    did = create(client, priya, text="Join over 80,000 customers.")
    client.post(f"/api/drafts/{did}/signoff", headers=meera, json={})
    f12 = next(g for g in client.get("/api/facts", headers=rahul).json() if g["key"] == "F-12")["current"]
    client.post(f"/api/facts/{f12['id']}/supersede", headers=rahul, json={"changes": {"value_num": 95000}})
    assert get(client, meera, did)["status"] == "needs_renewal"
    client.post(f"/api/drafts/{did}/review", headers=meera)
    assert client.post(f"/api/drafts/{did}/signoff", headers=meera, json={"comment": "renewed"}).status_code == 200
    d = get(client, meera, did)
    assert d["status"] == "signed_off" and sorted(s["status"] for s in d["signoffs"]) == ["superseded", "valid"]
    open_renewals = client.get("/api/radar", headers=meera).json()["open_risk"]["renewals"]
    assert did not in [r["draft_id"] for r in open_renewals]


# ---------- text read from an image ----------

def test_image_text_cannot_be_edited_away(client):
    priya = login(client, "priya")
    did = create(client, priya, files={"file": ("p.docx", make_docx("x", "Intro line.", banner()))})
    content = get(client, priya, did)["version"]["content"]
    r = client.post(f"/api/drafts/{did}/versions", headers=priya, data={"text": content.replace("50,000", "80,000")})
    assert r.status_code == 400 and "image" in r.json()["detail"]
    block_gone = content.split("\n\n")[0]
    assert client.post(f"/api/drafts/{did}/versions", headers=priya, data={"text": block_gone}).status_code == 400
    ok = client.post(f"/api/drafts/{did}/versions", headers=priya, data={"text": content.replace("Intro line.", "New intro.")})
    assert ok.status_code == 200
    v = get(client, priya, did)["version"]
    assert v["number"] == 2 and len(v["assets"]) == 1  # the image stays with the new version
    fixed = client.post(f"/api/drafts/{did}/versions", headers=priya, data={"note": "New picture"},
                        files={"file": ("p.docx", make_docx("x", "New intro."))})
    assert fixed.status_code == 200 and get(client, priya, did)["version"]["assets"] == []


# ---------- rule and fact input ----------

@pytest.mark.parametrize("key,config", [
    ("R-09", {"colors": ["#XYZ"], "tolerance": 48, "min_share": 0.08}),
    ("R-09", {"colors": [], "tolerance": 48, "min_share": 0.08}),
    ("R-08", {"require_alt": True, "min_contrast": "abc", "min_contrast_large": 3}),
    ("R-08", {"require_alt": True, "min_contrast": 0, "min_contrast_large": 3}),
    ("R-05", {"trigger_regex": "(", "present_regex": "x", "required": "T&C"}),
    ("R-05", {"trigger_regex": "x", "present_regex": "x", "required": " "}),
    ("R-01", {"correct": "", "variants": []}),
    ("R-03", {"terms": "ZipWallet"}),
    ("R-03", {"terms": ["ok", "  "]}),
])
def test_invalid_rule_config_is_refused(client, db, key, config):
    rahul = login(client, "rahul")
    rule = next(r for r in client.get("/api/rules", headers=rahul).json()["rules"] if r["key"] == key)
    assert client.post(f"/api/rules/{rule['id']}/simulate", headers=rahul, json={"config": config}).status_code == 400
    assert client.put(f"/api/rules/{rule['id']}", headers=rahul, json={"config": config}).status_code == 400
    db.expire_all()
    assert db.scalar(select(func.max(Rulebook.version))) == 1  # nothing was saved


def test_blank_guideline_is_refused(client):
    rahul = login(client, "rahul")
    rule = client.get("/api/rules", headers=rahul).json()["rules"][0]
    assert client.put(f"/api/rules/{rule['id']}", headers=rahul, json={"guideline": "  "}).status_code == 400


@pytest.mark.parametrize("patch", [
    {"metric": "   "}, {"scope": ""}, {"source": " "}, {"value_num": -1},
    {"valid_until": "2026-01-01"},  # before the effective date
])
def test_invalid_new_fact_is_refused(client, patch):
    rahul = login(client, "rahul")
    body = {"kind": "count", "metric": "M", "value_num": 1, "scope": "India", "effective_date": "2026-10-01",
            "source": "s", "source_version": "1", **patch}
    assert client.post("/api/facts", headers=rahul, json=body).status_code == 400


def test_fact_change_limits_and_renewing_past_its_end_date(client):
    rahul = login(client, "rahul")
    g = {x["key"]: x["current"] for x in client.get("/api/facts", headers=rahul).json()}
    url = f"/api/facts/{g['F-14']['id']}"
    for changes in ({"value_num": 150}, {"value_num": -3}, {"effective_date": "2020-01-01"}, {"scope": " "}):
        assert client.post(f"{url}/simulate", headers=rahul, json={"changes": changes}).status_code == 400, changes
        assert client.post(f"{url}/supersede", headers=rahul, json={"changes": changes}).status_code == 400, changes
    # The new version starts after the old end date: the admin must give a new one, and then it is current.
    late = {"value_num": 99.5, "effective_date": "2027-02-01"}
    r = client.post(f"{url}/supersede", headers=rahul, json={"changes": late})
    assert r.status_code == 400 and "valid until" in r.json()["detail"]
    r = client.post(f"{url}/supersede", headers=rahul, json={"changes": {**late, "valid_until": "2027-12-31"}})
    assert r.status_code == 200 and r.json()["fact"]["valid_until"] == "2027-12-31"
    assert client.post(f"/api/facts/{g['F-16']['id']}/simulate", headers=rahul, json={"changes": {"value_num": 6}}).status_code == 400


def test_simulator_explains_a_draft_that_only_cites_the_fact_as_a_candidate(client):
    priya, rahul = login(client, "priya"), login(client, "rahul")
    did = create(client, priya, text="Nimbus Pay has 80,000 active users.")
    f12 = next(g for g in client.get("/api/facts", headers=rahul).json() if g["key"] == "F-12")["current"]
    sim = client.post(f"/api/facts/{f12['id']}/simulate", headers=rahul, json={"changes": {"value_num": 95000}}).json()
    entry = next(d for d in sim["drafts"] if d["draft_id"] == did)
    assert "candidate" in entry["reason"] and not any(c["changed"] for c in entry["claims"])


# ---------- readable errors ----------

def test_validation_errors_are_readable(client):
    meera = login(client, "meera")
    r = client.get("/api/drafts/abc", headers=meera)
    assert r.status_code == 422 and isinstance(r.json()["detail"], str) and "draft id" in r.json()["detail"]


def test_unexpected_errors_return_json(db, monkeypatch):
    from app.services import llm

    def boom():
        raise RuntimeError("secret")

    monkeypatch.setattr(llm, "local_available", boom)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/health", headers={"Origin": "https://x.vercel.app"})
    assert r.status_code == 500 and "secret" not in r.text and "went wrong" in r.json()["detail"]
    assert r.headers.get("access-control-allow-origin") == "https://x.vercel.app"
