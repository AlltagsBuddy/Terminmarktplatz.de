import os
import traceback
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal  # für Geldbeträge
from typing import Optional

import json
import hmac
import hashlib
import base64

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
    Flask,
    request,
    redirect,
    jsonify,
    make_response,
    render_template,
    url_for,
    abort,
)
from flask_cors import CORS
from argon2 import PasswordHasher
import jwt

# Stripe (optional)
try:
    import stripe
except ImportError:
    stripe = None

# Deine ORM-Modelle
from models import Base, Provider, Slot, Booking, PlanPurchase, Invoice, AlertSubscription

# --------------------------------------------------------
# .env laden + Google Maps API Key
# --------------------------------------------------------
load_dotenv()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# --------------------------------------------------------
# Init / Mode / Pfade
# --------------------------------------------------------
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_ROOT, "static")
TEMPLATE_DIR = os.path.join(APP_ROOT, "templates")

IS_RENDER = bool(
    os.environ.get("RENDER")
    or os.environ.get("RENDER_SERVICE_ID")
    or os.environ.get("RENDER_EXTERNAL_URL")
)
API_ONLY = os.environ.get("API_ONLY") == "1"

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
SECRET = os.environ.get("SECRET_KEY", "dev")
DB_URL = os.environ.get("DATABASE_URL", "")
JWT_ISS = os.environ.get("JWT_ISS", "terminmarktplatz")
JWT_AUD = os.environ.get("JWT_AUD", "terminmarktplatz_client")
JWT_EXP_MIN = int(os.environ.get("JWT_EXP_MINUTES", "60"))
REFRESH_EXP_DAYS = int(os.environ.get("REFRESH_EXP_DAYS", "14"))

# --- MAIL Konfiguration (Resend standard; Postmark/SMTP optional) ---
MAIL_PROVIDER = os.getenv("MAIL_PROVIDER", "resend")  # resend | postmark | smtp | console
MAIL_FROM = os.getenv("MAIL_FROM", "Terminmarktplatz <no-reply@terminmarktplatz.de>")
MAIL_REPLY_TO = os.getenv("MAIL_REPLY_TO", os.getenv("REPLY_TO", MAIL_FROM))
EMAILS_ENABLED = os.getenv("EMAILS_ENABLED", "true").lower() == "true"
CONTACT_TO = os.getenv("CONTACT_TO", MAIL_FROM)

# RESEND (HTTPS)
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

# POSTMARK (HTTPS)
POSTMARK_API_TOKEN = os.getenv("POSTMARK_API_TOKEN") or os.getenv("POSTMARK_TOKEN")
POSTMARK_MESSAGE_STREAM = os.getenv("POSTMARK_MESSAGE_STREAM", "outbound")

# SMTP (z. B. STRATO) – für lokale Tests
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"


def _cfg(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        raise RuntimeError(f"Missing required setting: {name}")
    return val


BASE_URL = _cfg(
    "BASE_URL",
    "https://api.terminmarktplatz.de" if IS_RENDER else "http://127.0.0.1:5000",
)
FRONTEND_URL = _cfg(
    "FRONTEND_URL",
    "https://terminmarktplatz.de" if IS_RENDER else "http://127.0.0.1:5000",
)

# Stripe Config
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

if stripe and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# CopeCart IPN / Webhook
COPECART_WEBHOOK_SECRET = os.getenv("COPECART_WEBHOOK_SECRET")

# Mappe CopeCart-Produkt-IDs auf deine internen Provider-Tarife
COPECART_PRODUCT_PLAN_MAP: dict[str, str] = {}
for env_name, plan_key in [
    ("COPECART_PRODUCT_STARTER_ID", "starter"),
    ("COPECART_PRODUCT_PROFI_ID", "profi"),
    ("COPECART_PRODUCT_BUSINESS_ID", "business"),
]:
    pid = os.getenv(env_name)
    if pid:
        COPECART_PRODUCT_PLAN_MAP[pid] = plan_key

# CopeCart Checkout-URLs (aus .env) für Provider-Pakete
COPECART_STARTER_URL = os.getenv("COPECART_STARTER_URL")
COPECART_PROFI_URL = os.getenv("COPECART_PROFI_URL")
COPECART_BUSINESS_URL = os.getenv("COPECART_BUSINESS_URL")

COPECART_PLAN_URLS = {
    "starter": COPECART_STARTER_URL,
    "profi": COPECART_PROFI_URL,
    "business": COPECART_BUSINESS_URL,
}

# Pakete / Pläne (Provider)
PLANS = {
    "starter": {
        "key": "starter",
        "name": "Starter",
        "price_eur": Decimal("9.90"),
        "price_cents": 990,
        "free_slots": 50,
    },
    "profi": {
        "key": "profi",
        "name": "Profi",
        "price_eur": Decimal("19.90"),
        "price_cents": 1990,
        "free_slots": 500,
    },
    "business": {
        "key": "business",
        "name": "Business",
        "price_eur": Decimal("39.90"),
        "price_cents": 3990,
        "free_slots": 5000,
    },
}

# --------------------------------------------------------
# Benachrichtigungs-Pakete (Suchende) + CopeCart-Mapping
# --------------------------------------------------------
ALERT_PLANS = {
    "alert_email": {
        "key": "alert_email",
        "name": "Termin-Alarm E-Mail",
        "sms_quota_month": 0,
    },
    "alert_sms50": {
        "key": "alert_sms50",
        "name": "Termin-Alarm E-Mail + SMS (50/Monat)",
        "sms_quota_month": 50,
    },
}

# Mappe CopeCart-Produkt-IDs auf Alert-Pakete
COPECART_ALERT_PRODUCT_MAP: dict[str, str] = {}
for env_name, pkg_key in [
    ("COPECART_ALERT_EMAIL_ID", "alert_email"),
    ("COPECART_ALERT_SMS50_ID", "alert_sms50"),
]:
    pid = os.getenv(env_name)
    if pid:
        COPECART_ALERT_PRODUCT_MAP[pid] = pkg_key


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
engine = create_engine(
    DB_URL,
    pool_pre_ping=True,     # prüft Verbindung vor Benutzung
    pool_recycle=180,       # recycelt Connections regelmäßig (SSL/Proxy zickt oft)
    pool_timeout=30,
    pool_size=5,
    max_overflow=10,
    connect_args={
        # bei Render/Supabase/managed Postgres fast immer korrekt:
        "sslmode": os.getenv("PGSSLMODE", "require"),
    },
)
ph = PasswordHasher(time_cost=2, memory_cost=102_400, parallelism=8)

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
        r"/auth/*": {"origins": ALLOWED_ORIGINS},
        r"/me": {"origins": ALLOWED_ORIGINS},
        r"/me/*": {"origins": ALLOWED_ORIGINS},
        r"/slots*": {"origins": ALLOWED_ORIGINS},
        r"/provider/*": {"origins": ALLOWED_ORIGINS},
        r"/admin/*": {"origins": ALLOWED_ORIGINS},
        r"/public/*": {"origins": ALLOWED_ORIGINS},
        r"/api/*": {"origins": ALLOWED_ORIGINS},
        r"/paket-buchen*": {"origins": ALLOWED_ORIGINS},
        r"/copecart/*": {"origins": ALLOWED_ORIGINS},
        r"/webhook/stripe": {"origins": ALLOWED_ORIGINS},
        r"/webhook/copecart": {"origins": ALLOWED_ORIGINS},
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


# --------------------------------------------------------
# Publish-Quota Tabellen (idempotent, best effort)
# --------------------------------------------------------
def _ensure_publish_quota_tables():
    ddl_quota_uuid = """
    CREATE TABLE IF NOT EXISTS public.publish_quota (
      provider_id uuid NOT NULL,
      month date NOT NULL,
      used integer NOT NULL DEFAULT 0,
      "limit" integer NOT NULL,
      PRIMARY KEY (provider_id, month)
    );
    """
    ddl_quota_fk = """
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'publish_quota_provider_fk'
      ) THEN
        ALTER TABLE public.publish_quota
        ADD CONSTRAINT publish_quota_provider_fk
        FOREIGN KEY (provider_id) REFERENCES public.provider(id) ON DELETE CASCADE;
      END IF;
    END $$;
    """
    ddl_slot_published_at = """
    ALTER TABLE public.slot
      ADD COLUMN IF NOT EXISTS published_at timestamp without time zone;
    """
    with engine.begin() as conn:
        try:
            conn.exec_driver_sql(ddl_quota_uuid)
            conn.exec_driver_sql(ddl_quota_fk)
        except Exception as e:
            try:
                conn.exec_driver_sql(
                    """
                    CREATE TABLE IF NOT EXISTS public.publish_quota (
                      provider_id text NOT NULL,
                      month date NOT NULL,
                      used integer NOT NULL DEFAULT 0,
                      "limit" integer NOT NULL,
                      PRIMARY KEY (provider_id, month)
                    );
                    """
                )
            except Exception:
                app.logger.warning("publish_quota ensure failed: %r", e)

        try:
            conn.exec_driver_sql(ddl_slot_published_at)
        except Exception as e:
            app.logger.warning("slot.published_at ensure failed: %r", e)


_ensure_publish_quota_tables()


def _gc_key(zip_code: str | None, city: str | None) -> str:
    if zip_code and zip_code.strip():
        return f"zip:{zip_code.strip()}"
    if city and city.strip():
        return f"city:{city.strip().lower()}"
    return ""


def geocode_cached(
    session: Session, zip_code: str | None, city: str | None
) -> tuple[float | None, float | None]:
    key = _gc_key(zip_code, city)
    if not key:
        return None, None

    row = session.execute(
        text("SELECT lat, lon FROM geocode_cache WHERE key=:k"), {"k": key}
    ).first()
    if row and row[0] is not None and row[1] is not None:
        return float(row[0]), float(row[1])

    query = zip_code if zip_code else city
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": "de",
            },
            headers={
                "User-Agent": "Terminmarktplatz/1.0 (kontakt@terminmarktplatz.de)"
            },
            timeout=8,
        )
        if r.ok:
            js = r.json()
            if js:
                lat = float(js[0]["lat"])
                lon = float(js[0]["lon"])
                session.execute(
                    text(
                        """INSERT INTO geocode_cache(key, lat, lon)
                           VALUES(:k,:lat,:lon)
                           ON CONFLICT (key) DO UPDATE
                           SET lat=EXCLUDED.lat, lon=EXCLUDED.lon, updated_at=now()"""
                    ),
                    {"k": key, "lat": lat, "lon": lon},
                )
                session.commit()
                time.sleep(0.2)
                return lat, lon
    except Exception:
        pass

    session.execute(
        text(
            "INSERT INTO geocode_cache(key, lat, lon) VALUES(:k,NULL,NULL) ON CONFLICT (key) DO NOTHING"
        ),
        {"k": key},
    )
    session.commit()
    return None, None


# --------------------------------------------------------
# Zeit / Kategorien / Utilities
# --------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
    "Friseur",
    "Kosmetik",
    "Physiotherapie",
    "Nagelstudio",
    "Zahnarzt",
    "Handwerk",
    "KFZ-Service",
    "Fitness",
    "Coaching",
    "Tierarzt",
    "Behörde",
    "Sonstiges",
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
    published_at = getattr(x, "published_at", None)
    return {
        "id": x.id,
        "provider_id": x.provider_id,
        "title": x.title,
        "category": x.category,
        "start_at": _from_db_as_iso_utc(x.start_at),
        "end_at": _from_db_as_iso_utc(x.end_at),
        "location": x.location,
        "capacity": x.capacity,
        "contact_method": x.contact_method,
        "booking_link": x.booking_link,
        "price_cents": x.price_cents,
        "notes": x.notes,
        "status": x.status,
        "published_at": _from_db_as_iso_utc(published_at) if published_at else None,
        "created_at": _from_db_as_iso_utc(x.created_at),
    }


