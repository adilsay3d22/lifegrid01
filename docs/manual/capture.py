"""Capture user-manual screenshots by driving the real app (Playwright + installed Edge).

Run with the API on :8100 (fresh seeded DB), the live web app on :5175 and the demo-mode web app on :5176.
Screenshots go to docs/manual/img/<name>.png. Re-run after UI changes, then `python build.py`.
"""

import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pyotp
from playwright.sync_api import Browser, Page, sync_playwright

LIVE, MOCK = "http://localhost:5175", "http://localhost:5176"
IMG = Path(__file__).parent / "img"
IMG.mkdir(exist_ok=True)
TOTP = "LIFEGRIDDEMOSECRETKEYAAAAAAAAAAA"
DESKTOP = {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 1.5}
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2.5, "is_mobile": True, "has_touch": True}
done: list[str] = []


def settle(p: Page, ms: int = 900) -> None:
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(ms)


def shot(p: Page, name: str, *, el: str | None = None, full: bool = False, ms: int = 900) -> None:
    settle(p, ms)
    path = IMG / f"{name}.png"
    if el:
        p.locator(el).first.screenshot(path=path)
    elif full:
        # Stitched full-page shots repeat sticky bars mid-page; flatten them for the capture only.
        tag = p.add_style_tag(content=".sticky{position:static!important}.fixed.bottom-0{position:static!important;width:100%!important;max-width:none!important}")
        p.screenshot(path=path, full_page=True)
        tag.evaluate("t => t.remove()")
    else:
        p.screenshot(path=path)
    done.append(name)
    print("captured", name, flush=True)


def ctx(b: Browser, kind: dict) -> Page:  # type: ignore[type-arg]
    return b.new_context(**kind, reduced_motion="reduce", locale="en-GB", timezone_id="Asia/Dhaka").new_page()


def staff_login(p: Page, base: str, who: str, totp: bool = False, capture: str | None = None) -> None:
    p.goto(f"{base}/staff/login")
    settle(p)
    p.locator("details summary").click()
    p.locator("details button", has_text=who).click()
    if capture:
        shot(p, capture)
    p.get_by_role("button", name=re.compile("^Sign in")).click()
    if totp:
        p.wait_for_selector("input[name=totp]")
        if capture:
            shot(p, capture + "-totp")
        p.fill("input[name=totp]", pyotp.TOTP(TOTP).now() if base == LIVE else "123456")
        p.get_by_role("button", name="Verify and continue").click()
    p.wait_for_url(re.compile(r"/staff(?!/login)"))
    settle(p)


def phone_login(p: Page, role: str, phone: str, capture: bool = False) -> None:
    p.goto(f"{LIVE}/app")
    settle(p)
    p.get_by_role("button", name=re.compile("I want to donate" if role == "donor" else "I need blood")).click()
    p.fill("input[type=tel]", phone)
    if capture:
        shot(p, "app-phone")
    p.get_by_role("button", name="Send code").click()
    code_btn = p.locator("p", has_text="Development code").locator("button")
    code_btn.wait_for()
    code_btn.click()
    if capture:
        shot(p, "app-code")
    p.get_by_role("button", name="Continue").click()
    p.wait_for_url(re.compile(r"/app/(donor|requests|register)"))
    settle(p)


def go(p: Page, path: str, base: str = LIVE) -> None:
    p.goto(base + path)
    settle(p)


def api(p: Page, method: str, path: str, body: object | None = None) -> object:
    """Call the API with the page's session (used only to set up data the screens then show)."""
    return p.evaluate("""async ([m, u, b]) => {
        const r = await fetch('/api/v1/auth/refresh', {method: 'POST'}); const t = (await r.json()).access_token;
        const res = await fetch('/api/v1' + u, {method: m, headers: {'Authorization': 'Bearer ' + t, 'Content-Type': 'application/json'},
                                               body: b ? JSON.stringify(b) : undefined});
        return res.status === 204 ? null : await res.json(); }""", [method, path, body])


