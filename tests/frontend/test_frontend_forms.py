"""Browser-Tests (Playwright) fuer Frontend-Logik ohne laufendes Backend.

Die HTML-Seiten werden von einem lokalen Mini-Webserver ausgeliefert; alle
API-Aufrufe werden im Browser abgefangen und mit Testdaten beantwortet.
So laufen die Tests ueberall (lokal und in GitHub Actions) ohne Datenbank.

Abgedeckt:
- Buchungsformular: rote Markierung, Handynummer optional, WhatsApp braucht Nummer,
  Server-Fehler werden dem Feld zugeordnet (Desktop + Mobil)
- Anbieter-Portal: Link ?slot=<id> oeffnet den Termin mit Buchungsdetails + Buchungs-Nr.
- Login: Weiterleitung nach Login nur auf eigene Seiten (kein Open Redirect)
"""

from __future__ import annotations

import functools
import http.server
import json
import socket
import threading
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]
SLOT_ID = "11111111-2222-4333-8444-555555555555"
BOOKING_ID = "3f2a9c1d-0000-4000-8000-000000000000"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keine Server-Logs im Testlauf
        pass


@pytest.fixture(scope="module")
def tm_base():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    handler = functools.partial(_QuietHandler, directory=str(ROOT))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


@pytest.fixture(scope="module")
def tm_browser():
    try:
        pw = sync_api.sync_playwright().start()
        b = pw.chromium.launch()
    except Exception as exc:  # Browser nicht installiert
        pytest.skip(f"Playwright-Browser nicht verfuegbar: {exc}")
    yield b
    b.close()
    pw.stop()


def _new_page(browser, mobile: bool = False):
    if mobile:
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148")
    else:
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.alerts = []
    page.on("dialog", lambda d: (page.alerts.append(d.message), d.accept()))
    return page


def _mock_api(page, responses: dict, sent: list):
    """Faengt alle Nicht-HTML/CSS/JS-Anfragen ab. responses: {pfad-teil: (status, body)}."""
    def handle(route):
        req = route.request
        url = req.url
        for key, (status, body) in responses.items():
            if key in url:
                if req.method in ("POST", "PUT", "DELETE"):
                    try:
                        sent.append((key, json.loads(req.post_data or "{}")))
                    except Exception:
                        sent.append((key, req.post_data))
                return route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
        if url.startswith(page.base) and any(url.split("?")[0].endswith(ext) for ext in
                                              (".html", ".css", ".js", ".png", ".svg", ".woff2", ".ico", ".webp", ".jpg")):
            return route.continue_()
        # Unbekannte API-Aufrufe / externe Ressourcen: leer beantworten
        return route.fulfill(status=200, content_type="application/json", body="[]")
    page.route("**/*", handle)


# ---------------------------------------------------------------------------
# Buchungsformular
# ---------------------------------------------------------------------------
def _open_booking(page, tm_base, sfx=""):
    page.base = tm_base
    page.goto(f"{tm_base}/suche.html", wait_until="domcontentloaded")
    page.evaluate(f"window.slotsMap = {{'{SLOT_ID}': {{category:'Friseur', slot_type:'einzel'}}}}; openBook('{SLOT_ID}');")
    page.wait_for_selector(f"#book-first-name{sfx}", state="visible")


def _fill_valid(page, sfx=""):
    page.fill(f"#book-first-name{sfx}", "Erika")
    page.fill(f"#book-last-name{sfx}", "Musterfrau")
    page.fill(f"#book-address{sfx}", "Musterstraße 1, 10115 Berlin")
    page.fill(f"#book-email{sfx}", "erika@example.com")
    page.check(f"#book-confirmed{sfx}")


def _errors(page, sfx=""):
    return page.eval_on_selector_all(f"#book-form{sfx} .bk-err", "els => els.map(e => e.textContent)")