# ---- Validierungen & Profil-Check ----
def _is_valid_zip(v: str | None) -> bool:
    v = (v or "").strip()
    return len(v) == 5 and v.isdigit()

def normalize_zip(v: str | None) -> str:
    # macht aus "96191 Viereth" -> "96191"
    digits = "".join(ch for ch in (v or "") if ch.isdigit())
    return digits[:5]



def _is_valid_phone(v: str | None) -> bool:
    v = (v or "").strip()
    return len(v) >= 6


def is_profile_complete(p: Provider) -> bool:
    return all(
        [
            bool(p.company_name),
            bool(p.branch),
            bool(p.street),
            _is_valid_zip(p.zip),
            bool(p.city),
            _is_valid_phone(p.phone),
        ]
    )


# --------------------------------------------------------
# SLOT Status Konstanz (einheitlich)
# --------------------------------------------------------
SLOT_STATUS_DRAFT = "DRAFT"
SLOT_STATUS_PUBLISHED = "PUBLISHED"
VALID_STATUSES = {SLOT_STATUS_DRAFT, SLOT_STATUS_PUBLISHED}


def _effective_monthly_limit(raw_limit) -> tuple[int, bool]:
    """
    FIX:
      - None / 0 => Basislimit 3 (NICHT unlimited)
      - < 0      => unlimited (z.B. -1)
      - > 0      => genau dieses Limit
    """
    try:
        if raw_limit is None:
            return 3, False
        raw = int(raw_limit)
    except Exception:
        return 3, False

    if raw == 0:
        return 3, False
    if raw < 0:
        return raw, True
    return raw, False


# --------------------------------------------------------
# Publish-Quota (Variante A)
# --------------------------------------------------------
class PublishLimitReached(Exception):
    pass


def _month_key_from_dt(dt: datetime) -> date:
    dt_aware = _as_utc_aware(dt)
    local = dt_aware.astimezone(BERLIN)
    return date(local.year, local.month, 1)


def _month_bounds_utc_naive(month_key: date) -> tuple[datetime, datetime]:
    start_local = datetime(month_key.year, month_key.month, 1, 0, 0, 0, tzinfo=BERLIN)
    if month_key.month == 12:
        next_local = datetime(month_key.year + 1, 1, 1, 0, 0, 0, tzinfo=BERLIN)
    else:
        next_local = datetime(month_key.year, month_key.month + 1, 1, 0, 0, 0, tzinfo=BERLIN)
    return _to_db_utc_naive(start_local), _to_db_utc_naive(next_local)


def _published_count_for_month(session: Session, provider_id: str, month_key: date) -> int:
    start_db, next_db = _month_bounds_utc_naive(month_key)
    c = (
        session.scalar(
            select(func.count())
            .select_from(Slot)
            .where(
                Slot.provider_id == provider_id,
                Slot.start_at >= start_db,
                Slot.start_at < next_db,
                Slot.status == SLOT_STATUS_PUBLISHED,
            )
        )
        or 0
    )
    return int(c)


def _publish_slot_quota_tx(session: Session, provider_id: str, slot_id: str) -> dict:
    """
    Atomisch publishen:
      - Slot FOR UPDATE lock
      - publish_quota upsert + sync used mit IST-Zählung
      - used++ nur wenn used < limit
      - Slot.status -> PUBLISHED + published_at
    """
    slot = session.execute(
        text(
            """
            SELECT id, provider_id, start_at, status, capacity
            FROM public.slot
            WHERE id = :sid AND provider_id = :pid
            FOR UPDATE
            """
        ),
        {"sid": str(slot_id), "pid": str(provider_id)},
    ).mappings().first()

    if not slot:
        raise ValueError("not_found")
    if slot["status"] != SLOT_STATUS_DRAFT:
        raise ValueError("not_draft")

    start_at = slot["start_at"]
    if start_at is None:
        raise ValueError("bad_datetime")
    start_at_aware = _as_utc_aware(start_at)
    if start_at_aware <= _now():
        raise ValueError("start_in_past")

    cap = int(slot["capacity"] or 1)
    if cap < 1:
        raise ValueError("bad_capacity")

    lim_row = session.execute(
        text("SELECT free_slots_per_month AS lim FROM public.provider WHERE id=:pid"),
        {"pid": str(provider_id)},
    ).mappings().first()
    if not lim_row:
        raise ValueError("provider_not_found")

    eff_limit, unlimited = _effective_monthly_limit(lim_row["lim"])
    month_key = _month_key_from_dt(start_at_aware)
    now_db = _to_db_utc_naive(_now())

    # Sync-Zählung (wichtig: bevor wir bumpen)
    plan_limit = int(eff_limit)
    actual_used = _published_count_for_month(session, provider_id, month_key)

    # Unlimited -> direkt publishen (kein Limit-Bump nötig)
    if unlimited:
        session.execute(
            text(
                """
                UPDATE public.slot
                SET status='PUBLISHED', published_at=:now
                WHERE id=:sid AND provider_id=:pid AND status='DRAFT'
                """
            ),
            {"sid": str(slot_id), "pid": str(provider_id), "now": now_db},
        )
        return {"unlimited": True, "month": str(month_key), "used": None, "limit": None}

    # Quota-Row upsert + used mit IST-Zählung synchronisieren
    session.execute(
        text(
                """
                INSERT INTO public.publish_quota (provider_id, month, used, "limit")
                VALUES (:pid, :m, :used, :lim)
                ON CONFLICT (provider_id, month) DO UPDATE
                SET used    = GREATEST(public.publish_quota.used, EXCLUDED.used),
                    "limit" = EXCLUDED."limit"
                """
        ),
        {"pid": str(provider_id), "m": month_key, "used": int(actual_used), "lim": int(plan_limit)},
    )

    bumped = session.execute(
        text(
            """
            UPDATE public.publish_quota
            SET used = used + 1
            WHERE provider_id=:pid AND month=:m AND used < "limit"
            RETURNING used, "limit"
            """
        ),
        {"pid": str(provider_id), "m": month_key},
    ).mappings().first()

    if not bumped:
        raise PublishLimitReached("monthly_publish_limit_reached")

    session.execute(
        text(
            """
            UPDATE public.slot
            SET status='PUBLISHED', published_at=:now
            WHERE id=:sid AND provider_id=:pid AND status='DRAFT'
            """
        ),
        {"sid": str(slot_id), "pid": str(provider_id), "now": now_db},
    )

    return {
        "unlimited": False,
        "month": str(month_key),
        "used": int(bumped["used"]),
        "limit": int(bumped["limit"]),
    }


def _unpublish_slot_quota_tx(session: Session, provider_id: str, slot_id: str) -> dict:
    """
    PUBLISHED -> DRAFT und Quota used--.
    """
    slot = session.execute(
        text(
            """
            SELECT id, provider_id, start_at, status
            FROM public.slot
            WHERE id=:sid AND provider_id=:pid
            FOR UPDATE
            """
        ),
        {"sid": str(slot_id), "pid": str(provider_id)},
    ).mappings().first()

    if not slot:
        raise ValueError("not_found")
    if slot["status"] != SLOT_STATUS_PUBLISHED:
        raise ValueError("not_published")

    start_at = slot["start_at"]
    start_at_aware = _as_utc_aware(start_at) if start_at else _now()
    month_key = _month_key_from_dt(start_at_aware)

    session.execute(
        text(
            """
            UPDATE public.publish_quota
            SET used = GREATEST(used - 1, 0)
            WHERE provider_id=:pid AND month=:m
            """
        ),
        {"pid": str(provider_id), "m": month_key},
    )

    session.execute(
        text(
            """
            UPDATE public.slot
            SET status='DRAFT', published_at=NULL
            WHERE id=:sid AND provider_id=:pid AND status='PUBLISHED'
            """
        ),
        {"sid": str(slot_id), "pid": str(provider_id)},
    )

    row = session.execute(
        text("""SELECT used, "limit" FROM public.publish_quota WHERE provider_id=:pid AND month=:m"""),
        {"pid": str(provider_id), "m": month_key},
    ).mappings().first()

    if row:
        return {"month": str(month_key), "used": int(row["used"] or 0), "limit": int(row["limit"] or 0)}
    return {"month": str(month_key), "used": 0, "limit": None}


# Monatsabrechnung: Sammelrechnungen erzeugen
def create_invoices_for_period(session: Session, year: int, month: int) -> dict:
    """
    Erzeugt Sammelrechnungen für alle bestätigten Buchungen (status='confirmed')
    eines Monats, deren fee_status='open' ist.
    """
    period_start_dt = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        next_month_dt = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month_dt = datetime(year, month + 1, 1, 1, 0, 0, tzinfo=timezone.utc)

    start_db = _to_db_utc_naive(period_start_dt)
    end_db = _to_db_utc_naive(next_month_dt)

    bookings = (
        session.execute(
            select(Booking).where(
                Booking.status == "confirmed",
                Booking.fee_status == "open",
                Booking.created_at >= start_db,
                Booking.created_at < end_db,
            )
        )
        .scalars()
        .all()
    )

    by_provider: dict[str, list[Booking]] = {}
    for b in bookings:
        by_provider.setdefault(b.provider_id, []).append(b)

    invoices_summary = []

    for provider_id, blist in by_provider.items():
        total = sum((b.provider_fee_eur or Decimal("0.00")) for b in blist)
        if total <= 0:
            continue

        inv = Invoice(
            provider_id=provider_id,
            period_start=period_start_dt.date(),
            period_end=(next_month_dt - timedelta(days=1)).date(),
            total_eur=total,
            status="open",
        )
        session.add(inv)
        session.flush()

        now = _now()
        for b in blist:
            b.invoice_id = inv.id
            b.fee_status = "invoiced"
            b.is_billed = True
            b.billed_at = now

        invoices_summary.append(
            {
                "provider_id": provider_id,
                "invoice_id": inv.id,
                "booking_count": len(blist),
                "total_eur": float(total),
            }
        )

    return {
        "period": {"year": year, "month": month},
        "invoices_created": len(invoices_summary),
        "items": invoices_summary,
    }


