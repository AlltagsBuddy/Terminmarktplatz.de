# app.py — API + HTML (Root-Templates; Render & Local)
import os
import traceback
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from email_validator import validate_email, EmailNotValidError
from flask import (
    Flask, request, redirect, jsonify, make_response,
    render_template, url_for, abort
)
from flask_cors import CORS
from sqlalchemy import create_engine, select, and_, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from argon2 import PasswordHasher
import jwt

from models import Base, Provider, Slot, Booking

# --------------------------------------------------------
# Init / Paths / Mode
# --------------------------------------------------------
load_dotenv()

APP_ROOT     = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR   = os.path.join(APP_ROOT, "static")
TEMPLATE_DIR = APP_ROOT  # HTML-Dateien liegen im Projekt-Root

IS_RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID") or os.environ.get("RENDER_EXTERNAL_URL"))
API_ONLY  = os.environ.get("API_ONLY") == "1"

app = Flask(
    __name__,
    static_folder=STATIC_DIR,
    static_url_path="/static",
    template_folder=TEMPLATE_DIR,
)

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
MAIL_FROM         = os.environ.get("MAIL_FROM", "no-reply@example.com")
REPLY_TO          = os.environ.get("REPLY_TO", MAIL_FROM)
MAIL_PROVIDER     = os.environ.get("MAIL_PROVIDER", "console")
POSTMARK_TOKEN    = os.environ.get("POSTMARK_TOKEN", "")
CONTACT_TO        = os.environ.get("CONTACT_TO", MAIL_FROM)

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

# SQLAlchemy auf psycopg v3 biegen
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DB_URL.startswith("postgresql://"):
    DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# --------------------------------------------------------
# DB & Crypto
# --------------------------------------------------------
engine = create_engine(DB_URL, pool_pre_ping=True)
ph = PasswordHasher(time_cost=2, memory_cost=102400, parallelism=8)

# --------------------------------------------------------
# CORS & Security Headers
# --------------------------------------------------------
ALLOWED_ORIGINS = ["*"]
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
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
)

@app.after_request
def add_headers(resp):
    resp.headers.setdefault("Cache-Control", "no-store")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp

# --------------------------------------------------------
# Time helpers (einheitlich!)
# --------------------------------------------------------
def parse_iso_utc(s: str) -> datetime:
    """
    Akzeptiert ISO-Strings mit 'Z' (UTC) oder mit Offset (+00:00).
    Gibt immer einen AWARE datetime in UTC zurück.
    """
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
    """
    Konvertiert Datum nach UTC und entfernt tzinfo.
    Für TIMESTAMP WITHOUT TIME ZONE (Postgres).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)

def _from_db_as_iso_utc(dt: datetime) -> str:
    """
    Gibt ISO8601 in UTC zurück, normalisiert auf 'Z'.
    Falls DB naive UTC speichert, behandeln wir sie als UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")

def parse_local_date(s: str | None) -> datetime.date:
    """
    Flexibler Datumsparser für UI: 'YYYY-MM-DD' oder 'DD.MM.YYYY'.
    Fällt auf heutiges Datum (Europe/Berlin) zurück.
    """
    berlin = ZoneInfo("Europe/Berlin")
    if not s:
        return datetime.now(berlin).date()
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return datetime.now(berlin).date()

# --------------------------------------------------------
# Kategorien-Whitelist & Normalizer
# --------------------------------------------------------
BRANCHES = {
    "Friseur", "Kosmetik", "Physiotherapie", "Nagelstudio", "Zahnarzt",
    "Handwerk", "KFZ-Service", "Fitness", "Coaching", "Tierarzt",
    "Behörde", "Sonstiges"
}

def normalize_category(raw: str | None) -> str:
    """Gültige Kategorie für die DB zurückgeben; unbekannt => 'Sonstiges'."""
    if raw is None:
        return "Sonstiges"
    val = str(raw).strip()
    if not val:
        return "Sonstiges"
    return val if val in BRANCHES else "Sonstiges"

# --------------------------------------------------------
# Utilities
# --------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)

