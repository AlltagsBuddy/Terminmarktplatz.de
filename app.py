# app.py – konsolidiert & statics-fix
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from email_validator import validate_email, EmailNotValidError
from flask import (
    Flask, request, redirect, jsonify, make_response, render_template
)
from flask_cors import CORS
from sqlalchemy import create_engine, select, and_, func
from sqlalchemy.orm import Session
from argon2 import PasswordHasher
import jwt

from models import Base, Provider, Slot, Booking

# --------------------------------------------------------
# Init
# --------------------------------------------------------
load_dotenv()

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_ROOT, "static")
TEMPLATE_DIR = os.path.join(APP_ROOT, "templates")

app = Flask(
    __name__,
    static_folder=STATIC_DIR,        # -> <project>/static
    static_url_path="/static",       # -> /static/...
    template_folder=TEMPLATE_DIR,    # -> <project>/templates
)

# Sichtbares Startup-Logging
print("STATIC FOLDER:", app.static_folder)
print("TEMPLATES FOLDER:", app.template_folder)
logo_path = os.path.join(app.static_folder, "terminmarktplatz-logo.png")
print("LOGO EXISTS:", os.path.isfile(logo_path))

# CORS (für spätere API-Calls)
CORS(
    app,
    supports_credentials=True,
    origins=[
        "http://localhost:5000",
        "https://terminmarktplatz.de",
        "https://www.terminmarktplatz.de",
    ],
)

# --------------------------------------------------------
# Config
# --------------------------------------------------------
SECRET = os.environ.get("SECRET_KEY", "dev")
DB_URL = os.environ.get("DATABASE_URL")
JWT_ISS = os.environ.get("JWT_ISS", "terminmarktplatz")
JWT_AUD = os.environ.get("JWT_AUD", "terminmarktplatz_client")
JWT_EXP_MIN = int(os.environ.get("JWT_EXP_MINUTES", "60"))
REFRESH_EXP_DAYS = int(os.environ.get("REFRESH_EXP_DAYS", "14"))
MAIL_FROM = os.environ.get("MAIL_FROM", "no-reply@example.com")
MAIL_PROVIDER = os.environ.get("MAIL_PROVIDER", "console")
POSTMARK_TOKEN = os.environ.get("POSTMARK_TOKEN", "")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")

engine = create_engine(DB_URL, pool_pre_ping=True)
ph = PasswordHasher(time_cost=2, memory_cost=102400, parallelism=8)

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
        {
            "sub": provider_id,
            "adm": is_admin,
            "iss": JWT_ISS,
            "aud": JWT_AUD,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=JWT_EXP_MIN)).timestamp()),
        },
        SECRET,
        algorithm="HS256",
    )
    refresh = jwt.encode(
        {
            "sub": provider_id,
            "iss": JWT_ISS,
            "aud": JWT_AUD,
            "typ": "refresh",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=REFRESH_EXP_DAYS)).timestamp()),
        },
        SECRET,
        algorithm="HS256",
    )
    return access, refresh

def auth_required(admin: bool = False):
    def wrapper(fn):
        def inner(*args, **kwargs):
            token = request.cookies.get("access_token")
            if not token:
                return _json_error("unauthorized", 401)
            try:
                data = jwt.decode(
                    token, SECRET, algorithms=["HS256"], audience=JWT_AUD, issuer=JWT_ISS
                )
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
    if MAIL_PROVIDER == "console":
        print(f"\n--- MAIL (console) ---\nTo: {to}\nFrom: {MAIL_FROM}\nSubject: {subject}\n\n{text}\n--- END ---\n")
        return True
    elif MAIL_PROVIDER == "postmark" and POSTMARK_TOKEN:
        import requests
        r = requests.post(
            "https://api.postmarkapp.com/email",
            headers={"X-Postmark-Server-Token": POSTMARK_TOKEN},
            json={"From": MAIL_FROM, "To": to, "Subject": subject, "TextBody": text},
        )
        return r.status_code == 200
    return False

def slot_to_json(x: Slot):
    return {
        "id": x.id,
        "provider_id": x.provider_id,
        "title": x.title,
        "category": x.category,
        "start_at": x.start_at.isoformat(),
        "end_at": x.end_at.isoformat(),
        "location": x.location,
        "capacity": x.capacity,
        "contact_method": x.contact_method,
        "booking_link": x.booking_link,
        "price_cents": x.price_cents,
        "notes": x.notes,
        "status": x.status,
        "created_at": x.created_at.isoformat(),
    }