# --------------------------------------------------------
# Mail
# --------------------------------------------------------
def send_mail(
    to: str,
    subject: str,
    text: str | None = None,
    html: str | None = None,
    tag: str | None = None,
    metadata: dict | None = None,
):
    """
    Vereinheitlichte Mail-Funktion.
    """
    try:
        if not EMAILS_ENABLED:
            print(
                f"[mail] disabled: EMAILS_ENABLED=false subject={subject!r} to={to}",
                flush=True,
            )
            return True, "disabled"

        provider = (MAIL_PROVIDER or "resend").strip().lower()
        print(
            f"[mail] provider={provider} from={MAIL_FROM} to={to} subject={subject!r}",
            flush=True,
        )

        # Console
        if provider == "console":
            print(
                "\n--- MAIL (console) ---\n"
                f"From: {MAIL_FROM}\n"
                f"To: {to}\n"
                f"Subject: {subject}\n"
                f"Reply-To: {MAIL_REPLY_TO}\n\n"
                f"{text or ''}\n{html or ''}\n"
                "--- END ---\n",
                flush=True,
            )
            return True, "console"

        # RESEND
        if provider == "resend":
            if not RESEND_API_KEY:
                return False, "missing RESEND_API_KEY"

            payload: dict[str, object] = {
                "from": MAIL_FROM,
                "to": to,
                "subject": subject,
            }
            if text:
                payload["text"] = text
            if html:
                payload["html"] = html
            if MAIL_REPLY_TO:
                payload["reply_to"] = MAIL_REPLY_TO

            r = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15,
            )
            ok = 200 <= r.status_code < 300
            print("[resend]", r.status_code, r.text, flush=True)
            if not ok:
                try:
                    print("[resend][payload]", payload, flush=True)
                except Exception:
                    pass
            return ok, str(r.status_code)

        # POSTMARK
        if provider == "postmark":
            if not POSTMARK_API_TOKEN:
                return False, "missing POSTMARK_API_TOKEN"

            payload: dict[str, object] = {
                "From": MAIL_FROM,
                "To": to,
                "Subject": subject,
                "MessageStream": POSTMARK_MESSAGE_STREAM,
            }
            if MAIL_REPLY_TO:
                payload["ReplyTo"] = MAIL_REPLY_TO
            if text:
                payload["TextBody"] = text
            if html:
                payload["HtmlBody"] = html
            if tag:
                payload["Tag"] = tag
            if metadata:
                payload["Metadata"] = {
                    str(k): ("" if v is None else str(v)) for k, v in metadata.items()
                }

            r = requests.post(
                "https://api.postmarkapp.com/email",
                headers={
                    "X-Postmark-Server-Token": POSTMARK_API_TOKEN,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15,
            )
            ok = 200 <= r.status_code < 300
            print("[postmark]", r.status_code, r.text, flush=True)
            if not ok:
                try:
                    print("[postmark][payload]", payload, flush=True)
                except Exception:
                    pass
            return ok, str(r.status_code)

        # SMTP
        if provider == "smtp":
            missing = [
                k
                for k, v in {
                    "SMTP_HOST": SMTP_HOST,
                    "SMTP_PORT": SMTP_PORT,
                    "SMTP_USER": SMTP_USER,
                    "SMTP_PASS": SMTP_PASS,
                }.items()
                if not v
            ]
            if missing:
                return False, f"missing smtp config: {', '.join(missing)}"

            disp_name, _ = parseaddr(MAIL_FROM or "")
            from_hdr = formataddr((disp_name or "Terminmarktplatz", SMTP_USER))
            msg = EmailMessage()
            msg["From"] = from_hdr
            msg["To"] = to
            msg["Subject"] = subject
            if MAIL_REPLY_TO:
                msg["Reply-To"] = MAIL_REPLY_TO

            if html:
                msg.set_content(text or "")
                msg.add_alternative(html, subtype="html")
            else:
                msg.set_content(text or "")

            try:
                if SMTP_USE_TLS:
                    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                        s.starttls()
                        s.login(SMTP_USER, SMTP_PASS)
                        s.send_message(msg, from_addr=SMTP_USER)
                else:
                    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                        s.login(SMTP_USER, SMTP_PASS)
                        s.send_message(msg, from_addr=SMTP_USER)
                return True, "smtp"
            except Exception as e:
                print("[smtp][ERROR]", repr(e), flush=True)
                return False, repr(e)

        # Fallback
        return False, f"unknown provider '{provider}'"

    except Exception as e:
        print("send_mail exception:", repr(e), flush=True)
        return False, repr(e)


# --------------------------------------------------------
# SMS-Stub (für Termin-Alarm; später echten Provider einbauen)
# --------------------------------------------------------
    def send_sms(to: str, text: str) -> None:
        to = (to or "").strip()
        text = (text or "").strip()
        if not to or not text:
            return
    print(f"[sms][stub] to={to} text={text}", flush=True)


# --------------------------------------------------------
# Spezielle Mails: Paket gekündigt / aktiviert
# --------------------------------------------------------
    def send_email_plan_canceled(provider: Provider, old_plan: str | None):
        to = (provider.email or "").strip().lower()
    if not to:
        return

    plan_name = "Basis-Paket (kostenlos)"
    eff_limit, unlimited = _effective_monthly_limit(provider.free_slots_per_month)
    slots = "unbegrenzt" if unlimited else eff_limit

    body = f"""Hallo {provider.company_name or 'Anbieter/in'},

du hast dein kostenpflichtiges Paket im Terminmarktplatz-Anbieterportal gekündigt.

Was wurde jetzt in deinem Portal geändert?
- Dein Konto wurde auf das kostenlose {plan_name} zurückgesetzt.
- Dein Slot-Kontingent im Portal liegt jetzt bei {slots} freien Slots pro Monat.
- Deine bestehenden Slots und Buchungen bleiben erhalten.

WICHTIG: CopeCart-Abo separat kündigen
Wenn du dein Paket ursprünglich über CopeCart gebucht hast, läuft dort weiterhin dein Zahlungs-Abo.
Dieses Abo wird NICHT automatisch von Terminmarktplatz gekündigt.

So kündigst du dein CopeCart-Abo:
1. Öffne die Bestellbestätigungs-E-Mail von CopeCart zu deinem Paket.
2. Klicke dort auf den Link „Abo verwalten“ oder „Abo kündigen“.
3. Folge den Schritten bei CopeCart, bis dir die Kündigung bestätigt wird.

Alternativ kannst du dich im CopeCart-Kundenbereich anmelden und dein Abo dort beenden:
https://copecart.com/login

Wichtig: Erst nach der Kündigung bei CopeCart werden keine weiteren Zahlungen mehr abgebucht.

Bei Fragen antworte einfach auf diese E-Mail.

Viele Grüße
Terminmarktplatz
"""

    try:
        send_mail(
            to,
            "Bestätigung deiner Paket-Kündigung im Terminmarktplatz-Portal",
            text=body,
            tag="plan_canceled",
            metadata={
                "provider_id": str(provider.id),
                "old_plan": old_plan or "",
                "source": "portal_cancel_plan",
            },
        )
    except Exception as e:
        app.logger.warning("send_email_plan_canceled failed: %r", e)


def send_email_plan_activated(
    provider: Provider,
    plan_key: str,
    source: str,
    period_start: date,
    period_end: date,
    ):
    to = (provider.email or "").strip().lower()
    if not to:
        return

    plan_conf = PLANS.get(plan_key)
    plan_name = plan_conf["name"] if plan_conf else plan_key
    eff_limit, unlimited = _effective_monthly_limit(provider.free_slots_per_month)

    slots_txt = "unbegrenzte Veröffentlichungen pro Monat" if unlimited else f"bis zu {eff_limit} veröffentlichte Slots pro Monat"

    src_label = {
        "copecart": "CopeCart",
        "stripe": "Stripe",
        "manual": "manuelle Aktivierung (Testmodus)",
    }.get(source, source)

    body = f"""Hallo {provider.company_name or 'Anbieter/in'},

dein Paket "{plan_name}" im Terminmarktplatz-Anbieterportal wurde soeben aktiviert.

Details:
- Aktiviert über: {src_label}
- Laufzeit: {period_start.isoformat()} bis {period_end.isoformat()}
- Kontingent: {slots_txt}

Du kannst ab sofort im Anbieter-Portal neue Slots anlegen und veröffentlichen.
Dein aktuelles Limit und die bereits genutzten Veröffentlichungen siehst du jederzeit in deinem Profilbereich.

Viele Grüße
Terminmarktplatz
"""

    try:
        send_mail(
            to,
            f"Dein Terminmarktplatz-Paket '{plan_name}' ist aktiv",
            text=body,
            tag="plan_activated",
            metadata={
                "provider_id": str(provider.id),
                "plan_key": plan_key,
                "source": source,
            },
        )
    except Exception as e:
        app.logger.warning("send_email_plan_activated failed: %r", e)


# --------------------------------------------------------
# Auth / Tokens
# --------------------------------------------------------
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
                auth = request.headers.get("Authorization", "")
                if auth.lower().startswith("bearer "):
                    token = auth.split(" ", 1)[1].strip()
            if not token:
                return _json_error("unauthorized", 401)
            try:
                data = jwt.decode(
                    token,
                    SECRET,
                    algorithms=["HS256"],
                    audience=JWT_AUD,
                    issuer=JWT_ISS,
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


def _current_provider_id_or_none() -> str | None:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    if not token:
        return None

    try:
        data = jwt.decode(
            token,
            SECRET,
            algorithms=["HS256"],
            audience=JWT_AUD,
            issuer=JWT_ISS,
        )
    except Exception:
        return None

    return data.get("sub")


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
        request.path.startswith("/auth/")
        or request.path.startswith("/admin/")
        or request.path.startswith("/public/")
        or request.path.startswith("/slots")
        or request.path.startswith("/provider/")
        or request.path.startswith("/paket-buchen")
        or request.path.startswith("/copecart/")
        or request.path.startswith("/webhook/stripe")
        or request.path.startswith("/webhook/copecart")
        or request.path.startswith("/me")
        or request.path.startswith("/api/")
        or request.path.startswith("/alerts/")   # ✅ verify + cancel Links aus Mails erlauben
        or request.path in ("/api/health", "/healthz", "/favicon.ico", "/robots.txt")
        or request.path.startswith("/static/")
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

    # --- Suche mit Google Maps API Key ---
    @app.get("/suche")
    def suche_page():
        return render_template("suche.html", GOOGLE_MAPS_API_KEY=GOOGLE_MAPS_API_KEY)

    @app.get("/suche.html")
    def suche_page_html():
        return render_template("suche.html", GOOGLE_MAPS_API_KEY=GOOGLE_MAPS_API_KEY)

    @app.get("/impressum")
    def impressum():
        return render_template("impressum.html")

    @app.get("/datenschutz")
    def datenschutz():
        return render_template("datenschutz.html")

    @app.get("/agb")
    def agb():
        return render_template("agb.html")

    @app.get("/paket-buchen")
    @auth_required()
    def paket_buchen_page():
        plan_key = (request.args.get("plan") or "starter").strip()
        plan = PLANS.get(plan_key)
        if not plan:
            plan_key = "starter"
            plan = PLANS["starter"]

        with Session(engine) as s:
            p = s.get(Provider, request.provider_id)
            if not p:
                abort(404)

        return render_template(
            "paket_buchen.html",
            plan_key=plan_key,
            plan=plan,
        )

    @app.get("/copecart/kaufen")
    def copecart_kaufen():
            plan_key = (request.args.get("plan") or "starter").strip().lower()
            url = COPECART_PLAN_URLS.get(plan_key)
            if not url:
                abort(404)

            provider_id = _current_provider_id_or_none()
            if not provider_id:
                next_url = url_for("copecart_kaufen", plan=plan_key)
                login_url = url_for("login_page")
                return redirect(f"{login_url}?next={next_url}&register=1")

            sep = "&" if "?" in url else "?"
            target = f"{url}{sep}subid={provider_id}"
            return redirect(target, code=302)

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
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
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
            send_mail(
                email,
                "Danke für deine Nachricht",
                "Wir haben deine Nachricht erhalten und melden uns bald.\n\n— Terminmarktplatz",
            )
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
    pw = password or ""
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
        resp.set_cookie(
            "refresh_token",
            refresh,
            max_age=REFRESH_EXP_DAYS * 86400,
            **flags,
        )
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
            exists = s.scalar(
                select(func.count())
                .select_from(Provider)
                .where(Provider.email == email)
            )
            if exists:
                return _json_error("email_exists")

            p = Provider(
                email=email,
                pw_hash=ph.hash(password),
                status="pending",
                plan="basic",
                free_slots_per_month=3,
                plan_valid_until=None,
            )

            s.add(p)
            s.commit()
            provider_id = p.id
            reg_email = p.email

        try:
            admin_to = os.getenv("ADMIN_NOTIFY_TO", CONTACT_TO)
            if admin_to:
                subj = "[Terminmarktplatz] Neuer Anbieter registriert"
                txt = (
                    "Es hat sich ein neuer Anbieter registriert.\n\n"
                    f"ID: {provider_id}\n"
                    f"E-Mail: {reg_email}\n"
                    f"Zeit: {_now().isoformat()}\n"
                    "Status: pending (E-Mail-Verifizierung ausstehend)\n"
                )
                send_mail(
                    admin_to,
                    subj,
                    text=txt,
                    tag="provider_signup",
                    metadata={"provider_id": str(provider_id), "email": reg_email},
                )
        except Exception as _e:
            print("[notify_admin][register] failed:", repr(_e), flush=True)

        payload = {
            "sub": provider_id,
            "aud": "verify",
            "iss": JWT_ISS,
            "exp": int((_now() + timedelta(days=2)).timestamp()),
        }
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        link = f"{BASE_URL}/auth/verify?token={token}"
        ok_mail, reason = send_mail(
            reg_email,
            "Bitte E-Mail bestätigen",
            f"Willkommen beim Terminmarktplatz.\n\nBitte bestätige deine E-Mail:\n{link}\n",
        )
        return jsonify(
            {
                "ok": True,
                "mail_sent": ok_mail,
                "mail_reason": reason,
                "message": "Registrierung gespeichert. Bitte prüfe deine E-Mails und bestätige die Anmeldung.",
                "post_verify_redirect": f"{FRONTEND_URL}/login.html?verified=1",
            }
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "server_error", "detail": str(e)}), 500


@app.get("/auth/verify")
def auth_verify():
    token = request.args.get("token", "")
    debug = request.args.get("debug") == "1"

    def _ret(kind: str):
        url = f"{FRONTEND_URL}/login.html?verified={'1' if kind == '1' else '0'}"
        if debug:
            return jsonify({"ok": kind == "1", "redirect": url})
        return redirect(url)

    try:
        data = jwt.decode(
            token,
            SECRET,
            algorithms=["HS256"],
            audience="verify",
            issuer=JWT_ISS,
        )
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
        return (
            render_template(
                "login.html",
                error=(
                    "Login fehlgeschlagen."
                    if err != "email_not_verified"
                    else "E-Mail noch nicht verifiziert."
                ),
            ),
            401,
        )

    access, refresh = issue_tokens(p.id, p.is_admin)
    next_url = request.args.get("next") or url_for("anbieter_portal_page")
    resp = make_response(redirect(next_url))
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
        data = jwt.decode(
            token,
            SECRET,
            algorithms=["HS256"],
            audience=JWT_AUD,
            issuer=JWT_ISS,
        )
        if data.get("typ") != "refresh":
            raise Exception("wrong type")
    except Exception:
        return _json_error("unauthorized", 401)

    access, _ = issue_tokens(data["sub"], bool(data.get("adm")))
    resp = make_response(jsonify({"ok": True, "access": access}))
    return _set_auth_cookies(resp, access)


@app.delete("/me")
@auth_required()
def delete_me():
    try:
        with Session(engine) as s:
            p = s.get(Provider, request.provider_id)
            if not p:
                return _json_error("not_found", 404)
            s.delete(p)
            s.commit()

        resp = make_response(jsonify({"ok": True, "deleted": True}))
        flags = _cookie_flags()
        resp.delete_cookie("access_token", **flags)
        resp.delete_cookie("refresh_token", **flags)
        return resp
    except Exception:
        app.logger.exception("delete_me failed")
        return jsonify({"error": "server_error"}), 500


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

        plan_key = (p.plan or "").strip() if hasattr(p, "plan") else ""
        plan_conf = PLANS.get(plan_key) if plan_key else None
        if plan_conf:
            plan_label = plan_conf["name"]
        elif plan_key:
            plan_label = plan_key
        else:
            plan_label = "Basis (Standard)"

        eff_limit, unlimited = _effective_monthly_limit(getattr(p, "free_slots_per_month", None))

        now_berlin = datetime.now(BERLIN)
        month_key = date(now_berlin.year, now_berlin.month, 1)

        try:
            row = s.execute(
                text("""SELECT used, "limit" FROM public.publish_quota WHERE provider_id=:pid AND month=:m"""),
                {"pid": str(p.id), "m": month_key},
            ).mappings().first()
        except Exception as e:
            # DB hiccup: nicht alles killen
            app.logger.warning("me(): publish_quota query failed: %r", e)
            row = None


        if row:
            slots_used = int(row["used"] or 0)
        else:
            slots_used = _published_count_for_month(s, str(p.id), month_key)

        slots_left = None if unlimited else max(0, int(eff_limit) - int(slots_used))

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
                "profile_complete": is_profile_complete(p),
                "plan_key": plan_key or None,
                "plan_label": plan_label,
                "plan_valid_until": p.plan_valid_until.isoformat()
                if getattr(p, "plan_valid_until", None)
                else None,
                "free_slots_per_month": eff_limit if not unlimited else -1,
                "slots_used_this_month": int(slots_used),
                "slots_left_this_month": slots_left,
                "slots_unlimited": unlimited,
            }
        )