@pytest.mark.parametrize("mobile,sfx", [(False, ""), (True, "-mobile")])
def test_empty_form_marks_all_required_fields(tm_browser, tm_base, mobile, sfx):
    page = _new_page(tm_browser, mobile)
    sent = []
    page.base = tm_base
    _mock_api(page, {"/public/book": (200, {"ok": True})}, sent)
    _open_booking(page, tm_base, sfx)
    page.click(f"#book-form{sfx} button[type=submit]")
    errs = _errors(page, sfx)
    assert len(errs) == 5, errs  # Vorname, Nachname, Adresse, E-Mail, Bestaetigung
    assert page.locator(f"#book-form{sfx} .bk-err-summary").inner_text().startswith("Bitte die 5")
    assert page.locator(f"#book-first-name{sfx}").get_attribute("aria-invalid") == "true"
    assert sent == [], "Bei Fehlern darf nichts gesendet werden"
    page.context.close()


@pytest.mark.parametrize("mobile,sfx", [(False, ""), (True, "-mobile")])
def test_valid_form_without_phone_is_sent(tm_browser, tm_base, mobile, sfx):
    page = _new_page(tm_browser, mobile)
    sent = []
    page.base = tm_base
    _mock_api(page, {"/public/book": (200, {"ok": True})}, sent)
    _open_booking(page, tm_base, sfx)
    _fill_valid(page, sfx)
    page.click(f"#book-form{sfx} button[type=submit]")
    page.wait_for_timeout(400)
    assert _errors(page, sfx) == []
    assert len(sent) == 1
    payload = sent[0][1]
    assert payload["phone"] == ""
    assert payload["first_name"] == "Erika" and payload["booking_confirmed"] is True
    assert any("Fast geschafft" in a for a in page.alerts)
    page.context.close()


def test_address_without_zip_and_bad_email_are_marked(tm_browser, tm_base):
    page = _new_page(tm_browser)
    sent = []
    page.base = tm_base
    _mock_api(page, {"/public/book": (200, {"ok": True})}, sent)
    _open_booking(page, tm_base)
    _fill_valid(page)
    page.fill("#book-address", "Steigerwaldstraße 35")
    page.fill("#book-email", "erika@example")
    page.click("#book-submit")
    errs = _errors(page)
    assert any("PLZ" in e for e in errs)
    assert any("E-Mail" in e for e in errs)
    assert sent == []
    # Tippen entfernt die Markierung am Feld
    page.fill("#book-address", "Steigerwaldstraße 35, 96191 Viereth")
    assert "bk-invalid" not in (page.get_attribute("#book-address", "class") or "")
    page.context.close()


def test_whatsapp_requires_phone_and_label_changes(tm_browser, tm_base):
    page = _new_page(tm_browser)
    sent = []
    page.base = tm_base
    _mock_api(page, {"/public/book": (200, {"ok": True})}, sent)
    _open_booking(page, tm_base)
    assert page.inner_text("#book-phone-req-label") == "(optional)"
    # WhatsApp ist im Formular ausgeblendet, solange der Versand nicht angebunden ist.
    # Die Logik bleibt fuer spaeter erhalten -> Option fuer den Test einblenden.
    page.evaluate("""() => { const o = document.createElement('option'); o.value = 'whatsapp'; o.textContent = 'WhatsApp';
                     document.getElementById('book-reminder-channel').appendChild(o); }""")
    page.select_option("#book-reminder-channel", "whatsapp")
    assert page.inner_text("#book-phone-req-label").startswith("*")
    _fill_valid(page)
    page.click("#book-submit")
    errs = _errors(page)
    assert errs == ["Für die WhatsApp-Erinnerung bitte Handynummer angeben."]
    assert sent == []
    page.fill("#book-phone", "0170 1234567")
    page.click("#book-submit")
    page.wait_for_timeout(400)
    assert len(sent) == 1 and sent[0][1]["reminder_channel"] == "whatsapp"
    page.context.close()


def test_server_error_marks_matching_field(tm_browser, tm_base):
    page = _new_page(tm_browser)
    sent = []
    page.base = tm_base
    _mock_api(page, {"/public/book": (400, {"error": "invalid_email"})}, sent)
    _open_booking(page, tm_base)
    _fill_valid(page)
    page.click("#book-submit")
    page.wait_for_timeout(400)
    assert _errors(page) == ["Diese E-Mail-Adresse ist ungültig."]
    assert page.alerts == [], "Bekannte Fehler sollen am Feld stehen, nicht als Popup"
    page.context.close()