# --------------------------------------------------------
# Kleine Helfer / Debug
# --------------------------------------------------------
@app.get("/__debug__/static-list")
def dbg_list():
    try:
        return "<br>".join(sorted(os.listdir(app.static_folder)))
    except Exception as e:
        return f"ERR: {e}", 500

@app.get("/logo-test")
def logo_test():
    # -> sollte auf /static/terminmarktplatz-logo.png landen
    return redirect("/static/terminmarktplatz-logo.png", code=302)

@app.get("/favicon.ico")
def favicon():
    return redirect("/static/favicon.ico", code=302)

@app.get("/robots.txt")
def robots():
    return redirect("/static/robots.txt", code=302)

# --------------------------------------------------------
# Canonical Redirect (www → non-www)
# --------------------------------------------------------
@app.before_request
def redirect_www():
    host = request.host.lower()
    if host.startswith("www.terminmarktplatz.de"):
        path = request.full_path
        if path.endswith("?"):
            path = path[:-1]
        return redirect(f"https://terminmarktplatz.de{path}", code=301)

# --------------------------------------------------------
# Seiten aus templates
# --------------------------------------------------------
@app.get("/")
def page_home():
    return render_template("index.html")

@app.get("/index.html")
def page_home_canonical():
    return redirect("/", code=301)

@app.get("/login")
def page_login():
    return render_template("login.html")

@app.get("/impressum")
def page_impressum():
    return render_template("impressum.html")

@app.get("/datenschutz")
def page_datenschutz():
    return render_template("datenschutz.html")

@app.get("/portal")
def page_portal():
    return render_template("portal.html")

@app.get("/wie-es-funktioniert")
def page_howitworks():
    return render_template("wie-es-funktioniert.html")

@app.get("/kategorien")
def page_kategorien():
    return render_template("kategorien.html")

@app.get("/preise")
def page_preise():
    return render_template("preise.html")

# --------------------------------------------------------
# Auth
# --------------------------------------------------------
@app.post("/auth/register")
def register():
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
        s.add(p)
        s.commit()
        payload = {
            "sub": p.id,
            "aud": "verify",
            "iss": JWT_ISS,
            "exp": int((_now() + timedelta(days=2)).timestamp()),
        }
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        link = f"{BASE_URL}/auth/verify?token={token}"
        send_mail(p.email, "Bitte E-Mail bestätigen", f"Willkommen beim Terminmarktplatz. Bitte bestätigen: {link}")
        return jsonify({"ok": True})

@app.get("/auth/verify")
def verify():
    token = request.args.get("token")
    if not token:
        return _json_error("missing_token")
    try:
        data = jwt.decode(token, SECRET, algorithms=["HS256"], audience="verify", issuer=JWT_ISS)
    except Exception:
        return _json_error("invalid_token", 400)

    with Session(engine) as s:
        p = s.get(Provider, data["sub"])
        if not p:
            return _json_error("not_found", 404)
        p.email_verified_at = _now()
        s.commit()
    return jsonify({"ok": True})

@app.post("/auth/login")
def auth_login():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    with Session(engine) as s:
        p = s.scalar(select(Provider).where(Provider.email == email))
        if not p:
            return _json_error("invalid_credentials", 401)
        try:
            ph.verify(p.pw_hash, password)
        except Exception:
            return _json_error("invalid_credentials", 401)
        if not p.email_verified_at:
            return _json_error("email_not_verified", 403)
        access, refresh = issue_tokens(p.id, p.is_admin)

    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie("access_token", access, max_age=JWT_EXP_MIN * 60, httponly=True, secure=True, samesite="Lax")
    resp.set_cookie("refresh_token", refresh, max_age=REFRESH_EXP_DAYS * 86400, httponly=True, secure=True, samesite="Lax")
    return resp

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
        return _json_error("unauthorized", 401)
    try:
        data = jwt.decode(token, SECRET, algorithms=["HS256"], audience=JWT_AUD, issuer=JWT_ISS)
        if data.get("typ") != "refresh":
            raise Exception("wrong type")
    except Exception:
        return _json_error("unauthorized", 401)

    access, _ = issue_tokens(data["sub"], bool(data.get("adm")))
    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie("access_token", access, max_age=JWT_EXP_MIN * 60, httponly=True, secure=True, samesite="Lax")
    return resp

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
        return jsonify(
            {
                "id": p.id,
                "email": p.email,
                "status": p.status,
                "is_admin": p.is_admin,
                "company_name": p.company_name,
                "branch": p.branch,
                "street": p.street,
                "zip": p.zip,
                "city": p.city,
                "phone": p.phone,
                "whatsapp": p.whatsapp,
            }
        )

