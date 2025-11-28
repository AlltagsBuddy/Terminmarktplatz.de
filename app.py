# app.py — API + HTML (Root-Templates; Render & Local)
import os
import traceback
from datetime import datetime, timedelta, timezone

# E-Mail / HTTP-APIs / SMTP
from email.message import EmailMessage
from email.utils import parseaddr, formataddr
import smtplib
import requests

# ZoneInfo robust (Backport bei < 3.9)
try:
    from zoneinfo import ZoneInfo
except Exception:
    from backports.zoneinfo import ZoneInfo
BERLIN = ZoneInfo("Europe/Berlin")

import time
from sqlalchemy import create_engine, select, and_, or_, func, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from dotenv import load_dotenv
from email_validator import validate_email, EmailNotValidError
from flask import (
    Flask, request, redirect, jsonify, make_response,
    render_template, url_for, abort
)
from flask_cors import CORS
from argon2 import PasswordHasher
import jwt

# Deine ORM-Modelle
from models import Base, Provider, Slot, Booking


# --------------------------------------------------------
# Init / Mode / Pfade
# --------------------------------------------------------
load_dotenv()

APP_ROOT     = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR   = os.path.join(APP_ROOT, "static")
TEMPLATE_DIR = os.path.join(APP_ROOT, "templates")  # <— WICHTIG: Templates-Ordner!

IS_RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID") or os.environ.get("RENDER_EXTERNAL_URL"))
API_ONLY  = os.environ.get("API_ONLY") == "1"

app = Flask(
    __name__,
    static_folder=STATIC_DIR,
    static_url_path="/static",
    template_folder=TEMPLATE_DIR,
)

# Im Test/Dev Caching hart deaktivieren (hilft gegen „alte“ HTML/Assets)
if not IS_RENDER:
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

print("MODE       :", "API-only" if API_ONLY else "Full (API + HTML)")
print("TEMPLATES  :", TEMPLATE_DIR)
print("STATIC     :", STATIC_DIR)


# --------------------------------------------------------
# Config
# --------------------------------------------------------
SECRET            = os.environ.get("SECRET_KEY", "dev")
DB_URL            = os.environ.get("DATABASE_URL", "")
JWT_ISS           = os.environ.get("JWT_ISS", "terminmarktplatz")
JWT_AUD           = os.environ.get("JWT_AUD", "terminmarktplatz_client")
JWT_EXP_MIN       = int(os.environ.get("JWT_EXP_MINUTES", "60"))
REFRESH_EXP_DAYS  = int(os.environ.get("REFRESH_EXP_DAYS", "14"))

# --- MAIL Konfiguration (Resend standard; Postmark/SMTP optional) ---
MAIL_PROVIDER  = os.getenv("MAIL_PROVIDER", "resend")   # resend | postmark | smtp | console
MAIL_FROM      = os.getenv("MAIL_FROM", "Terminmarktplatz <no-reply@terminmarktplatz.de>")
MAIL_REPLY_TO  = os.getenv("MAIL_REPLY_TO", os.getenv("REPLY_TO", MAIL_FROM))
EMAILS_ENABLED = os.getenv("EMAILS_ENABLED", "true").lower() == "true"
CONTACT_TO     = os.getenv("CONTACT_TO", MAIL_FROM)

# RESEND (HTTPS)
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

# POSTMARK (HTTPS)
POSTMARK_API_TOKEN      = os.getenv("POSTMARK_API_TOKEN") or os.getenv("POSTMARK_TOKEN")
POSTMARK_MESSAGE_STREAM = os.getenv("POSTMARK_MESSAGE_STREAM", "outbound")

# SMTP (z. B. STRATO) – für lokale Tests
SMTP_HOST    = os.getenv("SMTP_HOST")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER    = os.getenv("SMTP_USER")
SMTP_PASS    = os.getenv("SMTP_PASS")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"


def _cfg(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        raise RuntimeError(f"Missing required setting: {name}")
    return val

BASE_URL     = _cfg("BASE_URL", "https://api.terminmarktplatz.de" if IS_RENDER else "http://127.0.0.1:5000")
FRONTEND_URL = _cfg("FRONTEND_URL", "https://terminmarktplatz.de" if IS_RENDER else "http://127.0.0.1:5000")

def _external_base() -> str:
    try:
        return request.url_root.rstrip("/")
    except RuntimeError:
        return BASE_URL

# PostgreSQL URL für SQLAlchemy (psycopg v3) normalisieren
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DB_URL.startswith("postgresql://"):
    DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg://", 1)


# --------------------------------------------------------
# DB / Crypto / CORS
# --------------------------------------------------------
engine = create_engine(DB_URL, pool_pre_ping=True)
ph = PasswordHasher(time_cost=2, memory_cost=102_400, parallelism=8)

ALLOWED_ORIGINS = [
    "https://terminmarktplatz.de",
    "https://www.terminmarktplatz.de",
    "https://api.terminmarktplatz.de",
    "http://127.0.0.1:5000",
    "http://localhost:5000",
]
# --- CORS -------------------------------------------------
if IS_RENDER:
    ALLOWED_ORIGINS = [
        "https://terminmarktplatz.de",
        "https://www.terminmarktplatz.de",
    ]
else:
    ALLOWED_ORIGINS = [
        "http://localhost:5000",
        "http://127.0.0.1:5000",
    ]

CORS(
    app,
    resources={
        r"/auth/*":   {"origins": ALLOWED_ORIGINS},
        r"/me":       {"origins": ALLOWED_ORIGINS},
        r"/slots*":   {"origins": ALLOWED_ORIGINS},
        r"/admin/*":  {"origins": ALLOWED_ORIGINS},
        r"/public/*": {"origins": ALLOWED_ORIGINS},
        r"/api/*":    {"origins": ALLOWED_ORIGINS},
    },
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET","POST","PUT","DELETE","OPTIONS"],
)


@app.after_request
def add_headers(resp):
    resp.headers.setdefault("Cache-Control", "no-store")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp


# --------------------------------------------------------
# Geocode-Cache (idempotent)
# --------------------------------------------------------
def _ensure_geo_tables():
    ddl_cache = """
    CREATE TABLE IF NOT EXISTS geocode_cache (
      key text PRIMARY KEY,
      lat double precision,
      lon double precision,
      updated_at timestamp with time zone DEFAULT now()
    );
    """
    with engine.begin() as conn:
        conn.exec_driver_sql(ddl_cache)

_ensure_geo_tables()

def _gc_key(zip_code: str | None, city: str | None) -> str:
    if zip_code and zip_code.strip():
        return f"zip:{zip_code.strip()}"
    if city and city.strip():
        return f"city:{city.strip().lower()}"
    return ""

def geocode_cached(session: Session, zip_code: str | None, city: str | None) -> tuple[float | None, float | None]:
    key = _gc_key(zip_code, city)
    if not key:
        return None, None

    row = session.execute(text("SELECT lat, lon FROM geocode_cache WHERE key=:k"), {"k": key}).first()
    if row and row[0] is not None and row[1] is not None:
        return float(row[0]), float(row[1])

    query = zip_code if zip_code else city
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "de"},
            headers={"User-Agent": "Terminmarktplatz/1.0 (kontakt@terminmarktplatz.de)"},
            timeout=8,
        )
        if r.ok:
            js = r.json()
            if js:
                lat = float(js[0]["lat"]); lon = float(js[0]["lon"])
                session.execute(
                    text("""INSERT INTO geocode_cache(key, lat, lon)
                            VALUES(:k,:lat,:lon)
                            ON CONFLICT (key) DO UPDATE
                            SET lat=EXCLUDED.lat, lon=EXCLUDED.lon, updated_at=now()"""),
                    {"k": key, "lat": lat, "lon": lon}
                )
                session.commit()
                time.sleep(0.2)
                return lat, lon
    except Exception:
        pass

    session.execute(
        text("INSERT INTO geocode_cache(key, lat, lon) VALUES(:k,NULL,NULL) ON CONFLICT (key) DO NOTHING"),
        {"k": key}
    )
    session.commit()
    return None, None