def test_reopening_dialog_clears_old_errors(tm_browser, tm_base):
    page = _new_page(tm_browser)
    page.base = tm_base
    _mock_api(page, {"/public/book": (200, {"ok": True})}, [])
    _open_booking(page, tm_base)
    page.click("#book-submit")
    assert len(_errors(page)) == 5
    page.evaluate(f"closeBook(); openBook('{SLOT_ID}');")
    assert _errors(page) == []
    page.context.close()


# ---------------------------------------------------------------------------
# Anbieter-Portal: Link aus Google-Kalender / E-Mail
# ---------------------------------------------------------------------------
def _portal_mocks(slot_status="PUBLISHED"):
    slot = {
        "id": SLOT_ID, "title": "Herrenschnitt", "category": "Friseur",
        "start_at": "2030-01-07T09:00:00Z", "end_at": "2030-01-07T10:00:00Z",
        "location": "Teststr. 1, 12345 Teststadt", "capacity": 1, "status": slot_status,
        "archived": False, "booked": 1,
        "bookings": [{
            "id": BOOKING_ID, "status": "confirmed", "customer_name": "Erika Musterfrau",
            "customer_first_name": "Erika", "customer_last_name": "Musterfrau",
            "customer_email": "erika@example.com", "customer_phone": "0170 1234567",
            "customer_address": "Musterstraße 1, 10115 Berlin",
        }],
    }
    me = {"id": "p1", "email": "anbieter@example.com", "company_name": "Salon", "plan": "profi",
          "profile_complete": True, "status": "approved"}
    return {
        "/slots?": (200, [slot]),
        "/me": (200, me),
        "/api/google/status": (200, {"configured": True, "eligible": True, "connected": False}),
    }


def test_portal_deeplink_opens_booking(tm_browser, tm_base):
    page = _new_page(tm_browser)
    page.base = tm_base
    _mock_api(page, _portal_mocks(), [])
    page.goto(f"{tm_base}/anbieter-portal.html?slot={SLOT_ID}", wait_until="domcontentloaded")
    row = page.locator(f'#tbl-slots tbody tr[data-slot-id="{SLOT_ID}"]')
    row.wait_for(state="attached", timeout=10000)
    page.wait_for_timeout(300)
    assert row.locator("details.booking-details").get_attribute("open") is not None
    assert "B-3F2A9C1D" in row.inner_text()
    assert "outline" in (row.get_attribute("style") or "")  # lila Hervorhebung
    page.context.close()


def test_portal_without_deeplink_keeps_details_closed(tm_browser, tm_base):
    page = _new_page(tm_browser)
    page.base = tm_base
    _mock_api(page, _portal_mocks(), [])
    page.goto(f"{tm_base}/anbieter-portal.html", wait_until="domcontentloaded")
    row = page.locator(f'#tbl-slots tbody tr[data-slot-id="{SLOT_ID}"]')
    row.wait_for(state="attached", timeout=10000)
    assert row.locator("details.booking-details").get_attribute("open") is None
    page.context.close()


def test_portal_redirects_to_login_with_return_path(tm_browser, tm_base):
    page = _new_page(tm_browser)
    page.base = tm_base
    mocks = _portal_mocks()
    mocks["/me"] = (401, {"error": "unauthorized"})
    _mock_api(page, mocks, [])
    page.goto(f"{tm_base}/anbieter-portal.html?slot={SLOT_ID}", wait_until="domcontentloaded")
    page.wait_for_url("**/login.html**", timeout=10000)
    assert "next=%2Fanbieter-portal.html%3Fslot%3D" + SLOT_ID in page.url
    page.context.close()


# ---------------------------------------------------------------------------
# Login: Weiterleitung nur auf eigene Seiten
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("next_value,expected_path", [
    ("/anbieter-portal.html?slot=abc", "/anbieter-portal.html"),
    ("https://evil.example/phish", "/anbieter-portal.html"),
    ("//evil.example/phish", "/anbieter-portal.html"),
    ("/\\evil.example", "/anbieter-portal.html"),
])
def test_login_next_only_internal(tm_browser, tm_base, next_value, expected_path):
    page = _new_page(tm_browser)
    page.base = tm_base
    from urllib.parse import quote
    _mock_api(page, {
        "/auth/login": (200, {"ok": True, "profile_complete": True}),
        "/me": (200, {"id": "p1", "profile_complete": True}),
    }, [])
    page.goto(f"{tm_base}/login.html?tab=login&next={quote(next_value)}", wait_until="domcontentloaded")
    page.fill("#login-email", "anbieter@example.com")
    page.fill("#login-password", "geheim123")
    page.click("#login-form button[type=submit]")
    page.wait_for_url(f"{tm_base}{expected_path}**", timeout=10000)
    assert page.url.startswith(tm_base), f"Weiterleitung auf fremde Seite: {page.url}"
    if next_value.startswith("/anbieter-portal.html?slot="):
        assert "slot=abc" in page.url
    page.context.close()