@app.put("/me")
@auth_required()
def me_update():
    data = request.get_json(force=True)
    allowed = {"company_name", "branch", "street", "zip", "city", "phone", "whatsapp"}
    with Session(engine) as s:
        p = s.get(Provider, request.provider_id)
        if not p:
            return _json_error("not_found", 404)
        for k, v in data.items():
            if k in allowed:
                setattr(p, k, v)
        s.commit()
        return jsonify({"ok": True})

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
    data = request.get_json(force=True)
    required = ["title", "category", "start_at", "end_at"]
    if any(k not in data for k in required):
        return _json_error("missing_fields")
    try:
        start = datetime.fromisoformat(data["start_at"])
        end = datetime.fromisoformat(data["end_at"])
    except Exception:
        return _json_error("bad_datetime")
    if end <= start:
        return _json_error("end_before_start")

    with Session(engine) as s:
        count = s.scalar(
            select(func.count())
            .select_from(Slot)
            .where(and_(Slot.provider_id == request.provider_id, Slot.status.in_(["pending_review", "published"])))
        )
        if count and count > 200:
            return _json_error("limit_reached")
        slot = Slot(
            provider_id=request.provider_id,
            title=data["title"],
            category=data["category"],
            start_at=start,
            end_at=end,
            location=data.get("location"),
            capacity=int(data.get("capacity") or 1),
            contact_method=data.get("contact_method") or "mail",
            booking_link=data.get("booking_link"),
            price_cents=data.get("price_cents"),
            notes=data.get("notes"),
            status="pending_review",
        )
        s.add(slot)
        s.commit()
        return jsonify(slot_to_json(slot)), 201

@app.put("/slots/<slot_id>")
@auth_required()
def slots_update(slot_id):
    data = request.get_json(force=True)
    with Session(engine) as s:
        slot = s.get(Slot, slot_id)
        if not slot or slot.provider_id != request.provider_id:
            return _json_error("not_found", 404)
        if "start_at" in data:
            slot.start_at = datetime.fromisoformat(data["start_at"])
        if "end_at" in data:
            slot.end_at = datetime.fromisoformat(data["end_at"])
        for k in [
            "title", "category", "location", "capacity",
            "contact_method", "booking_link", "price_cents",
            "notes", "status",
        ]:
            if k in data:
                setattr(slot, k, data[k])
        s.commit()
        return jsonify({"ok": True})

@app.delete("/slots/<slot_id>")
@auth_required()
def slots_delete(slot_id):
    with Session(engine) as s:
        slot = s.get(Slot, slot_id)
        if not slot or slot.provider_id != request.provider_id:
            return _json_error("not_found", 404)
        s.delete(slot)
        s.commit()
        return jsonify({"ok": True})

# --------------------------------------------------------
# Admin
# --------------------------------------------------------
@app.get("/admin/providers")
@auth_required(admin=True)
def admin_providers():
    status = request.args.get("status", "pending")
    with Session(engine) as s:
        items = s.scalars(
            select(Provider).where(Provider.status == status).order_by(Provider.created_at.asc())
        ).all()
        return jsonify(
            [{"id": p.id, "email": p.email, "company_name": p.company_name, "status": p.status} for p in items]
        )

@app.post("/admin/providers/<pid>/approve")
@auth_required(admin=True)
def admin_provider_approve(pid):
    with Session(engine) as s:
        p = s.get(Provider, pid)
        if not p:
            return _json_error("not_found", 404)
        p.status = "approved"
        s.commit()
        return jsonify({"ok": True})

@app.post("/admin/providers/<pid>/reject")
@auth_required(admin=True)
def admin_provider_reject(pid):
    with Session(engine) as s:
        p = s.get(Provider, pid)
        if not p:
            return _json_error("not_found", 404)
        p.status = "rejected"
        s.commit()
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
        slot = s.get(Slot, sid)
        if not slot:
            return _json_error("not_found", 404)
        slot.status = "published"
        s.commit()
        return jsonify({"ok": True})

