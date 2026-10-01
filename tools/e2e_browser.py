"""Browser end-to-end check of the dashboard, against the Pi or the AWS relay.

Drives a real Chrome through Playwright: signs in, walks Live / Reports / Savings /
FESCO Bill / Readings, and verifies live pushes, the relay socket, data loads on every
tab, a CSRF-protected POST, the CSV export, the theme toggle, phone-width layout and
sign-out. Screenshots land in the output directory.

    pip install playwright            # Chrome itself is used via channel="chrome"
    BASE=http://192.168.18.130:5000 E2E_USER=admin E2E_PASS=... python tools/e2e_browser.py shots-pi
    BASE=https://<id>.execute-api.ap-south-1.amazonaws.com E2E_USER=admin E2E_PASS=... python tools/e2e_browser.py shots-aws

Prints one PASS/FAIL line per check; exits 1 if any check failed.
"""
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ["BASE"].rstrip("/")
USER = os.environ.get("E2E_USER", "admin")
PASS = os.environ["E2E_PASS"]
SHOTS = sys.argv[1] if len(sys.argv) > 1 else "shots"
os.makedirs(SHOTS, exist_ok=True)
RELAY = "execute-api" in BASE

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def scrub(s):
    return str(s).replace(PASS, "<pw>")


def goto(page, url, wait_until="networkidle", tries=4):
    """page.goto with retries: this Mac's network flaps (ERR_NETWORK_CHANGED) mid-run."""
    for i in range(tries):
        try:
            return page.goto(url, wait_until=wait_until, timeout=60000)
        except Exception as e:  # noqa: BLE001
            transient = "net::ERR_" in str(e) or "Timeout" in str(e)
            if i == tries - 1 or not transient:
                raise
            print(f"  (retrying {url.split('/')[-1] or '/'} after {str(e).splitlines()[0][:60]})", flush=True)
            time.sleep(4)
    return None

PAGES = [("/", "solar_flow"), ("/reports", "history"), ("/savings", "savings"),
         ("/fesco-bill", "fesco_bill"), ("/classic", "dashboard")]


def collect(page):
    errors, failed = [], []
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type in ("error",) else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("requestfailed", lambda r: failed.append(f"{r.method} {r.url} -> {r.failure}"))
    page.on("response", lambda r: failed.append(f"{r.request.method} {r.url} -> {r.status}")
            if r.status >= 400 and "/favicon" not in r.url else None)
    return errors, failed