@app.put("/me")
@auth_required()
def me_update():
    try:
        data = request.get_json(force=True) or {}
        allowed = {"company_name", "branch", "street", "zip", "city", "phone", "whatsapp"}

        def clean(v):
            if v is None:
                return None
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
                return (
                    jsonify(
                        {
                            "error": "db_constraint_error",
                            "constraint": getattr(detail, "constraint_name", None),
                            "message": str(e.orig),
                        }
                    ),
                    400,
                )
            except SQLAlchemyError:
                s.rollback()
                return _json_error("db_error", 400)

            # optional: geocode-cache auffrischen (best effort)
            try:
                geocode_cached(s, p.zip, p.city)
            except Exception:
                s.rollback()

        return jsonify({"ok": True})
    except Exception as e:
        print("[/me] server error:", repr(e), flush=True)
        return jsonify({"error": "server_error"}), 500


@app.post("/me/cancel_plan")
@auth_required()
def cancel_plan():
    """
    Kündigt das Paket NUR im Portal (Provider).
    """
    try:
        with Session(engine) as s:
            p = s.get(Provider, request.provider_id)
            if not p:
                return _json_error("not_found", 404)

            if not p.plan or p.plan == "basic":
                return _json_error("no_active_plan", 400)

            old_plan = p.plan

            p.plan = "basic"
            p.plan_valid_until = None
            p.free_slots_per_month = 3

            s.commit()

            try:
                send_email_plan_canceled(p, old_plan)
            except Exception as e:
                app.logger.warning("cancel_plan: send_email_plan_canceled failed: %r", e)

        return jsonify({"ok": True, "status": "canceled_to_basic"})
    except Exception:
        app.logger.exception("cancel_plan failed")
        return jsonify({"error": "server_error"}), 500


# --------------------------------------------------------
# Termin-Alarm / Benachrichtigungen (Suchende)
# --------------------------------------------------------
ALERT_MAX_PER_EMAIL = 10          # max. Alerts (Subscriptions) pro E-Mail
ALERT_MAX_EMAILS_PER_ALERT = 10   # max. E-Mail-Benachrichtigungen pro Alert (email_sent_total)


def _reset_alert_quota_if_needed(alert: AlertSubscription) -> None:
    now = _now()
    if not alert.last_reset_quota:
        alert.last_reset_quota = now
        alert.sms_sent_this_month = 0
        return

    lr = _as_utc_aware(alert.last_reset_quota)
    nr = _as_utc_aware(now)
    if lr.year != nr.year or lr.month != nr.month:
        alert.sms_sent_this_month = 0
        alert.last_reset_quota = now


def _send_notifications_for_alert_and_slot(
    session: Session,
    alert: AlertSubscription,
    slot: Slot,
    provider: Provider,
) -> None:
    _reset_alert_quota_if_needed(alert)

    # --- LIMIT: max 10 E-Mail-Benachrichtigungen pro Alert ---
    sent_total = int(getattr(alert, "email_sent_total", 0) or 0)
    if sent_total >= ALERT_MAX_EMAILS_PER_ALERT:
        return

    slot_title = slot.title
    starts_at = _from_db_as_iso_utc(slot.start_at)
    provider_address = ""
    try:
        provider_address = provider.to_public_dict().get("address") or ""
    except Exception:
        provider_address = ""

    slot_location = slot.location or ""
    address = provider_address or slot_location or ""

    if hasattr(app, "view_functions") and "public_slots" in app.view_functions:
        base = _external_base()
        slot_url = f"{base}/suche.html"
    else:
        slot_url = ""

    # E-Mail-Benachrichtigung
    if alert.via_email and alert.email_confirmed and alert.active:
        cancel_url = url_for("cancel_alert", token=alert.verify_token, _external=True)
        body_lines = [
            "Es gibt einen neuen Termin, der zu deinem Suchauftrag passt:",
            "",
            f"{slot_title}",
            f"Zeit: {starts_at}",
        ]
        if address:
            body_lines.append(f"Adresse: {address}")
        if slot_url:
            body_lines.append("")
            body_lines.append(f"Details & Buchung: {slot_url}")
        body_lines.append("")
        body_lines.append("Wenn du diesen Alarm nicht mehr erhalten möchtest, kannst du ihn hier deaktivieren:")
        body_lines.append(cancel_url)

        body = "\n".join(body_lines)

        try:
            ok, reason = send_mail(
                alert.email,
                "Neuer Termin passt zu deinem Suchauftrag",
                text=body,
                tag="alert_slot_match",
                metadata={"zip": alert.zip, "package": alert.package_name or ""},
            )

            # Nur zählen, wenn Versand ok war
            if ok:
                alert.email_sent_total = int(getattr(alert, "email_sent_total", 0) or 0) + 1
            else:
                app.logger.warning("send_mail alert not delivered: %s", reason)

        except Exception as e:
            app.logger.warning("send_mail alert failed: %r", e)

    # SMS-Benachrichtigung
    if (
        alert.via_sms
        and alert.phone
        and alert.active
        and (alert.sms_quota_month or 0) > 0
    ):
        if alert.sms_sent_this_month < (alert.sms_quota_month or 0):
            parts = [f"Neuer Termin: {slot_title}", starts_at]
            if slot_url:
                parts.append(f"Details: {slot_url}")
            text_msg = " | ".join(str(p) for p in parts if p)

            try:
                send_sms(alert.phone, text_msg)
                alert.sms_sent_this_month += 1
            except Exception as e:
                app.logger.warning("send_sms alert failed: %r", e)

    alert.last_notified_at = _now()


def _extract_zip_from_text(txt: str | None) -> str | None:
    """
    Fallback: versucht eine deutsche PLZ (5 Ziffern) aus Freitext zu ziehen.
    """
    import re
    t = (txt or "").strip()
    if not t:
        return None
    m = re.search(r"\b(\d{5})\b", t)
    return m.group(1) if m else None