@app.post("/admin/slots/<sid>/reject")
@auth_required(admin=True)
def admin_slot_reject(sid):
    with Session(engine) as s:
        slot = s.get(Slot, sid)
        if not slot:
            return _json_error("not_found", 404)
        slot.status = "archived"
        s.commit()
        return jsonify({"ok": True})

# --------------------------------------------------------
# Public (Slots + Booking)
# --------------------------------------------------------
BOOKING_HOLD_MIN = 15  # Minuten

def _booking_token(booking_id: str) -> str:
    return jwt.encode(
        {"sub": booking_id, "typ": "booking", "iss": JWT_ISS, "exp": int((_now() + timedelta(hours=6)).timestamp())},
        SECRET,
        algorithm="HS256",
    )

def _verify_booking_token(token: str) -> str | None:
    try:
        data = jwt.decode(token, SECRET, algorithms=["HS256"], issuer=JWT_ISS)
        return data.get("sub") if data.get("typ") == "booking" else None
    except Exception:
        return None

@app.get("/public/slots")
def public_slots():
    category = request.args.get("category")
    since = request.args.get("from")
    zip_filter = request.args.get("zip")

    start_from = datetime.fromisoformat(since) if since else _now()
    with Session(engine) as s:
        q = select(Slot).join(Provider).where(and_(Slot.status == "published", Slot.start_at >= start_from))
        if category:
            q = q.where(Slot.category == category)
        if zip_filter:
            q = q.where(Provider.zip == zip_filter)  # exakte PLZ
        items = s.scalars(q.order_by(Slot.start_at.asc()).limit(200)).all()

        def to_json(x: Slot):
            return {
                "id": x.id,
                "title": x.title,
                "category": x.category,
                "start_at": x.start_at.isoformat(),
                "end_at": x.end_at.isoformat(),
                "location": x.location,
                "provider_id": x.provider_id,
            }

        return jsonify([to_json(x) for x in items])

@app.post("/public/book")
def public_book():
    data = request.get_json(force=True)
    slot_id = (data.get("slot_id") or "").strip()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    if not slot_id or not name or not email:
        return _json_error("missing_fields")

    with Session(engine) as s:
        slot = s.get(Slot, slot_id, with_for_update=True)
        if not slot:
            return _json_error("not_found", 404)
        if slot.status != "published" or slot.start_at <= _now():
            return _json_error("not_bookable", 409)

        active = s.scalar(
            select(func.count()).select_from(Booking).where(
                and_(Booking.slot_id == slot.id, Booking.status.in_(["hold", "confirmed"]))
            )
        ) or 0
        if active >= (slot.capacity or 1):
            return _json_error("slot_full", 409)

        b = Booking(slot_id=slot.id, customer_name=name, customer_email=email, status="hold")
        s.add(b)
        s.commit()

        token = _booking_token(b.id)
        base = os.environ.get("BASE_URL", "https://api.terminmarktplatz.de")
        confirm_link = f"{base}/public/confirm?token={token}"
        cancel_link = f"{base}/public/cancel?token={token}"
        send_mail(
            email,
            "Bitte Terminbuchung bestätigen",
            f"Hallo {name},\n\nbitte bestätige deine Buchung:\n{confirm_link}\n\nStornieren:\n{cancel_link}\n",
        )
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
            b.status = "canceled"
            s.commit()
            return _json_error("hold_expired", 409)

        slot = s.get(Slot, b.slot_id, with_for_update=True)
        active = s.scalar(
            select(func.count()).select_from(Booking).where(
                and_(Booking.slot_id == slot.id, Booking.status.in_(["hold", "confirmed"]))
            )
        ) or 0
        if active > (slot.capacity or 1):
            b.status = "canceled"
            s.commit()
            return _json_error("slot_full", 409)

        b.status = "confirmed"
        b.confirmed_at = _now()
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
        b.status = "canceled"
        s.commit()
        return jsonify({"ok": True})

# --------------------------------------------------------
# Start
# --------------------------------------------------------
if __name__ == "__main__":
    # Hinweis: Hard Reload im Browser (Ctrl/Cmd + Shift + R), wenn Assets gecacht sind
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