# ---------------------------------------------------------------------------
# Hilfe-Seite: neue Eintraege vorhanden, aufklappbar, nichts abgeschnitten
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("anchor", [
    "google-kalender-verbinden", "google-kalender-sync", "wer-hat-gebucht",
    "kundennamen-google", "google-trennen", "kalender-abo", "formular-fehler",
])
def test_help_entries_open_fully(tm_browser, tm_base, anchor):
    page = _new_page(tm_browser)
    page.base = tm_base
    _mock_api(page, {}, [])
    page.goto(f"{tm_base}/hilfe.html", wait_until="domcontentloaded")
    item = page.locator(f"#{anchor}")
    item.locator(".faq-question").click()
    page.wait_for_timeout(450)  # Aufklapp-Animation
    answer = item.locator(".faq-answer")
    content = item.locator(".faq-answer-content")
    assert content.is_visible()
    # Antwort darf nicht durch max-height abgeschnitten werden
    assert answer.evaluate("el => el.clientHeight + 2 >= el.scrollHeight")
    page.context.close()


def test_help_no_longer_promises_sms_alerts(tm_browser, tm_base):
    page = _new_page(tm_browser)
    page.base = tm_base
    _mock_api(page, {}, [])
    page.goto(f"{tm_base}/hilfe.html", wait_until="domcontentloaded")
    assert "SMS-Benachrichtigungen" not in page.content()
    page.context.close()


# ---------------------------------------------------------------------------
# Rechtliches im Buchungsformular und in den Rechtstexten
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mobile,sfx", [(False, ""), (True, "-mobile")])
def test_booking_form_has_no_whatsapp_and_legal_hint(tm_browser, tm_base, mobile, sfx):
    page = _new_page(tm_browser, mobile)
    page.base = tm_base
    _mock_api(page, {}, [])
    _open_booking(page, tm_base, sfx)
    values = page.eval_on_selector_all(f"#book-reminder-channel{sfx} option", "els => els.map(e => e.value)")
    assert values == ["email"], "WhatsApp darf erst angeboten werden, wenn der Versand funktioniert"
    hint = page.locator(f"#book-form{sfx} .bk-legal-hint")
    assert hint.is_visible()
    hrefs = hint.locator("a").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert "agb.html" in hrefs and "datenschutz.html#terminbuchungen" in hrefs
    page.context.close()


def test_privacy_policy_covers_new_features(tm_browser, tm_base):
    page = _new_page(tm_browser)
    page.base = tm_base
    _mock_api(page, {}, [])
    page.goto(f"{tm_base}/datenschutz.html", wait_until="domcontentloaded")
    text = page.inner_text("main")
    for needle in ("5.8 Benachrichtigungen", "5.9 Google-Kalender-Anbindung", "5.10 Aktionscodes",
                   "tm_gcal_pkce", "Google Calendar API", "Data Privacy Framework", "Handynummer (freiwillig)"):
        assert needle in text, needle
    assert page.locator("#terminbuchungen").count() == 1  # Sprungziel aus dem Buchungsformular
    page.context.close()


def test_terms_cover_new_features(tm_browser, tm_base):
    page = _new_page(tm_browser)
    page.base = tm_base
    _mock_api(page, {}, [])
    page.goto(f"{tm_base}/agb.html", wait_until="domcontentloaded")
    text = page.inner_text("main")
    for needle in ("4.1 Kalender-Anbindungen", "6.1 Aktionscodes", "6.2 Aufbewahrungspflicht",
                   "Unternehmer im Sinne des § 14 BGB"):
        assert needle in text, needle
    page.context.close()