def _json_error(msg, code=400):
    return jsonify({"error": msg}), code

def issue_tokens(provider_id: str, is_admin: bool):
    now = _now()
    access = jwt.encode(
        {"sub": provider_id, "adm": is_admin, "iss": JWT_ISS, "aud": JWT_AUD,
         "iat": int(now.timestamp()),
         "exp": int((now + timedelta(minutes=JWT_EXP_MIN)).timestamp())},
        SECRET, algorithm="HS256",
    )
    refresh = jwt.encode(
        {"sub": provider_id, "iss": JWT_ISS, "aud": JWT_AUD, "typ": "refresh",
         "iat": int(now.timestamp()),
         "exp": int((now + timedelta(days=REFRESH_EXP_DAYS)).timestamp())},
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

def send_mail(to: str, subject: str, text: str):
    try:
        print(f"[mail] provider={MAIL_PROVIDER} from={MAIL_FROM} to={to}", flush=True)
        if MAIL_PROVIDER == "console":
            print(f"\n--- MAIL (console) ---\nFrom: {MAIL_FROM}\nTo: {to}\nSubject: {subject}\n\n{text}\n--- END ---\n", flush=True)
            return True, "console"

        if MAIL_PROVIDER == "postmark" and POSTMARK_TOKEN:
            import requests
            payload = {"From": MAIL_FROM, "To": to, "Subject": subject, "TextBody": text, "ReplyTo": REPLY_TO}
            r = requests.post(
                "https://api.postmarkapp.com/email",
                headers={
                    "X-Postmark-Server-Token": POSTMARK_TOKEN,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=12,
            )
            print("Postmark response:", r.status_code, r.text, flush=True)
            ok = 200 <= r.status_code < 300
            reason = f"{r.status_code} {r.text}"
            return ok, reason

        if MAIL_PROVIDER != "postmark":
            return False, f"provider={MAIL_PROVIDER} not supported"
        if not POSTMARK_TOKEN:
            return False, "missing POSTMARK_TOKEN"

    except Exception as e:
        print("send_mail exception:", repr(e), flush=True)
        return False, repr(e)

    return False, "unknown"

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

def _cookie_flags():
    if IS_RENDER:
        return {"httponly": True, "secure": True, "samesite": "None"}
    return {"httponly": True, "secure": False, "samesite": "Lax"}

# --- Slot-Status-Validierung -----------------------------------------------
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
            validate_email(email)
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
                      "Wir haben deine Nachricht erhalten und melden uns bald.\n\n— Terminmarktplatz")
        except Exception:
            pass

        return jsonify({"ok": bool(ok), "delivered": bool(ok), "reason": reason})
    except Exception as e:
        print("[public_contact] error:", repr(e), flush=True)
        return jsonify({"error": "server_error"}), 500

# --------------------------------------------------------
# Auth helpers
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

# --------------------------------------------------------
# Auth (JSON API)
# --------------------------------------------------------
@app.post("/auth/register")
def register():
    try:
        data = request.get_json(force=True)
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        try:
            validate_email(email)
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

        payload = {
            "sub": provider_id, "aud": "verify", "iss": JWT_ISS,
            "exp": int((_now() + timedelta(days=2)).timestamp())
        }
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        link = f"{BASE_URL}/auth/verify?token={token}"
        ok_mail, reason = send_mail(reg_email, "Bitte E-Mail bestätigen",
                                    f"Willkommen beim Terminmarktplatz.\n\nBitte bestätige deine E-Mail:\n{link}\n")
        return jsonify({"ok": True, "mail_sent": ok_mail, "mail_reason": reason})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "server_error", "detail": str(e)}), 500

@app.get("/auth/verify")
def auth_verify():
    token = request.args.get("token", "")
    debug = request.args.get("debug") == "1"

    def _ret(kind: str):
        url = f"{FRONTEND_URL}/login.html"
        if debug:
            return jsonify({"ok": kind == "1", "redirect": url})
        return redirect(url)

    if not token:
        return _ret("missing")

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