def notify_alerts_for_slot(slot_id: str) -> None:
    """
    Wird aufgerufen, wenn ein Slot veröffentlicht wurde (Status PUBLISHED).
    """
    for attempt in (1, 2):
        try:
            with Session(engine) as s:
                # --- ab hier bleibt dein bisheriger Inhalt der Funktion ---
                slot = s.get(Slot, slot_id)
                if not slot:
                    print(f"[alerts] slot_not_found id={slot_id}", flush=True)
                    return
                if slot.status != SLOT_STATUS_PUBLISHED:
                    print(f"[alerts] slot_not_published id={slot_id} status={slot.status}", flush=True)
                    return

                provider = s.get(Provider, slot.provider_id)
                if not provider:
                    print(f"[alerts] provider_not_found slot_id={slot_id} provider_id={slot.provider_id}", flush=True)
                    return

                slot_zip = normalize_zip(getattr(slot, "zip", None))
                if len(slot_zip) != 5:
                    slot_zip = normalize_zip(getattr(provider, "zip", None))
                if len(slot_zip) != 5:
                    slot_zip = normalize_zip(_extract_zip_from_text(getattr(slot, "location", None)))


                slot_cat = (getattr(slot, "category", "") or "").lower().strip()

                print(f"[alerts] check slot_id={slot_id} zip={slot_zip!r} cat={slot_cat!r}", flush=True)

                if len(slot_zip) != 5:
                    print(f"[alerts] no_valid_zip_for_slot slot_id={slot_id} zip={slot_zip!r}", flush=True)
                    return


                alerts = (
                    s.execute(
                        select(AlertSubscription).where(
                            AlertSubscription.active.is_(True),
                            AlertSubscription.email_confirmed.is_(True),
                            AlertSubscription.zip == slot_zip,
                        )
                    )
                    .scalars()
                    .all()
                )

                print(f"[alerts] candidates zip={slot_zip} count={len(alerts)}", flush=True)

                matched_alerts: list[AlertSubscription] = []
                for alert in alerts:
                    if not getattr(alert, "categories", None):
                        matched_alerts.append(alert)
                        continue

                    alert_cats = [
                        c.strip().lower()
                        for c in (alert.categories or "").split(",")
                        if c.strip()
                    ]
                    if any(c == slot_cat for c in alert_cats) or any(c in slot_cat for c in alert_cats):
                        matched_alerts.append(alert)

                print(f"[alerts] matched count={len(matched_alerts)}", flush=True)

                if not matched_alerts:
                    return

                for alert in matched_alerts:
                    _send_notifications_for_alert_and_slot(s, alert, slot, provider)

                s.commit()
                print(f"[alerts] done slot_id={slot_id}", flush=True)
                return

        except Exception as e:
            app.logger.warning("notify_alerts_for_slot failed attempt=%s slot_id=%s err=%r", attempt, slot_id, e)
            if attempt == 2:
                app.logger.exception("notify_alerts_for_slot final failure")
                return


@app.get("/api/alerts/stats")
def alert_stats():
    email = (request.args.get("email") or "").strip().lower()
    if not email:
        return _json_error("email_required", 400)

    try:
        email = validate_email(email).email
    except EmailNotValidError:
        return _json_error("invalid_email", 400)

    with Session(engine) as s:
        used = (
            s.scalar(
                select(func.count())
                .select_from(AlertSubscription)
                .where(AlertSubscription.email == email)
            )
            or 0
        )

    used = int(used)
    left = max(0, ALERT_MAX_PER_EMAIL - used)

    return jsonify(
        {
            "ok": True,
            "used": used,
            "limit": ALERT_MAX_PER_EMAIL,
            "left": left,
        }
    )

@app.get("/api/alerts/debug/by_zip")
def debug_alerts_by_zip():
    zip_code = (request.args.get("zip") or "").strip()
    if not zip_code:
        return _json_error("zip_required", 400)

    with Session(engine) as s:
        rows = (
            s.execute(
                select(AlertSubscription).where(AlertSubscription.zip == zip_code)
            )
            .scalars()
            .all()
        )

    return jsonify(
        {
            "zip": zip_code,
            "count": len(rows),
            "items": [
                {
                    "id": str(a.id),
                    "email": a.email,
                    "zip": a.zip,
                    "active": bool(a.active),
                    "email_confirmed": bool(a.email_confirmed),
                    "via_email": bool(a.via_email),
                    "categories": a.categories,
                    "package_name": a.package_name,
                    "created_at": _from_db_as_iso_utc(a.created_at) if getattr(a, "created_at", None) else None,
                    "verify_token": a.verify_token,
                }
                for a in rows
            ],
        }
    )
@app.get("/api/alerts/debug/active_confirmed_by_zip")
def debug_active_confirmed_by_zip():
    zip_code = (request.args.get("zip") or "").strip()
    if not zip_code:
        return _json_error("zip_required", 400)

    with Session(engine) as s:
        rows = (
            s.execute(
                select(AlertSubscription).where(
                    AlertSubscription.zip == zip_code,
                    AlertSubscription.active.is_(True),
                    AlertSubscription.email_confirmed.is_(True),
                )
            )
            .scalars()
            .all()
        )

    return jsonify(
        {
            "zip": zip_code,
            "count": len(rows),
            "items": [
                {
                    "id": str(a.id),
                    "email": a.email,
                    "zip": a.zip,
                    "active": bool(a.active),
                    "email_confirmed": bool(a.email_confirmed),
                    "via_email": bool(a.via_email),
                    "categories": a.categories,
                }
                for a in rows
            ],
        }
    )


@app.post("/api/alerts")
def create_alert():
    try:
        data = request.get_json(force=True) or {}

        email = (data.get("email") or "").strip().lower()
        phone = (data.get("phone") or "").strip()

        zip_code = normalize_zip(data.get("zip"))
        city = (data.get("city") or "").strip()

        if len(zip_code) != 5:
            return _json_error("invalid_zip", 400)



        radius_km_raw = data.get("radius_km") or 0
        try:
            radius_km = int(radius_km_raw)
        except (TypeError, ValueError):
            radius_km = 0

        categories_raw = data.get("categories") or ""
        categories = categories_raw.lower().strip() or None

        via_email = bool(data.get("via_email", True))
        via_sms = bool(data.get("via_sms", False))

        package_name = (data.get("package_name") or "free").strip().lower()

        if not via_email and not via_sms:
            return _json_error("channel_required", 400)

        if not zip_code:
            return _json_error("zip_required", 400)

        try:
            email = validate_email(email).email
        except EmailNotValidError:
            return _json_error("invalid_email", 400)

        if via_sms and not phone:
            return _json_error("phone_required_for_sms", 400)

        sms_quota_month = 0
        if package_name in ALERT_PLANS:
            sms_quota_month = ALERT_PLANS[package_name]["sms_quota_month"]

        import secrets
        verify_token = secrets.token_urlsafe(32)

        with Session(engine) as s:
            # --- LIMIT: max. 10 Alerts pro E-Mail (egal welche Kategorie) ---
            existing_count = (
                s.scalar(
                    select(func.count())
                    .select_from(AlertSubscription)
                    .where(AlertSubscription.email == email)
                )
                or 0
            )
            existing_count = int(existing_count)

            if existing_count >= ALERT_MAX_PER_EMAIL:
                return _json_error("alert_limit_reached", 409)

            alert = AlertSubscription(
                email=email,
                phone=phone or None,
                via_email=via_email,
                via_sms=via_sms,
                zip=zip_code,
                city=city or None,
                radius_km=radius_km,
                categories=categories,
                active=False,
                email_confirmed=False,
                sms_confirmed=False,
                package_name=package_name,
                sms_quota_month=sms_quota_month,
                sms_sent_this_month=0,
                email_sent_total=0,
                verify_token=verify_token,
            )
            s.add(alert)
            s.commit()

            # ✅ Stats NACH Erstellung
            used = existing_count + 1
            left = max(0, ALERT_MAX_PER_EMAIL - used)
            stats = {"used": used, "limit": ALERT_MAX_PER_EMAIL, "left": left}


            verify_url = url_for("verify_alert", token=verify_token, _external=True)
            body = (
            "Du hast auf Terminmarktplatz einen Termin-Alarm eingerichtet.\n\n"
            "Bitte klicke auf folgenden Link, um deine E-Mail-Adresse zu bestätigen "
            "und den Alarm zu aktivieren:\n\n"
            f"{verify_url}\n\n"
            "Wenn du das nicht warst, kannst du diese E-Mail ignorieren."
        )

        try:
            send_mail(
                email,
                "Termin-Alarm bestätigen",
                text=body,
                tag="alert_verify",
            )
        except Exception as e:
            app.logger.warning("create_alert: send_mail failed: %r", e)

        return jsonify(
    {
        "ok": True,
        "message": "Alarm angelegt. Bitte E-Mail bestätigen.",
        "stats": stats,
    }
)

    except Exception:
        app.logger.exception("create_alert failed")
        return jsonify({"error": "server_error"}), 500


@app.get("/alerts/verify/<token>")
def verify_alert(token: str):
    try:
        with Session(engine) as s:
            alert = (
                s.execute(
                    select(AlertSubscription).where(AlertSubscription.verify_token == token)
                )
                .scalars()
                .first()
            )
            if not alert:
                # optional: eigene Fehlerseite, sonst plain text
                return "Dieser Bestätigungslink ist ungültig oder abgelaufen.", 400

            # idempotent: mehrfach klicken soll nicht kaputtgehen
            if not alert.email_confirmed or not alert.active:
                alert.email_confirmed = True
                alert.active = True
                alert.last_reset_quota = _now()
                s.commit()

        # ✅ Nach Bestätigung auf deine Frontend-Seite weiterleiten
        return redirect(f"{FRONTEND_URL}/benachrichtigung-bestaetigung.html", code=302)

    except Exception:
        app.logger.exception("verify_alert failed")
        return "Serverfehler", 500



@app.get("/alerts/cancel/<token>")
def cancel_alert(token: str):
    try:
        with Session(engine) as s:
            alert = (
                s.execute(
                    select(AlertSubscription).where(AlertSubscription.verify_token == token)
                )
                .scalars()
                .first()
            )
            if not alert:
                return "Alarm nicht gefunden oder bereits deaktiviert.", 400

            alert.active = False
            s.commit()

        return "Dein Termin-Alarm wurde deaktiviert."
    except Exception:
        app.logger.exception("cancel_alert failed")
        return "Serverfehler", 500


# --------------------------------------------------------
# Slots (Provider)
# --------------------------------------------------------
@app.get("/slots")
@auth_required()
def slots_list():
    status = request.args.get("status")
    status = status.strip().upper() if status else None

    with Session(engine) as s:
        bq = (
            select(Booking.slot_id, func.count().label("booked"))
            .where(Booking.status.in_(["hold", "confirmed"]))
            .group_by(Booking.slot_id)
            .subquery()
        )

        q = (
            select(
                Slot,
                func.coalesce(bq.c.booked, 0).label("booked"),
            )
            .outerjoin(bq, bq.c.slot_id == Slot.id)
            .where(Slot.provider_id == request.provider_id)
        )

        if status:
            q = q.where(Slot.status == status)

        rows = s.execute(q.order_by(Slot.start_at.desc())).all()

        slot_ids = [slot.id for slot, _ in rows]
        bookings_by_slot: dict[str, list[dict]] = {}
        canceled_counts: dict[str, int] = {}

        if slot_ids:
            booking_rows = (
                s.execute(
                    select(Booking)
                    .where(
                        Booking.slot_id.in_(slot_ids),
                        Booking.status.in_(["hold", "confirmed", "canceled"]),
                    )
                    .order_by(Booking.created_at.asc())
                )
                .scalars()
                .all()
            )

            for b in booking_rows:
                slot_id = b.slot_id
                bookings_by_slot.setdefault(slot_id, []).append(
                    {
                        "id": b.id,
                        "customer_name": b.customer_name,
                        "customer_email": b.customer_email,
                        "status": b.status,
                    }
                )
                if b.status == "canceled":
                    canceled_counts[slot_id] = canceled_counts.get(slot_id, 0) + 1

        out = []
        for slot, booked in rows:
            cap = slot.capacity or 1
            booked_int = int(booked or 0)
            available = max(0, cap - booked_int)

            item = slot_to_json(slot)
            item["booked"] = booked_int
            item["available"] = available
            item["bookings"] = bookings_by_slot.get(slot.id, [])
            item["has_canceled"] = canceled_counts.get(slot.id, 0) > 0
            item["canceled_count"] = canceled_counts.get(slot.id, 0)
            out.append(item)

        return jsonify(out)


# ... ab hier ist dein restlicher Code (Slots CRUD, Public Slots/Booking,
# Admin, Stripe/CopeCart) unverändert lang.
# Du kannst ihn aus deiner Version drunter lassen.
# WICHTIG: Wenn du willst, dass ich die komplette Datei 1:1 wieder zusammensetze
# inkl. ALLER unteren Bereiche, sag nur "ja, komplett zusammensetzen" und ich liefere
# dir die komplette Datei in einem Stück (hier würde es sonst unnötig 1000+ Zeilen).

