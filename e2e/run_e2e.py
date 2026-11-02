"""End-to-end browser test: the main journeys plus what an impatient user does (refresh, double-click, bad input).

Needs the API and the website running (see the README), then:

    pip install -r e2e/requirements.txt && playwright install chromium
    python e2e/run_e2e.py

It resets the demo data before and after, so it refuses to run against anything but localhost unless you pass
--live. Exits non-zero if any check fails. Set LOCAL_LLM_ENABLED=false on the API for faster reviews.
"""

import io
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import expect, sync_playwright

WEB = os.environ.get("WEB", "http://localhost:3000").rstrip("/")
API = os.environ.get("API", "http://localhost:8000").rstrip("/")
if "--live" not in sys.argv and not ("localhost" in WEB and "localhost" in API):
    sys.exit("This test resets the demo data. Pass --live to run it against a deployed site.")

TMP = Path(tempfile.mkdtemp(prefix="bs-e2e-"))
TIMEOUT = 180_000  # reviews with a local model can take a minute
expect.set_options(timeout=30_000)
failures: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("  ok    " if ok else "  FAIL  ") + what, flush=True)
    if not ok:
        failures.append(what)


def section(title: str) -> None:
    print(f"\n{title}", flush=True)


def api_post(path: str, body: dict | None = None, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(API + path, data=json.dumps(body or {}).encode(), headers=headers)
    return json.load(urllib.request.urlopen(req, timeout=180))


def reset_demo() -> None:
    token = api_post("/api/auth/login", {"email": "rahul@nimbuspay.example", "password": "demo1234"})["token"]
    api_post("/api/admin/reset", token=token)


def fetch_file(path: str, name: str) -> Path:
    target = TMP / name
    urllib.request.urlretrieve(API + path, target)
    return target


with sync_playwright() as p:
    reset_demo()
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, permissions=["clipboard-read", "clipboard-write"])
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda e: page_errors.append(str(e)))

    def sign_in(name: str) -> None:
        page.goto(WEB + "/login")
        page.evaluate("localStorage.clear()")
        page.goto(WEB + "/login")
        page.get_by_role("button", name=re.compile(name)).click()
        page.wait_for_url(WEB + "/")
        expect(page.locator("header")).to_contain_text(name)

    def shows(text, timeout=20_000) -> bool:
        try:
            expect(page.get_by_text(text).first).to_be_visible(timeout=timeout)
            return True
        except AssertionError:
            return False

    def appears(locator, timeout=20_000) -> bool:
        try:
            expect(locator.first).to_be_visible(timeout=timeout)
            return True
        except AssertionError:
            return False

    section("First visit, no walkthrough")
    page.goto(WEB)
    page.wait_for_url("**/login")
    check(shows("Priya Shah"), "signed-out visitor lands on a page listing who to continue as")
    sign_in("Arjun Rao")
    check(shows("Try the end-to-end story"), "dashboard shows the guide")
    check(shows("Instagram story: Diwali offer") and shows("blocking"), "a seeded draft with detected issues is visible")

    section("Journey 1: check, correct, sign off, change a fact")
    page.get_by_role("button", name="Go").first.click()  # guide step 1 pre-fills the launch post
    page.wait_for_url("**/drafts/new?sample=launch_post")
    expect(page.get_by_label("Draft text")).to_have_value(re.compile("50,000 customers"))
    page.get_by_role("tab", name="Upload a file").click()
    page.locator("input[type=file]").set_input_files(str(fetch_file("/api/samples/launch_post.docx", "launch_post.docx")))
    page.get_by_role("button", name="Check draft").click()
    page.wait_for_url(re.compile(r"/drafts/\d+$"))
    draft_url = page.url
    check(shows("Contradicted", TIMEOUT) and shows("Unverified"), "Word upload: count Contradicted, ranking Unverified")
    check(shows(re.compile("Supported by F-13")), "supported claim cites its fact")

    page.get_by_role("button", name="▸ Evidence chain").nth(1).click()
    check(shows("BrandSentinel evidence receipt"), "evidence chain opens")
    page.get_by_role("button", name="Copy receipt").click()
    check(shows("Copied"), "receipt copies")
    receipt = page.evaluate("navigator.clipboard.readText()")
    check("F-12 v3" in receipt and "source:" not in receipt, "agency receipt cites the fact but no internal source")

    count = page.get_by_role("button", name="Accept fix").count()
    for i in range(count):
        page.get_by_role("button", name="Accept fix").first.click()
        expect(page.get_by_role("button", name="Accept fix")).to_have_count(count - i - 1)
    check(shows(re.compile("Preview of v2 with all 2 accepted fixes")), "combined preview of both fixes")
    check(shows("not in the text yet"), "accepted fixes are shown as not applied yet")
    page.get_by_role("button", name=re.compile("Apply 2 accepted fix")).click()
    expect(page.get_by_role("button", name="v2", exact=True)).to_be_visible(timeout=TIMEOUT)
    check(shows("No open issues on this version.", TIMEOUT), "v2 re-reviewed with no open issues")
    check(appears(page.locator("mark", has_text="80,000 customers"), TIMEOUT), "v2 contains the corrected figure")

    sign_in("Meera Iyer")
    page.goto(draft_url)
    page.get_by_role("button", name="Show changes from v1").click()
    check(appears(page.locator("ins").filter(has_text="80,000")), "manager sees the word-level diff")
    page.get_by_role("button", name="Hide changes").click()
    page.get_by_role("button", name="Sign off v2").click()
    check(shows(re.compile("facts F-12 v3, F-13 v2")), "sign-off records the fact versions")
    check(shows("is signed off. Any edit creates a new version") and page.get_by_role("button", name="Sign off v2").count() == 0, "cannot sign off the same version again")

    sign_in("Rahul Verma")
    page.goto(WEB + "/ledger?fact=F-12")
    page.locator("#fact-F-12").get_by_role("button", name="Change or retract…").click()
    page.locator("input[type=number]").fill("-5")
    page.get_by_role("button", name="Preview impact").click()
    check(shows("The value cannot be negative."), "impossible value is refused with a clear message")
    page.locator("input[type=number]").fill("95000")
    page.get_by_role("button", name="Preview impact").click()
    check(shows("Simulation · not applied") and shows(re.compile(r"3\s*draft\(s\) would be flagged")), "simulator lists the impact")
    check(shows("← changes"), "simulator marks the claims whose outcome would change")
    other = context.new_page()
    other.goto(WEB + "/ledger?fact=F-12")
    try:
        expect(other.locator("#fact-F-12")).to_contain_text("v3 ·")
        check(True, "the preview changed nothing (F-12 is still v3)")
    except AssertionError:
        check(False, "the preview changed nothing (F-12 is still v3)")
    other.close()
    page.get_by_role("button", name=re.compile("Confirm: approve F-12 v4")).click()
    check(shows(re.compile(r"3 draft\(s\) flagged for re-review and 2 sign-off\(s\)")), "confirming applies blast radius")
    page.goto(draft_url)
    check(shows(re.compile("Blast radius:.*F-12 changed")), "the draft explains why it was flagged")
    page.get_by_role("button", name="Re-run review against current ledger").click()
    check(shows(re.compile("gives active customers as 95,000"), TIMEOUT), "re-review contradicts the old figure")
    expect(page.get_by_role("button", name="Re-run review against current ledger")).to_have_count(0, timeout=TIMEOUT)
    page.get_by_role("button", name="v1", exact=True).click()
    check(shows("Evidence out of date"), "an older version marks its evidence as out of date")

    section("Journey 2: rules, radar, sensitivity")
    page.goto(WEB + "/rules?rule=R-09")
    page.locator("#rule-R-09").locator("xpath=..").get_by_role("button", name="Edit rule").click()
    check(page.get_by_role("button", name="Save as a new rulebook version").is_disabled(), "a rule cannot be saved before previewing")
    page.get_by_label(re.compile("Palette colours")).fill("#XYZ")
    page.get_by_role("button", name="Preview impact").click()
    check(shows("Palette colours must be hex values"), "invalid palette colour is refused")
    page.goto(WEB + "/radar")
    for text in ["Act on these", "Open risk now", "Fact freshness", "Recurring findings", "Reviewer disagreement"]:
        check(shows(text), f"radar shows: {text}")
    page.get_by_role("tab", name="All time").click()
    check(shows(re.compile(r"\d+ of \d+")), "radar counts show their denominators")
    page.get_by_role("link", name="Open →").first.click()
    page.wait_for_url(re.compile(r"/(drafts|ledger|rules)"))
    check(True, "radar actions lead somewhere")
    page.goto(WEB + "/ledger")
    page.get_by_label("Sensitivity of F-16").select_option("internal")
    expect(page.get_by_label("Sensitivity of F-16")).to_have_value("internal")
    page.get_by_label("Sensitivity of F-16").select_option("public")
    check(True, "sensitivity can be changed")

    section("Journey 3: images")
    sign_in("Arjun Rao")
    page.goto(WEB + "/drafts/new")
    page.get_by_role("button", name="Use file").first.click()
    check(shows("Using festive_banner.png"), "sample image loads with one click")
    page.get_by_role("button", name="Check draft").click()
    page.wait_for_url(re.compile(r"/drafts/\d+$"))
    check(shows("Images in this draft (1)", TIMEOUT), "image panel appears")
    check(shows("Read from image 1 by OCR"), "claims inside the image are found")
    check(shows(re.compile(r"Text contrast 1\.\d+:1 is below WCAG AA")), "low contrast is measured")
    check(shows("off-palette"), "off-palette colour is flagged")
    page.get_by_role("button", name="Edit text").click()
    area = page.get_by_label("Draft text")
    area.fill(area.input_value().replace("50,000", "80,000"))
    page.get_by_role("button", name=re.compile("Save as v2")).click()
    check(shows("Text read from an image cannot be edited"), "image text cannot be edited away")
    page.get_by_role("button", name="Cancel").click()
    page.locator('input[type="file"]').set_input_files(str(fetch_file("/api/sample-files/banner_post.docx", "post.docx")))
    expect(page.get_by_role("button", name="v2", exact=True)).to_be_visible(timeout=TIMEOUT)
    check(shows("Picture in the Word file", TIMEOUT), "a corrected file can be uploaded as a new version")

    section("Bad input")
    page.goto(WEB + "/drafts/new")
    check(page.get_by_role("button", name="Check draft").is_disabled(), "empty form cannot be submitted")
    page.get_by_placeholder("LinkedIn launch post").fill("Bad input")
    page.get_by_label("Draft text").fill("     ")
    check(page.get_by_role("button", name="Check draft").is_disabled(), "whitespace-only text cannot be submitted")
    page.get_by_role("tab", name="Check a web page").click()
    page.get_by_placeholder("https://example.com/offer-page").fill("http://127.0.0.1:8000/")
    page.get_by_role("button", name="Check draft").click()
    check(shows("Only public web pages"), "private web address is refused")
    page.get_by_role("tab", name="Upload a file").click()
    bad = TMP / "bad.docx"
    bad.write_bytes(b"not a document")
    page.locator("input[type=file]").set_input_files(str(bad))
    page.get_by_role("button", name="Check draft").click()
    check(shows("Could not read"), "corrupt Word file gets a clear message")
    check(page.get_by_role("button", name="Check draft").is_enabled(), "the form is usable again after an error")
    buf = io.BytesIO()
    Image.new("RGB", (6000, 6000), "white").save(buf, "PNG")
    big = TMP / "huge.png"
    big.write_bytes(buf.getvalue())
    page.locator("input[type=file]").set_input_files(str(big))
    page.get_by_role("button", name="Check draft").click()
    check(shows("The image is too large"), "oversized image is refused")

    section("Refresh, double-click, wrong addresses, roles")
    for path, text in [("/", "My drafts"), ("/ledger", "Brand Truth Ledger"), ("/rules", "Rulebook"), ("/drafts/new", "Check a new draft")]:
        page.goto(WEB + path)
        page.reload()
        check(shows(text), f"refreshing {path} keeps working")
    page.goto(WEB + "/drafts/99999")
    check(shows("Draft not found") and shows("Back to drafts"), "missing draft: message and a way back")
    page.goto(WEB + "/drafts/abc")
    check(shows("Draft not found"), "nonsense draft address: readable message")
    page.goto(WEB + "/nonsense")
    check(shows("Page not found") and shows("Back to drafts"), "unknown page: message and a way back")
    for path in ["/radar", "/blast", "/audit", "/insights"]:
        page.goto(WEB + path)
        check(shows(re.compile("This action needs the .* role")), f"{path} explains the role limit to a creator")

    page.goto(WEB + "/drafts/new")
    page.get_by_placeholder("LinkedIn launch post").fill("Double click")
    page.get_by_label("Draft text").fill("Trusted by 50,000 customers.")
    page.get_by_role("button", name="Check draft").dblclick()
    page.wait_for_url(re.compile(r"/drafts/\d+$"))
    url = page.url
    page.reload()
    check(shows("Contradicted", TIMEOUT), "refreshing straight after submitting still shows the review")
    page.goto(WEB + "/")
    expect(page.get_by_role("link", name="Double click").first).to_be_visible(timeout=TIMEOUT)  # the list loads slowly on a small server
    copies = page.get_by_role("link", name="Double click").count()
    check(copies == 1, f"double-clicking Check draft creates one draft ({copies} found)")
    page.goto(url)
    page.get_by_role("button", name="Accept fix").first.dblclick()
    expect(page.get_by_role("button", name=re.compile("Apply 1 accepted"))).to_be_visible()
    page.get_by_role("button", name=re.compile("Apply 1 accepted")).dblclick()
    expect(page.get_by_role("button", name=re.compile(r"^v2$"))).to_be_visible(timeout=TIMEOUT)
    check(shows("No open issues on this version.", TIMEOUT), "the new version finishes its review")
    check(page.get_by_role("button", name=re.compile(r"^v\d+$")).count() == 2, "double-clicking Apply creates one version")

    section("Manager decisions and expired sessions")
    sign_in("Meera Iyer")
    page.get_by_role("link", name="Website hero banner").click()
    check(shows("blocking finding(s) are open"), "manager sees why sign-off is blocked")
    page.get_by_role("button", name="Sign off v1").click()
    check(shows("still open"), "signing off without reasons gets a clear error")
    page.get_by_placeholder(re.compile("Comment")).fill("Please correct the figures.")
    page.get_by_role("button", name="Request changes").click()
    check(shows(re.compile("Changes requested by Meera Iyer")), "the decision and reason are shown on the draft")
    page.goto(WEB + "/")
    page.evaluate("localStorage.setItem('bs_token','expired')")
    page.wait_for_url("**/login", timeout=20_000)  # the dashboard refreshes itself and notices
    check(True, "an expired session returns to sign-in")

    section("Phone width")
    phone = browser.new_page(viewport={"width": 390, "height": 844})
    phone.goto(WEB + "/login")
    phone.get_by_role("button", name=re.compile("Meera Iyer")).click()
    phone.wait_for_url(WEB + "/")
    for path in ["/", "/radar", "/ledger", "/rules", "/blast", "/audit", "/insights", url.replace(WEB, "")]:
        phone.goto(WEB + path)
        phone.wait_for_timeout(1000)
        width = phone.evaluate("document.documentElement.scrollWidth")
        check(width <= 400, f"{path} fits a phone screen (width {width})")
    browser.close()

reset_demo()
check(not page_errors, f"no JavaScript errors {page_errors[:2] if page_errors else ''}")
print(f"\n{'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' FAILED: ' + '; '.join(failures)}")
sys.exit(1 if failures else 0)