# --------------------------------------------------------
# Zeit / Kategorien / Utilities
# --------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)

def parse_iso_utc(s: str) -> datetime:
    if not isinstance(s, str):
        raise ValueError("not a string")
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt

def _to_db_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)

def _from_db_as_iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")

BRANCHES = {
    "Friseur", "Kosmetik", "Physiotherapie", "Nagelstudio", "Zahnarzt",
    "Handwerk", "KFZ-Service", "Fitness", "Coaching", "Tierarzt",
    "Behörde", "Sonstiges"
}

def normalize_category(raw: str | None) -> str:
    if raw is None:
        return "Sonstiges"
    val = str(raw).strip()
    if not val:
        return "Sonstiges"
    return val if val in BRANCHES else "Sonstiges"

def _json_error(msg, code=400):
    return jsonify({"error": msg}), code

def _cookie_flags():
    if IS_RENDER:
        return {"httponly": True, "secure": True, "samesite": "None", "path": "/"}
    return {"httponly": True, "secure": False, "samesite": "Lax", "path": "/"}

def slot_to_json(x: Slot):
    return {
        "id": x.id, "provider_id": x.provider_id,
        "title": x.title, "category": x.category,
        "start_at": _from_db_as_iso_utc(x.start_at),
        "end_at": _from_db_as_iso_utc(x.end_at),
        "location": x.location, "capacity": x.capacity,
        "contact_method": x.contact_method, "booking_link": x.booking_link,
        "price_cents": x.price_cents, "notes": x.notes,
        "status": x.status, "created_at": _from_db_as_iso_utc(x.created_at),
    }

# ---- Validierungen & Profil-Check ----
def _is_valid_zip(v: str | None) -> bool:
    v = (v or "").strip()
    return len(v) == 5 and v.isdigit()

def _is_valid_phone(v: str | None) -> bool:
    v = (v or "").strip()
    return len(v) >= 6

def is_profile_complete(p: Provider) -> bool:
    return all([
        bool(p.company_name),
        bool(p.branch),
        bool(p.street),
        _is_valid_zip(p.zip),
        bool(p.city),
        _is_valid_phone(p.phone),
    ])


# --------------------------------------------------------
# Mail
# --------------------------------------------------------
def send_mail(to: str, subject: str, text: str | None = None, html: str | None = None,
              tag: str | None = None, metadata: dict | None = None):
    try:
        if not EMAILS_ENABLED:
            print(f"[mail] disabled: EMAILS_ENABLED=false subject='{subject}' to={to}", flush=True)
            return True, "disabled"

        provider = (MAIL_PROVIDER or "resend").lower()
        print(f"[mail] provider={provider} from={MAIL_FROM} to={to} subject='{subject}'", flush=True)

        if provider == "console":
            print(
                "\n--- MAIL (console) ---\n"
                f"From: {MAIL_FROM}\nTo: {to}\nSubject: {subject}\nReply-To: {MAIL_REPLY_TO}\n\n"
                f"{text or ''}\n{html or ''}\n--- END ---\n",
                flush=True
            )
            return True, "console"

        if provider == "resend":
            if not RESEND_API_KEY:
                return False, "missing RESEND_API_KEY"
            payload = {"from": MAIL_FROM, "to": [to], "subject": subject}
            if text: payload["text"] = text
            if html: payload["html"] = html
            if MAIL_REPLY_TO: payload["reply_to"] = [MAIL_REPLY_TO]
            r = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json=payload, timeout=15
            )
            ok = 200 <= r.status_code < 300
            print("[resend]", r.status_code, r.text, flush=True)
            return ok, f"{r.status_code}"

        if provider == "postmark":
            if not POSTMARK_API_TOKEN:
                return False, "missing POSTMARK_API_TOKEN"
            payload = {"From": MAIL_FROM, "To": to, "Subject": subject, "MessageStream": POSTMARK_MESSAGE_STREAM}
            if MAIL_REPLY_TO: payload["ReplyTo"] = MAIL_REPLY_TO
            if text: payload["TextBody"] = text
            if html: payload["HtmlBody"] = html
            if tag: payload["Tag"] = tag
            if metadata: payload["Metadata"] = metadata
            r = requests.post(
                "https://api.postmarkapp.com/email",
                headers={"X-Postmark-Server-Token": POSTMARK_API_TOKEN, "Accept": "application/json", "Content-Type": "application/json"},
                json=payload, timeout=15
            )
            ok = 200 <= r.status_code < 300
            print("[postmark]", r.status_code, r.text, flush=True)
            return ok, f"{r.status_code}"

        if provider == "smtp":
            missing = [k for k, v in {"SMTP_HOST": SMTP_HOST, "SMTP_PORT": SMTP_PORT, "SMTP_USER": SMTP_USER, "SMTP_PASS": SMTP_PASS}.items() if not v]
            if missing:
                return False, f"missing smtp config: {', '.join(missing)}"
            disp_name, _ = parseaddr(MAIL_FROM or "")
            from_hdr = formataddr((disp_name or "Terminmarktplatz", SMTP_USER))
            msg = EmailMessage()
            msg["From"] = from_hdr; msg["To"] = to; msg["Subject"] = subject
            if MAIL_REPLY_TO: msg["Reply-To"] = MAIL_REPLY_TO
            if html:
                msg.set_content(text or "")
                msg.add_alternative(html, subtype="html")
            else:
                msg.set_content(text or "")
            try:
                if SMTP_USE_TLS:
                    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                        s.starttls(); s.login(SMTP_USER, SMTP_PASS); s.send_message(msg, from_addr=SMTP_USER)
                else:
                    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                        s.login(SMTP_USER, SMTP_PASS); s.send_message(msg, from_addr=SMTP_USER)
                return True, "smtp"
            except Exception as e:
                print("[smtp][ERROR]", repr(e), flush=True)
                return False, repr(e)

        return False, f"unknown provider '{provider}'"

    except Exception as e:
        print("send_mail exception:", repr(e), flush=True)
        return False, repr(e)