# --------------------------------------------------------
# Start
# --------------------------------------------------------

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
            end = parse_iso_utc(data["end_at"])
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
        end_db = _to_db_utc_naive(end)

        with Session(engine) as s:
            p = s.get(Provider, request.provider_id)
            if not p or not is_profile_complete(p):
                return _json_error("profile_incomplete", 400)

            count = (
                s.scalar(
                    select(func.count())
                    .select_from(Slot)
                    .where(Slot.provider_id == request.provider_id, Slot.status.in_([SLOT_STATUS_DRAFT, SLOT_STATUS_PUBLISHED]))
                )
                or 0
            )
            if count > 50000:
                return _json_error("limit_reached", 400)

            title = (str(data["title"]).strip() or "Slot")[:100]
            category = normalize_category(data.get("category"))
            location_db = location[:120]

            # Falls Slot-Spalten für Adresse existieren: default = Provider-Adresse
            prov_zip = (p.zip or "").strip()
            prov_city = (p.city or "").strip()
            prov_street = (p.street or "").strip()

            slot_kwargs_extra = {}
            if hasattr(Slot, "zip"):
                slot_kwargs_extra["zip"] = prov_zip
            if hasattr(Slot, "city"):
                slot_kwargs_extra["city"] = prov_city
            if hasattr(Slot, "street"):
                slot_kwargs_extra["street"] = prov_street
            slot = Slot(
                provider_id=request.provider_id,
                title=title,
                category=category,
                start_at=start_db,
                end_at=end_db,
                location=location_db,
                capacity=cap,
                contact_method=(data.get("contact_method") or "mail"),
                booking_link=(data.get("booking_link") or None),
                price_cents=(data.get("price_cents") or None),
                notes=(data.get("notes") or None),
                status=SLOT_STATUS_DRAFT,
                **slot_kwargs_extra,
            )

            s.add(slot)
            try:
                s.commit()
            except IntegrityError as e:
                s.rollback()
                constraint = getattr(
                    getattr(getattr(e, "orig", None), "diag", None),
                    "constraint_name",
                    None,
                )
                if constraint == "slot_category_check":
                    return (
                        jsonify(
                            {
                                "error": "bad_category",
                                "detail": "Kategorie entspricht nicht den DB-Vorgaben.",
                            }
                        ),
                        400,
                    )
                return (
                    jsonify(
                        {
                            "error": "db_constraint_error",
                            "constraint": constraint,
                            "detail": str(e.orig),
                        }
                    ),
                    400,
                )
            except SQLAlchemyError as e:
                s.rollback()
                return jsonify({"error": "db_error", "detail": str(e)}), 400

            return jsonify(slot_to_json(slot)), 201

    except Exception as e:
        print("[/slots] server error:", traceback.format_exc(), flush=True)
        return jsonify({"error": "server_error", "detail": str(e)}), 500


@app.put("/slots/<slot_id>")
@auth_required()
def slots_update(slot_id):
    """
    Aktualisiert Slot-Daten.
    """
    try:
        data = request.get_json(force=True) or {}
        published_now = False

        with Session(engine) as s:
            slot = s.get(Slot, slot_id, with_for_update=True)
            if not slot or slot.provider_id != request.provider_id:
                return _json_error("not_found", 404)

            original_status = slot.status

            if "status" in data:
                target_status = str(data["status"] or "").strip().upper()
                if target_status not in VALID_STATUSES:
                    return _json_error("invalid_status", 400)

                if target_status != original_status:
                    try:
                        if original_status == SLOT_STATUS_DRAFT and target_status == SLOT_STATUS_PUBLISHED:
                            _publish_slot_quota_tx(s, request.provider_id, slot_id)
                            published_now = True
                        elif original_status == SLOT_STATUS_PUBLISHED and target_status == SLOT_STATUS_DRAFT:
                            _unpublish_slot_quota_tx(s, request.provider_id, slot_id)
                            published_now = False
                        else:
                            return _json_error("invalid_status_transition", 400)

                        slot = s.get(Slot, slot_id, with_for_update=True)
                        original_status = slot.status
                    except PublishLimitReached:
                        return _json_error("monthly_publish_limit_reached", 409)
                    except ValueError as e:
                        msg = str(e)
                        if msg == "not_found":
                            return _json_error("not_found", 404)
                        if msg in ("not_draft", "not_published"):
                            return _json_error(msg, 409)
                        if msg == "start_in_past":
                            return _json_error("start_in_past", 409)
                        if msg == "bad_capacity":
                            return _json_error("bad_capacity", 400)
                        return _json_error("bad_request", 400)

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

            if _as_utc_aware(slot.start_at) <= _now():
                return _json_error("start_in_past", 409)

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

            for k in [
                "title",
                "category",
                "location",
                "capacity",
                "contact_method",
                "booking_link",
                "price_cents",
                "notes",
            ]:
                if k in data:
                    setattr(slot, k, data[k])

            try:
                s.commit()
            except IntegrityError as e:
                s.rollback()
                constraint = getattr(
                    getattr(getattr(e, "orig", None), "diag", None),
                    "constraint_name",
                    None,
                )
                if constraint == "slot_category_check":
                    return (
                        jsonify(
                            {
                                "error": "bad_category",
                                "detail": "Kategorie entspricht nicht den DB-Vorgaben.",
                            }
                        ),
                        400,
                    )
                return (
                    jsonify(
                        {
                            "error": "db_constraint_error",
                            "constraint": constraint,
                            "detail": str(e.orig),
                        }
                    ),
                    400,
                )
            except SQLAlchemyError as e:
                s.rollback()
                return jsonify({"error": "db_error", "detail": str(e)}), 400

        if published_now:
            try:
                notify_alerts_for_slot(slot_id)
            except Exception:
                app.logger.exception("notify_alerts_for_slot (slots_update) failed")

        return jsonify({"ok": True})
    except Exception as e:
        print("[PUT /slots] server error:", traceback.format_exc(), flush=True)
        return jsonify({"error": "server_error", "detail": str(e)}), 500


@app.post("/slots/<slot_id>/publish")
@auth_required()
def slots_publish(slot_id):
    try:
        with Session(engine) as s:
            try:
                with s.begin():
                    result = _publish_slot_quota_tx(s, request.provider_id, slot_id)
            except PublishLimitReached:
                return _json_error("monthly_publish_limit_reached", 409)
            except ValueError as e:
                msg = str(e)
                if msg == "not_found":
                    return _json_error("not_found", 404)
                if msg == "not_draft":
                    return _json_error("not_draft", 409)
                if msg == "start_in_past":
                    return _json_error("start_in_past", 409)
                if msg == "bad_capacity":
                    return _json_error("bad_capacity", 400)
                return _json_error("bad_request", 400)

        try:
            notify_alerts_for_slot(slot_id)
        except Exception:
            app.logger.exception("notify_alerts_for_slot (slots_publish) failed")

        return jsonify({"ok": True, "quota": result})
    except Exception:
        app.logger.exception("slots_publish failed")
        return jsonify({"error": "server_error"}), 500


@app.post("/slots/<slot_id>/unpublish")
@auth_required()
def slots_unpublish(slot_id):
    try:
        with Session(engine) as s:
            try:
                with s.begin():
                    result = _unpublish_slot_quota_tx(s, request.provider_id, slot_id)
                return jsonify({"ok": True, "quota": result})
            except ValueError as e:
                msg = str(e)
                if msg == "not_found":
                    return _json_error("not_found", 404)
                if msg == "not_published":
                    return _json_error("not_published", 409)
                return _json_error("bad_request", 400)
    except Exception:
        app.logger.exception("slots_unpublish failed")
        return jsonify({"error": "server_error"}), 500


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
# Provider: Buchung aktiv stornieren (+ Mail an Kund:in)
# --------------------------------------------------------
@app.post("/provider/bookings/<booking_id>/cancel")
@auth_required()
def provider_cancel_booking(booking_id):
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()

    try:
        with Session(engine) as s:
            b = s.get(Booking, booking_id, with_for_update=True)
            if not b:
                return _json_error("not_found", 404)

            if b.provider_id != request.provider_id:
                return _json_error("forbidden", 403)

            if b.status == "canceled":
                return _json_error("already_canceled", 409)
            if b.status not in ("hold", "confirmed"):
                return _json_error("not_cancelable", 409)

            slot_obj = s.get(Slot, b.slot_id) if b.slot_id else None
            provider_obj = s.get(Provider, b.provider_id) if b.provider_id else None

            customer_email = b.customer_email
            customer_name = b.customer_name
            slot_title = slot_obj.title if slot_obj and slot_obj.title else "dein Termin"
            slot_time_iso = _from_db_as_iso_utc(slot_obj.start_at) if slot_obj else ""
            provider_name = (
                (provider_obj.company_name or provider_obj.email)
                if provider_obj
                else "der Anbieter"
            )
            booking_id_str = str(b.id)
            slot_id_str = str(b.slot_id) if b.slot_id else None

            b.status = "canceled"
            s.commit()

        try:
            if customer_email:
                reason_txt = f"\n\nBegründung:\n{reason}" if reason else ""
                body = (
                    f"Hallo {customer_name},\n\n"
                    f"dein Termin '{slot_title}' am {slot_time_iso} wurde von {provider_name} abgesagt."
                    f"{reason_txt}\n\n"
                    "Bitte buche bei Bedarf einen neuen Termin.\n\n"
                    "Viele Grüße\n"
                    "Terminmarktplatz"
                )

                ok, info = send_mail(
                    customer_email,
                    "Termin abgesagt",
                    text=body,
                    tag="booking_canceled_by_provider",
                    metadata={"booking_id": booking_id_str, "slot_id": slot_id_str},
                )
                print("[provider_cancel_booking][mail]", ok, info, flush=True)
        except Exception as e:
            print("[provider_cancel_booking][mail_error]", repr(e), flush=True)

        return jsonify({"ok": True})
    except Exception:
        app.logger.exception("provider_cancel_booking failed")
        return jsonify({"error": "server_error"}), 500


