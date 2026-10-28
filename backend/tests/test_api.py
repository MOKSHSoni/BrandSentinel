"""End-to-end tests through the HTTP API: the four-step demo, permissions, sign-off rules and blast radius."""

import io
import time

from conftest import login

from app.services.intake import make_docx

LAUNCH = ("Meet the new Nimbus Pay app.\n\nIndia's #1 payments app, trusted by 50,000 customers. Send money, split "
          "bills and pay at over 12,000 merchants, all with UPI.\n\nDownload Nimbus Pay today.")
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def create(client, h, text=LAUNCH, **extra):
    data = {"title": "LinkedIn launch post", "goal": "Build trust in the new app", "channel": "LinkedIn", **extra}
    r = client.post("/api/drafts", headers=h, data=data,
                    files={"file": ("post.docx", make_docx("Launch", text), DOCX)})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def get(client, h, did):
    r = client.get(f"/api/drafts/{did}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_full_demo_journey(client):
    arjun, meera, rahul = login(client, "arjun"), login(client, "meera"), login(client, "rahul")

    # 1. Check a draft (DOCX intake).
    did = create(client, arjun)
    d = get(client, arjun, did)
    v1 = d["version"]
    assert v1["review_state"] == "done" and v1["number"] == 1
    by_outcome = {f["outcome"]: f for f in v1["findings"]}
    assert by_outcome["contradicted"]["quote"] == "50,000 customers"
    assert by_outcome["contradicted"]["fact"]["label"] == "F-12 v3"
    assert by_outcome["unverified"]["quote"] == "India's #1 payments app"
    assert by_outcome["supported"]["fact"]["label"] == "F-13 v2"
    # Agencies see the fact ID but not the internal document behind it.
    assert "source_detail" not in by_outcome["contradicted"]["fact"]

    # Sign-off is refused while blocking findings are open.
    r = client.post(f"/api/drafts/{did}/signoff", headers=meera, json={})
    assert r.status_code == 400 and "blocking" in r.json()["detail"]

    # 2. Correct it: accept both checked fixes, apply, re-review.
    for f in v1["findings"]:
        if f["suggestion"] is not None:
            assert f["correction_check"]["shown"]
            assert client.post(f"/api/findings/{f['id']}/decision", headers=arjun, json={"action": "accept"}).status_code == 200
    r = client.post(f"/api/drafts/{did}/apply-fixes", headers=arjun)
    assert r.json()["version"] == 2
    v2 = get(client, arjun, did)["version"]
    assert "Trusted by 80,000 customers." in v2["content"]
    assert all(f["outcome"] == "supported" for f in v2["findings"])

    diff = client.get(f"/api/drafts/{did}/diff?a=1&b=2", headers=arjun).json()
    assert any(op["op"] == "insert" and "80,000" in op["text"] for op in diff["ops"])

    # 3. Sign off: bound to hash, rulebook version and fact versions.
    assert client.post(f"/api/drafts/{did}/signoff", headers=arjun, json={}).status_code == 403
    r = client.post(f"/api/drafts/{did}/signoff", headers=meera, json={"comment": "Approved."})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["version_number"] == 2 and s["rulebook_version"] == 1 and s["fact_labels"] == ["F-12 v3", "F-13 v2"]
    assert s["content_hash"] == v2["content_hash"]

    # 4. Change a fact: blast radius flags this post and the two seeded drafts citing F-12 v3.
    f12 = next(g for g in client.get("/api/facts", headers=rahul).json() if g["key"] == "F-12")["current"]
    preview = client.get(f"/api/facts/{f12['id']}/blast-preview", headers=rahul).json()
    assert len(preview["drafts"]) == 3
    assert client.post(f"/api/facts/{f12['id']}/supersede", headers=meera,
                       json={"changes": {"value_num": 95000}, "note": "x"}).status_code == 403
    r = client.post(f"/api/facts/{f12['id']}/supersede", headers=rahul,
                    json={"changes": {"value_num": 95000, "source_version": "v4"}, "note": "Restated"})
    assert r.status_code == 200, r.text
    blast = r.json()["blast"]
    titles = sorted(x["title"] for x in blast["affected"]["drafts"])
    assert titles == ["Diwali festive email", "Instagram caption: city launch", "LinkedIn launch post"]
    assert len(blast["affected"]["signoffs"]) == 2  # this post and the Diwali e-mail
    assert r.json()["fact"]["label"] == "F-12 v4" and r.json()["fact"]["value_text"] == "95,000"
    assert r.json()["fact"]["statement"] == "Trusted by 95,000 active customers across India"

    d = get(client, meera, did)
    assert d["status"] == "needs_renewal" and d["needs_rereview"]
    assert d["signoffs"][0]["status"] == "needs_renewal"
    # The merchant blog cites only F-13, so the F-12 change does not touch it (its flag is the seeded F-13 one).
    blog = next(x for x in client.get("/api/drafts", headers=meera).json() if x["title"].startswith("Merchant"))
    assert "F-13" in blog["rereview_reason"] and "F-12" not in blog["rereview_reason"]

    # Renewal: sign-off is refused until re-review; the re-review now contradicts 80,000.
    assert client.post(f"/api/drafts/{did}/signoff", headers=meera, json={}).status_code == 400
    client.post(f"/api/drafts/{did}/review", headers=arjun)
    d = get(client, arjun, did)
    assert not d["needs_rereview"]
    contra = next(f for f in d["version"]["findings"] if f["outcome"] == "contradicted")
    assert contra["fact"]["label"] == "F-12 v4" and contra["suggestion"] == "95,000 customers"


def test_override_needs_reason_and_is_recorded(client):
    arjun, meera = login(client, "arjun"), login(client, "meera")
    did = create(client, arjun, text="Nimbus Pay is India's #1 payments app.")
    f = get(client, arjun, did)["version"]["findings"][0]
    r = client.post(f"/api/drafts/{did}/signoff", headers=meera, json={"overrides": {str(f["id"]): "  "}})
    assert r.status_code == 400
    r = client.post(f"/api/drafts/{did}/signoff", headers=meera,
                    json={"overrides": {str(f["id"]): "Legal holds the 2026 ranking report."}})
    assert r.status_code == 200
    assert r.json()["overrides"][0]["reason"] == "Legal holds the 2026 ranking report."
    assert get(client, meera, did)["version"]["findings"][0]["status"] == "overridden"


def test_edit_after_signoff_needs_new_signoff(client):
    priya, meera = login(client, "priya"), login(client, "meera")
    did = create(client, priya, text="Pay at over 12,000 merchants with Nimbus Pay.")
    assert client.post(f"/api/drafts/{did}/signoff", headers=meera, json={}).status_code == 200
    r = client.post(f"/api/drafts/{did}/versions", headers=priya, data={"text": "Pay at 12,000 merchants with Nimbus Pay.", "note": "tweak"})
    assert r.status_code == 200 and r.json()["version"] == 2
    d = get(client, priya, did)
    assert d["status"] == "in_review" and d["signoffs"][0]["status"] == "superseded"
    # Identical text is not a new version.
    r = client.post(f"/api/drafts/{did}/versions", headers=priya, data={"text": "Pay at 12,000 merchants with Nimbus Pay."})
    assert r.status_code == 400


def test_dismiss_needs_reason_and_carries_over(client):
    priya = login(client, "priya")
    did = create(client, priya, text="Nimbus Pay is the best way to pay. Pay at 12,000 merchants.")
    f = next(x for x in get(client, priya, did)["version"]["findings"] if x["outcome"] == "unverified")
    assert client.post(f"/api/findings/{f['id']}/decision", headers=priya, json={"action": "dismiss"}).status_code == 400
    assert client.post(f"/api/findings/{f['id']}/decision", headers=priya,
                       json={"action": "dismiss", "reason": "Brand tagline approved by legal"}).status_code == 200
    client.post(f"/api/drafts/{did}/versions", headers=priya,
                data={"text": "Nimbus Pay is the best way to pay. Pay at over 12,000 merchants."})
    f2 = next(x for x in get(client, priya, did)["version"]["findings"] if x["quote"] == f["quote"])
    assert f2["status"] == "dismissed" and "carried over" in f2["decision_reason"]


def test_edited_fix_is_rechecked(client):
    priya = login(client, "priya")
    did = create(client, priya, text="Trusted by 50,000 customers.")
    f = next(x for x in get(client, priya, did)["version"]["findings"] if x["outcome"] == "contradicted")
    bad = client.post(f"/api/findings/{f['id']}/decision", headers=priya, json={"action": "edit", "text": "60,000 customers"}).json()
    assert bad["check"]["supported"]["pass"] is False
    good = client.post(f"/api/findings/{f['id']}/decision", headers=priya, json={"action": "edit", "text": "over 75,000 customers"}).json()
    assert good["check"]["supported"]["pass"] is True
    client.post(f"/api/drafts/{did}/apply-fixes", headers=priya)
    assert get(client, priya, did)["version"]["content"] == "Trusted by over 75,000 customers."


def test_permissions(client):
    priya, arjun, meera = login(client, "priya"), login(client, "arjun"), login(client, "meera")
    assert client.get("/api/drafts").status_code == 401
    priya_draft = next(d for d in client.get("/api/drafts", headers=priya).json())
    assert client.get(f"/api/drafts/{priya_draft['id']}", headers=arjun).status_code == 403
    assert all(d["created_by"]["email"] == "arjun@bluefin.example" for d in client.get("/api/drafts", headers=arjun).json())
    assert len(client.get("/api/drafts", headers=meera).json()) == 3
    assert client.post("/api/facts", headers=meera, json={}).status_code == 403
    assert client.put("/api/settings", headers=priya, json={"external_tiers": ["internal"]}).status_code == 403
    # Agencies see only public facts and never their source documents.
    facts = client.get("/api/facts", headers=arjun).json()
    assert all("source_detail" not in g["current"] for g in facts)
    assert "F-23" not in {g["key"] for g in facts}
    internal = client.get("/api/facts", headers=meera).json()
    assert "F-23" in {g["key"] for g in internal}


def test_agency_does_not_see_internal_figure(client):
    arjun = login(client, "arjun")
    did = create(client, arjun, text="This month Nimbus Pay processed 3 million transactions across India.")
    f = get(client, arjun, did)["version"]["findings"][0]
    assert f["outcome"] == "contradicted" and "2.4 million" not in f["message"] and f["suggestion"] is None
    meera = login(client, "meera")
    f_mgr = get(client, meera, did)["version"]["findings"][0]
    assert "2.4 million" in f_mgr["message"]


def test_retract_and_rule_change_flag_signoffs(client):
    rahul, meera = login(client, "rahul"), login(client, "meera")
    rules = client.get("/api/rules", headers=rahul).json()
    assert rules["current_version"] == 1
    r01 = next(r for r in rules["rules"] if r["key"] == "R-01")
    r = client.put(f"/api/rules/{r01['id']}", headers=rahul, json={"severity": "critical", "note": "Brand name is critical"})
    assert r.json()["rulebook_version"] == 2
    flagged = client.get("/api/blast-radius", headers=meera).json()
    # Diwali e-mail (flagged by the rulebook change) and the merchant blog (flagged by the seeded F-13 change).
    assert len(flagged["signoffs_needing_renewal"]) == 2

    f18 = next(g for g in client.get("/api/facts", headers=rahul).json() if g["key"] == "F-18")["current"]
    r = client.post(f"/api/facts/{f18['id']}/retract", headers=rahul, json={"note": "Coverage report was wrong"})
    assert [d["title"] for d in r.json()["blast"]["affected"]["drafts"]] == ["Instagram caption: city launch"]


def test_create_fact_and_validation(client):
    rahul = login(client, "rahul")
    r = client.post("/api/facts", headers=rahul, json={"kind": "count", "metric": "App downloads", "aliases": ["downloads"],
                                                       "value_num": 200000, "scope": "India", "effective_date": "2026-10-01",
                                                       "source": "Store console", "source_version": "Oct"})
    assert r.status_code == 200 and r.json()["key"] == "F-24" and r.json()["value_text"] == "200,000"
    assert client.post("/api/facts", headers=rahul, json={"kind": "count"}).status_code == 400
    priya = login(client, "priya")
    did = create(client, priya, text="Nimbus Pay has 2 lakh downloads.")
    assert get(client, priya, did)["version"]["findings"][0]["outcome"] == "supported"


def test_text_and_pdf_intake(client):
    import fitz

    priya = login(client, "priya")
    r = client.post("/api/drafts", headers=priya, data={"title": "t", "text": "Rated 4.6 on Google Play."})
    assert r.status_code == 200
    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "Rated 4.8 on Google Play.")
    r = client.post("/api/drafts", headers=priya, data={"title": "pdf"},
                    files={"file": ("x.pdf", io.BytesIO(pdf.tobytes()), "application/pdf")})
    assert r.status_code == 200
    f = get(client, priya, r.json()["id"])["version"]["findings"][0]
    assert f["outcome"] == "contradicted"
    assert client.post("/api/drafts", headers=priya, data={"title": "x"},
                       files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 400
    assert client.post("/api/drafts", headers=priya, data={"title": "x", "text": "   "}).status_code == 400


def test_restricted_draft_never_reaches_external_model(client, monkeypatch):
    from app.services import llm

    monkeypatch.setattr(llm, "local_available", lambda: False)
    monkeypatch.setattr(llm, "external_available", lambda: True)
    sent = []
    monkeypatch.setattr(llm, "_call", lambda loc, s, u: (sent.append((loc, u)) or ('{"claims": [], "findings": [], "results": []}', "ext")))
    priya = login(client, "priya")
    did = create(client, priya, text="Coming soon: the Falcon Card. Rated 4.6 on Google Play.")
    v = get(client, priya, did)["version"]
    assert v["effective_tier"] == "restricted" and sent == []
    assert "skipped" in v["ai_status"]
    # A public draft may use the external model.
    did = create(client, priya, text="Rated 4.6 on Google Play.")
    assert sent and all(loc == "external" for loc, _ in sent)
    calls = client.get("/api/insights", headers=login(client, "rahul")).json()["model_calls"]
    assert any(c["location"] == "blocked" and c["tier"] == "restricted" for c in calls)
    assert any(c["location"] == "external" and c["tier"] == "public" for c in calls)


def test_internal_draft_masked_when_admin_allows(client, monkeypatch):
    from app.services import llm

    monkeypatch.setattr(llm, "local_available", lambda: False)
    monkeypatch.setattr(llm, "external_available", lambda: True)
    sent = []
    monkeypatch.setattr(llm, "_call", lambda loc, s, u: (sent.append(u) or ('{"claims": [], "findings": [], "results": []}', "ext")))
    rahul, priya = login(client, "rahul"), login(client, "priya")
    create(client, priya, text="Call Priya on 9876543210 about Nimbus Pay.", sensitivity="internal")
    assert sent == []  # confidential (PII) and internal are blocked by default
    client.put("/api/settings", headers=rahul, json={"external_tiers": ["internal", "confidential"]})
    create(client, priya, text="Call Priya on 9876543210 about Nimbus Pay.", sensitivity="internal")
    assert sent and all("9876543210" not in u for u in sent)


def test_blast_radius_over_500_drafts_under_2_seconds(client, db):
    from app.models import Draft, Fact, User
    from app.services import governance, review

    author = db.query(User).filter_by(role="creator").first()
    admin = db.query(User).filter_by(role="admin").first()
    f12 = db.query(Fact).filter_by(key="F-12", status="approved").one()
    facts, rules = review.ledger(db)
    for i in range(500):
        d = Draft(title=f"Bulk {i}", created_by_id=author.id)
        db.add(d)
        db.flush()
        v = review.new_version(db, d, f"Draft {i}: trusted by 80,000 customers.", author, "bulk")
        review.run_review(db, v, author, use_ai=False)
    db.commit()
    t0 = time.perf_counter()
    _, ev = governance.supersede_fact(db, f12, {"value_num": 95000}, admin, "perf")
    db.commit()
    elapsed = time.perf_counter() - t0
    assert len(ev.affected["drafts"]) == 502  # 500 bulk + 2 seeded drafts
    assert elapsed < 2.0, elapsed


def test_health_samples_and_eval(client):
    assert client.get("/api/health").json()["ok"]
    assert {s["key"] for s in client.get("/api/samples").json()} == {"launch_post", "festive_offer", "near_miss"}
    assert client.get("/api/samples/launch_post.docx").status_code == 200
    rahul = login(client, "rahul")
    r = client.post("/api/eval/run", headers=rahul).json()
    assert r["drafts"] == 50 and r["severity"]["critical"]["recall"] >= 0.9
    assert "pipeline_rules" in client.get("/api/eval", headers=rahul).json()


def test_seed_starts_with_one_real_blast_radius_example(client):
    meera = login(client, "meera")
    overview = client.get("/api/blast-radius", headers=meera).json()
    assert len(overview["events"]) == 1
    ev = overview["events"][0]
    assert ev["old_fact"]["label"] == "F-13 v1" and ev["new_fact"]["label"] == "F-13 v2"
    assert [d["title"] for d in ev["affected"]["drafts"]] == ["Merchant onboarding blog intro"]
    assert len(ev["affected"]["signoffs"]) == 1
    assert [d["title"] for d in overview["flagged_drafts"]] == ["Merchant onboarding blog intro"]
    # Re-review explains the flag: 10,000 is now contradicted by F-13 v2, and the fix offers 12,000.
    blog = next(d for d in client.get("/api/drafts", headers=meera).json() if d["title"].startswith("Merchant"))
    assert blog["status"] == "needs_renewal"
    client.post(f"/api/drafts/{blog['id']}/review", headers=meera)
    f = next(x for x in client.get(f"/api/drafts/{blog['id']}", headers=meera).json()["version"]["findings"]
             if x["outcome"] == "contradicted")
    assert f["fact"]["label"] == "F-13 v2" and f["suggestion"] == "12,000 merchants"


def test_reset_restores_seed_in_one_transaction(client, monkeypatch):
    rahul, priya = login(client, "rahul"), login(client, "priya")
    create(client, priya, text="Trusted by 50,000 customers.")
    assert len(client.get("/api/drafts", headers=rahul).json()) == 4

    # A reset that fails part-way leaves the existing data untouched.
    import app.seed as seed_module

    def broken_seed(db, with_drafts=True):
        raise RuntimeError("simulated crash mid-reset")

    monkeypatch.setattr(seed_module, "seed", broken_seed)
    r = client.post("/api/admin/reset", headers=rahul)
    assert r.status_code == 500 and "unchanged" in r.json()["detail"]
    assert len(client.get("/api/drafts", headers=rahul).json()) == 4
    monkeypatch.undo()

    # A real reset restores exactly the seeded state, and the existing login still works.
    assert client.post("/api/admin/reset", headers=rahul).json() == {"ok": True}
    drafts = client.get("/api/drafts", headers=rahul).json()
    assert sorted(d["title"] for d in drafts) == ["Diwali festive email", "Instagram caption: city launch",
                                                   "Merchant onboarding blog intro"]
    assert len(client.get("/api/blast-radius", headers=rahul).json()["events"]) == 1
    assert client.get("/api/auth/me", headers=rahul).json()["email"] == "rahul@nimbuspay.example"