@app.post("/auth/logout")
@auth_required()
def auth_logout():
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie("access_token")
    resp.delete_cookie("refresh_token")
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

# --------------------------------------------------------
# HTML-Form Login (POST /login) → Redirect /anbieter-portal
# --------------------------------------------------------
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
            if not p: return _json_error("not_found", 404)

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

        return jsonify({"ok": True})
    except Exception as e:
        print("[/me] server error:", repr(e), flush=True)
        return jsonify({"error": "server_error"}), 500

# --------------------------------------------------------
# Slots (Provider)
# --------------------------------------------------------
@app.get("/slots")
@auth_required()
def slots_list():
    status = request.args.get("status")
    with Session(engine) as s:
        q = select(Slot).where(Slot.provider_id == request.provider_id)
        if status:
            q = q.where(Slot.status == status)
        slots = s.scalars(q.order_by(Slot.start_at.desc())).all()
        return jsonify([slot_to_json(x) for x in slots])

@app.post("/slots")
@auth_required()
def slots_create():
    try:
        data = request.get_json(force=True) or {}
        required = ["title", "category", "start_at", "end_at"]
        if any(k not in data or data[k] in (None, "") for k in required):
            return _json_error("missing_fields", 400)

        # Zeiten validieren
        try:
            start = parse_iso_utc(data["start_at"])
            end   = parse_iso_utc(data["end_at"])
        except Exception:
            return _json_error("bad_datetime", 400)
        if end <= start:
            return _json_error("end_before_start", 400)
        if start <= _now():
            return _json_error("start_in_past", 409)

        # Für DB (TIMESTAMP WITHOUT TIME ZONE) → UTC-naiv
        start_db = _to_db_utc_naive(start)
        end_db   = _to_db_utc_naive(end)

        with Session(engine) as s:
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
            location = (data.get("location") or None)
            if location:
                location = str(location).strip()[:120]

            slot = Slot(
                provider_id=request.provider_id,
                title=title,
                category=category,
                start_at=start_db, end_at=end_db,
                location=location,
                capacity=int(data.get("capacity") or 1),
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

            # Zeiten
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

            # Felder normalisieren
            if "category" in data:
                data["category"] = normalize_category(data.get("category"))
            if "location" in data and data["location"]:
                data["location"] = str(data["location"]).strip()[:120]
            if "title" in data and data["title"]:
                data["title"] = str(data["title"]).strip()[:100]

            for k in ["title","category","location","capacity","contact_method","booking_link","price_cents","notes"]:
                if k in data:
                    setattr(slot, k, data[k])

            # Statuswechsel
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

# ---- NEU: robuste Suche mit Stadt (Provider ODER Slot), Datum & Availability
@app.get("/public/slots")
def public_slots():
    """
    Query-Parameter:
      - city:       z.B. 'Bamberg' (optional)
      - day:        'YYYY-MM-DD' ODER 'DD.MM.YYYY' (optional, default: heute in Europe/Berlin)
      - category:   z.B. 'Physiotherapie' (optional)
      - zip:        (Kompatibilität: filtert weiterhin Provider.zip)
    """
    city       = request.args.get("city")
    day_raw    = request.args.get("day")
    category   = request.args.get("category")
    zip_filter = request.args.get("zip")

    # 1) Tagesrange in UTC bauen (lokale Mitternacht → UTC)
    day = parse_local_date(day_raw)
    berlin = ZoneInfo("Europe/Berlin")
    day_start_utc = datetime.combine(day, time.min, berlin).astimezone(timezone.utc)
    day_end_utc   = datetime.combine(day, time.max, berlin).astimezone(timezone.utc)

    with Session(engine) as s:
        # Subquery: aktive Buchungen je Slot (hold + confirmed)
        booked_sq = (
            select(Booking.slot_id, func.count().label("booked"))
            .where(Booking.status.in_(["hold", "confirmed"]))
            .group_by(Booking.slot_id)
            .subquery()
        )

        # Basis: veröffentlichte Slots am gewählten Tag
        q = (
            select(
                Slot,
                Provider.zip.label("provider_zip"),
                Provider.city.label("provider_city"),
                ( (Slot.capacity - func.coalesce(booked_sq.c.booked, 0)) ).label("available")
            )
            .join(Provider, Provider.id == Slot.provider_id)
            .outerjoin(booked_sq, booked_sq.c.slot_id == Slot.id)
            .where(
                and_(
                    Slot.status == "published",
                    Slot.start_at >= day_start_utc,
                    Slot.start_at <= day_end_utc,
                )
            )
        )

        # Stadt-Filter: Provider.city ODER Slot.location
        if city:
            like = f"%{city}%"
            q = q.where(or_(Provider.city.ilike(like), Slot.location.ilike(like)))

        # Kategorie (tolerant)
        if category:
            cat = str(category).strip()
            q = q.where(or_(func.lower(Slot.category) == func.lower(cat),
                            Slot.title.ilike(f"%{cat}%")))

        # PLZ (Kompatibilität)
        if zip_filter:
            q = q.where(Provider.zip == zip_filter)

        # nur freie Plätze
        q = q.where( (Slot.capacity - func.coalesce(booked_sq.c.booked, 0)) > 0 )

        rows = s.execute(q.order_by(Slot.start_at.asc()).limit(200)).all()

        def to_json(row):
            slot, p_zip, p_city, available = row
            return {
                "id": slot.id,
                "title": slot.title,
                "category": slot.category,
                "start_at": _from_db_as_iso_utc(slot.start_at),
                "end_at": _from_db_as_iso_utc(slot.end_at),
                "location": slot.location,
                "provider_id": slot.provider_id,
                "provider_zip": p_zip,
                "provider_city": p_city,
                "available": int(available),
            }

        return jsonify([to_json(r) for r in rows])

@app.post("/public/book")
def public_book():
    data = request.get_json(force=True)
    slot_id = (data.get("slot_id") or "").strip()
    name    = (data.get("name") or "").strip()
    email   = (data.get("email") or "").strip()
    if not slot_id or not name or not email:
        return _json_error("missing_fields")

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
        send_mail(email, "Bitte Terminbuchung bestätigen",
                  f"Hallo {name},\n\nbitte bestätige deine Buchung:\n{confirm_link}\n\nStornieren:\n{cancel_link}\n")
        return jsonify({"ok": True})

@app.get("/public/confirm")
def public_confirm():
    token = request.args.get("token")
    booking_id = _verify_booking_token(token) if token else None
    if not booking_id:
        return _json_error("invalid_token", 400)

    with Session(engine) as s:
        b = s.get(Booking, booking_id, with_for_update=True)
        if not b or b.status != "hold":
            return _json_error("not_found_or_state", 404)
        if (_now() - b.created_at) > timedelta(minutes=BOOKING_HOLD_MIN):
            b.status = "canceled"; s.commit()
            return _json_error("hold_expired", 409)

        slot = s.get(Slot, b.slot_id, with_for_update=True)
        active = s.scalar(
            select(func.count()).select_from(Booking).where(
                and_(Booking.slot_id == slot.id, Booking.status.in_(["hold","confirmed"]))
            )
        ) or 0
        if active > (slot.capacity or 1):
            b.status = "canceled"; s.commit()
            return _json_error("slot_full", 409)

        b.status = "confirmed"; b.confirmed_at = _now()
        s.commit()
        send_mail(b.customer_email, "Termin bestätigt", "Dein Termin ist bestätigt.")
        return jsonify({"ok": True})

@app.get("/public/cancel")
def public_cancel():
    token = request.args.get("token")
    booking_id = _verify_booking_token(token) if token else None
    if not booking_id:
        return _json_error("invalid_token", 400)
    with Session(engine) as s:
        b = s.get(Booking, booking_id, with_for_update=True)
        if not b or b.status == "canceled":
            return _json_error("not_found_or_state", 404)
        b.status = "canceled"; s.commit()
        return jsonify({"ok": True})

# --------------------------------------------------------
# Start
# --------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