# --------------------------------------------------------
# Admin
# --------------------------------------------------------
@app.get("/admin/providers")
@auth_required(admin=True)
def admin_providers():
    status = request.args.get("status", "pending")
    with Session(engine) as s:
        items = (
            s.scalars(
                select(Provider)
                .where(Provider.status == status)
                .order_by(Provider.created_at.asc())
            )
            .all()
        )
        return jsonify(
            [
                {"id": p.id, "email": p.email, "company_name": p.company_name, "status": p.status}
                for p in items
            ]
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
    status = (request.args.get("status") or SLOT_STATUS_DRAFT).strip().upper()
    with Session(engine) as s:
        items = (
            s.scalars(
                select(Slot)
                .where(Slot.status == status)
                .order_by(Slot.start_at.asc())
            )
            .all()
        )
        return jsonify([slot_to_json(x) for x in items])


@app.post("/admin/slots/<sid>/publish")
@auth_required(admin=True)
def admin_slot_publish(sid):
    try:
        with Session(engine) as s:
            slot = s.get(Slot, sid)
            if not slot:
                return _json_error("not_found", 404)
            try:
                with s.begin():
                    result = _publish_slot_quota_tx(s, str(slot.provider_id), str(sid))
            except PublishLimitReached:
                return _json_error("monthly_publish_limit_reached", 409)
            except ValueError as e:
                msg = str(e)
                if msg == "not_draft":
                    return _json_error("not_draft", 409)
                if msg == "start_in_past":
                    return _json_error("start_in_past", 409)
                return _json_error("bad_request", 400)

        try:
            notify_alerts_for_slot(str(sid))
        except Exception:
            app.logger.exception("notify_alerts_for_slot (admin_slot_publish) failed")

        return jsonify({"ok": True, "quota": result})
    except Exception:
        app.logger.exception("admin_slot_publish failed")
        return jsonify({"error": "server_error"}), 500


@app.post("/admin/slots/<sid>/reject")
@auth_required(admin=True)
def admin_slot_reject(sid):
    """
    "reject" == unpublish (PUBLISHED -> DRAFT).
    """
    try:
        with Session(engine) as s:
            slot = s.get(Slot, sid)
            if not slot:
                return _json_error("not_found", 404)

            if slot.status == SLOT_STATUS_DRAFT:
                return jsonify({"ok": True, "already": SLOT_STATUS_DRAFT})

            if slot.status != SLOT_STATUS_PUBLISHED:
                return _json_error("not_published", 409)

            with s.begin():
                result = _unpublish_slot_quota_tx(s, str(slot.provider_id), str(sid))
            return jsonify({"ok": True, "quota": result})
    except Exception:
        app.logger.exception("admin_slot_reject failed")
        return jsonify({"error": "server_error"}), 500


@app.get("/admin/billing_overview")
@auth_required(admin=True)
def admin_billing_overview():
    with Session(engine) as s:
        rows = s.execute(
            select(
                Provider.id,
                Provider.email,
                Provider.company_name,
                func.count(Booking.id).label("booking_count"),
                func.coalesce(func.sum(Booking.provider_fee_eur), 0).label("total_eur"),
            )
            .join(Booking, Booking.provider_id == Provider.id)
            .where(Booking.status == "confirmed", Booking.fee_status == "open")
            .group_by(Provider.id, Provider.email, Provider.company_name)
            .order_by(Provider.created_at.asc())
        ).all()

    out = []
    for pid, email, company_name, booking_count, total_eur in rows:
        out.append(
            {
                "provider_id": pid,
                "email": email,
                "company_name": company_name,
                "booking_count": int(booking_count or 0),
                "total_eur": float(total_eur or 0),
            }
        )
    return jsonify(out)


@app.post("/admin/run_billing")
@auth_required(admin=True)
def admin_run_billing():
    data = request.get_json(silent=True) or {}
    now = _now()
    year = int(data.get("year") or now.year)

    if "month" in data and data["month"] is not None:
        month = int(data["month"])
    else:
        if now.month == 1:
            year = now.year - 1
            month = 12
        else:
            month = now.month - 1

    with Session(engine) as s:
        result = create_invoices_for_period(s, year, month)
        s.commit()

    return jsonify(result)


# --------------------------------------------------------
# Pakete / Stripe / CopeCart (Provider)
# --------------------------------------------------------
@app.post("/paket-buchen")
@auth_required()
def paket_buchen_start():
    data = request.get_json(silent=True) or {}
    plan_key = (
        data.get("plan")
        or request.form.get("plan")
        or request.form.get("plan_key")
        or request.args.get("plan")
        or "starter"
    )
    plan = PLANS.get(plan_key)
    if not plan:
        return _json_error("unknown_plan", 400)

    if stripe and STRIPE_SECRET_KEY:
        try:
            checkout_session = stripe.checkout.Session.create(
                mode="payment",
                success_url=f"{FRONTEND_URL}/anbieter-portal.html?plan_success=1",
                cancel_url=f"{FRONTEND_URL}/anbieter-portal.html?plan_cancel=1",
                line_items=[
                    {
                        "price_data": {
                            "currency": "eur",
                            "unit_amount": plan["price_cents"],
                            "product_data": {"name": f"{plan['name']} – Monatszugang"},
                        },
                        "quantity": 1,
                    }
                ],
                metadata={"provider_id": request.provider_id, "plan_key": plan_key},
            )
            return jsonify(
                {
                    "ok": True,
                    "provider_id": request.provider_id,
                    "plan": plan_key,
                    "checkout_url": checkout_session.url,
                }
            )
        except Exception as e:
            app.logger.exception("stripe checkout failed")
            return jsonify({"error": "stripe_error", "detail": str(e)}), 500

    today = date.today()
    period_start = today
    period_end = today + timedelta(days=30)

    with Session(engine) as s:
        p = s.get(Provider, request.provider_id)
        if not p:
            return _json_error("not_found", 404)

        p.plan = plan_key
        p.plan_valid_until = period_end
        p.free_slots_per_month = plan["free_slots"]

        purchase = PlanPurchase(
            provider_id=p.id,
            plan=plan_key,
            price_eur=plan["price_eur"],
            period_start=period_start,
            period_end=period_end,
            payment_provider="manual",
            payment_ref="no-stripe",
            status="paid",
        )
        s.add(purchase)
        s.commit()

    # Optional: Aktivierungs-Mail (manual)
    try:
        with Session(engine) as s2:
            p2 = s2.get(Provider, request.provider_id)
        if p2:
            send_email_plan_activated(p2, plan_key, "manual", period_start, period_end)
    except Exception:
        pass

    return jsonify({"ok": True, "provider_id": request.provider_id, "plan": plan_key, "mode": "manual_no_stripe"})


@app.post("/webhook/stripe")
def stripe_webhook():
    if not (stripe and STRIPE_WEBHOOK_SECRET):
        return jsonify({"error": "stripe_not_configured"}), 501

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        app.logger.exception("stripe webhook signature error")
        return jsonify({"error": "invalid_signature", "detail": str(e)}), 400

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        metadata = session_obj.get("metadata", {}) or {}
        provider_id = metadata.get("provider_id")
        plan_key = metadata.get("plan_key")
        plan = PLANS.get(plan_key)

        if not provider_id or not plan:
            return jsonify({"error": "missing_metadata"}), 400

        today = date.today()
        period_start = today
        period_end = today + timedelta(days=30)

        with Session(engine) as s:
            p = s.get(Provider, provider_id)
            if not p:
                return jsonify({"error": "provider_not_found"}), 404

            p.plan = plan_key
            p.plan_valid_until = period_end
            p.free_slots_per_month = plan["free_slots"]

            purchase = PlanPurchase(
                provider_id=p.id,
                plan=plan_key,
                price_eur=plan["price_eur"],
                period_start=period_start,
                period_end=period_end,
                payment_provider="stripe",
                payment_ref=session_obj.get("id"),
                status="paid",
            )
            s.add(purchase)
            s.commit()

        # Optional: Aktivierungs-Mail (stripe)
        try:
            with Session(engine) as s2:
                p2 = s2.get(Provider, provider_id)
            if p2:
                send_email_plan_activated(p2, plan_key, "stripe", period_start, period_end)
        except Exception:
            pass

    return jsonify({"ok": True})


@app.post("/webhook/copecart")
def copecart_webhook():
    if not COPECART_WEBHOOK_SECRET:
        app.logger.warning("CopeCart webhook hit, but COPECART_WEBHOOK_SECRET not set")
        return "OK", 200

    sig = request.headers.get("X-Copecart-Signature", "")
    raw_body = request.get_data() or b""

    generated = base64.b64encode(
        hmac.new(
            COPECART_WEBHOOK_SECRET.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).digest()
    ).decode("ascii")

    if not sig or not hmac.compare_digest(sig, generated):
        app.logger.warning("CopeCart webhook: invalid signature")
        return "invalid signature", 400

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        app.logger.exception("CopeCart webhook: invalid JSON")
        return "invalid json", 400

    app.logger.info("CopeCart IPN payload: %s", payload)

    event_type = payload.get("event_type")
    payment_status = payload.get("payment_status")
    transaction_type = payload.get("transaction_type")
    product_id = payload.get("product_id")
    buyer_email = (payload.get("buyer_email") or "").strip().lower()

    if not (event_type and payment_status and product_id and buyer_email):
        app.logger.warning("CopeCart webhook: missing required fields")
        return "OK", 200

    product_id_str = str(product_id)

    plan_key = COPECART_PRODUCT_PLAN_MAP.get(product_id_str)
    alert_plan_key = COPECART_ALERT_PRODUCT_MAP.get(product_id_str)

    if not plan_key and not alert_plan_key:
        app.logger.info("CopeCart webhook: product_id %s not mapped", product_id_str)
        return "OK", 200

    if event_type not in ("payment.made", "payment.trial"):
        return "OK", 200

    if payment_status not in ("paid", "test_paid", "trial", "test_trial"):
        return "OK", 200

    if transaction_type and transaction_type not in ("sale",):
        return "OK", 200

    payment_ref = payload.get("transaction_id") or payload.get("order_id")

    try:
        with Session(engine) as s:
            if plan_key:
                plan_conf = PLANS.get(plan_key)
                if not plan_conf:
                    app.logger.warning("CopeCart webhook: plan_key %s not in PLANS", plan_key)
                    return "OK", 200

                p = s.scalar(select(Provider).where(Provider.email == buyer_email))
                if not p:
                    app.logger.warning("CopeCart webhook: no provider with email %s", buyer_email)
                    return "OK", 200

                if payment_ref:
                    existing = s.scalar(
                        select(PlanPurchase).where(
                            PlanPurchase.payment_provider == "copecart",
                            PlanPurchase.payment_ref == str(payment_ref),
                        )
                    )
                    if existing:
                        app.logger.info("CopeCart webhook: PlanPurchase with ref %s already exists", payment_ref)
                        return "OK", 200

                today = date.today()
                period_start = today
                period_end = today + timedelta(days=30)

                p.plan = plan_key
                p.plan_valid_until = period_end
                p.free_slots_per_month = plan_conf["free_slots"]

                purchase = PlanPurchase(
                    provider_id=p.id,
                    plan=plan_key,
                    price_eur=plan_conf["price_eur"],
                    period_start=period_start,
                    period_end=period_end,
                    payment_provider="copecart",
                    payment_ref=str(payment_ref) if payment_ref else None,
                    status="paid",
                )
                s.add(purchase)
                s.commit()

                # Optional: Aktivierungs-Mail (copecart)
                try:
                    send_email_plan_activated(p, plan_key, "copecart", period_start, period_end)
                except Exception:
                    pass

                return "OK", 200

            if alert_plan_key:
                alert_conf = ALERT_PLANS.get(alert_plan_key)
                if not alert_conf:
                    app.logger.warning("CopeCart webhook: alert_plan_key %s not in ALERT_PLANS", alert_plan_key)
                    return "OK", 200

                alerts = (
                    s.execute(
                        select(AlertSubscription).where(AlertSubscription.email == buyer_email)
                    )
                    .scalars()
                    .all()
                )
                if not alerts:
                    app.logger.info(
                        "CopeCart webhook: no AlertSubscription for email %s (alert plan %s)",
                        buyer_email,
                        alert_plan_key,
                    )
                    return "OK", 200

                now = _now()
                sms_quota = int(alert_conf.get("sms_quota_month") or 0)

                for a in alerts:
                    a.package_name = alert_plan_key
                    a.sms_quota_month = sms_quota
                    a.sms_sent_this_month = 0
                    a.last_reset_quota = now

                s.commit()
                return "OK", 200

        return "OK", 200
    except Exception:
        app.logger.exception("CopeCart webhook failed")
        return "server error", 500


# --------------------------------------------------------
# Public (Slots + Booking)
# --------------------------------------------------------
BOOKING_HOLD_MIN = 15  # Minuten


def _booking_token(booking_id: str) -> str:
    return jwt.encode(
        {
            "sub": booking_id,
            "typ": "booking",
            "iss": JWT_ISS,
            "exp": int((_now() + timedelta(hours=6)).timestamp()),
        },
        SECRET,
        algorithm="HS256",
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
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(dlon / 2) ** 2
    )
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


@app.get("/public/slots")
def public_slots():
    q_text = (request.args.get("q") or "").strip()
    location_raw = (request.args.get("location") or "").strip()
    if not location_raw:
        location_raw = (request.args.get("ort") or "").strip()

    radius_raw = (request.args.get("radius") or "").strip()
    datum_raw = (request.args.get("datum") or "").strip()
    _zeit = (request.args.get("zeit") or "").strip()

    category = (request.args.get("category") or "").strip()
    city_q = (request.args.get("city") or "").strip()
    zip_filter = (request.args.get("zip") or "").strip()
    day_str = (request.args.get("day") or "").strip()
    from_str = (request.args.get("from") or "").strip()
    include_full = request.args.get("include_full") == "1"

    if location_raw and not zip_filter and not city_q:
        if location_raw.isdigit() and len(location_raw) == 5:
            zip_filter = location_raw
        else:
            city_q = location_raw

    search_term = q_text
    if not category and q_text in BRANCHES:
        category = q_text

    try:
        radius_km = float(radius_raw) if radius_raw else None
    except ValueError:
        radius_km = None

    start_from = None
    end_until = None
    try:
        if datum_raw:
            parts = datum_raw.split(".")
            if len(parts) == 3:
                d, m, y = map(int, parts)
                start_local = datetime(y, m, d, 0, 0, 0, tzinfo=BERLIN)
                end_local = start_local + timedelta(days=1)
                start_from = start_local.astimezone(timezone.utc)
                end_until = end_local.astimezone(timezone.utc)
        elif day_str:
            y, m, d = map(int, day_str.split("-"))
            start_local = datetime(y, m, d, 0, 0, 0, tzinfo=BERLIN)
            end_local = start_local + timedelta(days=1)
            start_from = start_local.astimezone(timezone.utc)
            end_until = end_local.astimezone(timezone.utc)
        elif from_str:
            start_from = parse_iso_utc(from_str)
        else:
            start_from = _now()
    except Exception:
        start_from = _now()
        end_until = None

    with Session(engine) as s:
        origin_lat = origin_lon = None
        if radius_km is not None and (zip_filter or city_q):
            origin_lat, origin_lon = geocode_cached(
                s,
                zip_filter if zip_filter else None,
                None if zip_filter else city_q,
            )

        bq = (
            select(Booking.slot_id, func.count().label("booked"))
            .where(Booking.status.in_(["hold", "confirmed"]))
            .group_by(Booking.slot_id)
            .subquery()
        )

        sq = (
            select(
                Slot,
                Provider,
                func.coalesce(bq.c.booked, 0).label("booked"),
            )
            .join(Provider, Provider.id == Slot.provider_id)
            .outerjoin(bq, bq.c.slot_id == Slot.id)
            .where(Slot.status == SLOT_STATUS_PUBLISHED)
        )

        if start_from is not None:
            sq = sq.where(Slot.start_at >= _to_db_utc_naive(start_from))
        if end_until is not None:
            sq = sq.where(Slot.start_at < _to_db_utc_naive(end_until))

        if category:
            if category in BRANCHES:
                sq = sq.where(Slot.category == category)
            else:
                sq = sq.where(Slot.category.ilike(f"%{category}%"))

        if radius_km is None:
            loc_for_filter = location_raw or city_q or zip_filter
            if loc_for_filter:
                pattern_loc = f"%{loc_for_filter}%"
                sq = sq.where(Slot.location.ilike(pattern_loc))

        if search_term:
            pattern = f"%{search_term}%"
            sq = sq.where(or_(Slot.title.ilike(pattern), Slot.category.ilike(pattern)))

        sq = sq.order_by(Slot.start_at.asc()).limit(300)

        rows = s.execute(sq).all()

        out = []
        for slot, provider, booked in rows:
            cap = slot.capacity or 1
            available = max(0, cap - int(booked or 0))
            if not include_full and available <= 0:
                continue

            p_zip = provider.zip
            p_city = provider.city

            if radius_km is not None:
                if origin_lat is None or origin_lon is None:
                    continue
                plat, plon = geocode_cached(s, p_zip, p_city)
                if plat is None or plon is None:
                    continue
                if _haversine_km(origin_lat, origin_lon, plat, plon) > radius_km:
                    continue

            item = slot_to_json(slot)
            item["available"] = available

            try:
                provider_dict = provider.to_public_dict()
            except Exception:
                provider_dict = {
                    "id": provider.id,
                    "name": getattr(provider, "public_name", None)
                    or provider.company_name
                    or provider.email,
                    "street": provider.street,
                    "zip": provider.zip,
                    "city": provider.city,
                    "address": f"{provider.street or ''}, {provider.zip or ''} {provider.city or ''}".strip(", "),
                    "branch": provider.branch,
                    "phone": provider.phone,
                    "whatsapp": provider.whatsapp,
                }

            item["provider"] = provider_dict
            item["provider_zip"] = p_zip
            item["provider_city"] = p_city

            out.append(item)

        return jsonify(out)


@app.post("/public/book")
def public_book():
    data = request.get_json(force=True)
    slot_id = (data.get("slot_id") or "").strip()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()

    if not slot_id or not name or not email:
        return _json_error("missing_fields")

    try:
        email = validate_email(email).email
    except EmailNotValidError:
        return _json_error("invalid_email", 400)

    with Session(engine) as s:
        slot = s.get(Slot, slot_id, with_for_update=True)
        if not slot:
            return _json_error("not_found", 404)

        if slot.status != SLOT_STATUS_PUBLISHED or _as_utc_aware(slot.start_at) <= _now():
            return _json_error("not_bookable", 409)

        active = (
            s.scalar(
                select(func.count())
                .select_from(Booking)
                .where(
                    and_(
                        Booking.slot_id == slot.id,
                        Booking.status.in_(["hold", "confirmed"]),
                    )
                )
            )
            or 0
        )
        if active >= (slot.capacity or 1):
            return _json_error("slot_full", 409)

        provider = s.get(Provider, slot.provider_id)
        if provider and provider.booking_fee_eur is not None:
            fee = provider.booking_fee_eur
        else:
            fee = Decimal("2.00")

        b = Booking(
            slot_id=slot.id,
            provider_id=slot.provider_id,
            customer_name=name,
            customer_email=email,
            status="hold",
            provider_fee_eur=fee,
        )
        s.add(b)
        s.commit()

        token = _booking_token(b.id)
        base = _external_base()
        confirm_link = f"{base}{url_for('public_confirm')}?token={token}"
        cancel_link = f"{base}{url_for('public_cancel')}?token={token}"
        send_mail(
            email,
            "Bitte Terminbuchung bestätigen",
            text=(
                f"Hallo {name},\n\n"
                f"bitte bestätige deine Buchung:\n{confirm_link}\n\n"
                f"Stornieren:\n{cancel_link}\n"
            ),
            tag="booking_request",
            metadata={"slot_id": str(slot.id)},
        )
        return jsonify({"ok": True})


@app.get("/public/confirm")
def public_confirm():
    token = request.args.get("token")
    booking_id = _verify_booking_token(token) if token else None
    if not booking_id:
        return _json_error("invalid_token", 400)

    try:
        with Session(engine) as s:
            b = s.get(Booking, booking_id, with_for_update=True)
            if not b:
                return _json_error("not_found", 404)

            slot_obj = s.get(Slot, b.slot_id) if b.slot_id else None
            provider_obj = s.get(Provider, slot_obj.provider_id) if slot_obj else None

            already_confirmed = b.status == "confirmed"

            if b.status == "hold":
                created_at_aware = _as_utc_aware(b.created_at)
                if (_now() - created_at_aware) > timedelta(minutes=BOOKING_HOLD_MIN):
                    b.status = "canceled"
                    s.commit()
                    return _json_error("hold_expired", 409)

                if not slot_obj:
                    b.status = "canceled"
                    s.commit()
                    return _json_error("slot_missing", 404)

                active = (
                    s.scalar(
                        select(func.count())
                        .select_from(Booking)
                        .where(
                            and_(
                                Booking.slot_id == slot_obj.id,
                                Booking.status.in_(["hold", "confirmed"]),
                            )
                        )
                    )
                    or 0
                )
                if active > (slot_obj.capacity or 1):
                    b.status = "canceled"
                    s.commit()
                    return _json_error("slot_full", 409)

                b.status = "confirmed"
                b.confirmed_at = _now()
                s.commit()

                send_mail(
                    b.customer_email,
                    "Termin bestätigt",
                    text="Dein Termin ist bestätigt.",
                    tag="booking_confirmed",
                    metadata={"slot_id": str(slot_obj.id)},
                )

            elif b.status == "canceled":
                return _json_error("booking_canceled", 409)

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
            "buchung_erfolg.html",
            booking=booking,
            slot=slot,
            provider=provider,
            bereits_bestaetigt=already_confirmed,
            frontend_url=FRONTEND_URL,
        )
    except Exception:
        app.logger.exception("public_confirm failed")
        return jsonify({"error": "server_error"}), 500