# --------------------------------------------------------
# Auth / Tokens
# --------------------------------------------------------
def issue_tokens(provider_id: str, is_admin: bool):
    now = _now()
    access = jwt.encode(
        {"sub": provider_id, "adm": is_admin, "iss": JWT_ISS, "aud": JWT_AUD,
         "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=JWT_EXP_MIN)).timestamp())},
        SECRET, algorithm="HS256",
    )
    refresh = jwt.encode(
        {"sub": provider_id, "iss": JWT_ISS, "aud": JWT_AUD, "typ": "refresh",
         "iat": int(now.timestamp()), "exp": int((now + timedelta(days=REFRESH_EXP_DAYS)).timestamp())},
        SECRET, algorithm="HS256",
    )
    return access, refresh

def auth_required(admin: bool = False):
    def wrapper(fn):
        def inner(*args, **kwargs):
            token = request.cookies.get("access_token")
            if not token:
                auth = request.headers.get("Authorization", "")
                if auth.lower().startswith("bearer "):
                    token = auth.split(" ", 1)[1].strip()
            if not token:
                return _json_error("unauthorized", 401)
            try:
                data = jwt.decode(token, SECRET, algorithms=["HS256"], audience=JWT_AUD, issuer=JWT_ISS)
            except Exception:
                return _json_error("unauthorized", 401)
            if admin and not data.get("adm"):
                return _json_error("forbidden", 403)
            request.provider_id = data["sub"]
            request.is_admin = bool(data.get("adm"))
            return fn(*args, **kwargs)
        inner.__name__ = fn.__name__
        return inner
    return wrapper


# --------------------------------------------------------
# Misc (favicon/robots + health)
# --------------------------------------------------------
@app.get("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="favicon.ico"), code=302)

@app.get("/robots.txt")
def robots():
    return redirect(url_for("static", filename="robots.txt"), code=302)

@app.get("/healthz")
@app.get("/api/health")
def health():
    try:
        with Session(engine) as s:
            s.execute(select(func.now()))
        return jsonify({"ok": True, "service": "api", "time": _now().isoformat()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --------------------------------------------------------
# API-only Gate (optional)
# --------------------------------------------------------
@app.before_request
def maybe_api_only():
    if not API_ONLY:
        return
    if not (
        request.path.startswith("/auth/") or
        request.path.startswith("/admin/") or
        request.path.startswith("/public/") or
        request.path.startswith("/slots") or
        request.path in ("/me", "/api/health", "/healthz", "/favicon.ico", "/robots.txt") or
        request.path.startswith("/static/")
    ):
        return _json_error("api_only", 404)


# --------------------------------------------------------
# HTML ROUTES (Full mode)
# --------------------------------------------------------
def _html_enabled() -> bool:
    return not API_ONLY

if _html_enabled():
    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/login")
    def login_page():
        return render_template("login.html")

    @app.get("/anbieter-portal")
    def anbieter_portal_page():
        return render_template("anbieter-portal.html")

    @app.get("/anbieter-portal.html")
    def anbieter_portal_page_html():
        return render_template("anbieter-portal.html")

    @app.get("/impressum")
    def impressum():
        return render_template("impressum.html")

    @app.get("/datenschutz")
    def datenschutz():
        return render_template("datenschutz.html")

    @app.get("/agb")
    def agb():
        return render_template("agb.html")

    @app.get("/<path:slug>")
    def any_page(slug: str):
        filename = slug if slug.endswith(".html") else f"{slug}.html"
        try:
            return render_template(filename)
        except Exception:
            abort(404)
else:
    @app.get("/")
    def api_root():
        return jsonify({"ok": True, "service": "api", "time": _now().isoformat()})


# --------------------------------------------------------
# Public: Kontaktformular
# --------------------------------------------------------
@app.post("/public/contact")
def public_contact():
    try:
        data = request.get_json(force=True) or {}
        name    = (data.get("name") or "").strip()
        email   = (data.get("email") or "").strip().lower()
        subject = (data.get("subject") or "").strip()
        message = (data.get("message") or "").strip()

        if not name or not email or not subject or not message:
            return _json_error("missing_fields", 400)
        try:
            email = validate_email(email).email
        except EmailNotValidError:
            return _json_error("invalid_email", 400)

        consent = bool(data.get("consent"))
        if not consent:
            return _json_error("consent_required", 400)

        ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "-"
        ua = request.headers.get("User-Agent", "-")
        body = (
            f"[Kontaktformular]\n"
            f"Name: {name}\n"
            f"E-Mail: {email}\n"
            f"IP: {ip}\nUA: {ua}\n"
            f"Zeit: {_now().isoformat()}\n\n"
            f"Betreff: {subject}\n"
            f"Nachricht:\n{message}\n"
        )

        ok, reason = send_mail(CONTACT_TO, f"[Terminmarktplatz] Kontakt: {subject}", body)
        try:
            send_mail(email, "Danke für deine Nachricht",
                      "Wir haben deine Nachricht erhalten undmelden uns bald.\n\n— Terminmarktplatz")
        except Exception:
            pass

        return jsonify({"ok": bool(ok), "delivered": bool(ok), "reason": reason})
    except Exception as e:
        print("[public_contact] error:", repr(e), flush=True)
        return jsonify({"error": "server_error"}), 500


# --------------------------------------------------------
# Auth helpers + Endpoints
# --------------------------------------------------------
def _authenticate(email: str, password: str):
    email = (email or "").strip().lower()
    pw    = password or ""
    with Session(engine) as s:
        p = s.scalar(select(Provider).where(Provider.email == email))
        if not p:
            return None, "invalid_credentials"
        try:
            ph.verify(p.pw_hash, pw)
        except Exception:
            return None, "invalid_credentials"
        if not p.email_verified_at:
            return None, "email_not_verified"
        return p, None

def _set_auth_cookies(resp, access: str, refresh: str | None = None):
    flags = _cookie_flags()
    resp.set_cookie("access_token", access, max_age=JWT_EXP_MIN * 60, **flags)
    if refresh:
        resp.set_cookie("refresh_token", refresh, max_age=REFRESH_EXP_DAYS * 86400, **flags)
    return resp

@app.post("/auth/register")
def register():
    try:
        data = request.get_json(force=True)
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        try:
            email = validate_email(email).email
        except EmailNotValidError:
            return _json_error("invalid_email")
        if len(password) < 8:
            return _json_error("password_too_short")

        with Session(engine) as s:
            exists = s.scalar(select(func.count()).select_from(Provider).where(Provider.email == email))
            if exists:
                return _json_error("email_exists")

            p = Provider(email=email, pw_hash=ph.hash(password), status="pending")
            s.add(p); s.commit()
            provider_id = p.id
            reg_email   = p.email

        # --- Admin-Notification bei neuer Registrierung -------------------
        try:
            admin_to = os.getenv("ADMIN_NOTIFY_TO", CONTACT_TO)
            if admin_to:
                subj = "[Terminmarktplatz] Neuer Anbieter registriert"
                txt  = (
                    "Es hat sich ein neuer Anbieter registriert.\n\n"
                    f"ID: {provider_id}\n"
                    f"E-Mail: {reg_email}\n"
                    f"Zeit: {_now().isoformat()}\n"
                    "Status: pending (E-Mail-Verifizierung ausstehend)\n"
                )
                send_mail(
                    admin_to, subj, text=txt,
                    tag="provider_signup",
                    metadata={"provider_id": str(provider_id), "email": reg_email}
                )
        except Exception as _e:
            print("[notify_admin][register] failed:", repr(_e), flush=True)
        # ------------------------------------------------------------------

        payload = {
            "sub": provider_id, "aud": "verify", "iss": JWT_ISS,
            "exp": int((_now() + timedelta(days=2)).timestamp())
        }
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        link = f"{BASE_URL}/auth/verify?token={token}"
        ok_mail, reason = send_mail(reg_email, "Bitte E-Mail bestätigen",
                                    f"Willkommen beim Terminmarktplatz.\n\nBitte bestätige deine E-Mail:\n{link}\n")
        return jsonify({
            "ok": True,
            "mail_sent": ok_mail,
            "mail_reason": reason,
            "message": "Registrierung gespeichert. Bitte prüfe deine E-Mails und bestätige die Anmeldung.",
            "post_verify_redirect": f"{FRONTEND_URL}/login.html?verified=1"
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "server_error", "detail": str(e)}), 500


@app.get("/auth/verify")
def auth_verify():
    token = request.args.get("token", "")
    debug = request.args.get("debug") == "1"

    def _ret(kind: str):
        # Immer zurück auf die Login-Seite, mit Query-Flag
        url = f"{FRONTEND_URL}/login.html?verified={'1' if kind=='1' else '0'}"
        if debug:
            return jsonify({"ok": kind == "1", "redirect": url})
        return redirect(url)
    try:
        data = jwt.decode(token, SECRET, algorithms=["HS256"], audience="verify", issuer=JWT_ISS)
    except jwt.ExpiredSignatureError:
        return _ret("expired")
    except Exception as e:
        print("[verify] token invalid:", repr(e), flush=True)
        return _ret("invalid")

    try:
        pid = data.get("sub")
        with Session(engine) as s:
            p = s.get(Provider, pid)
            if not p:
                return _ret("notfound")
            if not p.email_verified_at:
                p.email_verified_at = _now()
                s.commit()
        return _ret("1")
    except Exception as e:
        print("[verify] server error:", repr(e), flush=True)
        return _ret("server")

@app.post("/auth/login")
def auth_login_json():
    data = request.get_json(force=True)
    p, err = _authenticate(data.get("email"), data.get("password"))
    if err:
        status = 403 if err == "email_not_verified" else 401
        return _json_error(err, status)

    access, refresh = issue_tokens(p.id, p.is_admin)
    resp = make_response(jsonify({"ok": True, "access": access}))
    return _set_auth_cookies(resp, access, refresh)

@app.post("/login")
def auth_login_form():
    email = request.form.get("email")
    password = request.form.get("password")
    p, err = _authenticate(email, password)
    if err:
        return render_template(
            "login.html",
            error="Login fehlgeschlagen." if err != "email_not_verified" else "E-Mail noch nicht verifiziert."
        ), 401

    access, refresh = issue_tokens(p.id, p.is_admin)
    resp = make_response(redirect("anbieter-portal"))
    return _set_auth_cookies(resp, access, refresh)

@app.post("/auth/logout")
@auth_required()
def auth_logout():
    resp = make_response(jsonify({"ok": True}))
    flags = _cookie_flags()
    resp.delete_cookie("access_token", **flags)
    resp.delete_cookie("refresh_token", **flags)
    return resp

@app.post("/auth/refresh")
def auth_refresh():
    token = request.cookies.get("refresh_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    if not token:
        return _json_error("unauthorized", 401)
    try:
        data = jwt.decode(token, SECRET, algorithms=["HS256"], audience=JWT_AUD, issuer=JWT_ISS)
        if data.get("typ") != "refresh":
            raise Exception("wrong type")
    except Exception:
        return _json_error("unauthorized", 401)

    access, _ = issue_tokens(data["sub"], bool(data.get("adm")))
    resp = make_response(jsonify({"ok": True, "access": access}))
    return _set_auth_cookies(resp, access)

# --- Account löschen --------------------------------
@app.delete("/me")
@auth_required()
def delete_me():
    try:
        with Session(engine) as s:
            p = s.get(Provider, request.provider_id)
            if not p:
                return _json_error("not_found", 404)
            # DB-FKs erledigen Cascade: provider -> slot -> booking
            s.delete(p)
            s.commit()

        resp = make_response(jsonify({"ok": True, "deleted": True}))
        flags = _cookie_flags()
        resp.delete_cookie("access_token", **flags)
        resp.delete_cookie("refresh_token", **flags)
        return resp
    except Exception as e:
        app.logger.exception("delete_me failed")
        return jsonify({"error": "server_error"}), 500
# ---------------------------------------------------------


# --------------------------------------------------------
# Me / Profile
# --------------------------------------------------------
@app.get("/me")
@auth_required()
def me():
    with Session(engine) as s:
        p = s.get(Provider, request.provider_id)
        if not p:
            return _json_error("not_found", 404)
        return jsonify({
            "id": p.id, "email": p.email, "status": p.status, "is_admin": p.is_admin,
            "company_name": p.company_name, "branch": p.branch, "street": p.street,
            "zip": p.zip, "city": p.city, "phone": p.phone, "whatsapp": p.whatsapp,
            "profile_complete": is_profile_complete(p)
        })

@app.put("/me")
@auth_required()
def me_update():
    try:
        data = request.get_json(force=True) or {}
        allowed = {"company_name","branch","street","zip","city","phone","whatsapp"}

        def clean(v):
            if v is None: return None
            v = str(v).strip()
            return v or None

        upd = {k: clean(v) for k, v in data.items() if k in allowed}

        if "zip" in upd and upd["zip"] is not None:
            z = upd["zip"]
            if not z.isdigit() or len(z) != 5:
                return _json_error("invalid_zip", 400)

        with Session(engine) as s:
            p = s.get(Provider, request.provider_id)
            if not p:
                return _json_error("not_found", 404)

            for k, v in upd.items():
                setattr(p, k, v)

            try:
                s.commit()
            except IntegrityError as e:
                s.rollback()
                detail = getattr(getattr(e, "orig", None), "diag", None)
                return jsonify({
                    "error": "db_constraint_error",
                    "constraint": getattr(detail, "constraint_name", None),
                    "message": str(e.orig)
                }), 400
            except SQLAlchemyError:
                s.rollback()
                return _json_error("db_error", 400)

            # Koordinaten in Cache (optional, für spätere Optimierungen)
            try:
                lat, lon = geocode_cached(s, p.zip, p.city)
                if lat is not None and lon is not None:
                    s.execute(
                        text("UPDATE provider SET lat=:lat, lon=:lon WHERE id=:pid"),
                        {"lat": lat, "lon": lon, "pid": p.id}
                    )
                    s.commit()
            except Exception:
                s.rollback()

        return jsonify({"ok": True})
    except Exception as e:
        print("[/me] server error:", repr(e), flush=True)
        return jsonify({"error": "server_error"}), 500


# --------------------------------------------------------
# Slots (Provider)
# --------------------------------------------------------
VALID_STATUSES = {"pending_review", "published", "archived"}

def _status_transition_ok(current: str, new: str) -> bool:
    if new not in VALID_STATUSES:
        return False
    if current == new:
        return True
    if current == "pending_review":
        return new in {"published", "archived"}
    if current == "published":
        return new in {"archived"}
    if current == "archived":
        return new in {"published"}
    return False

@app.get("/slots")
@auth_required()
def slots_list():
    status = request.args.get("status")
    with Session(engine) as s:
        # Buchungs-Aggregat: alle "hold" + "confirmed" Buchungen pro Slot
        bq = (
            select(Booking.slot_id, func.count().label("booked"))
            .where(Booking.status.in_(["hold", "confirmed"]))
            .group_by(Booking.slot_id)
            .subquery()
        )

        q = (
            select(
                Slot,
                func.coalesce(bq.c.booked, 0).label("booked")
            )
            .outerjoin(bq, bq.c.slot_id == Slot.id)
            .where(Slot.provider_id == request.provider_id)
        )

        if status:
            q = q.where(Slot.status == status)

        rows = s.execute(q.order_by(Slot.start_at.desc())).all()

        out = []
        for slot, booked in rows:
            cap = slot.capacity or 1
            booked = int(booked or 0)
            available = max(0, cap - booked)

            item = slot_to_json(slot)
            item["booked"] = booked
            item["available"] = available
            out.append(item)

        return jsonify(out)


@app.post("/slots")
@auth_required()
def slots_create():
    try:
        data = request.get_json(force=True) or {}
        required = ["title", "category", "start_at", "end_at"]
        if any(k not in data or data[k] in (None, "") for k in required):
            return _json_error("missing_fields", 400)

        try:
            start = parse_iso_utc(data["start_at"])
            end   = parse_iso_utc(data["end_at"])
        except Exception:
            return _json_error("bad_datetime", 400)
        if end <= start:
            return _json_error("end_before_start", 400)
        if start <= _now():
            return _json_error("start_in_past", 409)

        location = (data.get("location") or "").strip()
        if not location:
            return _json_error("missing_location", 400)

        cap = int(data.get("capacity") or 1)
        if cap < 1:
            return _json_error("bad_capacity", 400)

        start_db = _to_db_utc_naive(start)
        end_db   = _to_db_utc_naive(end)

        with Session(engine) as s:
            p = s.get(Provider, request.provider_id)
            if not p or not is_profile_complete(p):
                return _json_error("profile_incomplete", 400)

            count = s.scalar(
                select(func.count()).select_from(Slot).where(
                    and_(Slot.provider_id == request.provider_id,
                         Slot.status.in_(["pending_review", "published"]))
                )
            ) or 0
            if count > 200:
                return _json_error("limit_reached", 400)

            title = (str(data["title"]).strip() or "Slot")[:100]
            category = normalize_category(data.get("category"))
            location_db = location[:120]

            slot = Slot(
                provider_id=request.provider_id,
                title=title,
                category=category,
                start_at=start_db, end_at=end_db,
                location=location_db,
                capacity=cap,
                contact_method=(data.get("contact_method") or "mail"),
                booking_link=(data.get("booking_link") or None),
                price_cents=(data.get("price_cents") or None),
                notes=(data.get("notes") or None),
                status="pending_review",
            )
            s.add(slot)
            try:
                s.commit()
            except IntegrityError as e:
                s.rollback()
                constraint = getattr(getattr(getattr(e, "orig", None), "diag", None), "constraint_name", None)
                if constraint == "slot_category_check":
                    return jsonify({"error": "bad_category", "detail": "Kategorie entspricht nicht den DB-Vorgaben."}), 400
                return jsonify({"error":"db_constraint_error","constraint": constraint, "detail": str(e.orig)}), 400
            except SQLAlchemyError as e:
                s.rollback()
                return jsonify({"error":"db_error","detail":str(e)}), 400

            return jsonify(slot_to_json(slot)), 201

    except Exception as e:
        print("[/slots] server error:", traceback.format_exc(), flush=True)
        return jsonify({"error":"server_error","detail":str(e)}), 500

@app.put("/slots/<slot_id>")
@auth_required()
def slots_update(slot_id):
    try:
        data = request.get_json(force=True) or {}
        with Session(engine) as s:
            slot = s.get(Slot, slot_id, with_for_update=True)
            if not slot or slot.provider_id != request.provider_id:
                return _json_error("not_found", 404)

            if "start_at" in data:
                try:
                    slot.start_at = _to_db_utc_naive(parse_iso_utc(data["start_at"]))
                except Exception:
                    return _json_error("bad_datetime", 400)
            if "end_at" in data:
                try:
                    slot.end_at = _to_db_utc_naive(parse_iso_utc(data["end_at"]))
                except Exception:
                    return _json_error("bad_datetime", 400)
            if slot.end_at <= slot.start_at:
                return _json_error("end_before_start", 400)

            if "category" in data:
                data["category"] = normalize_category(data.get("category"))
            if "location" in data and data["location"]:
                data["location"] = str(data["location"]).strip()[:120]
            if "title" in data and data["title"]:
                data["title"] = str(data["title"]).strip()[:100]
            if "capacity" in data:
                try:
                    c = int(data["capacity"])
                    if c < 1:
                        return _json_error("bad_capacity", 400)
                except Exception:
                    return _json_error("bad_capacity", 400)

            for k in ["title","category","location","capacity","contact_method","booking_link","price_cents","notes"]:
                if k in data:
                    setattr(slot, k, data[k])

            if "status" in data:
                new_status = str(data["status"])
                cur_status = slot.status
                if new_status not in VALID_STATUSES:
                    return _json_error("bad_status", 400)
                if not _status_transition_ok(cur_status, new_status):
                    return _json_error("transition_forbidden", 409)
                if new_status == "published":
                    if slot.start_at.replace(tzinfo=timezone.utc) <= _now():
                        return _json_error("start_in_past", 409)
                    if (slot.capacity or 1) < 1:
                        return _json_error("bad_capacity", 400)
                slot.status = new_status

            try:
                s.commit()
            except IntegrityError as e:
                s.rollback()
                constraint = getattr(getattr(getattr(e, "orig", None), "diag", None), "constraint_name", None)
                if constraint == "slot_category_check":
                    return jsonify({"error": "bad_category", "detail": "Kategorie entspricht nicht den DB-Vorgaben."}), 400
                return jsonify({"error":"db_constraint_error","constraint": constraint, "detail": str(e.orig)}), 400
            except SQLAlchemyError as e:
                s.rollback()
                return jsonify({"error":"db_error","detail":str(e)}), 400

            return jsonify({"ok": True})
    except Exception as e:
        print("[PUT /slots] server error:", traceback.format_exc(), flush=True)
        return jsonify({"error":"server_error","detail":str(e)}), 500

@app.delete("/slots/<slot_id>")
@auth_required()
def slots_delete(slot_id):
    with Session(engine) as s:
        slot = s.get(Slot, slot_id)
        if not slot or slot.provider_id != request.provider_id:
            return _json_error("not_found", 404)
        s.delete(slot); s.commit()
        return jsonify({"ok": True})


# --------------------------------------------------------
# Admin
# --------------------------------------------------------
@app.get("/admin/providers")
@auth_required(admin=True)
def admin_providers():
    status = request.args.get("status", "pending")
    with Session(engine) as s:
        items = s.scalars(select(Provider).where(Provider.status == status).order_by(Provider.created_at.asc())).all()
        return jsonify([{"id": p.id, "email": p.email, "company_name": p.company_name, "status": p.status} for p in items])

@app.post("/admin/providers/<pid>/approve")
@auth_required(admin=True)
def admin_provider_approve(pid):
    with Session(engine) as s:
        p = s.get(Provider, pid)
        if not p:
            return _json_error("not_found", 404)
        p.status = "approved"; s.commit()
        return jsonify({"ok": True})

@app.post("/admin/providers/<pid>/reject")
@auth_required(admin=True)
def admin_provider_reject(pid):
    with Session(engine) as s:
        p = s.get(Provider, pid)
        if not p:
            return _json_error("not_found", 404)
        p.status = "rejected"; s.commit()
        return jsonify({"ok": True})

@app.get("/admin/slots")
@auth_required(admin=True)
def admin_slots():
    status = request.args.get("status", "pending_review")
    with Session(engine) as s:
        items = s.scalars(select(Slot).where(Slot.status == status).order_by(Slot.start_at.asc())).all()
        return jsonify([slot_to_json(x) for x in items])

@app.post("/admin/slots/<sid>/publish")
@auth_required(admin=True)
def admin_slot_publish(sid):
    with Session(engine) as s:
        slot = s.get(Slot, sid, with_for_update=True)
        if not slot:
            return _json_error("not_found", 404)
        if not _status_transition_ok(slot.status, "published"):
            return _json_error("transition_forbidden", 409)
        if slot.start_at <= _now():
            return _json_error("start_in_past", 409)
        slot.status = "published"; s.commit()
        return jsonify({"ok": True})

@app.post("/admin/slots/<sid>/reject")
@auth_required(admin=True)
def admin_slot_reject(sid):
    with Session(engine) as s:
        slot = s.get(Slot, sid)
        if not slot:
            return _json_error("not_found", 404)
        slot.status = "archived"; s.commit()
        return jsonify({"ok": True})


# --------------------------------------------------------
# Public (Slots + Booking)
# --------------------------------------------------------
BOOKING_HOLD_MIN = 15  # Minuten

def _booking_token(booking_id: str) -> str:
    return jwt.encode(
        {"sub": booking_id, "typ": "booking", "iss": JWT_ISS,
         "exp": int((_now() + timedelta(hours=6)).timestamp())},
        SECRET, algorithm="HS256",
    )

def _verify_booking_token(token: str) -> str | None:
    try:
        data = jwt.decode(token, SECRET, algorithms=["HS256"], issuer=JWT_ISS)
        return data.get("sub") if data.get("typ") == "booking" else None
    except Exception:
        return None

def _haversine_km(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, atan2, sqrt
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


@app.get("/public/slots")
def public_slots():
    """
    Öffentliche Slot-Suche.

    Haupt-Parameter (neue Suche.html):
      - q         : Freitext (Titel/Kategorie)
      - location  : Ort / PLZ, wie im SLOT-Feld "Ort / PLZ" eingegeben
      - radius    : Umkreis in km (optional)
      - day       : YYYY-MM-DD (optional)
      - datum     : TT.MM.JJJJ (optional, alt)
      - category  : exakte Kategorie (optional)
      - include_full : "1" zeigt auch vollgebuchte Slots

    Abwärtskompatibel:
      - ort       : wird wie location behandelt
      - city, zip : werden weiterhin für Geocoding/Radius akzeptiert
    """
    # neue Parameter
    q_text      = (request.args.get("q") or "").strip()
    location_raw = (request.args.get("location") or "").strip()
    # alt: ort -> wie location behandeln, falls location leer
    if not location_raw:
        location_raw = (request.args.get("ort") or "").strip()

    radius_raw  = (request.args.get("radius") or "").strip()
    datum_raw   = (request.args.get("datum") or "").strip()
    _zeit       = (request.args.get("zeit") or "").strip()  # aktuell ignoriert

    # alte / zusätzliche Parameter
    category    = (request.args.get("category") or "").strip()
    city_q      = (request.args.get("city") or "").strip()
    zip_filter  = (request.args.get("zip") or "").strip()
    day_str     = (request.args.get("day") or "").strip()
    from_str    = (request.args.get("from") or "").strip()
    include_full = request.args.get("include_full") == "1"

    # Falls city/zip nicht explizit gesetzt sind, aus location_raw ableiten
    if location_raw and not zip_filter and not city_q:
        if location_raw.isdigit() and len(location_raw) == 5:
            zip_filter = location_raw
        else:
            city_q = location_raw

    # Wenn q exakt eine bekannte Branche ist, als Kategorie nutzen
    search_term = q_text
    if not category and q_text in BRANCHES:
        category = q_text
        # search_term bleibt, damit Titel mit 'Friseur' etc. trotzdem matchen

    # Radius parsen
    try:
        radius_km = float(radius_raw) if radius_raw else None
    except ValueError:
        radius_km = None

    # Datumslogik
    start_from = None
    end_until  = None
    try:
        if datum_raw:
            # Format TT.MM.JJJJ
            parts = datum_raw.split(".")
            if len(parts) == 3:
                d, m, y = map(int, parts)
                start_local = datetime(y, m, d, 0, 0, 0, tzinfo=BERLIN)
                end_local   = start_local + timedelta(days=1)
                start_from  = start_local.astimezone(timezone.utc)
                end_until   = end_local.astimezone(timezone.utc)
        elif day_str:
            # Format YYYY-MM-DD
            y, m, d = map(int, day_str.split("-"))
            start_local = datetime(y, m, d, 0, 0, 0, tzinfo=BERLIN)
            end_local   = start_local + timedelta(days=1)
            start_from  = start_local.astimezone(timezone.utc)
            end_until   = end_local.astimezone(timezone.utc)
        elif from_str:
            start_from = parse_iso_utc(from_str)
        else:
            start_from = _now()
    except Exception:
        start_from = _now()
        end_until  = None

    with Session(engine) as s:
        origin_lat = origin_lon = None
        # Geocoding für Radius: Eingabe wird über zip/city abgebildet
        if radius_km is not None and (zip_filter or city_q):
            origin_lat, origin_lon = geocode_cached(
                s,
                zip_filter if zip_filter else None,
                None if zip_filter else city_q
            )

        # Buchungsaggregat
        bq = (
            select(Booking.slot_id, func.count().label("booked"))
            .where(Booking.status.in_(["hold", "confirmed"]))
            .group_by(Booking.slot_id)
            .subquery()
        )

        # Basis-Query
        sq = (
            select(
                Slot,
                Provider.zip.label("p_zip"),
                Provider.city.label("p_city"),
                func.coalesce(bq.c.booked, 0).label("booked")
            )
            .join(Provider, Provider.id == Slot.provider_id)
            .outerjoin(bq, bq.c.slot_id == Slot.id)
            .where(Slot.status == "published")
        )

        # Zeitfilter
        if start_from is not None:
            sq = sq.where(Slot.start_at >= start_from)
        if end_until is not None:
            sq = sq.where(Slot.start_at < end_until)

        # Kategorie-Filter
        if category:
            if category in BRANCHES:
                sq = sq.where(Slot.category == category)
            else:
                sq = sq.where(Slot.category.ilike(f"%{category}%"))

        # Orts-/PLZ-Filter: jetzt nur noch über Slot.location (nicht Provider-Profil)
        # Nur anwenden, wenn KEIN Radius (bei Radius filtern wir später per Distanz)
        # Für Kompatibilität fallback auf city_q/zip_filter, falls location_raw leer
        if radius_km is None:
            loc_for_filter = location_raw or city_q or zip_filter
            if loc_for_filter:
                pattern_loc = f"%{loc_for_filter}%"
                sq = sq.where(Slot.location.ilike(pattern_loc))

        # Textsuche auf Titel/Kategorie
        if search_term:
            pattern = f"%{search_term}%"
            sq = sq.where(
                or_(
                    Slot.title.ilike(pattern),
                    Slot.category.ilike(pattern),
                )
            )

        # Sortierung & Limit
        sq = sq.order_by(Slot.start_at.asc()).limit(300)

        rows = s.execute(sq).all()

        out = []
        for slot, p_zip, p_city, booked in rows:
            cap = slot.capacity or 1
            available = max(0, cap - int(booked or 0))
            if not include_full and available <= 0:
                continue

            # Radiusfilter (weiterhin über Provider-Standort, da Slot.location nur Text ist)
            if radius_km is not None:
                if origin_lat is None or origin_lon is None:
                    # ohne Mittelpunkt macht Umkreissuche keinen Sinn
                    continue
                plat, plon = geocode_cached(s, p_zip, p_city)
                if plat is None or plon is None:
                    continue
                if _haversine_km(origin_lat, origin_lon, plat, plon) > radius_km:
                    continue

            out.append({
                "id": slot.id,
                "title": slot.title,
                "category": slot.category,
                "start_at": _from_db_as_iso_utc(slot.start_at),
                "end_at": _from_db_as_iso_utc(slot.end_at),
                "location": slot.location,
                "provider_id": slot.provider_id,
                "provider_zip": p_zip,
                "provider_city": p_city,
                "available": available,
            })

        return jsonify(out)

@app.post("/public/book")
def public_book():
    data = request.get_json(force=True)
    slot_id = (data.get("slot_id") or "").strip()
    name    = (data.get("name") or "").strip()
    email   = (data.get("email") or "").strip().lower()

    if not slot_id or not name or not email:
        return _json_error("missing_fields")

    try:
        email = validate_email(email).email
    except EmailNotValidError:
        return _json_error("invalid_email", 400)

    with Session(engine) as s:
        slot = s.get(Slot, slot_id, with_for_update=True)
        if not slot: return _json_error("not_found", 404)
        if slot.status != "published" or slot.start_at <= _now():
            return _json_error("not_bookable", 409)

        active = s.scalar(
            select(func.count()).select_from(Booking).where(
                and_(Booking.slot_id == slot.id, Booking.status.in_(["hold","confirmed"]))
            )
        ) or 0
        if active >= (slot.capacity or 1):
            return _json_error("slot_full", 409)

        b = Booking(slot_id=slot.id, customer_name=name, customer_email=email, status="hold")
        s.add(b); s.commit()

        token = _booking_token(b.id)
        base = _external_base()
        confirm_link = f"{base}{url_for('public_confirm')}?token={token}"
        cancel_link  = f"{base}{url_for('public_cancel')}?token={token}"
        send_mail(
            email,
            "Bitte Terminbuchung bestätigen",
            text=f"Hallo {name},\n\nbitte bestätige deine Buchung:\n{confirm_link}\n\nStornieren:\n{cancel_link}\n",
            tag="booking_request",
            metadata={"slot_id": str(slot.id)}
        )
        return jsonify({"ok": True})

@app.get("/public/confirm")
def public_confirm():
    """
    Bestätigt eine Terminbuchung über den Token aus der E-Mail
    und zeigt danach die HTML-Bestätigungsseite an.
    """
    token = request.args.get("token")
    booking_id = _verify_booking_token(token) if token else None
    if not booking_id:
        return _json_error("invalid_token", 400)

    try:
        with Session(engine) as s:
            # Buchung holen
            b = s.get(Booking, booking_id, with_for_update=True)
            if not b:
                return _json_error("not_found", 404)

            # Slot & Provider für die Anzeige laden
            slot_obj = s.get(Slot, b.slot_id) if b.slot_id else None
            provider_obj = s.get(Provider, slot_obj.provider_id) if slot_obj else None

            # Wurde die Buchung bereits bestätigt?
            already_confirmed = (b.status == "confirmed")

            # Falls die Buchung noch im Hold-Status ist, jetzt versuchen zu bestätigen
            if b.status == "hold":
                # Hold abgelaufen?
                if (_now() - b.created_at) > timedelta(minutes=BOOKING_HOLD_MIN):
                    b.status = "canceled"
                    s.commit()
                    return _json_error("hold_expired", 409)

                # Slot noch vorhanden?
                if not slot_obj:
                    b.status = "canceled"
                    s.commit()
                    return _json_error("slot_missing", 404)

                # Kapazität prüfen
                active = s.scalar(
                    select(func.count()).select_from(Booking).where(
                        and_(Booking.slot_id == slot_obj.id,
                             Booking.status.in_(["hold", "confirmed"]))
                    )
                ) or 0
                if active > (slot_obj.capacity or 1):
                    b.status = "canceled"
                    s.commit()
                    return _json_error("slot_full", 409)

                # Jetzt bestätigen
                b.status = "confirmed"
                b.confirmed_at = _now()
                s.commit()

                # Bestätigungs-Mail nur beim ersten Mal schicken
                send_mail(
                    b.customer_email,
                    "Termin bestätigt",
                    text="Dein Termin ist bestätigt.",
                    tag="booking_confirmed",
                    metadata={"slot_id": str(slot_obj.id)}
                )

            elif b.status == "canceled":
                # Stornierte Buchungen nicht mehr bestätigen
                return _json_error("booking_canceled", 409)

            # ==== ORM-Objekte in einfache Dicts umwandeln, bevor Session zu ist ====
            booking = {
                "id": b.id,
                "customer_name": b.customer_name,
                "customer_email": b.customer_email,
                "status": b.status,
                "created_at": b.created_at,
                "confirmed_at": getattr(b, "confirmed_at", None),
            }

            slot = None
            if slot_obj is not None:
                slot = {
                    "id": slot_obj.id,
                    "title": slot_obj.title,
                    "start_at": slot_obj.start_at,
                    "end_at": slot_obj.end_at,
                    "location": slot_obj.location,
                }

            provider = None
            if provider_obj is not None:
                provider = {
                    "company_name": provider_obj.company_name,
                    "zip": provider_obj.zip,
                    "city": provider_obj.city,
                }

        # Session ist hier bereits zu, aber wir arbeiten nur noch mit Dicts.
        return render_template(
            "buchung_erfolg.html",
            booking=booking,
            slot=slot,
            provider=provider,
            bereits_bestaetigt=already_confirmed,
            frontend_url=FRONTEND_URL,
        )
    except Exception as e:
        app.logger.exception("public_confirm failed")
        return jsonify({"error": "server_error"}), 500


@app.get("/public/cancel")
def public_cancel():
    """
    Storniert eine Buchung über den Token aus der E-Mail
    und zeigt danach die HTML-Storno-Seite an.
    """
    token = request.args.get("token")
    booking_id = _verify_booking_token(token) if token else None
    if not booking_id:
        return _json_error("invalid_token", 400)

    try:
        with Session(engine) as s:
            b = s.get(Booking, booking_id, with_for_update=True)
            if not b:
                return _json_error("not_found", 404)

            # Slot & Provider laden (für Anzeige)
            slot_obj = s.get(Slot, b.slot_id) if b.slot_id else None
            provider_obj = s.get(Provider, slot_obj.provider_id) if slot_obj else None

            already_canceled = (b.status == "canceled")

            # Nur wenn noch nicht storniert, jetzt stornieren
            if b.status in ("hold", "confirmed"):
                b.status = "canceled"
                s.commit()

            # Optional: bei bereits "canceled" nichts ändern, aber trotzdem Seite anzeigen

            # ==== ORM-Objekte in Dicts umwandeln ====
            booking = {
                "id": b.id,
                "customer_name": b.customer_name,
                "customer_email": b.customer_email,
                "status": b.status,
                "created_at": b.created_at,
                "confirmed_at": getattr(b, "confirmed_at", None),
            }

            slot = None
            if slot_obj is not None:
                slot = {
                    "id": slot_obj.id,
                    "title": slot_obj.title,
                    "start_at": slot_obj.start_at,
                    "end_at": slot_obj.end_at,
                    "location": slot_obj.location,
                }

            provider = None
            if provider_obj is not None:
                provider = {
                    "company_name": provider_obj.company_name,
                    "zip": provider_obj.zip,
                    "city": provider_obj.city,
                }

        return render_template(
            "buchung_storniert.html",
            booking=booking,
            slot=slot,
            provider=provider,
            bereits_storniert=already_canceled,
            frontend_url=FRONTEND_URL,
        )
    except Exception as e:
        app.logger.exception("public_cancel failed")
        return jsonify({"error": "server_error"}), 500


# --------------------------------------------------------
# Start
# --------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