def relay_state(page):
    return page.evaluate("""() => {
        const s = window.relaySocket; if (!s) return null;
        return {connected: s.connected, deviceOnline: s.deviceOnline, ready: s.ws && s.ws.readyState};
    }""")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", timeout=300000)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    errors, failed = collect(page)

    # ---- 1. login page: renders once, no reload loop -------------------------------------
    navs = []
    page.on("framenavigated", lambda f: navs.append(f.url) if f == page.main_frame else None)
    goto(page, BASE + "/login", "networkidle")
    page.wait_for_timeout(6000)
    check("login page stays put for 6 s (no reload loop)", len(navs) == 1, f"navigations={len(navs)}")
    check("login page has form", page.locator("form").count() == 1)
    check("login page has no relay bootstrap", page.evaluate("() => !window.RELAY && !window.relaySocket") if RELAY else True)
    page.screenshot(path=f"{SHOTS}/00-login.png", full_page=True)

    # ---- 2. protected page redirects to login when signed out --------------------------
    goto(page, BASE + "/savings", "domcontentloaded")
    check("signed-out /savings redirects to /login", page.url.startswith(BASE + "/login"), page.url)

    # ---- 3. wrong password shows an error, right password lands on the dashboard -------
    goto(page, BASE + "/login?next=/savings", "networkidle")
    page.fill("input[name=username]", USER)
    page.fill("input[name=password]", "definitely-wrong-password")
    with page.expect_navigation(wait_until="networkidle", timeout=60000):
        page.click("button[type=submit], input[type=submit]")
    check("wrong password stays on login with an error", "/login" in page.url and re.search(r"invalid|incorrect", page.content(), re.I) is not None, page.url)
    page.fill("input[name=username]", USER)
    page.fill("input[name=password]", PASS)
    with page.expect_navigation(wait_until="networkidle", timeout=60000):
        page.click("button[type=submit], input[type=submit]")
    check("login with ?next=/savings lands on /savings", page.url.split("?")[0] == BASE + "/savings", page.url)

    # ---- 4. dashboard (solar flow): relay connects, live updates arrive -------------------
    goto(page, BASE + "/", "networkidle")
    page.wait_for_timeout(1500)
    if RELAY:
        deadline = time.time() + 15
        st = relay_state(page)
        while time.time() < deadline and not (st and st["connected"]):
            page.wait_for_timeout(500); st = relay_state(page)
        check("relay socket connected", st and st["connected"], json.dumps(st))
        check("relay says device (Pi) online", st and st["deviceOnline"], json.dumps(st))
    # count inverter_update events over 6 s via the page's own socket
    n = page.evaluate("""() => new Promise(res => {
        let n = 0; const s = window.io();
        const h = () => n++; s.on('inverter_update', h);
        setTimeout(() => { s.off && s.off('inverter_update', h); res(n); }, 6000);
    })""")
    check("live inverter_update pushes arrive (expect ~1/s)", n >= 3, f"{n} in 6 s")
    vals = page.evaluate("""() => ({
        solar: document.getElementById('solar-power')?.textContent.trim(),
        load: document.getElementById('load-power')?.textContent.trim(),
        batt: document.getElementById('battery-percentage')?.textContent.trim(),
        grid: document.getElementById('grid-voltage')?.textContent.trim(),
        mode: document.getElementById('mode-pill-label')?.textContent.trim(),
        conn: document.getElementById('connection-status')?.textContent.trim(),
        last: document.getElementById('last-update')?.textContent.trim(),
        todaySolar: document.getElementById('today-solar')?.textContent.trim(),
        svToday: document.getElementById('sv-today')?.textContent.trim(),
    })""")
    check("dashboard tiles show numbers", all(v and v not in ("--", "—", "-", "0 W", "") for v in (vals["solar"], vals["load"], vals["batt"], vals["grid"])), json.dumps(vals))
    check("today energy + savings strip populated", vals["todaySolar"] not in (None, "", "--", "—") and vals["svToday"] not in (None, "", "--", "—"), f"{vals['todaySolar']} / {vals['svToday']}")
    chart_ok = page.evaluate("() => { const c = document.getElementById('live-chart'); return !!c && c.getBoundingClientRect().height > 50; }")
    check("live chart rendered", chart_ok)
    # CSRF-protected POST through the tunnel
    r = page.evaluate("""async () => {
        const meta = document.querySelector('meta[name=csrf-token]');
        const h = {}; if (meta) h['X-CSRFToken'] = meta.content;
        const r = await fetch('/refresh-extras', {method: 'POST', headers: h});
        let body = null; try { body = await r.json(); } catch (e) { body = 'non-json'; }
        return {status: r.status, ok: body && body.success !== undefined ? body.success : body};
    }""")
    check("POST /refresh-extras (CSRF) succeeds", r["status"] == 200 and r["ok"] not in (False, "non-json"), json.dumps(r))
    page.screenshot(path=f"{SHOTS}/01-dashboard.png", full_page=True)
    # light theme via the nav toggle, then back
    page.click("[data-theme-toggle]"); page.wait_for_timeout(800)
    check("theme toggle switches to light", page.evaluate("() => document.documentElement.getAttribute('data-theme') === 'light'"))
    page.screenshot(path=f"{SHOTS}/01b-dashboard-light.png", full_page=True)
    page.click("[data-theme-toggle]"); page.wait_for_timeout(300)
    # component sheet opens on tap
    page.click("#battery-component"); page.wait_for_timeout(600)
    sheet = page.evaluate("() => ({open: !document.getElementById('component-modal').classList.contains('hidden'), title: document.querySelector('#component-modal-card .modal-title')?.textContent, choices: document.querySelectorAll('#component-modal-card .choice-btn').length})")
    check("battery sheet opens with charger choices", sheet["open"] and sheet["choices"] >= 3, json.dumps(sheet))
    page.screenshot(path=f"{SHOTS}/01c-battery-sheet.png")
    page.keyboard.press("Escape"); page.wait_for_timeout(400)

    # ---- 5. reports (history): day/month/year/outages/gaps tabs load --------------------
    goto(page, BASE + "/reports", "networkidle")
    page.wait_for_timeout(2500)
    v = page.evaluate("""() => ({
        daySolar: document.getElementById('day-solar-kwh')?.textContent.trim(),
        dayLoad: document.getElementById('day-load-kwh')?.textContent.trim(),
        status: document.getElementById('tab-status')?.textContent.trim(),
        chart: document.getElementById('day-chart')?.getBoundingClientRect().height,
    })""")
    def num(x):
        try: return float(x)
        except (TypeError, ValueError): return 0.0
    check("reports: day tab populated", "Failed" not in (v["status"] or "") and (num(v["daySolar"]) > 0 or num(v["dayLoad"]) > 0) and (v["chart"] or 0) > 50, json.dumps(v))
    for tab, elem in (("month", "mo-solar"), ("year", "yr-solar"), ("outages", "out-count"), ("gaps", None)):
        page.locator(f"[data-tab='{tab}']").click(); page.wait_for_timeout(3000)
        status = page.evaluate("() => document.getElementById('tab-status')?.textContent.trim()") or ""
        txt = page.evaluate(f"() => document.getElementById('{elem}')?.textContent.trim()") if elem else "n/a"
        check(f"reports: {tab} tab populated", "Failed" not in status and txt not in (None, "", "--", "—"), f"{elem}={txt} status={status!r}")
    page.locator("[data-tab='day']").click(); page.wait_for_timeout(2500)
    page.screenshot(path=f"{SHOTS}/02-reports.png", full_page=True)

    # CSV export (goes through relayDownload on AWS)
    page.locator("#day-export-toggle").click()
    page.wait_for_timeout(300)
    with page.expect_download(timeout=120000) as dl:
        page.locator("#day-export-menu button[data-format='csv'][data-bucket='60']").click()
    d = dl.value
    path = d.path()
    size = os.path.getsize(path) if path else 0
    check("reports: CSV export downloads", size > 200, f"{d.suggested_filename} {size} bytes")

    # ---- 6. savings -----------------------------------------------------------------------
    goto(page, BASE + "/savings", "networkidle")
    page.wait_for_timeout(3000)
    v = page.evaluate("""() => ({
        today: document.getElementById('kpi-today')?.textContent.trim(),
        month: document.getElementById('kpi-month')?.textContent.trim(),
        lifetime: document.getElementById('kpi-lifetime')?.textContent.trim(),
        payback: document.getElementById('kpi-payback')?.textContent.trim(),
        rows: document.querySelectorAll('#month-history tr').length,
        tariffRows: document.querySelectorAll('#tariff-check-body tr').length,
        fixMin: document.getElementById('cfg-fix-min')?.value,
    })""")
    check("savings: KPIs populated", all(v[k] not in (None, "", "--", "—") for k in ("today", "month", "lifetime", "payback")), json.dumps(v))
    check("savings: billing-cycle history + tariff check tables filled", v["rows"] >= 1 and v["tariffRows"] >= 1, json.dumps(v))
    # what-if calculator (pure client) and config round-trip (POST + reload)
    page.fill("#whatif-units", "350"); page.click("#whatif-calc"); page.wait_for_timeout(500)
    wi = page.evaluate("() => document.getElementById('whatif-result')?.textContent.trim()")
    check("savings: what-if calculator returns a bill", wi and re.search(r"\d", wi), (wi or "")[:80])
    page.click("#save-config"); page.wait_for_timeout(2500)
    toast = page.evaluate("() => document.getElementById('config-toast')?.textContent.trim()")
    check("savings: save tariff config (CSRF POST) acknowledged", toast and len(toast) > 2, toast or "")
    page.screenshot(path=f"{SHOTS}/03-savings.png", full_page=True)

    # ---- 7. FESCO bill -------------------------------------------------------------------
    goto(page, BASE + "/fesco-bill", "networkidle")
    page.wait_for_timeout(3000)
    v = page.evaluate("""() => ({
        title: document.getElementById('bill-title')?.textContent.trim(),
        picker: document.getElementById('cycle-picker')?.querySelectorAll('option, button, li').length,
        payable: document.getElementById('payable-block')?.textContent.trim().slice(0, 80),
        hist: document.querySelectorAll('#history-body tr').length,
        calib: document.getElementById('calibration-line')?.textContent.trim().slice(0, 80),
        bootstrapVisible: (() => { const b = document.getElementById('bootstrap-pane'); return b && getComputedStyle(b).display !== 'none'; })(),
    })""")
    check("fesco: bill rendered with payable + history", v["payable"] and re.search(r"\d", v["payable"] or "") and v["hist"] >= 1 and not v["bootstrapVisible"], json.dumps(v))
    page.screenshot(path=f"{SHOTS}/04-fesco.png", full_page=True)

    # ---- 8. classic dashboard -------------------------------------------------------------
    goto(page, BASE + "/classic", "networkidle")
    page.wait_for_timeout(4000)
    v = page.evaluate("""() => ({
        solar: document.getElementById('solar-power')?.textContent.trim(),
        rows: document.querySelectorAll('#data-table-body tr').length,
        info: document.getElementById('pagination-info')?.textContent.trim(),
        status: document.getElementById('status-text')?.textContent.trim(),
    })""")
    check("classic: live tiles + raw-data table populated", v["solar"] not in (None, "", "--") and v["rows"] >= 5, json.dumps(v))
    page.screenshot(path=f"{SHOTS}/05-classic.png", full_page=True)

    # ---- 9. phone width screenshots + horizontal overflow check ----------------------------
    m = ctx.new_page(); m.set_viewport_size({"width": 390, "height": 844})
    merr, mfail = collect(m)
    for path_, name in PAGES:
        goto(m, BASE + path_); m.wait_for_timeout(2500)
        over = m.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(f"phone: {name} has no horizontal scroll", over <= 1, f"overflow={over}px")
        m.screenshot(path=f"{SHOTS}/m-{name}.png", full_page=True)
    m.close()

    # ---- 10. logout ------------------------------------------------------------------------
    goto(page, BASE + "/logout", "domcontentloaded")
    check("logout lands on /login", page.url.startswith(BASE + "/login"), page.url)
    goto(page, BASE + "/", "domcontentloaded")
    check("after logout, / redirects to /login", page.url.startswith(BASE + "/login"), page.url)

    # ---- console + network summary ---------------------------------------------------------
    ignore = re.compile(r"favicon|net::ERR_ABORTED|Failed to load resource: the server responded with a status of 40[13].*(?:/savings|/login)")
    errs = [scrub(e) for e in errors + merr if not ignore.search(e)]
    fails = [scrub(f) for f in failed + mfail if not ignore.search(f)]
    check("no console errors", not errs, "; ".join(errs)[:600])
    check("no failed requests / 4xx-5xx", not fails, "; ".join(fails)[:600])
    browser.close()

bad = [r for r in results if not r[1]]
print(f"\n{len(results) - len(bad)}/{len(results)} checks passed")
sys.exit(1 if bad else 0)