BACKEND = Path(__file__).resolve().parents[2] / "backend"
PY = BACKEND / ".venv" / "Scripts" / "python.exe"


def fresh_api() -> subprocess.Popen[bytes]:
    """Seed a new SQLite database and serve it on :8100, so every capture run starts from the same data."""
    db = BACKEND / "manual.db"
    db.unlink(missing_ok=True)
    env = {**os.environ, "DATABASE_URL": "sqlite:///./manual.db", "ENV": "dev", "CELERY_ALWAYS_EAGER": "true"}
    subprocess.run([str(PY), "-m", "simulation", "seed", "--create-schema"], cwd=BACKEND, env=env, check=True, capture_output=True)
    proc = subprocess.Popen([str(PY), "-m", "uvicorn", "app.main:app", "--port", "8100"], cwd=BACKEND, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen("http://localhost:8100/api/v1/healthz")
            return proc
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("API did not start")


def main() -> None:
    api_proc = fresh_api()
    try:
        run()
    finally:
        api_proc.terminate()


def run() -> None:
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge", headless=True)

        # ---------- getting started ----------
        ph = ctx(b, PHONE)
        go(ph, "/app")
        shot(ph, "app-welcome")
        st = ctx(b, DESKTOP)
        go(st, "/staff/login")
        shot(st, "staff-login")

        # ---------- bank manager ----------
        staff_login(st, LIVE, "nabila", capture="staff-login-demo")
        shot(st, "overview", full=True)
        shot(st, "overview-lowstock", el="section[aria-labelledby=low-h]")
        shot(st, "overview-matrix", el="section[aria-labelledby=matrix-h]")
        st.locator("section[aria-labelledby=low-h] li", has=st.get_by_role("button", name="Appeal to donors")).first \
            .get_by_role("button", name="Appeal to donors").click()
        shot(st, "appeal-dialog", el="dialog[open]")
        st.locator("dialog[open]").get_by_role("button", name="Send appeal").click()
        st.wait_for_selector("dialog[open] [role=status]")
        shot(st, "appeal-sent", el="dialog[open]")
        st.locator("dialog[open]").get_by_role("button", name="Done").click()

        sites = api(st, "GET", "/sites")
        bank = next(s for s in sites if s["type"] == "blood_bank")  # type: ignore[index]
        south = next(s for s in sites if s["code"] == "H-01")  # type: ignore[index]
        go(st, f"/staff/sites/{bank['id']}/stock")
        shot(st, "stock")
        boxes = st.locator("tbody input[type=checkbox]")
        boxes.nth(0).check()
        boxes.nth(1).check()
        shot(st, "stock-bulk")
        st.locator(".sticky.bottom-4").get_by_role("button", name="Quarantine").click()
        st.locator("dialog[open] textarea").fill("Fridge 2 temperature alarm at 06:10")
        shot(st, "stock-quarantine", el="dialog[open]")
        st.locator("dialog[open] .justify-end").get_by_role("button", name=re.compile("^Quarantine")).click()
        settle(st)
        st.get_by_role("button", name="Receive unit").click()
        st.fill("dialog[open] input[name=unit_code]", "LG26-9900001")
        shot(st, "stock-receive", el="dialog[open]")
        st.locator("dialog[open]").get_by_role("button", name="Cancel").click()
        st.get_by_role("button", name="Import CSV").click()
        st.locator("dialog[open] textarea").fill(
            "unit_code,abo,rh,component,collected_at,expires_at\n"
            "LG26-9900011,O,pos,red_cells,2026-09-28T08:00:00Z,2026-11-09T08:00:00Z\n"
            "LG26-9900012,Q,pos,red_cells,2026-09-28T08:00:00Z,2026-11-09T08:00:00Z\n"
            "LG26-9900013,A,neg,plasma,2026-09-28T08:00:00Z,2026-09-01T08:00:00Z\n")
        shot(st, "stock-import", el="dialog[open]")
        st.locator("dialog[open] .justify-end").get_by_role("button", name="Import").click()
        st.wait_for_selector("dialog[open] table")
        shot(st, "stock-import-result", el="dialog[open]")
        st.locator("dialog[open]").get_by_role("button", name="Done").click()
        go(st, f"/staff/sites/{bank['id']}/stock?status=quarantined")
        st.locator("tbody a").first.click()
        shot(st, "unit-detail")

        go(st, f"/staff/forecasts?site={south['id']}")
        shot(st, "forecasts")

        go(st, "/staff/plans")
        shot(st, "plan")
        row = st.locator("main ul > li").first
        row.locator("input[type=number]").fill("2")
        row.get_by_role("button", name="Approve").click()
        shot(st, "plan-approve", el="dialog[open]")
        st.locator("dialog[open]").get_by_role("button", name="Approve").click()
        settle(st)
        go(st, "/staff/transfers")
        shot(st, "transfers")
        st.locator("main ul > li").first.get_by_role("button", name="Dispatch").click()
        st.wait_for_selector("dialog[open] ol li")
        shot(st, "transfer-dispatch", el="dialog[open]")
        st.locator("dialog[open] .justify-end").get_by_role("button", name=re.compile("^Dispatch")).click()
        settle(st)
        go(st, "/staff/transfers?tab=dispatched")
        shot(st, "transfers-in-transit")
        # appeal at Southfield for O+ so the demo donor (lives near Southfield) gets an invitation
        api(st, "POST", "/appeals", {"site_id": south["id"], "abo": "O", "rh": "pos", "units": 3, "urgency": "urgent"})

        # ---------- requester (phone) ----------
        rq = ctx(b, PHONE)
        phone_login(rq, "requester", "+8801000009999", capture=True)
        shot(rq, "requester-empty")
        go(rq, "/app/requests/new")
        rq.locator("input[name=group][value=Bpos]").check(force=True)
        hosp = rq.locator("select[name=site_id]")
        hosp.select_option(label=south["name"])
        rq.fill("input[name=units_needed]", "4")
        rq.locator("input[name=urgency][value=urgent]").check(force=True)
        rq.fill("input[name=needed_by]", "2026-12-01T18:00")
        shot(rq, "requester-new", full=True)
        rq.get_by_role("button", name="Submit request").click()
        rq.wait_for_url(re.compile(r"/app/requests/[0-9a-f-]{36}"))
        shot(rq, "requester-status", full=True)

        # ---------- hospital lead ----------
        ld = ctx(b, DESKTOP)
        staff_login(ld, LIVE, "tanvir")
        shot(ld, "lead-stock")
        go(ld, "/staff/requests")
        shot(ld, "lead-requests", full=True)
        ld.locator("section[aria-labelledby=confirm-h] button").first.click()
        shot(ld, "lead-request-dialog", el="dialog[open]")
        ld.locator("dialog[open]").get_by_role("button", name="Confirm request").click()
        ld.wait_for_selector("dialog[open] [role=status]")
        shot(ld, "lead-request-confirmed", el="dialog[open]")
        ld.locator("dialog[open]").get_by_role("button", name="Close").click()
        go(rq, rq.url.replace(LIVE, ""))
        shot(rq, "requester-status-confirmed", full=True)
        go(rq, "/app/requests")
        shot(rq, "requester-list")

        # ---------- donor (phone) ----------
        dn = ctx(b, PHONE)
        phone_login(dn, "donor", "+8801000000001")
        shot(dn, "donor-home", full=True)
        go(dn, "/app/invitations")
        shot(dn, "donor-invitations")
        dn.get_by_role("button", name="I can donate").first.click()
        settle(dn)
        shot(dn, "donor-accepted")
        dn.get_by_role("link", name="Open messages").first.click()
        settle(dn)
        dn.fill("textarea", "Hello, I can come to the hospital at 4 pm today.")
        dn.locator("form button[type=submit]").click()
        shot(dn, "donor-chat")
        go(dn, "/app/privacy")
        shot(dn, "donor-privacy", full=True)
        dn.get_by_role("button", name="Delete my data").click()
        shot(dn, "donor-delete-dialog")
        dn.locator("dialog[open]").get_by_role("button", name="Cancel").click()

        # new donor registration
        nd = ctx(b, PHONE)
        phone_login(nd, "donor", "+8801000004242")
        nd.wait_for_url(re.compile("/app/register"))
        settle(nd, 1500)
        shot(nd, "register-empty", full=True)
        nd.locator("input[name=group][value=Aneg]").check(force=True)
        nd.locator(".leaflet-container").click(position={"x": 190, "y": 100})
        nd.fill("input[autocomplete=bday-year]", "1996")
        for c in nd.locator("input[type=checkbox]").all():
            c.check()
        shot(nd, "register-filled", full=True, ms=1500)
        nd.get_by_role("button", name="Save and continue").click()
        nd.wait_for_url(re.compile("/app/donor"))
        shot(nd, "register-done", full=True)

        # ---------- staff side of the appeal: reply and outcome ----------
        go(st, "/staff/requests")
        shot(st, "manager-requests", full=True)
        st.locator("section[aria-labelledby=list-h] li button", has_text="AP-").first.click()
        st.wait_for_selector("dialog[open]")
        settle(st, 1500)
        shot(st, "appeal-request-dialog", el="dialog[open]")
        st.locator("dialog[open]").get_by_role("button", name="Message").first.click()
        st.locator("dialog[open] >> nth=-1").locator("input").fill("Thank you! The donation desk is on the ground floor.")
        st.locator("dialog[open] >> nth=-1").get_by_role("button", name="Send message").click()
        shot(st, "staff-chat", el="dialog[open] >> nth=-1", ms=1500)

        co = ctx(b, DESKTOP)
        staff_login(co, LIVE, "imran")
        shot(co, "coordinator-donors")
        co.locator("tbody tr").first.get_by_role("button", name="Defer").click()
        co.fill("dialog[open] input[type=date]", "2026-12-15")
        shot(co, "coordinator-deferral", el="dialog[open]")
        co.locator("dialog[open]").get_by_role("button", name="Cancel").click()
        go(co, "/staff/requests")
        co.locator("section[aria-labelledby=list-h] li button", has_text="AP-").first.click()
        co.wait_for_selector("dialog[open]")
        settle(co, 1500)
        shot(co, "coordinator-outcome", el="dialog[open]")

        # ---------- admin ----------
        ad = ctx(b, DESKTOP)
        staff_login(ad, LIVE, "sadia", totp=True, capture="admin-login")
        go(ad, "/staff/admin")
        shot(ad, "admin-users")
        go(ad, "/staff/admin?tab=sites")
        shot(ad, "admin-sites")
        go(ad, "/staff/admin?tab=settings")
        ad.fill("#set-solver_time_limit_s", "45")
        ad.locator("#set-solver_time_limit_s").locator("xpath=ancestor::tr").get_by_role("button", name="Save").click()
        shot(ad, "admin-settings", ms=1500)
        go(ad, "/staff/admin?tab=rules")
        shot(ad, "admin-rules", full=True)
        go(ad, "/staff/audit")
        ad.get_by_role("button", name="Verify chain").click()
        shot(ad, "audit", ms=1500)

        # ---------- phase 7 previews (demo mode) and small screens ----------
        mk = ctx(b, DESKTOP)
        staff_login(mk, MOCK, "nabila", totp=True)
        go(mk, "/staff/alerts", MOCK)
        shot(mk, "alerts")
        go(mk, "/staff/reports", MOCK)
        shot(mk, "reports", full=True)
        sm = ctx(b, PHONE)
        staff_login(sm, LIVE, "nabila")
        sm.get_by_role("button", name="Open menu").click()
        shot(sm, "staff-mobile-menu")
        b.close()
    print(f"{len(done)} screenshots")


if __name__ == "__main__":
    sys.exit(main())