@app.get("/public/cancel")
def public_cancel():
    token = request.args.get("token")
    booking_id = _verify_booking_token(token) if token else None
    if not booking_id:
        return _json_error("invalid_token", 400)

    just_canceled = False
    customer_email = None
    customer_name = None
    slot_title = "dein Termin"
    slot_time_iso = ""
    provider_email = None
    provider_name = "der Anbieter"

    try:
        with Session(engine) as s:
            b = s.get(Booking, booking_id, with_for_update=True)
            if not b:
                return _json_error("not_found", 404)

            slot_obj = s.get(Slot, b.slot_id) if b.slot_id else None
            provider_obj = s.get(Provider, slot_obj.provider_id) if slot_obj else None

            already_canceled = b.status == "canceled"

            customer_email = b.customer_email
            customer_name = b.customer_name
            if slot_obj is not None:
                slot_title = slot_obj.title or "dein Termin"
                slot_time_iso = _from_db_as_iso_utc(slot_obj.start_at)
            if provider_obj is not None:
                provider_email = provider_obj.email
                provider_name = (provider_obj.company_name or provider_obj.email) or provider_name

            if b.status in ("hold", "confirmed"):
                b.status = "canceled"
                s.commit()
                just_canceled = True

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

        if just_canceled:
            try:
                if customer_email:
                    body_cust = (
                        f"Hallo {customer_name},\n\n"
                        f"deine Buchung für '{slot_title}' am {slot_time_iso} wurde storniert.\n\n"
                        "Wenn du möchtest, kannst du einen neuen Termin buchen.\n\n"
                        "Viele Grüße\n"
                        "Terminmarktplatz"
                    )
                    send_mail(
                        customer_email,
                        "Termin storniert",
                        text=body_cust,
                        tag="booking_canceled_by_customer",
                        metadata={
                            "booking_id": str(booking["id"]),
                            "slot_id": str(slot["id"]) if slot else None,
                        },
                    )
            except Exception as e:
                print("[public_cancel][mail_customer_error]", repr(e), flush=True)

            try:
                if provider_email:
                    body_prov = (
                        f"Hallo {provider_name},\n\n"
                        f"die Buchung von {customer_name} für '{slot_title}' am {slot_time_iso} "
                        "wurde von der Kundin / dem Kunden storniert.\n\n"
                        "Viele Grüße\n"
                        "Terminmarktplatz"
                    )
                    send_mail(
                        provider_email,
                        "Buchung storniert",
                        text=body_prov,
                        tag="booking_canceled_notify_provider",
                        metadata={
                            "booking_id": str(booking["id"]),
                            "slot_id": str(slot["id"]) if slot else None,
                        },
                    )
            except Exception as e:
                print("[public_cancel][mail_provider_error]", repr(e), flush=True)

        return render_template(
            "buchung_storniert.html",
            booking=booking,
            slot=slot,
            provider=provider,
            bereits_storniert=already_canceled,
            frontend_url=FRONTEND_URL,
        )
    except Exception:
        app.logger.exception("public_cancel failed")
        return jsonify({"error": "server_error"}), 500


# --------------------------------------------------------
# Start
# --------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
