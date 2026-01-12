import os
import traceback
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal  # für Geldbeträge
from typing import Optional

import json
import hmac
import hashlib
import base64
import re

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
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, OperationalError

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
    send_from_directory,
    Response,
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
from models import Base, Provider, Slot, Booking, PlanPurchase, Invoice, AlertSubscription, PasswordReset

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
if DB_URL and DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DB_URL and DB_URL.startswith("postgresql://"):
    DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# Prüfe ob es PostgreSQL ist (für connect_args)
_is_postgresql_url = DB_URL and ("postgresql" in DB_URL.lower() or "postgres" in DB_URL.lower())

# --------------------------------------------------------
# DB / Crypto / CORS
# --------------------------------------------------------
# connect_args nur für PostgreSQL setzen (SQLite unterstützt kein sslmode)
if _is_postgresql_url:
    engine = create_engine(
        DB_URL,
        pool_pre_ping=True,     # prüft Verbindung vor Benutzung
        pool_recycle=300,       # recycelt Connections alle 5 Minuten (Render PostgreSQL Timeout)
        pool_timeout=30,
        pool_size=5,
        max_overflow=10,
        echo=False,
        connect_args={
            # bei Render/Supabase/managed Postgres fast immer korrekt:
            "sslmode": os.getenv("PGSSLMODE", "require"),
            "connect_timeout": 10,  # Timeout für initiale Verbindung
        },
    )
else:
    # SQLite oder andere Datenbanken (keine connect_args mit sslmode)
    engine = create_engine(
        DB_URL,
        pool_pre_ping=True,
        pool_timeout=30,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )

# Datenbanktyp erkennen (dynamisch über engine.dialect)
def _get_db_type():
    """Ermittelt den Datenbanktyp (postgresql, sqlite, etc.)"""
    try:
        dialect_name = engine.dialect.name
        return dialect_name.lower()
    except Exception:
        # Fallback: Prüfe URL
        db_url_lower = DB_URL.lower()
        if "postgresql" in db_url_lower or "postgres" in db_url_lower:
            return "postgresql"
        elif "sqlite" in db_url_lower:
            return "sqlite"
        return "unknown"

DB_TYPE = _get_db_type()
IS_POSTGRESQL = DB_TYPE == "postgresql"
IS_SQLITE = DB_TYPE == "sqlite"

ph = PasswordHasher(time_cost=2, memory_cost=102_400, parallelism=8)

# --- CORS -------------------------------------------------
# --- CORS -------------------------------------------------
if IS_RENDER:
    # Prüfe ob es ein Testsystem ist (basierend auf RENDER_EXTERNAL_URL oder Service-Name)
    RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
    IS_TESTSYSTEM = "testsystem" in RENDER_EXTERNAL_URL.lower() or "test" in RENDER_EXTERNAL_URL.lower()
    
    if IS_TESTSYSTEM:
        # Testsystem: Erlaube die Testsystem-URL und Produktions-URLs
        ALLOWED_ORIGINS = [
            RENDER_EXTERNAL_URL.rstrip("/"),  # Testsystem-URL
            "https://terminmarktplatz.de",
            "https://www.terminmarktplatz.de",
        ]
    else:
        # Produktion: Nur Produktions-URLs
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
        # ✅ Cookie/Credentials nötig (Provider-Login/Portal)
        r"/auth/*": {"origins": ALLOWED_ORIGINS, "supports_credentials": True},
        r"/me": {"origins": ALLOWED_ORIGINS, "supports_credentials": True},
        r"/me/*": {"origins": ALLOWED_ORIGINS, "supports_credentials": True},
        r"/provider/*": {"origins": ALLOWED_ORIGINS, "supports_credentials": True},
        r"/admin/*": {"origins": ALLOWED_ORIGINS, "supports_credentials": True},
        r"/paket-buchen*": {"origins": ALLOWED_ORIGINS, "supports_credentials": True},
        r"/copecart/*": {"origins": ALLOWED_ORIGINS, "supports_credentials": True},
        r"/slots*": {"origins": ALLOWED_ORIGINS, "supports_credentials": True},  # ✅ FIX

        # ✅ Ohne Cookies (public / alerts)
        r"/api/*": {"origins": ALLOWED_ORIGINS, "supports_credentials": False},
        # Public API: Alle Origins erlauben für Facebook in-app Browser & andere Embeddings
        r"/public/*": {"origins": "*", "supports_credentials": False},
        r"/alerts/*": {"origins": ALLOWED_ORIGINS, "supports_credentials": False},

        # Webhooks / health / assets
        r"/webhook/stripe": {"origins": ALLOWED_ORIGINS, "supports_credentials": False},
        r"/webhook/copecart": {"origins": ALLOWED_ORIGINS, "supports_credentials": False},
        r"/api/health": {"origins": "*", "supports_credentials": False},
        r"/healthz": {"origins": "*", "supports_credentials": False},
        r"/static/*": {"origins": "*", "supports_credentials": False},
    },
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
)




@app.after_request
def add_headers(resp):
    resp.headers.setdefault("Cache-Control", "no-store")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    # SAMEORIGIN statt DENY für Facebook in-app Browser Kompatibilität
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "no-referrer-when-downgrade")
    
    # Dynamische CORS-Header für Testsysteme auf Render
    # Überschreibt Flask-CORS für Testsystem-Origins
    if IS_RENDER:
        origin = request.headers.get("Origin")
        if origin:
            origin_lower = origin.lower()
            # Erlaube Testsystem-Origins (onrender.com mit "test" im Namen)
            is_testsystem_origin = (
                "onrender.com" in origin_lower and 
                ("test" in origin_lower or "testsystem" in origin_lower)
            )
            
            if is_testsystem_origin:
                # Setze/Überschreibe CORS-Header für Testsystem-Origins
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Allow-Credentials"] = "true"
                resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
                resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
                # Erlaube alle Request-Header für Preflight
                if request.method == "OPTIONS":
                    resp.status_code = 200
    
    return resp


# --------------------------------------------------------
# Basistabellen erstellen (falls nicht vorhanden)
# --------------------------------------------------------
def _ensure_base_tables():
    """
    Erstellt die Basistabellen (provider, slot, booking, etc.), falls sie nicht existieren.
    Wichtig für lokale SQLite-Entwicklung, wo Tabellen möglicherweise nicht initialisiert wurden.
    """
    try:
        with engine.begin() as conn:
            if IS_POSTGRESQL:
                # PostgreSQL: Verwende SQLAlchemy Metadata (benötigt aber safe_uuid_v4() Funktion)
                # Für PostgreSQL erwarten wir, dass db_init.sql bereits ausgeführt wurde
                try:
                    result = conn.execute(text("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' AND table_name = 'provider'
                        )
                    """))
                    if result.scalar():
                        return  # Tabellen existieren bereits
                except Exception:
                    pass
                
                try:
                    from models import Base
                    Base.metadata.create_all(engine, checkfirst=True)
                except Exception as e:
                    print(f"⚠️  Warnung: Basistabellen konnten nicht erstellt werden (PostgreSQL): {e}", flush=True)
            else:
                # SQLite: Erstelle Tabellen manuell (SQLite-kompatibel)
                try:
                    result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='provider'"))
                    if result.fetchone():
                        return  # Tabellen existieren bereits
                except Exception:
                    pass
                
                # Erstelle Basistabellen für SQLite
                ddl_provider = """
                CREATE TABLE IF NOT EXISTS provider (
                  id TEXT PRIMARY KEY,
                  email TEXT UNIQUE NOT NULL,
                  email_verified_at DATETIME,
                  pw_hash TEXT NOT NULL,
                  company_name TEXT,
                  branch TEXT,
                  street TEXT,
                  zip TEXT,
                  city TEXT,
                  phone TEXT,
                  whatsapp TEXT,
                  status TEXT NOT NULL DEFAULT 'pending',
                  is_admin INTEGER NOT NULL DEFAULT 0,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  "plan" TEXT,
                  plan_valid_until DATETIME,
                  free_slots_per_month INTEGER,
                  booking_fee_eur NUMERIC,
                  provider_number INTEGER
                );
                """
                
                ddl_slot = """
                CREATE TABLE IF NOT EXISTS slot (
                  id TEXT PRIMARY KEY,
                  provider_id TEXT NOT NULL REFERENCES provider(id) ON DELETE CASCADE,
                  title TEXT NOT NULL,
                  category TEXT NOT NULL,
                  start_at DATETIME NOT NULL,
                  end_at DATETIME NOT NULL,
                  location TEXT,
                  street TEXT,
                  house_number TEXT,
                  zip TEXT,
                  city TEXT,
                  lat REAL,
                  lng REAL,
                  capacity INTEGER NOT NULL DEFAULT 1,
                  contact_method TEXT NOT NULL DEFAULT 'mail',
                  booking_link TEXT,
                  price_cents INTEGER,
                  notes TEXT,
                  status TEXT NOT NULL DEFAULT 'DRAFT',
                  published_at DATETIME,
                  archived INTEGER DEFAULT 0,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
                
                ddl_booking = """
                CREATE TABLE IF NOT EXISTS booking (
                  id TEXT PRIMARY KEY,
                  slot_id TEXT NOT NULL REFERENCES slot(id) ON DELETE CASCADE,
                  provider_id TEXT NOT NULL REFERENCES provider(id) ON DELETE CASCADE,
                  name TEXT NOT NULL,
                  email TEXT NOT NULL,
                  phone TEXT,
                  message TEXT,
                  status TEXT NOT NULL DEFAULT 'pending',
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
                
                conn.exec_driver_sql(ddl_provider)
                conn.exec_driver_sql(ddl_slot)
                conn.exec_driver_sql(ddl_booking)
                
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS slot_status_start_idx ON slot(status, start_at)")
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS slot_provider_id_idx ON slot(provider_id)")
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS booking_slot_id_idx ON booking(slot_id)")
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS booking_provider_id_idx ON booking(provider_id)")
                
                print("✓ Basistabellen für SQLite erstellt", flush=True)
    except (OperationalError, SQLAlchemyError) as e:
        print(f"⚠️  Warnung: Basistabellen konnten nicht erstellt werden: {e}", flush=True)


# Versuche beim Start, aber stürze nicht ab, wenn die DB nicht verfügbar ist
# WICHTIG: Erst Basistabellen erstellen, dann Migrationen ausführen
_ensure_base_tables()


# --------------------------------------------------------
# Geocode-Cache (idempotent)
# --------------------------------------------------------
def _ensure_geo_tables():
    """
    Erstellt die Geocode-Cache-Tabelle, falls sie nicht existiert.
    Fängt Fehler ab, damit die App auch startet, wenn die DB noch nicht verfügbar ist.
    """
    try:
        if IS_POSTGRESQL:
            ddl_cache = """
            CREATE TABLE IF NOT EXISTS geocode_cache (
              key text PRIMARY KEY,
              lat double precision,
              lon double precision,
              updated_at timestamp with time zone DEFAULT now()
            );
            """
        else:
            # SQLite-kompatibel
            ddl_cache = """
            CREATE TABLE IF NOT EXISTS geocode_cache (
              key text PRIMARY KEY,
              lat REAL,
              lon REAL,
              updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        with engine.begin() as conn:
            conn.exec_driver_sql(ddl_cache)
    except (OperationalError, SQLAlchemyError) as e:
        # Logge den Fehler, aber verhindere nicht den App-Start
        print(f"⚠️  Warnung: Geocode-Tabellen konnten nicht erstellt werden: {e}", flush=True)
        print("   Die Tabellen werden beim ersten Request erstellt, wenn die DB verfügbar ist.", flush=True)


_ensure_geo_tables()


# --------------------------------------------------------
# Kategorie-Constraint entfernen (ermöglicht alle Kategorien)
# --------------------------------------------------------
def _remove_category_constraint():
    """
    Entfernt den alten CHECK-Constraint für Kategorien, damit alle Kategorien aus BRANCHES erlaubt sind.
    Die Validierung erfolgt jetzt in der Anwendung (normalize_category).
    """
    try:
        with engine.begin() as conn:
            if IS_POSTGRESQL:
                # PostgreSQL: Verwende DO-Block
                ddl_remove_constraint = """
                DO $$
                BEGIN
                  IF EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'slot_category_check'
                  ) THEN
                    ALTER TABLE public.slot DROP CONSTRAINT slot_category_check;
                  END IF;
                END $$;
                """
                conn.exec_driver_sql(ddl_remove_constraint)
            else:
                # SQLite: Prüfe ob Tabelle existiert, dann Constraint entfernen
                # SQLite unterstützt keine direkte Constraint-Entfernung, daher überspringen wir dies
                # Die Validierung erfolgt sowieso in der Anwendung
                pass
    except (OperationalError, SQLAlchemyError) as e:
        print(f"⚠️  Warnung: remove_category_constraint fehlgeschlagen: {e}", flush=True)


_remove_category_constraint()


# --------------------------------------------------------
# AlertSubscription: deleted_at Feld hinzufügen (Soft-Delete)
# --------------------------------------------------------
def _ensure_alert_deleted_at():
    """
    Fügt das deleted_at Feld zur alert_subscription Tabelle hinzu, falls es noch nicht existiert.
    Ermöglicht Soft-Delete, damit gelöschte Benachrichtigungen weiterhin zum Limit zählen.
    """
    try:
        with engine.begin() as conn:
            if IS_POSTGRESQL:
                # PostgreSQL: ADD COLUMN IF NOT EXISTS
                ddl_add_deleted_at = """
                ALTER TABLE public.alert_subscription
                  ADD COLUMN IF NOT EXISTS deleted_at timestamp without time zone;
                """
                conn.exec_driver_sql(ddl_add_deleted_at)
            else:
                # SQLite: Prüfe ob Tabelle existiert, dann ob Spalte existiert
                try:
                    # Prüfe ob Tabelle existiert
                    conn.execute(text("SELECT 1 FROM alert_subscription LIMIT 1"))
                    # Tabelle existiert, prüfe ob Spalte existiert
                    try:
                        conn.execute(text("SELECT deleted_at FROM alert_subscription LIMIT 1"))
                        # Spalte existiert bereits
                    except Exception:
                        # Spalte existiert nicht, hinzufügen
                        conn.exec_driver_sql("ALTER TABLE alert_subscription ADD COLUMN deleted_at DATETIME")
                except Exception:
                    # Tabelle existiert nicht - ignorieren (wird später erstellt)
                    pass
    except (OperationalError, SQLAlchemyError) as e:
        print(f"⚠️  Warnung: ensure_alert_deleted_at fehlgeschlagen: {e}", flush=True)


_ensure_alert_deleted_at()


# --------------------------------------------------------
# PasswordReset Tabelle sicherstellen
# --------------------------------------------------------
def _ensure_password_reset_table():
    """
    Erstellt die password_reset Tabelle, falls sie noch nicht existiert.
    """
    try:
        with engine.begin() as conn:
            if IS_POSTGRESQL:
                # PostgreSQL: Tabellen-Erstellung und Indizes einzeln (meist sicherer)
                ddl_table = """
                CREATE TABLE IF NOT EXISTS password_reset (
                  id uuid PRIMARY KEY DEFAULT safe_uuid_v4(),
                  provider_id uuid NOT NULL REFERENCES provider(id) ON DELETE CASCADE,
                  token text UNIQUE NOT NULL,
                  expires_at timestamp without time zone NOT NULL,
                  used_at timestamp without time zone,
                  created_at timestamp without time zone NOT NULL DEFAULT now()
                );
                """
                ddl_idx1 = "CREATE INDEX IF NOT EXISTS password_reset_provider_id_idx ON password_reset(provider_id);"
                ddl_idx2 = "CREATE INDEX IF NOT EXISTS password_reset_token_idx ON password_reset(token);"
                ddl_idx3 = "CREATE INDEX IF NOT EXISTS password_reset_expires_at_idx ON password_reset(expires_at) WHERE used_at IS NULL;"
                
                # Jedes Statement einzeln ausführen (sicherer für beide DB-Typen)
                conn.exec_driver_sql(ddl_table)
                try:
                    conn.exec_driver_sql(ddl_idx1)
                    conn.exec_driver_sql(ddl_idx2)
                    conn.exec_driver_sql(ddl_idx3)
                except Exception:
                    # Indizes existieren möglicherweise bereits
                    pass
            else:
                # SQLite-kompatibel - Einzelne Statements ausführen (SQLite unterstützt kein Multi-Statement)
                ddl_table = """
                CREATE TABLE IF NOT EXISTS password_reset (
                  id TEXT PRIMARY KEY,
                  provider_id TEXT NOT NULL REFERENCES provider(id) ON DELETE CASCADE,
                  token TEXT UNIQUE NOT NULL,
                  expires_at DATETIME NOT NULL,
                  used_at DATETIME,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
                ddl_idx1 = "CREATE INDEX IF NOT EXISTS password_reset_provider_id_idx ON password_reset(provider_id);"
                ddl_idx2 = "CREATE INDEX IF NOT EXISTS password_reset_token_idx ON password_reset(token);"
                ddl_idx3 = "CREATE INDEX IF NOT EXISTS password_reset_expires_at_idx ON password_reset(expires_at);"
                
                # Jedes Statement einzeln ausführen
                conn.exec_driver_sql(ddl_table)
                try:
                    conn.exec_driver_sql(ddl_idx1)
                    conn.exec_driver_sql(ddl_idx2)
                    conn.exec_driver_sql(ddl_idx3)
                except Exception:
                    # Indizes existieren möglicherweise bereits
                    pass
    except (OperationalError, SQLAlchemyError) as e:
        print(f"⚠️  Warnung: ensure_password_reset_table fehlgeschlagen: {e}", flush=True)


_ensure_password_reset_table()


# --------------------------------------------------------
# Provider-Number Feld sicherstellen
# --------------------------------------------------------
def _ensure_provider_number_field():
    """
    Erstellt das provider_number Feld, falls es noch nicht existiert, und nummeriert bestehende Provider.
    """
    try:
        with engine.begin() as conn:
            # Prüfen ob Spalte existiert
            column_exists = False
            if IS_POSTGRESQL:
                try:
                    # PostgreSQL: Prüfe in information_schema
                    result = conn.execute(text("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'provider' AND column_name = 'provider_number'
                    """))
                    column_exists = result.fetchone() is not None
                except Exception:
                    pass
            else:
                # SQLite: Versuche SELECT
                try:
                    conn.execute(text("SELECT provider_number FROM provider LIMIT 1"))
                    column_exists = True
                except Exception:
                    column_exists = False
            
            if not column_exists:
                # Spalte existiert nicht, erstellen
                conn.execute(text("ALTER TABLE provider ADD COLUMN provider_number INTEGER"))
            
            # Bestehende Provider nummerieren (nach Registrierungsdatum aufsteigend)
            try:
                # Hole alle Provider nach created_at sortiert
                all_providers = conn.execute(text("""
                    SELECT id, created_at
                    FROM provider
                    ORDER BY created_at ASC
                """)).fetchall()
                
                if IS_POSTGRESQL:
                    # PostgreSQL: UPDATE mit FROM
                    result = conn.execute(text("""
                        UPDATE provider
                        SET provider_number = sub.row_num
                        FROM (
                          SELECT id, ROW_NUMBER() OVER (ORDER BY created_at ASC) as row_num
                          FROM provider
                        ) AS sub
                        WHERE provider.id = sub.id
                    """))
                else:
                    # SQLite: Einzelne UPDATEs (kein FROM in UPDATE)
                    for idx, (pid, _) in enumerate(all_providers, start=1):
                        conn.execute(
                            text("UPDATE provider SET provider_number = :num WHERE id = :pid"),
                            {"num": idx, "pid": str(pid)}
                        )
            except Exception:
                pass
            
            # Index erstellen
            try:
                index_exists = False
                if IS_POSTGRESQL:
                    try:
                        result = conn.execute(text("""
                            SELECT indexname FROM pg_indexes 
                            WHERE tablename = 'provider' AND indexname = 'provider_number_idx'
                        """))
                        index_exists = result.fetchone() is not None
                    except Exception:
                        pass
                
                if not index_exists:
                    if IS_POSTGRESQL:
                        # PostgreSQL: WHERE-Klausel im Index
                        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS provider_number_idx ON provider(provider_number) WHERE provider_number IS NOT NULL"))
                    else:
                        # SQLite: einfacher Index (kein WHERE in Index)
                        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS provider_number_idx ON provider(provider_number)"))
            except Exception:
                pass
    except (OperationalError, SQLAlchemyError) as e:
        print(f"⚠️  Warnung: ensure_provider_number_field fehlgeschlagen: {e}", flush=True)


_ensure_provider_number_field()


# --------------------------------------------------------
# Archivierungs-Felder für Slots und Invoices hinzufügen
# --------------------------------------------------------
def _ensure_archive_fields():
    """
    Fügt archived Flag zu Slots und archived_at/exported_at zu Invoices hinzu (Aufbewahrungspflicht).
    """
    try:
        with engine.begin() as conn:
            if IS_POSTGRESQL:
                ddl_slot_archived = """
                ALTER TABLE public.slot
                  ADD COLUMN IF NOT EXISTS archived boolean DEFAULT false;
                """
                ddl_invoice_archived_at = """
                ALTER TABLE public.invoice
                  ADD COLUMN IF NOT EXISTS archived_at timestamp without time zone;
                """
                ddl_invoice_exported_at = """
                ALTER TABLE public.invoice
                  ADD COLUMN IF NOT EXISTS exported_at timestamp without time zone;
                """
                
                # PostgreSQL: ADD COLUMN IF NOT EXISTS funktioniert direkt
                for ddl in [ddl_slot_archived, ddl_invoice_archived_at, ddl_invoice_exported_at]:
                    try:
                        conn.exec_driver_sql(ddl)
                    except Exception:
                        pass
            else:
                # SQLite: Prüfe manuell ob Tabellen und Spalten existieren
                # Slot: archived
                try:
                    conn.execute(text("SELECT 1 FROM slot LIMIT 1"))
                    try:
                        conn.execute(text("SELECT archived FROM slot LIMIT 1"))
                    except Exception:
                        conn.exec_driver_sql("ALTER TABLE slot ADD COLUMN archived INTEGER DEFAULT 0")
                except Exception:
                    pass
                
                # Invoice: archived_at
                try:
                    conn.execute(text("SELECT 1 FROM invoice LIMIT 1"))
                    try:
                        conn.execute(text("SELECT archived_at FROM invoice LIMIT 1"))
                    except Exception:
                        conn.exec_driver_sql("ALTER TABLE invoice ADD COLUMN archived_at DATETIME")
                except Exception:
                    pass
                
                # Invoice: exported_at
                try:
                    conn.execute(text("SELECT 1 FROM invoice LIMIT 1"))
                    try:
                        conn.execute(text("SELECT exported_at FROM invoice LIMIT 1"))
                    except Exception:
                        conn.exec_driver_sql("ALTER TABLE invoice ADD COLUMN exported_at DATETIME")
                except Exception:
                    pass
    except (OperationalError, SQLAlchemyError) as e:
        print(f"⚠️  Warnung: ensure_archive_fields fehlgeschlagen: {e}", flush=True)


_ensure_archive_fields()


# --------------------------------------------------------
# Slot Status Constraint: EXPIRED und CANCELED erlauben
# --------------------------------------------------------
def _ensure_slot_status_constraint():
    """
    Aktualisiert die CHECK-Constraint für slot.status, um EXPIRED und CANCELED zu erlauben.
    Entfernt die alte Constraint und erstellt eine neue mit allen erlaubten Statuswerten.
    """
    try:
        with engine.begin() as conn:
            if IS_POSTGRESQL:
                # Schritt 1: Entferne alte Constraint falls vorhanden
                ddl_drop_constraint = """
                DO $$
                BEGIN
                  IF EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'ck_slot_status'
                  ) THEN
                    ALTER TABLE public.slot DROP CONSTRAINT ck_slot_status;
                  END IF;
                  
                  -- Entferne auch slot_status_check falls vorhanden
                  IF EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'slot_status_check'
                  ) THEN
                    ALTER TABLE public.slot DROP CONSTRAINT slot_status_check;
                  END IF;
                END $$;
                """
                
                # Schritt 2: Erstelle neue Constraint mit allen erlaubten Statuswerten
                ddl_add_constraint = """
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'ck_slot_status'
                  ) THEN
                    ALTER TABLE public.slot 
                      ADD CONSTRAINT ck_slot_status 
                      CHECK (status IN ('DRAFT', 'PUBLISHED', 'CANCELED', 'EXPIRED'));
                  END IF;
                END $$;
                """
                
                conn.exec_driver_sql(ddl_drop_constraint)
                conn.exec_driver_sql(ddl_add_constraint)
            else:
                # SQLite: Constraints werden nicht dynamisch verwaltet
                # Die Validierung erfolgt in der Anwendung (normalize_category, etc.)
                pass
    except (OperationalError, SQLAlchemyError) as e:
        print(f"⚠️  Warnung: ensure_slot_status_constraint fehlgeschlagen: {e}", flush=True)


_ensure_slot_status_constraint()


# --------------------------------------------------------
# Publish-Quota Tabellen (idempotent, best effort)
# --------------------------------------------------------
def _ensure_publish_quota_tables():
    try:
        with engine.begin() as conn:
            if IS_POSTGRESQL:
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
                
                try:
                    conn.exec_driver_sql(ddl_quota_uuid)
                    conn.exec_driver_sql(ddl_quota_fk)
                except Exception:
                    pass
            else:
                # SQLite-kompatibel
                ddl_quota = """
                CREATE TABLE IF NOT EXISTS publish_quota (
                  provider_id TEXT NOT NULL,
                  month DATE NOT NULL,
                  used INTEGER NOT NULL DEFAULT 0,
                  "limit" INTEGER NOT NULL,
                  PRIMARY KEY (provider_id, month),
                  FOREIGN KEY (provider_id) REFERENCES provider(id) ON DELETE CASCADE
                );
                """
                try:
                    conn.exec_driver_sql(ddl_quota)
                except Exception:
                    pass
            
            # published_at Spalte für Slot (beide DB-Typen)
            try:
                # Prüfe ob Tabelle existiert
                conn.execute(text("SELECT 1 FROM slot LIMIT 1"))
                
                if IS_POSTGRESQL:
                    conn.exec_driver_sql("ALTER TABLE public.slot ADD COLUMN IF NOT EXISTS published_at timestamp without time zone;")
                else:
                    # SQLite: Prüfe ob Spalte existiert
                    try:
                        conn.execute(text("SELECT published_at FROM slot LIMIT 1"))
                    except Exception:
                        # Spalte existiert nicht, hinzufügen
                        conn.exec_driver_sql("ALTER TABLE slot ADD COLUMN published_at DATETIME")
            except Exception:
                # Tabelle existiert nicht - ignorieren
                pass
    except (OperationalError, SQLAlchemyError) as e:
        print(f"⚠️  Warnung: ensure_publish_quota_tables fehlgeschlagen: {e}", flush=True)


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


# Kategorien mit Unterkategorien für Ärzte und Ämter
BRANCHES = {
    # Bestehende Kategorien
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
    "Rechtsanwalt",
    "Notar",
    "Tätowierer",
    "Sonstiges",
    # Ärzte - Unterkategorien
    "Hausärzte",
    "Orthopäden",
    "Gynäkologen",
    "Hautärzte",
    "Psychotherapeuten",
    "Zahnärzte",
    "Kinderärzte",
    # Ämter - Unterkategorien
    "Bürgeramt",
    "Kfz-Zulassungsstelle",
    "Finanzamt",
    "Ausländerbehörde",
    "Jobcenter",
}

# Mapping für Fuzzy-Search: Varianten -> Standard-Kategorie
CATEGORY_VARIANTS = {
    # Ärzte-Varianten
    "hausarzt": "Hausärzte",
    "hausärzte": "Hausärzte",
    "allgemeinarzt": "Hausärzte",
    "allgemeinärzte": "Hausärzte",
    "orthopäde": "Orthopäden",
    "orthopäden": "Orthopäden",
    "orthopaede": "Orthopäden",
    "orthopaeden": "Orthopäden",
    "gynäkologe": "Gynäkologen",
    "gynäkologen": "Gynäkologen",
    "frauenarzt": "Gynäkologen",
    "frauenärzte": "Gynäkologen",
    "hautarzt": "Hautärzte",
    "hautärzte": "Hautärzte",
    "dermatologe": "Hautärzte",
    "dermatologen": "Hautärzte",
    "psychotherapeut": "Psychotherapeuten",
    "psychotherapeuten": "Psychotherapeuten",
    "psychologe": "Psychotherapeuten",
    "psychologen": "Psychotherapeuten",
    "zahnarzt": "Zahnärzte",
    "zahnärzte": "Zahnärzte",
    "zahnaerzt": "Zahnärzte",
    "zahnaerzte": "Zahnärzte",
    "kinderarzt": "Kinderärzte",
    "kinderärzte": "Kinderärzte",
    "paediatrie": "Kinderärzte",
    "pädiatrie": "Kinderärzte",
    "arzt": "Hausärzte",  # Fallback
    "ärzte": "Hausärzte",
    # Ämter-Varianten
    "buergeramt": "Bürgeramt",
    "bürgeramt": "Bürgeramt",
    "einwohnermeldeamt": "Bürgeramt",
    "kfz": "Kfz-Zulassungsstelle",
    "kfz-zulassung": "Kfz-Zulassungsstelle",
    "kfz-zulassungsstelle": "Kfz-Zulassungsstelle",
    "zulassungsstelle": "Kfz-Zulassungsstelle",
    "finanzamt": "Finanzamt",
    "steueramt": "Finanzamt",
    "auslaenderbehoerde": "Ausländerbehörde",
    "ausländerbehörde": "Ausländerbehörde",
    "auslaenderamt": "Ausländerbehörde",
    "ausländeramt": "Ausländerbehörde",
    "jobcenter": "Jobcenter",
    "arbeitsamt": "Jobcenter",
    "arbeitsagentur": "Jobcenter",
    "amt": "Bürgeramt",  # Fallback
    "ämter": "Bürgeramt",
    # Weitere Varianten
    "friseur": "Friseur",
    "frisör": "Friseur",
    "frisoer": "Friseur",
    "kosmetik": "Kosmetik",
    "physiotherapie": "Physiotherapie",
    "physio": "Physiotherapie",
    "nagelstudio": "Nagelstudio",
    "handwerk": "Handwerk",
    "fitness": "Fitness",
    "coaching": "Coaching",
    "tierarzt": "Tierarzt",
    "tierärzte": "Tierarzt",
    "behoerde": "Behörde",
    "behörde": "Behörde",
}


def find_matching_categories(search_term: str) -> list[str]:
    """
    Findet passende Kategorien basierend auf Suchbegriff.
    Unterstützt Fuzzy-Search und Varianten.
    """
    if not search_term:
        return []
    
    search_lower = search_term.lower().strip()
    
    # 1. Exakte Übereinstimmung (case-insensitive)
    exact_matches = [cat for cat in BRANCHES if cat.lower() == search_lower]
    if exact_matches:
        return exact_matches
    
    # 2. Varianten-Mapping
    if search_lower in CATEGORY_VARIANTS:
        return [CATEGORY_VARIANTS[search_lower]]
    
    # 3. Teilstring-Suche in Kategorien
    partial_matches = [cat for cat in BRANCHES if search_lower in cat.lower() or cat.lower() in search_lower]
    
    # 4. Teilstring-Suche in Varianten
    variant_matches = []
    for variant, standard in CATEGORY_VARIANTS.items():
        if search_lower in variant or variant in search_lower:
            if standard not in variant_matches:
                variant_matches.append(standard)
    
    # Kombiniere und entferne Duplikate
    all_matches = list(set(exact_matches + partial_matches + variant_matches))
    
    return all_matches


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
    """
    Flags für set_cookie (alle Parameter).
    WICHTIG: SameSite=None nur für Cross-Origin (z.B. wenn Frontend auf anderer Domain).
    Für Same-Origin (Frontend und Backend auf derselben Domain) verwenden wir Lax.
    """
    if IS_RENDER:
        # Prüfe ob es ein Testsystem ist
        RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
        IS_TESTSYSTEM = "testsystem" in RENDER_EXTERNAL_URL.lower() or "test" in RENDER_EXTERNAL_URL.lower()
        
        # Testsystem: Frontend und Backend auf derselben Domain -> SameSite=Lax
        # Produktion: Frontend auf terminmarktplatz.de, Backend auf api.terminmarktplatz.de -> SameSite=None
        if IS_TESTSYSTEM:
            return {"httponly": True, "secure": True, "samesite": "Lax", "path": "/"}
        else:
            # Produktion: Cross-Origin zwischen terminmarktplatz.de und api.terminmarktplatz.de
            return {"httponly": True, "secure": True, "samesite": "None", "path": "/"}
    return {"httponly": True, "secure": False, "samesite": "Lax", "path": "/"}


def _cookie_delete_flags():
    """
    Flags für delete_cookie.
    WICHTIG: Flask's delete_cookie unterstützt nicht alle Parameter, daher müssen wir
    die Cookies auch mit max_age=0 setzen (siehe auth_logout).
    """
    return {"path": "/"}


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
        "archived": getattr(x, "archived", False),
        "published_at": _from_db_as_iso_utc(published_at) if published_at else None,
        "created_at": _from_db_as_iso_utc(x.created_at),
        "street": getattr(x, "street", None),
        "house_number": getattr(x, "house_number", None),
        "zip": getattr(x, "zip", None),
        "city": getattr(x, "city", None),

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


def split_street_and_number(street_value: str | None) -> tuple[str, str]:
    """Trennt Straße und Hausnummer (z.B. 'Musterstraße 12a' -> ('Musterstraße', '12a'))."""
    if not street_value:
        return ("", "")
    street_value = street_value.strip()
    # Regex: Straße (mind. 2 Zeichen) + Leerzeichen + Hausnummer (1-4 Ziffern + optional Buchstaben/Ziffern)
    match = re.match(r"^(.{2,}?)\s+(\d{1,4}[a-zA-Z0-9\-\/]*)$", street_value)
    if not match:
        return (street_value, "")
    return (match.group(1).strip(), match.group(2).strip())


# --------------------------------------------------------
# SLOT Status Konstanz (einheitlich)
# --------------------------------------------------------
SLOT_STATUS_DRAFT = "DRAFT"
SLOT_STATUS_PUBLISHED = "PUBLISHED"
SLOT_STATUS_EXPIRED = "EXPIRED"
VALID_STATUSES = {SLOT_STATUS_DRAFT, SLOT_STATUS_PUBLISHED, SLOT_STATUS_EXPIRED}


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
    """
    Zählt veröffentlichte Slots für einen Monat mit Retry bei SSL-Fehlern.
    WICHTIG: Zählt die Summe der Kapazitäten, nicht die Anzahl der Slots!
    Ein Slot mit capacity=3 zählt als 3 Slots.
    """
    start_db, next_db = _month_bounds_utc_naive(month_key)
    
    # Retry-Logik für SSL-Verbindungsfehler
    for attempt in range(3):
        try:
            # Summe der Kapazitäten statt Anzahl der Slots
            c = (
                session.scalar(
                    select(func.coalesce(func.sum(Slot.capacity), 0))
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
        except OperationalError as e:
            if attempt < 2 and ("SSL" in str(e) or "eof" in str(e).lower()):
                # SSL-Fehler: Session invalidieren und neu versuchen
                session.rollback()
                time.sleep(0.1 * (attempt + 1))  # Kurze Pause vor Retry
                continue
            raise  # Andere Fehler oder letzter Versuch: weiterwerfen
    return 0  # Fallback


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

    # Prüfe, ob die Kapazität des neuen Slots noch ins Limit passt
    # Ein Slot mit capacity=3 zählt als 3 Slots
    new_used = actual_used + cap
    if new_used > plan_limit:
        raise PublishLimitReached("monthly_publish_limit_reached")

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

    # Kapazität des neuen Slots zum used hinzufügen
    bumped = session.execute(
        text(
            """
            UPDATE public.publish_quota
            SET used = used + :cap
            WHERE provider_id=:pid AND month=:m AND used + :cap <= "limit"
            RETURNING used, "limit"
            """
        ),
        {"pid": str(provider_id), "m": month_key, "cap": int(cap)},
    ).mappings().first()

    if not bumped:
        # Berechne, wie viel noch verfügbar ist
        remaining = max(0, plan_limit - actual_used)
        error_msg = f"monthly_publish_limit_reached: {actual_used}/{plan_limit} used, {remaining} remaining, need {cap}"
        raise PublishLimitReached(error_msg)

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
    WICHTIG: Subtrahiert die Kapazität des Slots, nicht nur 1!
    """
    slot = session.execute(
        text(
            """
            SELECT id, provider_id, start_at, status, capacity
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
    
    # Kapazität des Slots (Standard: 1)
    cap = int(slot.get("capacity") or 1)
    if cap < 1:
        cap = 1

    session.execute(
        text(
            """
            UPDATE public.publish_quota
            SET used = GREATEST(used - :cap, 0)
            WHERE provider_id=:pid AND month=:m
            """
        ),
        {"pid": str(provider_id), "m": month_key, "cap": int(cap)},
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
            
            # Resend benötigt mindestens text ODER html
            if not text and not html:
                print("[resend][ERROR] Kein Text- oder HTML-Inhalt vorhanden!", flush=True)
                return False, "missing_text_or_html"

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
            if ok and text:
                print(f"[resend][debug] text length={len(text)}, preview={text[:100]}...", flush=True)
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

Alternativ:
https://copecart.com/login

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
            
            # Versuche Access-Token zu dekodieren
            data = None
            new_access_token = None  # Wird gesetzt, wenn wir einen neuen Token generieren müssen
            
            if token:
                try:
                    data = jwt.decode(
                        token,
                        SECRET,
                        algorithms=["HS256"],
                        audience=JWT_AUD,
                        issuer=JWT_ISS,
                    )
                except jwt.ExpiredSignatureError:
                    # Access-Token abgelaufen: Versuche Refresh-Token zu verwenden
                    refresh_token = request.cookies.get("refresh_token")
                    if refresh_token:
                        try:
                            refresh_data = jwt.decode(
                                refresh_token,
                                SECRET,
                                algorithms=["HS256"],
                                audience=JWT_AUD,
                                issuer=JWT_ISS,
                            )
                            if refresh_data.get("typ") == "refresh":
                                # Neuen Access-Token generieren
                                new_access_token, _ = issue_tokens(refresh_data["sub"], bool(refresh_data.get("adm")))
                                data = refresh_data  # Verwende Refresh-Daten für diese Request
                        except Exception:
                            pass  # Refresh-Token auch ungültig
                except Exception:
                    pass  # Andere Fehler beim Dekodieren
            
            # Wenn immer noch kein gültiger Token: Prüfe Refresh-Token direkt
            if not data:
                refresh_token = request.cookies.get("refresh_token")
                if refresh_token:
                    try:
                        refresh_data = jwt.decode(
                            refresh_token,
                            SECRET,
                            algorithms=["HS256"],
                            audience=JWT_AUD,
                            issuer=JWT_ISS,
                        )
                        if refresh_data.get("typ") == "refresh":
                            data = refresh_data
                            # Generiere neuen Access-Token
                            new_access_token, _ = issue_tokens(refresh_data["sub"], bool(refresh_data.get("adm")))
                    except Exception:
                        pass
            
            if not data:
                # Für HTML-Routen: Redirect zu Login
                if request.path.endswith('.html') or not request.path.startswith('/api/'):
                    return redirect(f"/login.html?next={request.path}")
                return _json_error("unauthorized", 401)
            
            if admin and not data.get("adm"):
                # Für HTML-Routen: Redirect zu Login mit Fehlermeldung
                if request.path.endswith('.html') or not request.path.startswith('/api/'):
                    return redirect(f"/login.html?error=admin_required&next={request.path}")
                return _json_error("forbidden", 403)
            
            request.provider_id = data["sub"]
            request.is_admin = bool(data.get("adm"))
            
            # Führe die ursprüngliche Funktion aus
            result = fn(*args, **kwargs)
            
            # Wenn wir einen neuen Access-Token generiert haben, setze ihn im Response
            if new_access_token:
                # Konvertiere zu Response-Objekt falls nötig
                if not isinstance(result, Response):
                    result = make_response(result)
                # Setze neuen Access-Token Cookie
                flags = _cookie_flags()
                result.set_cookie("access_token", new_access_token, max_age=JWT_EXP_MIN * 60, **flags)
            
            return result

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


@app.get("/sitemap.xml")
def sitemap():
    """Sitemap für Suchmaschinen"""
    return send_from_directory(app.root_path, "sitemap.xml", mimetype="application/xml")


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
        request.path == "/"  # ✅ Root-Route erlauben für Healthchecks
        or request.path.startswith("/auth/")
        or request.path.startswith("/admin/")
        or request.path.startswith("/admin-rechnungen")  # ✅ Admin-Rechnungen Route erlauben
        or request.path.startswith("/login")  # ✅ Login-Route erlauben für Admin-Auth
        or request.path.startswith("/reset-password")  # ✅ Passwort-Reset-Seite erlauben
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

    @app.route("/", methods=["GET", "HEAD"])
    def index():
        return send_from_directory(APP_ROOT, "index.html")

    @app.get("/login")
    def login_page():
        return send_from_directory(APP_ROOT, "login.html")

    @app.get("/anbieter-portal")
    def anbieter_portal_page():
        return send_from_directory(APP_ROOT, "anbieter-portal.html")

    @app.get("/anbieter-portal.html")
    def anbieter_portal_page_html():
        return send_from_directory(APP_ROOT, "anbieter-portal.html")

    # --- Suche mit Google Maps API Key ---
    @app.get("/suche")
    def suche_page():
        # suche.html liegt im Root, aber benötigt Template-Rendering für GOOGLE_MAPS_API_KEY
        # Daher: Datei lesen, hardcodierten Key durch Umgebungsvariablen-Key ersetzen
        suche_path = os.path.join(APP_ROOT, "suche.html")
        try:
            with open(suche_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Ersetze hardcodierten Google Maps API Key durch Umgebungsvariablen-Key
            if GOOGLE_MAPS_API_KEY:
                # Ersetze den hardcodierten Key (falls vorhanden)
                import re
                content = re.sub(
                    r'const gmKey = "[^"]*";',
                    f'const gmKey = "{GOOGLE_MAPS_API_KEY}";',
                    content
                )
            return Response(content, mimetype="text/html")
        except FileNotFoundError:
            # Fallback: Versuche Template-Verzeichnis
            return render_template("suche.html", GOOGLE_MAPS_API_KEY=GOOGLE_MAPS_API_KEY)

    @app.get("/suche.html")
    def suche_page_html():
        # Gleiche Logik wie /suche
        suche_path = os.path.join(APP_ROOT, "suche.html")
        try:
            with open(suche_path, "r", encoding="utf-8") as f:
                content = f.read()
            if GOOGLE_MAPS_API_KEY:
                import re
                content = re.sub(
                    r'const gmKey = "[^"]*";',
                    f'const gmKey = "{GOOGLE_MAPS_API_KEY}";',
                    content
                )
            return Response(content, mimetype="text/html")
        except FileNotFoundError:
            return render_template("suche.html", GOOGLE_MAPS_API_KEY=GOOGLE_MAPS_API_KEY)

    @app.get("/impressum")
    def impressum():
        return send_from_directory(APP_ROOT, "impressum.html")

    @app.get("/datenschutz")
    def datenschutz():
        return send_from_directory(APP_ROOT, "datenschutz.html")

    @app.get("/reset-password")
    @app.get("/reset-password.html")
    def reset_password_page():
        return send_from_directory(APP_ROOT, "reset-password.html")

    @app.get("/agb")
    def agb():
        return send_from_directory(APP_ROOT, "agb.html")

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
        # Spezifische Routen sollten bereits abgefangen worden sein
        # Diese Route ist nur für generische HTML-Dateien
        if slug.startswith("admin/"):
            abort(404)  # Admin-Routen müssen explizit definiert sein
        filename = slug if slug.endswith(".html") else f"{slug}.html"
        # Versuche zuerst Root-Verzeichnis (die meisten HTML-Dateien liegen dort)
        file_path = os.path.join(APP_ROOT, filename)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_from_directory(APP_ROOT, filename)
        # Fallback: Versuche Template-Verzeichnis
        try:
            return render_template(filename)
        except Exception:
            abort(404)


# --------------------------------------------------------
# Login & Admin-Rechnungen Routes (auch im API_ONLY-Modus verfügbar)
# --------------------------------------------------------
@app.get("/login")
@app.get("/login.html")
def login_page_always():
    return send_from_directory(APP_ROOT, "login.html")

@app.get("/admin-rechnungen")
@app.get("/admin-rechnungen.html")
@auth_required(admin=True)
def admin_rechnungen_page_always():
    return render_template("admin-rechnungen.html")


if not _html_enabled():

    @app.route("/", methods=["GET", "HEAD"])
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
        try:
            p = s.scalar(select(Provider).where(Provider.email == email))
        except Exception as e:
            # Falls provider_number Spalte fehlt, Migration nochmal versuchen
            if "provider_number" in str(e).lower() or "undefinedcolumn" in str(e).lower():
                app.logger.warning("provider_number column missing, running migration...")
                try:
                    _ensure_provider_number_field()
                    p = s.scalar(select(Provider).where(Provider.email == email))
                except Exception as e2:
                    app.logger.exception("Migration failed during auth: %r", e2)
                    return None, "server_error"
            else:
                raise
        
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
    # Für Testsystem: Stelle sicher, dass Cookies korrekt gesetzt werden
    # Domain wird nicht explizit gesetzt, damit Cookies für die aktuelle Domain gelten
    resp.set_cookie("access_token", access, max_age=JWT_EXP_MIN * 60, **flags)
    if refresh:
        resp.set_cookie(
            "refresh_token",
            refresh,
            max_age=REFRESH_EXP_DAYS * 86400,
            **flags,
        )
    # Debug: Log Cookie-Setting (nur im Testsystem)
    if IS_RENDER:
        RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
        IS_TESTSYSTEM = "testsystem" in RENDER_EXTERNAL_URL.lower() or "test" in RENDER_EXTERNAL_URL.lower()
        if IS_TESTSYSTEM:
            app.logger.info(f"Cookies gesetzt: access_token (max_age={JWT_EXP_MIN * 60}s), refresh_token (max_age={REFRESH_EXP_DAYS * 86400}s), flags={flags}")
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
            # Prüfung: Existiert die E-Mail bereits?
            exists = s.scalar(
                select(func.count())
                .select_from(Provider)
                .where(Provider.email == email)
            )
            if exists:
                return _json_error("email_exists")

            # Nächste Provider-Nummer vergeben
            max_number = s.scalar(select(func.max(Provider.provider_number)))
            next_number = (max_number or 0) + 1

            p = Provider(
                email=email,
                pw_hash=ph.hash(password),
                status="pending",
                plan="basic",
                free_slots_per_month=3,
                plan_valid_until=None,
                provider_number=next_number,
            )

            s.add(p)
            try:
                s.commit()
            except IntegrityError as e:
                s.rollback()
                # Prüfe, ob es ein UNIQUE Constraint Verstoß für email ist
                error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
                if 'email' in error_msg.lower() or 'unique' in error_msg.lower():
                    # E-Mail existiert bereits (Race Condition abgefangen)
                    return _json_error("email_exists")
                # Anderer Constraint-Fehler
                app.logger.warning(f"Registration IntegrityError (non-email): {error_msg}")
                return _json_error("registration_failed")
            
            provider_id = p.id
            provider_number = p.provider_number
            reg_email = p.email

        try:
            admin_to = os.getenv("ADMIN_NOTIFY_TO", CONTACT_TO)
            if admin_to:
                subj = "[Terminmarktplatz] Neuer Anbieter registriert"
                txt = (
                    "Es hat sich ein neuer Anbieter registriert.\n\n"
                    f"Anbieter-Nr.: {provider_number}\n"
                    f"UUID: {provider_id}\n"
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
    # WICHTIG: Cookies müssen mit den gleichen Flags gelöscht werden, mit denen sie gesetzt wurden
    # Flask's delete_cookie unterstützt nicht alle Parameter, daher setzen wir max_age=0
    set_flags = _cookie_flags()
    resp.set_cookie("access_token", "", max_age=0, **set_flags)
    resp.set_cookie("refresh_token", "", max_age=0, **set_flags)
    # Zusätzlich: delete_cookie für Kompatibilität
    delete_flags = _cookie_delete_flags()
    resp.delete_cookie("access_token", **delete_flags)
    resp.delete_cookie("refresh_token", **delete_flags)
    return resp


@app.post("/auth/forgot-password")
def auth_forgot_password():
    """Fordert einen Passwort-Reset-Link per E-Mail an."""
    try:
        data = request.get_json(force=True)
        email = (data.get("email") or "").strip().lower()
        
        if not email or "@" not in email:
            return _json_error("invalid_email", 400)
        
        with Session(engine) as s:
            provider = s.scalar(select(Provider).where(Provider.email == email))
            if not provider:
                # Aus Sicherheitsgründen: Immer "ok" zurückgeben, auch wenn E-Mail nicht existiert
                return jsonify({"ok": True, "message": "Wenn diese E-Mail registriert ist, wurde ein Reset-Link gesendet."})
            
            # Werte vor Session-Schließung speichern
            provider_id = provider.id
            provider_email = provider.email
            provider_company_name = provider.company_name
            
            # Token generieren (30 Minuten gültig)
            import secrets
            token = secrets.token_urlsafe(32)
            expires_at = _now() + timedelta(minutes=30)
            
            # Alte Tokens für diesen Provider als verwendet markieren
            s.execute(
                text("""
                    UPDATE password_reset
                    SET used_at = :now
                    WHERE provider_id = :pid AND used_at IS NULL AND expires_at > :now
                """),
                {"pid": str(provider_id), "now": _now()}
            )
            
            # Neuen Token anlegen
            reset = PasswordReset(
                provider_id=provider_id,
                token=token,
                expires_at=expires_at,
            )
            s.add(reset)
            s.commit()
        
        # E-Mail senden (außerhalb der Session)
        reset_url = f"{FRONTEND_URL}/reset-password.html?token={token}"
        email_body = f"""Hallo {provider_company_name or 'Anbieter/in'},

du hast einen Passwort-Reset für dein Terminmarktplatz-Konto angefordert.

Klicke auf folgenden Link, um dein Passwort zurückzusetzen:
{reset_url}

Dieser Link ist 30 Minuten gültig.

Falls du diese Anfrage nicht gestellt hast, ignoriere diese E-Mail einfach.

— Terminmarktplatz
"""
        send_mail(
            provider_email,
            "Passwort zurücksetzen",
            text=email_body,
            tag="password_reset",
        )
        
        return jsonify({"ok": True, "message": "Wenn diese E-Mail registriert ist, wurde ein Reset-Link gesendet."})
    except Exception as e:
        app.logger.exception("auth_forgot_password failed")
        return _json_error("server_error", 500)


@app.post("/auth/reset-password")
def auth_reset_password():
    """Setzt das Passwort mit einem gültigen Token zurück."""
    try:
        data = request.get_json(force=True)
        token = (data.get("token") or "").strip()
        new_password = data.get("password") or ""
        
        if not token:
            return _json_error("missing_token", 400)
        if len(new_password) < 8:
            return _json_error("password_too_short", 400)
        
        with Session(engine) as s:
            reset = s.scalar(
                select(PasswordReset)
                .where(PasswordReset.token == token)
                .where(PasswordReset.used_at.is_(None))
            )
            
            if not reset:
                return _json_error("invalid_token", 400)
            
            # expires_at ist offset-naive (timestamp without time zone)
            # _now() ist offset-aware, daher konvertieren wir es zu offset-naive für den Vergleich
            now_naive = _to_db_utc_naive(_now())
            if reset.expires_at < now_naive:
                return _json_error("token_expired", 400)
            
            # Passwort aktualisieren
            provider = s.get(Provider, reset.provider_id)
            if not provider:
                return _json_error("provider_not_found", 404)
            
            provider.pw_hash = ph.hash(new_password)
            
            # Token als verwendet markieren (offset-naive)
            reset.used_at = now_naive
            s.commit()
        
        return jsonify({"ok": True, "message": "Passwort wurde erfolgreich zurückgesetzt."})
    except Exception as e:
        app.logger.exception("auth_reset_password failed")
        return _json_error("server_error", 500)


@app.post("/auth/change-password")
@auth_required()
def auth_change_password():
    """Ändert das Passwort für einen eingeloggten Provider."""
    try:
        data = request.get_json(force=True)
        old_password = data.get("old_password") or ""
        new_password = data.get("password") or ""
        
        if not old_password or not new_password:
            return _json_error("missing_fields", 400)
        if len(new_password) < 8:
            return _json_error("password_too_short", 400)
        
        with Session(engine) as s:
            provider = s.get(Provider, request.provider_id)
            if not provider:
                return _json_error("not_found", 404)
            
            # Altes Passwort prüfen
            try:
                ph.verify(provider.pw_hash, old_password)
            except Exception:
                return _json_error("invalid_old_password", 401)
            
            # Neues Passwort setzen
            provider.pw_hash = ph.hash(new_password)
            s.commit()
        
        return jsonify({"ok": True, "message": "Passwort wurde erfolgreich geändert."})
    except Exception as e:
        app.logger.exception("auth_change_password failed")
        return _json_error("server_error", 500)


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
        flags = _cookie_delete_flags()
        resp.delete_cookie("access_token", **flags)
        resp.delete_cookie("refresh_token", **flags)
        # Zusätzlich: Cookies mit expiring max_age setzen (Fallback für Browser-Kompatibilität)
        set_flags = _cookie_flags()
        resp.set_cookie("access_token", "", max_age=0, **set_flags)
        resp.set_cookie("refresh_token", "", max_age=0, **set_flags)
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
        try:
            p = s.get(Provider, request.provider_id)
        except Exception as e:
            # Falls provider_number Spalte fehlt, Migration nochmal versuchen
            if "provider_number" in str(e).lower() or "undefinedcolumn" in str(e).lower():
                app.logger.warning("provider_number column missing in /me, running migration...")
                try:
                    _ensure_provider_number_field()
                    p = s.get(Provider, request.provider_id)
                except Exception as e2:
                    app.logger.exception("Migration failed during /me: %r", e2)
                    return _json_error("server_error", 500)
            else:
                raise
        
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
            try:
                slots_used = _published_count_for_month(s, str(p.id), month_key)
            except OperationalError as e:
                # SSL-Fehler: Fallback auf 0
                app.logger.warning("me(): _published_count_for_month failed: %r", e)
                slots_used = 0

        slots_left = None if unlimited else max(0, int(eff_limit) - int(slots_used))

        # Trenne street und house_number für Frontend-Kompatibilität
        street, house_number = split_street_and_number(p.street)

        # Provider-Nummer sicher abrufen - IMMER direkt aus DB lesen
        provider_number = None
        try:
            # ZUERST: Versuche direkt über SQL (zuverlässigster Weg)
            result = s.execute(text("""
                SELECT provider_number FROM provider WHERE id = :pid
            """), {"pid": str(request.provider_id)}).scalar()
            
            if result is not None:
                try:
                    provider_number = int(result)
                    app.logger.info(f"Provider {request.provider_id} provider_number from SQL: {provider_number}")
                except (ValueError, TypeError):
                    app.logger.warning(f"Provider {request.provider_id} has invalid provider_number in DB: {result}")
            
            # Falls immer noch None, versuche über SQLAlchemy Model
            if provider_number is None:
                try:
                    provider_number = getattr(p, "provider_number", None)
                    if provider_number is not None:
                        provider_number = int(provider_number)
                        app.logger.info(f"Provider {request.provider_id} provider_number from model: {provider_number}")
                except (ValueError, TypeError, AttributeError):
                    pass
            
            # Falls immer noch None, führe Migration aus
            if provider_number is None:
                app.logger.info(f"Provider {request.provider_id} has no provider_number, running migration...")
                try:
                    _ensure_provider_number_field()
                    # Nochmal direkt aus DB lesen
                    result = s.execute(text("""
                        SELECT provider_number FROM provider WHERE id = :pid
                    """), {"pid": str(request.provider_id)}).scalar()
                    if result is not None:
                        provider_number = int(result)
                        app.logger.info(f"Provider {request.provider_id} provider_number after migration: {provider_number}")
                except Exception as e_mig:
                    app.logger.warning(f"Migration failed for provider {request.provider_id}: %r", e_mig)
                    
        except Exception as e:
            app.logger.warning(f"Could not get provider_number for {request.provider_id}: %r", e)
            # Fallback: Versuche nochmal direkt aus DB
            try:
                result = s.execute(text("""
                    SELECT provider_number FROM provider WHERE id = :pid
                """), {"pid": str(request.provider_id)}).scalar()
                if result is not None:
                    provider_number = int(result)
            except Exception:
                pass

        return jsonify(
            {
                "id": p.id,
                "provider_number": provider_number,
                "email": p.email,
                "status": p.status,
                "is_admin": p.is_admin,
                "company_name": p.company_name,
                "branch": p.branch,
                "street": street,
                "house_number": house_number,
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

        # house_number akzeptieren und verarbeiten
        house_number = clean(data.get("house_number"))
        
        upd = {k: clean(v) for k, v in data.items() if k in allowed}

        # Wenn house_number vorhanden ist, mit street kombinieren
        if house_number:
            if "street" in upd and upd["street"]:
                # Kombiniere street und house_number
                upd["street"] = f"{upd['street']} {house_number}".strip()
            # Wenn house_number vorhanden, aber kein street im Update,
            # wird die bestehende street aus der DB geholt (siehe unten)

        if "zip" in upd and upd["zip"] is not None:
            z = upd["zip"]
            if not z.isdigit() or len(z) != 5:
                return _json_error("invalid_zip", 400)

        with Session(engine) as s:
            p = s.get(Provider, request.provider_id)
            if not p:
                return _json_error("not_found", 404)

            # Wenn house_number vorhanden, aber kein street im Update, bestehende street verwenden
            if house_number and "street" not in upd and p.street:
                upd["street"] = f"{p.street} {house_number}".strip()
            elif house_number and "street" not in upd:
                upd["street"] = house_number

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
            # Läuft in separater Session, damit Fehler hier nicht die Provider-Änderungen rückgängig machen
            try:
                with Session(engine) as geo_s:
                    geocode_cached(geo_s, p.zip, p.city)
            except Exception:
                app.logger.exception("geocode_cached failed for provider profile update")

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
from urllib.parse import unquote
import re

ALERT_MAX_PER_EMAIL = 10          # max. Alerts (Subscriptions) pro E-Mail (Fallback, wenn kein Paket gekauft)
ALERT_MAX_EMAILS_PER_ALERT = 10   # max. E-Mail-Benachrichtigungen pro Alert (email_sent_total)
ALERT_LIMIT_PER_PACKAGE = 10      # Anzahl Benachrichtigungen pro gekauftem Paket
 
def _norm_token(t: str | None) -> str:
    t = unquote((t or "")).strip()
    # echte Whitespaces killen (Space, Tabs, Newlines etc.)
    t = re.sub(r"\s+", "", t)
    return t



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

    # LIMIT: max 10 E-Mail-Benachrichtigungen pro Alert
    sent_total = int(getattr(alert, "email_sent_total", 0) or 0)
    if sent_total >= ALERT_MAX_EMAILS_PER_ALERT:
        return

    slot_title = slot.title
    starts_at = _from_db_as_iso_utc(slot.start_at)

            # Adresse: Slot hat Priorität (weil Slot-Adresse vom Profil abweichen kann)
    slot_address = ""
    try:
        s_street = (getattr(slot, "street", None) or "").strip()
        s_house  = (getattr(slot, "house_number", None) or "").strip()
        s_zip    = (getattr(slot, "zip", None) or "").strip()
        s_city   = (getattr(slot, "city", None) or "").strip()

        line1 = " ".join(p for p in [s_street, s_house] if p).strip()
        line2 = " ".join(p for p in [s_zip, s_city] if p).strip()
        slot_address = ", ".join(p for p in [line1, line2] if p).strip()
    except Exception:
        slot_address = ""

    # Fallback: slot.location
    slot_location = (getattr(slot, "location", None) or "").strip()

    # Letzter Fallback: Provider Profil-Adresse
    provider_address = ""
    try:
        provider_address = (provider.to_public_dict().get("address") or "").strip()
    except Exception:
        provider_address = ""

    address = slot_address or slot_location or provider_address or ""


    # 1) Wenn Slot strukturierte Felder hat -> daraus bauen (beste Qualität)
    try:
        s_street = (getattr(slot, "street", None) or "").strip()
        s_house  = (getattr(slot, "house_number", None) or "").strip()
        s_zip    = (getattr(slot, "zip", None) or "").strip()
        s_city   = (getattr(slot, "city", None) or "").strip()

        line1 = " ".join(p for p in [s_street, s_house] if p)
        line2 = " ".join(p for p in [s_zip, s_city] if p)

        slot_address = ", ".join(p for p in [line1, line2] if p)
    except Exception:
        slot_address = ""

    # 2) Fallback: slot.location (wenn du dort die Slot-Adresse pflegst)
    slot_location = (slot.location or "").strip()

    # 3) Letzter Fallback: Provider Profil-Adresse
    provider_address = ""
    try:
        provider_address = (provider.to_public_dict().get("address") or "").strip()
    except Exception:
        provider_address = ""

    address = slot_address or slot_location or provider_address or ""


    if hasattr(app, "view_functions") and "public_slots" in app.view_functions:
        base = _external_base()
        slot_url = f"{FRONTEND_URL}/suche.html"


    else:
        slot_url = ""

    # E-Mail-Benachrichtigung
    if alert.via_email and alert.email_confirmed and alert.active:
        cancel_url = url_for("alerts_cancel", token=alert.verify_token, _external=True)

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
        
        # Link zu "Meine Benachrichtigungen" hinzufügen
        manage_key = getattr(alert, "manage_key", None)
        if manage_key:
            manage_url = f"{FRONTEND_URL}/meine-benachrichtigungen.html?k={manage_key}"
            body_lines.append("")
            body_lines.append("Alle deine Benachrichtigungen verwalten:")
            body_lines.append(manage_url)

        body = "\n".join(body_lines)

        try:
            ok, reason = send_mail(
                alert.email,
                "Neuer Termin passt zu deinem Suchauftrag",
                text=body,
                tag="alert_slot_match",
                metadata={"zip": alert.zip, "package": alert.package_name or ""},
            ) 
            if ok:
                alert.email_sent_total = int(getattr(alert, "email_sent_total", 0) or 0) + 1
            else:
                app.logger.warning("send_mail alert not delivered: %s", reason)
        except Exception as e: 
            app.logger.warning("send_mail alert failed: %r", e)

    # SMS-Benachrichtigung (Stub)
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
                
                # NEU: Slot-Koordinaten bestimmen (wir nehmen Provider-Standort)
                slot_lat, slot_lng = geocode_cached(
                    s,
                    normalize_zip(getattr(provider, "zip", None)),
                    getattr(provider, "city", None),
                )
                if slot_lat is None or slot_lng is None:
                    print(f"[alerts] slot_geo_missing slot_id={slot_id} provider_id={provider.id}", flush=True)
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
                            AlertSubscription.deleted_at.is_(None),  # Nur nicht-gelöschte
                        )
                    )
                    .scalars()
                    .all()
                )
                print(f"[alerts] candidates total={len(alerts)}", flush=True)


                matched_alerts: list[AlertSubscription] = []

                for alert in alerts:
                    # NEU: Falls alte Alerts noch keine Koordinaten haben -> nachziehen
                    if getattr(alert, "search_lat", None) is None or getattr(alert, "search_lng", None) is None:
                        lat, lng = geocode_cached(
                            s,
                            normalize_zip(getattr(alert, "zip", None)),
                            getattr(alert, "city", None),
                        )
                        alert.search_lat = lat
                        alert.search_lng = lng

                    # Ohne Koordinaten kann Umkreis nicht funktionieren
                    if alert.search_lat is None or alert.search_lng is None:
                        continue

                    # Radius-Logik
                    r = int(getattr(alert, "radius_km", 0) or 0)

                    if r <= 0:
                        # altes Verhalten: gleiche PLZ
                        if normalize_zip(getattr(alert, "zip", None)) != slot_zip:
                            continue
                    else:
                        # NEU: Umkreis prüfen
                        dist = _haversine_km(
                            float(slot_lat), float(slot_lng),
                            float(alert.search_lat), float(alert.search_lng),
                        )
                        if dist > r:
                            continue

                    # Kategorien-Filter wie gehabt
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

    return jsonify({"ok": True, "used": used, "limit": ALERT_MAX_PER_EMAIL, "left": left})

@app.get("/api/alert-subscriptions/email-by-manage-key")
def get_email_by_manage_key():
    """Gibt die E-Mail-Adresse für einen manage_key zurück (für Frontend-Vorbelegung)"""
    k = (request.args.get("k") or "").strip()
    if not k or len(k) < 20:
        return _json_error("missing_or_invalid_key", 400)

    with Session(engine) as s:
        email_row = s.execute(
            text("""
                SELECT email
                FROM public.alert_subscription
                WHERE manage_key = :k
                LIMIT 1
            """),
            {"k": k},
        ).mappings().first()
        
        if not email_row:
            return jsonify({"ok": True, "email": None})
        
        return jsonify({"ok": True, "email": email_row["email"]})


@app.get("/api/alert-subscriptions/by-manage-key")
def alert_subscriptions_by_manage_key():
    k = (request.args.get("k") or "").strip()
    if not k or len(k) < 20:
        return _json_error("missing_or_invalid_key", 400)

    with Session(engine) as s:
        # Zuerst: Finde die E-Mail-Adresse für diesen manage_key
        email_row = s.execute(
            text("""
                SELECT email
                FROM public.alert_subscription
                WHERE manage_key = :k
                LIMIT 1
            """),
            {"k": k},
        ).mappings().first()
        
        if not email_row:
            return jsonify({"ok": True, "limit": 10, "used": 0, "remaining": 10, "alerts": []})
        
        email = email_row["email"]
        
        # Dann: Hole alle Alerts für diese E-Mail-Adresse (unabhängig vom manage_key)
        # und aktualisiere sie, um denselben manage_key zu haben
        s.execute(
            text("""
                UPDATE public.alert_subscription
                SET manage_key = :k
                WHERE email = :email AND (manage_key IS NULL OR manage_key != :k)
            """),
            {"k": k, "email": email},
        )
        s.commit()
        
        # Jetzt: Hole alle Alerts für diese E-Mail-Adresse (inkl. gelöschte für Limit-Berechnung)
        all_rows = s.execute(
            text("""
                SELECT
                  id, email, phone, via_email, via_sms,
                  zip, city, radius_km, categories,
                  active, email_confirmed, sms_confirmed,
                  package_name, sms_quota_month, sms_sent_this_month,
                  last_reset_quota, created_at, last_notified_at,
                  email_sent_total, notification_limit, deleted_at
                FROM public.alert_subscription
                WHERE email = :email
                ORDER BY created_at DESC
            """),
            {"email": email},
        ).mappings().all()
        
        # Für die Anzeige: nur nicht-gelöschte
        rows = [r for r in all_rows if not r.get("deleted_at")]

    # Limit: nimm max(notification_limit), fallback auf ALERT_MAX_PER_EMAIL
    # Verwende all_rows für Limit-Berechnung (inkl. gelöschte)
    limit_candidates = []
    for r in all_rows:
        try:
            if r["notification_limit"] is not None:
                limit_candidates.append(int(r["notification_limit"]))
        except Exception:
            pass
    limit_val = max(limit_candidates) if limit_candidates else ALERT_MAX_PER_EMAIL

    # "used": WICHTIG - zähle ALLE Benachrichtigungen, auch gelöschte und deaktivierte
    # Das Limit zählt für alle, nicht nur für aktive
    used = len(all_rows)  # Alle Benachrichtigungen zählen zum Limit (inkl. gelöschte)

    remaining = max(0, int(limit_val) - int(used))

    def ser(v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return _from_db_as_iso_utc(v)
        return v

    alerts = [{k2: ser(v2) for k2, v2 in dict(r).items()} for r in rows]

    return jsonify({
        "ok": True,
        "limit": int(limit_val),
        "used": int(used),
        "remaining": int(remaining),
        "alerts": alerts
    })

@app.delete("/api/alert-subscriptions/<alert_id>")
def delete_alert_subscription(alert_id: str):
    k = (request.args.get("k") or "").strip()
    if not k or len(k) < 20:
        return _json_error("missing_or_invalid_key", 400)

    with Session(engine) as s:
        row = s.execute(
            text("""
                SELECT id
                FROM public.alert_subscription
                WHERE id = :id
                  AND manage_key = :k
                LIMIT 1
            """),
            {"id": str(alert_id), "k": k},
        ).mappings().first()

        if not row:
            return _json_error("not_found", 404)

        # Soft-Delete: Markiere als gelöscht statt zu löschen, damit es zum Limit zählt
        s.execute(
            text("""
                UPDATE public.alert_subscription 
                SET deleted_at = :deleted_at, active = false
                WHERE id = :id AND manage_key = :k AND deleted_at IS NULL
            """),
            {"id": str(alert_id), "k": k, "deleted_at": _now()},
        )
        s.commit()

    return jsonify({"ok": True, "deleted": True, "id": str(alert_id)})


@app.post("/api/alert-subscriptions/<alert_id>/toggle")
def toggle_alert_subscription(alert_id: str):
    """Deaktiviert oder aktiviert eine Benachrichtigung"""
    k = (request.args.get("k") or "").strip()
    if not k or len(k) < 20:
        return _json_error("missing_or_invalid_key", 400)

    data = request.get_json(silent=True) or {}
    active = data.get("active")
    if active is None:
        return _json_error("missing_active", 400)

    with Session(engine) as s:
        row = s.execute(
            text("""
                SELECT id, active
                FROM public.alert_subscription
                WHERE id = :id
                  AND manage_key = :k
                  AND deleted_at IS NULL
                LIMIT 1
            """),
            {"id": str(alert_id), "k": k},
        ).mappings().first()

        if not row:
            return _json_error("not_found", 404)

        s.execute(
            text("""
                UPDATE public.alert_subscription
                SET active = :active
                WHERE id = :id AND manage_key = :k AND deleted_at IS NULL
            """),
            {"id": str(alert_id), "k": k, "active": bool(active)},
        )
        s.commit()

    return jsonify({"ok": True, "active": bool(active), "id": str(alert_id)})


@app.get("/api/alerts/debug/by_zip")
def debug_alerts_by_zip():
    zip_code = normalize_zip(request.args.get("zip"))
    if len(zip_code) != 5:
        return _json_error("invalid_zip", 400)

    with Session(engine) as s:
        rows = (
            s.execute(select(AlertSubscription).where(AlertSubscription.zip == zip_code))
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


@app.get("/api/alerts/debug/raw_by_zip")
def debug_raw_by_zip():
    zip_code = normalize_zip(request.args.get("zip"))
    if len(zip_code) != 5:
        return _json_error("invalid_zip", 400)

    with Session(engine) as s:
        rows = s.execute(
            text("""
                SELECT id, email, zip, active, email_confirmed, via_email, created_at, verify_token
                FROM public.alert_subscription
                WHERE zip = :z
                ORDER BY created_at DESC
                LIMIT 50
            """),
            {"z": zip_code},
        ).mappings().all()

    def _ser(v):
        if v is None:
            return None 
        try:
            import uuid
            if isinstance(v, uuid.UUID):
                return str(v)
        except Exception:
            pass
        if isinstance(v, datetime): 
            return _from_db_as_iso_utc(v)
        return v

    clean = [{k: _ser(v) for k, v in dict(r).items()} for r in rows]
    return jsonify({"zip": zip_code, "count": len(clean), "rows": clean})


@app.get("/api/alerts/debug/active_confirmed_by_zip")
def debug_active_confirmed_by_zip():
    zip_code = normalize_zip(request.args.get("zip"))
    if len(zip_code) != 5:
        return _json_error("invalid_zip", 400)

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


# ✅ EINMALIGER Create-Endpoint (nicht doppeln!)
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

        try:
            email = validate_email(email).email
        except EmailNotValidError:
            return _json_error("invalid_email", 400)

        via_email = bool(data.get("via_email", True))
        via_sms = bool(data.get("via_sms", False))
        if not via_email and not via_sms:
            return _json_error("channel_required", 400)

        if via_sms and not phone:
            return _json_error("phone_required_for_sms", 400)

        try:
            radius_km = int(data.get("radius_km") or 0)
        except Exception:
            radius_km = 0

        categories_raw = data.get("categories") or ""
        categories = categories_raw.lower().strip() or None
        if not categories:
            return _json_error("category_required", 400)

        package_name = (data.get("package_name") or "alert_email").strip().lower()
        sms_quota_month = int(ALERT_PLANS.get(package_name, {}).get("sms_quota_month", 0))

        import secrets

        incoming_manage_key = (data.get("manage_key") or "").strip() or None

        def get_existing_manage_key_for_email(session: Session, email_: str) -> str | None:
            row = session.execute(
                text("""
                    SELECT manage_key
                    FROM public.alert_subscription
                    WHERE email = :email
                      AND manage_key IS NOT NULL
                    ORDER BY created_at ASC
                    LIMIT 1
                """),
                {"email": email_},
            ).mappings().first()
            return (row["manage_key"] if row and row.get("manage_key") else None)

        def get_email_for_manage_key(session: Session, key: str) -> str | None:
            """Holt die E-Mail-Adresse für einen manage_key"""
            row = session.execute(
                text("""
                    SELECT email
                    FROM public.alert_subscription
                    WHERE manage_key = :key
                    LIMIT 1
                """),
                {"key": key},
            ).mappings().first()
            return (row["email"] if row and row.get("email") else None)

        manage_key = None
        verify_token = None
        used = 0  # ✅ immer definiert

        with Session(engine) as s:
            # ✅ WICHTIG: Wenn ein manage_key vorhanden ist, muss die E-Mail-Adresse übereinstimmen
            if incoming_manage_key:
                expected_email = get_email_for_manage_key(s, incoming_manage_key)
                if expected_email and expected_email.lower() != email.lower():
                    return _json_error("email_mismatch", 400)
            # Limit check (bei dir pro E-Mail)
            # WICHTIG: Zähle ALLE Benachrichtigungen, auch gelöschte und deaktivierte
            existing_count = int(
                s.scalar(
                    select(func.count())
                    .select_from(AlertSubscription)
                    .where(AlertSubscription.email == email)
                ) or 0
            )
            
            # Berechne das aktuelle Limit basierend auf notification_limit
            current_limit_row = s.execute(
                text("""
                    SELECT MAX(notification_limit) as max_limit
                    FROM public.alert_subscription
                    WHERE email = :email AND notification_limit IS NOT NULL
                """),
                {"email": email},
            ).mappings().first()
            current_limit = int(current_limit_row["max_limit"]) if current_limit_row and current_limit_row["max_limit"] else ALERT_MAX_PER_EMAIL
            
            if existing_count >= current_limit:
                return _json_error("alert_limit_reached", 409)

            # Reuse latest unconfirmed
            existing = (
                s.execute(
                    select(AlertSubscription)
                    .where(
                        AlertSubscription.email == email,
                        AlertSubscription.email_confirmed.is_(False),
                    )
                    .order_by(AlertSubscription.created_at.desc())
                )
                .scalars()
                .first()
            )

            def ensure_manage_key(obj: AlertSubscription) -> str:
                # 1) Key vom Client hat höchste Priorität
                if incoming_manage_key:
                    obj.manage_key = incoming_manage_key
                    return obj.manage_key

                # 2) Wenn Objekt schon Key hat, behalten
                if getattr(obj, "manage_key", None):
                    return obj.manage_key

                # 3) Sonst: bestehenden Key aus DB für diese E-Mail holen
                existing_key = get_existing_manage_key_for_email(s, email)
                if existing_key:
                    obj.manage_key = existing_key
                    return obj.manage_key

                # 4) Sonst neu erzeugen
                obj.manage_key = secrets.token_urlsafe(24)
                return obj.manage_key

            if existing:
                # ✅ Update unconfirmed (keine neue Subscription zählen)
                existing.phone = phone or None
                existing.via_email = via_email
                existing.via_sms = via_sms
                existing.zip = zip_code
                existing.city = city or None
                existing.radius_km = radius_km
                existing.categories = categories
                existing.package_name = package_name
                existing.sms_quota_month = sms_quota_month

                lat, lng = geocode_cached(s, zip_code, city or None)
                existing.search_lat = lat
                existing.search_lng = lng

                existing.active = False
                existing.sms_confirmed = False

                verify_token = existing.verify_token or secrets.token_urlsafe(32)
                existing.verify_token = verify_token

                manage_key = ensure_manage_key(existing)
                
                # Stelle sicher, dass alle Alerts dieser E-Mail denselben manage_key haben
                s.execute(
                    text("""
                        UPDATE public.alert_subscription
                        SET manage_key = :key
                        WHERE email = :email AND (manage_key IS NULL OR manage_key != :key)
                    """),
                    {"key": manage_key, "email": email},
                )

                s.commit()

                used = existing_count  # keine neue Zeile dazu

            else:
                # ✅ Neu anlegen: add + commit + used korrekt
                verify_token = secrets.token_urlsafe(32)
                lat, lng = geocode_cached(s, zip_code, city or None)

                # Hole zuerst den manage_key für diese E-Mail (vor dem Erstellen des Objekts)
                existing_manage_key = get_existing_manage_key_for_email(s, email)
                if not existing_manage_key and incoming_manage_key:
                    existing_manage_key = incoming_manage_key

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
                    search_lat=lat,
                    search_lng=lng,
                )

                # Setze manage_key direkt (nutze vorhandenen oder generiere neuen)
                if existing_manage_key:
                    manage_key = existing_manage_key
                    # Stelle sicher, dass alle Alerts dieser E-Mail denselben Key haben
                    s.execute(
                        text("""
                            UPDATE public.alert_subscription
                            SET manage_key = :key
                            WHERE email = :email AND (manage_key IS NULL OR manage_key != :key)
                        """),
                        {"key": manage_key, "email": email},
                    )
                elif incoming_manage_key:
                    manage_key = incoming_manage_key
                    # Stelle sicher, dass alle Alerts dieser E-Mail denselben Key haben
                    s.execute(
                        text("""
                            UPDATE public.alert_subscription
                            SET manage_key = :key
                            WHERE email = :email AND (manage_key IS NULL OR manage_key != :key)
                        """),
                        {"key": manage_key, "email": email},
                    )
                else:
                    # Erstelle neuen Key nur, wenn keiner existiert
                    manage_key = secrets.token_urlsafe(24)
                    # Aktualisiere alle anderen Alerts dieser E-Mail mit dem neuen Key
                    s.execute(
                        text("""
                            UPDATE public.alert_subscription
                            SET manage_key = :key
                            WHERE email = :email AND (manage_key IS NULL OR manage_key != :key)
                        """),
                        {"key": manage_key, "email": email},
                    )
                
                # Setze den manage_key für den neuen Alert
                alert.manage_key = manage_key

                s.add(alert)
                s.commit()

                used = existing_count + 1  # ✅ neue Zeile zählt
        
        # Sicherstellen, dass verify_token und manage_key gesetzt sind
        if not verify_token or not manage_key:
            app.logger.error("create_alert: verify_token or manage_key not set")
            return jsonify({"error": "server_error"}), 500

        # Berechne das Limit für die Stats
        with Session(engine) as s2:
            limit_row = s2.execute(
                text("""
                    SELECT MAX(notification_limit) as max_limit
                    FROM public.alert_subscription
                    WHERE email = :email AND notification_limit IS NOT NULL
                """),
                {"email": email},
            ).mappings().first()
            limit_val = int(limit_row["max_limit"]) if limit_row and limit_row["max_limit"] else ALERT_MAX_PER_EMAIL
            left = max(0, limit_val - used)
        
        stats = {"used": used, "limit": limit_val, "left": left}

        verify_url = url_for("alerts_verify", token=verify_token, _external=True)

        body = (
            "Du hast auf Terminmarktplatz einen Termin-Alarm eingerichtet.\n\n"
            "Bitte klicke auf folgenden Link, um deine E-Mail-Adresse zu bestätigen "
            "und den Alarm zu aktivieren:\n\n"
            f"{verify_url}\n\n"
            "Wenn du das nicht warst, kannst du diese E-Mail ignorieren."
        )
        
        # Debug: Log verify_url und body
        app.logger.info(f"create_alert: verify_url={verify_url}, body length={len(body)}")

        ok, reason = send_mail(
            email,
            "Termin-Alarm bestätigen",
            text=body,
            tag="alert_verify",
        )
        if not ok:
            app.logger.warning("create_alert: send_mail not delivered: %s", reason)
        else:
            app.logger.info(f"create_alert: Mail erfolgreich gesendet an {email}, verify_url={verify_url}")

        return jsonify({
            "ok": True,
            "message": "Alarm angelegt. Bitte E-Mail bestätigen.",
            "stats": stats,
            "manage_key": manage_key
        })

    except Exception:
        app.logger.exception("create_alert failed")
        return jsonify({"error": "server_error"}), 500

 
 
# ✅ EINZIGE Verify-Route (robust)
@app.get("/alerts/verify/<path:token>", endpoint="alerts_verify")
def alerts_verify(token: str):
    token = _norm_token(token)
    if not token:
        return "Dieser Bestätigungslink ist ungültig oder abgelaufen.", 400

    try:
        with Session(engine) as s:
            row = s.execute(
                text("""
                    SELECT id, manage_key, via_email, via_sms
                    FROM public.alert_subscription
                    WHERE regexp_replace(COALESCE(verify_token,''), '\\s+', '', 'g') = :t
                    LIMIT 1
                """),
                {"t": token},
            ).mappings().first()

            if not row:
                return "Dieser Bestätigungslink ist ungültig oder abgelaufen.", 400

            # Falls manage_key wider Erwarten fehlt: nachziehen
            if not row["manage_key"]:
                import secrets
                new_key = secrets.token_urlsafe(24)
                s.execute(
                    text("UPDATE public.alert_subscription SET manage_key=:k WHERE id=:id"),
                    {"k": new_key, "id": row["id"]},
                )
                row = dict(row)
                row["manage_key"] = new_key

            s.execute(
                text("""
                    UPDATE public.alert_subscription
                    SET email_confirmed = TRUE,
                        active = TRUE,
                        last_reset_quota = COALESCE(last_reset_quota, now())
                    WHERE id = :id
                """),
                {"id": row["id"]},
            )
            s.commit()

        # ✅ Magic-Link + id auf Bestätigungsseite übergeben
        return redirect(
            f"{FRONTEND_URL}/benachrichtigung-bestaetigung.html?k={row['manage_key']}&id={row['id']}",
            code=302
        )

    except Exception:
        app.logger.exception("alerts_verify failed")
        return "Serverfehler", 500



@app.get("/alerts/cancel/<path:token>", endpoint="alerts_cancel")
def alerts_cancel(token: str):
    token = _norm_token(token)
    if not token:
        return "Alarm nicht gefunden oder bereits deaktiviert.", 400

    try:
        with Session(engine) as s:
            row = s.execute(
                text("""
                    SELECT id
                    FROM public.alert_subscription
                    WHERE regexp_replace(COALESCE(verify_token,''), '\\s+', '', 'g') = :t
                    LIMIT 1
                """),
                {"t": token},
            ).mappings().first()


            if not row:
                return "Alarm nicht gefunden oder bereits deaktiviert.", 400

            s.execute(
                text("UPDATE public.alert_subscription SET active = FALSE WHERE id = :id"),
                {"id": row["id"]},
            )
            s.commit()

        return "Dein Termin-Alarm wurde deaktiviert."

    except Exception:
        app.logger.exception("alerts_cancel failed")
        return "Serverfehler", 500



@app.get("/api/alerts/debug/token")
def debug_alert_by_token():
    t = _norm_token(request.args.get("t"))
    if not t:
        return _json_error("t_required", 400)

    with Session(engine) as s:
        raw = s.execute(
            text(r"""
                SELECT id, email, verify_token, active, email_confirmed, created_at
                FROM public.alert_subscription
                WHERE regexp_replace(COALESCE(verify_token, ''), '\s+', '', 'g') = :t
                LIMIT 1
            """),
            {"t": t},
        ).mappings().first()

        dbinfo = s.execute(
            text("select current_database() as db, inet_server_addr() as addr")
        ).mappings().first()

    return jsonify({
        "input": t,
        "raw_found": bool(raw),
        "raw": dict(raw) if raw else None,
        "dbinfo": dict(dbinfo) if dbinfo else None,
    })




# --------------------------------------------------------
# Slots (Provider)
# --------------------------------------------------------
@app.get("/slots")
@auth_required()
def slots_list():
    status = request.args.get("status")
    status = status.strip().upper() if status else None
    archived = request.args.get("archived")
    show_archived = archived and archived.lower() in ("true", "1", "yes")

    with Session(engine) as s:
        bq = (
            select(Booking.slot_id, func.count().label("booked"))
            .where(Booking.status == "confirmed")
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
        
        # Archiv-Filter: Standard nur nicht-archivierte, explizit archived=true zeigt nur archivierte
        if show_archived:
            q = q.where(Slot.archived == True)
        else:
            # Standard: nur nicht-archivierte Slots
            q = q.where(Slot.archived == False)

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
                        Booking.status.in_(["confirmed", "canceled"]),
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

            # Slot-Adresse: POST-Daten haben Priorität, sonst Provider-Profil als Default
            prov_zip = (p.zip or "").strip()
            prov_city = (p.city or "").strip()
            prov_street = (p.street or "").strip()

            data_street = (data.get("street") or "").strip()
            data_house  = (data.get("house_number") or "").strip()
            data_zip    = normalize_zip(data.get("zip"))
            data_city   = (data.get("city") or "").strip()

            slot_kwargs_extra = {}

            # street
            if hasattr(Slot, "street"):
                slot_kwargs_extra["street"] = (data_street[:120] if data_street else prov_street[:120] or None)

            # house_number
            if hasattr(Slot, "house_number"):
                slot_kwargs_extra["house_number"] = (data_house[:20] if data_house else None)

            # zip
            if hasattr(Slot, "zip"):
                z = data_zip if len(data_zip) == 5 else prov_zip
                slot_kwargs_extra["zip"] = (z[:5] if z else None)

            # city
            if hasattr(Slot, "city"):
                slot_kwargs_extra["city"] = (data_city[:80] if data_city else prov_city[:80] or None)

            # optional: location automatisch sauber setzen, wenn im UI location nicht gepflegt werden soll
            # (du sendest location aber schon – daher nur Fallback)
            if not location_db:
                line1 = " ".join(x for x in [slot_kwargs_extra.get("street") or "", slot_kwargs_extra.get("house_number") or ""] if x).strip()
                line2 = " ".join(x for x in [slot_kwargs_extra.get("zip") or "", slot_kwargs_extra.get("city") or ""] if x).strip()
                location_db = ", ".join(x for x in [line1, line2] if x)[:120]

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
                    # NEU: strukturierte Adresse erlauben
            if "street" in data and data["street"] is not None:
                data["street"] = str(data["street"]).strip()[:120] or None

            if "house_number" in data and data["house_number"] is not None:
                data["house_number"] = str(data["house_number"]).strip()[:20] or None

            if "zip" in data and data["zip"] is not None:
                z = normalize_zip(data["zip"])
                if z and len(z) != 5:
                    return _json_error("invalid_zip", 400)
                data["zip"] = z or None

            if "city" in data and data["city"] is not None:
                data["city"] = str(data["city"]).strip()[:80] or None

            if "title" in data and data["title"]:
                data["title"] = str(data["title"]).strip()[:100]
            if "capacity" in data:
                try:
                    c = int(data["capacity"])
                    if c < 1:
                        return _json_error("bad_capacity", 400)
                except Exception:
                    return _json_error("bad_capacity", 400)

            # WICHTIG: Updates dürfen NICHT nur bei capacity laufen
            for k in [
                "title",
                "category",
                "location",
                "street",
                "house_number",
                "zip",
                "city",
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


@app.post("/slots/<slot_id>/archive")
@auth_required()
def slots_archive(slot_id):
    """
    Archiviert einen Slot (setzt archived=True und Status=EXPIRED).
    Archivierte Slots sind read-only und können nicht gelöscht werden.
    """
    with Session(engine) as s:
        slot = s.get(Slot, slot_id)
        if not slot or slot.provider_id != request.provider_id:
            return _json_error("not_found", 404)
        
        slot.archived = True
        slot.status = SLOT_STATUS_EXPIRED
        s.commit()
        return jsonify({"ok": True, "archived": True})


@app.delete("/slots/<slot_id>")
@auth_required()
def slots_delete(slot_id):
    """
    Löscht oder archiviert einen Slot je nach Situation (Aufbewahrungspflicht).
    Hard-Delete ist nicht erlaubt für abgerechnete Termine.
    """
    with Session(engine) as s:
        slot = s.get(Slot, slot_id)
        if not slot or slot.provider_id != request.provider_id:
            return _json_error("not_found", 404)
        
        # Wenn bereits archiviert: kann nicht gelöscht werden
        if getattr(slot, "archived", False):
            return _json_error("already_archived", 409)
        
        # Prüfe ob Slot bereits abgerechnet wurde (Buchungen vorhanden)
        has_bookings = (
            s.scalar(
                select(func.count())
                .select_from(Booking)
                .where(
                    Booking.slot_id == slot.id,
                    Booking.status == "confirmed",
                )
            )
            or 0
        ) > 0
        
        # Wenn Slot bereits stattgefunden hat (end_at in Vergangenheit) oder Buchungen vorhanden:
        # Nur archivieren, niemals löschen
        now = _now()
        slot_end_aware = _as_utc_aware(slot.end_at)
        has_ended = slot_end_aware < now
        
        if has_ended or has_bookings:
            # Archivieren statt löschen
            slot.archived = True
            slot.status = SLOT_STATUS_EXPIRED
            s.commit()
            return jsonify({"ok": True, "archived": True, "message": "Termin wurde archiviert (Aufbewahrungspflicht)"})
        else:
            # Für zukünftige, ungebuchte Slots ohne Buchungen: physisches Löschen erlaubt
            s.delete(slot)
            s.commit()
            return jsonify({"ok": True, "deleted": True})


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
# Admin: Rechnungen (Invoices)
# --------------------------------------------------------
@app.get("/admin/invoices/all")
@auth_required(admin=True)
def admin_invoices_all():
    """Gibt alle Rechnungen aller Provider zurück (nur für Super-Admin)."""
    with Session(engine) as s:
        # Prüfe ob provider_number Spalte existiert
        provider_number_exists = False
        try:
            s.execute(text("SELECT provider_number FROM provider LIMIT 1"))
            provider_number_exists = True
        except Exception:
            pass
        
        if provider_number_exists:
            invoices = (
                s.execute(
                    select(Invoice, Provider.email, Provider.company_name, Provider.provider_number)
                    .join(Provider, Invoice.provider_id == Provider.id)
                    .order_by(Invoice.created_at.desc())
                )
                .all()
            )
        else:
            # Fallback: ohne provider_number
            invoices = (
                s.execute(
                    select(Invoice, Provider.email, Provider.company_name)
                    .join(Provider, Invoice.provider_id == Provider.id)
                    .order_by(Invoice.created_at.desc())
                )
                .all()
            )

        result = []
        for row in invoices:
            inv = row[0]  # Invoice-Objekt
            provider_email = row[1]  # Provider.email
            provider_company_name = row[2]  # Provider.company_name
            provider_number = row[3] if provider_number_exists and len(row) > 3 else None
            result.append(
                {
                    "id": inv.id,
                    "provider_id": inv.provider_id,
                    "provider_number": provider_number,
                    "provider_email": provider_email,
                    "provider_company_name": provider_company_name,
                    "period_start": inv.period_start.isoformat(),
                    "period_end": inv.period_end.isoformat(),
                    "total_eur": float(inv.total_eur),
                    "status": inv.status,
                    "created_at": inv.created_at.isoformat() if inv.created_at else None,
                    "archived_at": inv.archived_at.isoformat() if inv.archived_at else None,
                    "exported_at": inv.exported_at.isoformat() if inv.exported_at else None,
                }
            )

        return jsonify(result)


@app.get("/me/debug")
@auth_required()
def me_debug():
    """Debug-Endpoint: Zeigt alle Daten des aktuellen Providers inkl. provider_number."""
    with Session(engine) as s:
        try:
            p = s.get(Provider, request.provider_id)
            if not p:
                return _json_error("not_found", 404)
            
            # Direkt aus DB lesen
            db_result = s.execute(text("""
                SELECT id, email, provider_number, created_at
                FROM provider
                WHERE id = :pid
            """), {"pid": str(request.provider_id)}).mappings().first()
            
            # Prüfe ob Spalte existiert
            column_exists = False
            try:
                s.execute(text("SELECT provider_number FROM provider LIMIT 1"))
                column_exists = True
            except Exception as e:
                column_error = str(e)
            else:
                column_error = None
            
            return jsonify({
                "provider_id": str(p.id),
                "email": p.email,
                "provider_number_from_model": getattr(p, "provider_number", "ATTRIBUTE_NOT_FOUND"),
                "provider_number_from_db": db_result["provider_number"] if db_result else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "column_exists": column_exists,
                "column_error": column_error,
                "db_result": dict(db_result) if db_result else None,
            })
        except Exception as e:
            app.logger.exception("me_debug failed: %r", e)
            return jsonify({"error": str(e)}), 500


@app.get("/admin/debug/provider-numbers")
@auth_required(admin=True)
def debug_provider_numbers():
    """Debug-Endpoint: Zeigt Status der provider_number Migration."""
    with Session(engine) as s:
        # Prüfe ob Spalte existiert
        column_exists = False
        column_error = None
        try:
            s.execute(text("SELECT provider_number FROM provider LIMIT 1"))
            column_exists = True
        except Exception as e:
            column_error = str(e)
        
        # Zähle Provider
        total_providers = s.scalar(select(func.count()).select_from(Provider))
        providers_with_number = 0
        providers_without_number = 0
        max_number = None
        
        if column_exists:
            providers_with_number = s.scalar(
                select(func.count()).select_from(Provider).where(Provider.provider_number.isnot(None))
            )
            providers_without_number = total_providers - providers_with_number
            max_number = s.scalar(select(func.max(Provider.provider_number)))
        
        # Zähle Rechnungen
        total_invoices = s.scalar(select(func.count()).select_from(Invoice))
        
        return jsonify({
            "column_exists": column_exists,
            "column_error": column_error,
            "total_providers": total_providers,
            "providers_with_number": providers_with_number,
            "providers_without_number": providers_without_number,
            "max_provider_number": max_number,
            "total_invoices": total_invoices,
        })


@app.post("/admin/debug/run-provider-number-migration")
@auth_required(admin=True)
def run_provider_number_migration():
    """Führt die provider_number Migration manuell aus."""
    try:
        with Session(engine) as s:
            # Zähle Provider vor Migration
            total_before = s.scalar(select(func.count()).select_from(Provider))
            with_number_before = s.scalar(
                select(func.count()).select_from(Provider).where(Provider.provider_number.isnot(None))
            )
        
        # Migration ausführen
        _ensure_provider_number_field()
        
        # Zähle Provider nach Migration
        with Session(engine) as s:
            total_after = s.scalar(select(func.count()).select_from(Provider))
            with_number_after = s.scalar(
                select(func.count()).select_from(Provider).where(Provider.provider_number.isnot(None))
            )
            max_number = s.scalar(select(func.max(Provider.provider_number)))
        
        return jsonify({
            "ok": True,
            "message": "Migration completed",
            "before": {
                "total": total_before,
                "with_number": with_number_before
            },
            "after": {
                "total": total_after,
                "with_number": with_number_after,
                "max_number": max_number
            },
            "newly_numbered": with_number_after - with_number_before
        })
    except Exception as e:
        app.logger.exception("Manual migration failed: %r", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/admin/debug/invoices")
@auth_required(admin=True)
def debug_invoices():
    """Debug-Endpoint: Zeigt alle Rechnungen mit Details."""
    with Session(engine) as s:
        # Prüfe ob provider_number Spalte existiert
        provider_number_exists = False
        try:
            s.execute(text("SELECT provider_number FROM provider LIMIT 1"))
            provider_number_exists = True
        except Exception as e:
            provider_number_error = str(e)
        else:
            provider_number_error = None
        
        # Hole alle Rechnungen mit rohem SQL
        try:
            if provider_number_exists:
                invoices_raw = s.execute(text("""
                    SELECT 
                        i.id,
                        i.provider_id,
                        i.period_start,
                        i.period_end,
                        i.total_eur,
                        i.status,
                        i.created_at,
                        p.email as provider_email,
                        p.company_name as provider_company_name,
                        p.provider_number
                    FROM invoice i
                    JOIN provider p ON i.provider_id = p.id
                    ORDER BY i.created_at DESC
                """)).mappings().all()
            else:
                invoices_raw = s.execute(text("""
                    SELECT 
                        i.id,
                        i.provider_id,
                        i.period_start,
                        i.period_end,
                        i.total_eur,
                        i.status,
                        i.created_at,
                        p.email as provider_email,
                        p.company_name as provider_company_name,
                        NULL as provider_number
                    FROM invoice i
                    JOIN provider p ON i.provider_id = p.id
                    ORDER BY i.created_at DESC
                """)).mappings().all()
            
            invoices = [dict(row) for row in invoices_raw]
            return jsonify({
                "provider_number_exists": provider_number_exists,
                "provider_number_error": provider_number_error,
                "invoice_count": len(invoices),
                "invoices": invoices,
            })
        except Exception as e:
            app.logger.exception("debug_invoices failed: %r", e)
            return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/admin/invoices/<invoice_id>")
@auth_required(admin=True)
def admin_invoice_detail(invoice_id):
    """Gibt Details einer Rechnung inkl. Buchungen zurück."""
    with Session(engine) as s:
        inv = s.get(Invoice, invoice_id)
        if not inv:
            return _json_error("not_found", 404)

        provider = s.get(Provider, inv.provider_id)
        bookings = (
            s.execute(
                select(Booking, Slot.title, Slot.start_at, Slot.end_at)
                .join(Slot, Booking.slot_id == Slot.id)
                .where(Booking.invoice_id == invoice_id)
                .order_by(Booking.created_at.asc())
            )
            .all()
        )

        booking_list = []
        for row in bookings:
            b = row[0]
            slot_title = row[1]
            slot_start = row[2]
            slot_end = row[3]
            booking_list.append(
                {
                    "id": b.id,
                    "customer_name": b.customer_name,
                    "customer_email": b.customer_email,
                    "slot_title": slot_title,
                    "slot_start": slot_start.isoformat() if slot_start else None,
                    "slot_end": slot_end.isoformat() if slot_end else None,
                    "provider_fee_eur": float(b.provider_fee_eur),
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                }
            )

        return jsonify(
            {
                "id": inv.id,
                "provider_id": inv.provider_id,
                "provider_email": provider.email if provider else None,
                "provider_company_name": provider.company_name if provider else None,
                "period_start": inv.period_start.isoformat(),
                "period_end": inv.period_end.isoformat(),
                "total_eur": float(inv.total_eur),
                "status": inv.status,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
                "bookings": booking_list,
            }
        )


# PDF-Generierung für Rechnungen (reportlab)
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from io import BytesIO

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def generate_invoice_pdf(invoice: Invoice, provider: Provider, bookings: list[Booking], session: Session | None = None) -> bytes:
    """Generiert ein PDF für eine Rechnung."""
    if not REPORTLAB_AVAILABLE:
        raise Exception("reportlab nicht installiert")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    story = []
    styles = getSampleStyleSheet()

    # Custom Styles
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=30,
        alignment=TA_LEFT,
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#334155"),
        spaceAfter=12,
        alignment=TA_LEFT,
    )

    normal_style = styles["Normal"]
    normal_style.fontSize = 10
    normal_style.textColor = colors.HexColor("#475569")

    # Header
    story.append(Paragraph("Terminmarktplatz", title_style))
    story.append(Paragraph("Rechnung", heading_style))
    story.append(Spacer(1, 0.5*cm))

    # Rechnungsinformationen
    invoice_data = [
        ["Rechnungsnummer:", invoice.id[:8].upper()],
        ["Rechnungsdatum:", invoice.created_at.strftime("%d.%m.%Y") if invoice.created_at else "-"],
        ["Zeitraum:", f"{invoice.period_start.strftime('%d.%m.%Y')} - {invoice.period_end.strftime('%d.%m.%Y')}"],
        ["Status:", invoice.status],
    ]

    invoice_table = Table(invoice_data, colWidths=[5*cm, 10*cm])
    invoice_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1e293b")),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(invoice_table)
    story.append(Spacer(1, 0.8*cm))

    # Anbieter-Informationen
    story.append(Paragraph("Anbieter", heading_style))
    provider_info = []
    if provider.provider_number:
        provider_info.append(["Anbieter-Nr.:", str(provider.provider_number)])
    if provider.company_name:
        provider_info.append(["Firma:", provider.company_name])
    provider_info.append(["E-Mail:", provider.email])
    if provider.street:
        provider_info.append(["Straße:", provider.street])
    if provider.zip and provider.city:
        provider_info.append(["PLZ/Ort:", f"{provider.zip} {provider.city}"])

    provider_table = Table(provider_info, colWidths=[5*cm, 10*cm])
    provider_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1e293b")),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(provider_table)
    story.append(Spacer(1, 0.8*cm))

    # Buchungsdetails
    story.append(Paragraph("Buchungsdetails", heading_style))
    booking_data = [["Datum", "Termin", "Kunde", "Betrag"]]

    for b in bookings:
        # Slot-Informationen laden falls Session verfügbar
        slot_title = "Termin"
        if session and hasattr(b, "slot_id") and b.slot_id:
            slot = session.get(Slot, b.slot_id)
            if slot:
                slot_title = slot.title or "Termin"

        booking_date = b.created_at.strftime("%d.%m.%Y") if b.created_at else "-"
        customer = b.customer_name or (b.customer_email[:30] + "..." if b.customer_email and len(b.customer_email) > 30 else b.customer_email) or "N/A"
        amount = f"{float(b.provider_fee_eur):.2f} €"
        booking_data.append([booking_date, slot_title[:40], customer[:40], amount])

    # Gesamtbetrag
    booking_data.append(["", "", "Gesamtbetrag:", f"{float(invoice.total_eur):.2f} €"])

    booking_table = Table(booking_data, colWidths=[3.5*cm, 5*cm, 4*cm, 2.5*cm])
    booking_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("TOPPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -2), colors.white),
                ("TEXTCOLOR", (0, 1), (-1, -2), colors.HexColor("#475569")),
                ("FONTNAME", (0, 1), (-1, -2), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -2), 9),
                ("GRID", (0, 0), (-1, -2), 1, colors.HexColor("#e2e8f0")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                # Gesamtbetrag-Zeile
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f8fafc")),
                ("FONTNAME", (0, -1), (-2, -1), "Helvetica"),
                ("FONTNAME", (-1, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, -1), (-1, -1), 10),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#1e293b")),
                ("TOPPADDING", (0, -1), (-1, -1), 10),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
            ]
        )
    )
    story.append(booking_table)

    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


@app.get("/admin/invoices/<invoice_id>/pdf")
@auth_required(admin=True)
def admin_invoice_pdf(invoice_id):
    """Lädt eine Rechnung als PDF herunter."""
    try:
        with Session(engine) as s:
            inv = s.get(Invoice, invoice_id)
            if not inv:
                return _json_error("not_found", 404)

            provider = s.get(Provider, inv.provider_id)
            if not provider:
                return _json_error("provider_not_found", 404)

            bookings = (
                s.execute(
                    select(Booking).where(Booking.invoice_id == invoice_id).order_by(Booking.created_at.asc())
                )
                .scalars()
                .all()
            )

            if not REPORTLAB_AVAILABLE:
                return jsonify({"error": "pdf_generation_not_available", "detail": "reportlab nicht installiert"}), 503

            pdf_bytes = generate_invoice_pdf(inv, provider, bookings, s)
            filename = f"Rechnung_{inv.id[:8].upper()}_{inv.period_start.strftime('%Y%m')}.pdf"

            return Response(
                pdf_bytes,
                mimetype="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
    except Exception as e:
        app.logger.exception("admin_invoice_pdf failed")
        return jsonify({"error": "server_error", "detail": str(e)}), 500


def send_invoice_email(invoice: Invoice, provider: Provider, bookings: list[Booking], session: Session | None = None) -> tuple[bool, str]:
    """Sendet eine Rechnung per E-Mail mit PDF-Anhang."""
    try:
        if not REPORTLAB_AVAILABLE:
            return False, "reportlab nicht installiert"

        pdf_bytes = generate_invoice_pdf(invoice, provider, bookings, session)
        filename = f"Rechnung_{invoice.id[:8].upper()}_{invoice.period_start.strftime('%Y%m')}.pdf"

        # E-Mail-Text
        subject = f"Rechnung {invoice.id[:8].upper()} - {invoice.period_start.strftime('%B %Y')}"
        text_body = f"""Hallo {provider.company_name or 'Anbieter/in'},

anbei erhalten Sie Ihre Rechnung für den Zeitraum {invoice.period_start.strftime('%d.%m.%Y')} bis {invoice.period_end.strftime('%d.%m.%Y')}.

Rechnungsnummer: {invoice.id[:8].upper()}
Rechnungsdatum: {invoice.created_at.strftime('%d.%m.%Y') if invoice.created_at else '-'}
Betrag: {float(invoice.total_eur):.2f} €

Das PDF finden Sie im Anhang dieser E-Mail.

Bei Fragen stehen wir Ihnen gerne zur Verfügung.

Viele Grüße
Terminmarktplatz
"""

        # Für E-Mail-Versand mit Attachment müssen wir send_mail erweitern oder eine spezielle Funktion verwenden
        # Da send_mail aktuell keine Attachments unterstützt, verwenden wir SMTP direkt für Attachments
        if MAIL_PROVIDER == "smtp":
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.base import MIMEBase
            from email import encoders

            if not SMTP_USER or not SMTP_PASS or not SMTP_HOST:
                return False, "SMTP nicht konfiguriert"

            msg = MIMEMultipart()
            msg["From"] = MAIL_FROM or SMTP_USER
            msg["To"] = provider.email
            msg["Subject"] = subject
            if MAIL_REPLY_TO:
                msg["Reply-To"] = MAIL_REPLY_TO

            msg.attach(MIMEText(text_body, "plain", "utf-8"))

            attachment = MIMEBase("application", "pdf")
            attachment.set_payload(pdf_bytes)
            encoders.encode_base64(attachment)
            attachment.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(attachment)

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
                app.logger.exception("SMTP send_invoice_email failed")
                return False, str(e)
        else:
            # Für Resend/Postmark: PDF als base64 anhängen (falls API es unterstützt)
            # Oder einfach Text-Mail ohne Attachment senden mit Download-Link
            send_mail(
                provider.email,
                subject,
                text=text_body + f"\n\nPDF-Download: {BASE_URL}/admin/invoices/{invoice.id}/pdf",
                tag="invoice",
                metadata={"invoice_id": invoice.id},
            )
            return True, "sent_without_attachment"

    except Exception as e:
        app.logger.exception("send_invoice_email failed")
        return False, str(e)


@app.post("/admin/invoices/<invoice_id>/send-email")
@auth_required(admin=True)
def admin_invoice_send_email(invoice_id):
    """Sendet eine Rechnung per E-Mail."""
    try:
        with Session(engine) as s:
            inv = s.get(Invoice, invoice_id)
            if not inv:
                return _json_error("not_found", 404)

            provider = s.get(Provider, inv.provider_id)
            if not provider:
                return _json_error("provider_not_found", 404)

            bookings = (
                s.execute(
                    select(Booking).where(Booking.invoice_id == invoice_id).order_by(Booking.created_at.asc())
                )
                .scalars()
                .all()
            )

            ok, reason = send_invoice_email(inv, provider, bookings, s)

            if ok:
                return jsonify({"ok": True, "reason": reason})
            else:
                return jsonify({"error": "email_send_failed", "detail": reason}), 500

    except Exception as e:
        app.logger.exception("admin_invoice_send_email failed")
        return jsonify({"error": "server_error", "detail": str(e)}), 500


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

                # Zähle das aktuelle Limit (basierend auf notification_limit der vorhandenen Alerts)
                current_limit_row = s.execute(
                    text("""
                        SELECT MAX(notification_limit) as max_limit
                        FROM public.alert_subscription
                        WHERE email = :email AND notification_limit IS NOT NULL
                    """),
                    {"email": buyer_email},
                ).mappings().first()
                
                current_limit = int(current_limit_row["max_limit"]) if current_limit_row and current_limit_row["max_limit"] else 0
                
                # Erhöhe das Limit um 10 (ein neues Paket = 10 weitere Benachrichtigungen)
                new_limit = current_limit + ALERT_LIMIT_PER_PACKAGE

                for a in alerts:
                    a.package_name = alert_plan_key
                    a.sms_quota_month = sms_quota
                    a.sms_sent_this_month = 0
                    a.last_reset_quota = now
                
                # Setze notification_limit für alle Alerts dieser E-Mail auf das neue Limit
                s.execute(
                    text("""
                        UPDATE public.alert_subscription
                        SET notification_limit = :limit
                        WHERE email = :email
                    """),
                    {"limit": new_limit, "email": buyer_email},
                )

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
    # Prüfe ob q_text eine passende Kategorie ist (mit Fuzzy-Search)
    if not category and q_text:
        matching_cats = find_matching_categories(q_text)
        if matching_cats:
            # Wenn exakt eine Kategorie gefunden wurde, verwende diese
            if len(matching_cats) == 1:
                category = matching_cats[0]
            # Ansonsten bleibt search_term aktiv für die erweiterte Suche

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

    # Retry-Logik für Datenbankverbindungsfehler (max 2 Versuche)
    for attempt in range(1, 3):
        try:
            with Session(engine) as s:
                origin_lat = origin_lon = None
                # Umkreissuche funktioniert mit PLZ ODER Ort (Stadtname)
                if radius_km is not None:
                    if zip_filter:
                        # PLZ hat Priorität
                        origin_lat, origin_lon = geocode_cached(s, zip_filter, None)
                    elif city_q:
                        # Falls keine PLZ, verwende Ortsname
                        origin_lat, origin_lon = geocode_cached(s, None, city_q)
                    elif location_raw:
                        # Fallback: versuche location_raw als PLZ oder Stadt
                        if location_raw.isdigit() and len(location_raw) == 5:
                            origin_lat, origin_lon = geocode_cached(s, location_raw, None)
                        else:
                            origin_lat, origin_lon = geocode_cached(s, None, location_raw)

                bq = (
                    select(Booking.slot_id, func.count().label("booked"))
                    .where(Booking.status == "confirmed")
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

                # Kategorie-Filterung mit Fuzzy-Search
                if category:
                    matching_categories = find_matching_categories(category)
                    if matching_categories:
                        # Suche nach exakten Übereinstimmungen
                        sq = sq.where(Slot.category.in_(matching_categories))
                    else:
                        # Fallback: Teilstring-Suche
                        sq = sq.where(Slot.category.ilike(f"%{category}%"))

                if radius_km is None:
                    loc_for_filter = location_raw or city_q or zip_filter
                    if loc_for_filter:
                        pattern_loc = f"%{loc_for_filter}%"
                        # Suche in Slot.location ODER Slot.zip ODER Slot.city ODER Provider.zip/city
                        if zip_filter and zip_filter.isdigit() and len(zip_filter) == 5:
                            # Wenn es eine PLZ ist, suche nach Slot.zip ODER Provider.zip ODER location
                            sq = sq.where(
                                or_(
                                    Slot.zip == zip_filter,
                                    Provider.zip == zip_filter,
                                    Slot.location.ilike(pattern_loc),
                                )
                            )
                        elif city_q:
                            # Wenn es eine Stadt ist, suche nach Slot.city ODER Provider.city ODER location
                            sq = sq.where(
                                or_(
                                    Slot.city.ilike(f"%{city_q}%"),
                                    Provider.city.ilike(f"%{city_q}%"),
                                    Slot.location.ilike(pattern_loc),
                                )
                            )
                        else:
                            # Fallback: location ODER Provider Adressfelder
                            sq = sq.where(
                                or_(
                                    Slot.location.ilike(pattern_loc),
                                    Slot.zip.ilike(pattern_loc),
                                    Slot.city.ilike(pattern_loc),
                                    Provider.zip.ilike(pattern_loc),
                                    Provider.city.ilike(pattern_loc),
                                )
                            )

                # Erweiterte Suche: Titel UND Kategorie mit Fuzzy-Matching
                if search_term:
                    pattern = f"%{search_term}%"
                    
                    # Finde passende Kategorien für den Suchbegriff
                    matching_categories = find_matching_categories(search_term)
                    
                    # Baue OR-Bedingung: Titel ODER Kategorie (exakt) ODER Kategorie (Teilstring)
                    conditions = [Slot.title.ilike(pattern)]
                    
                    if matching_categories:
                        # Exakte Kategorie-Übereinstimmungen
                        conditions.append(Slot.category.in_(matching_categories))
                    else:
                        # Fallback: Teilstring-Suche in Kategorie
                        conditions.append(Slot.category.ilike(pattern))
                    
                    sq = sq.where(or_(*conditions))

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
                        
                        # Verwende zuerst Slot-Adresse, dann Provider-Adresse als Fallback
                        slot_zip = getattr(slot, "zip", None) or p_zip
                        slot_city = getattr(slot, "city", None) or p_city
                        
                        plat, plon = geocode_cached(s, slot_zip, slot_city)
                        if plat is None or plon is None:
                            continue
                            
                        distance_km = _haversine_km(origin_lat, origin_lon, plat, plon)
                        if distance_km > radius_km:
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
        except OperationalError as e:
            if attempt < 2:
                app.logger.warning(f"public_slots: DB connection error (attempt {attempt}), retrying...")
                time.sleep(0.1 * attempt)  # Kurze Verzögerung vor Retry
                continue
            else:
                app.logger.exception("public_slots: DB connection error after retries")
                return jsonify({"error": "DB connection error"}), 500
        except SQLAlchemyError as e:
            app.logger.exception("public_slots: DB error")
            return jsonify({"error": "DB error"}), 500
        except Exception as e:
            app.logger.exception("public_slots: Unexpected error")
            return jsonify({"error": "server_error"}), 500


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
        
        # Slot-Details für E-Mail formatieren
        slot_start_local = _as_utc_aware(slot.start_at).astimezone(BERLIN)
        slot_end_local = _as_utc_aware(slot.end_at).astimezone(BERLIN)
        start_str = slot_start_local.strftime("%d.%m.%Y %H:%M")
        end_str = slot_end_local.strftime("%H:%M")
        
        slot_address = slot.public_address() if hasattr(slot, 'public_address') else (slot.location or "")
        if not slot_address and provider:
            provider_address = f"{provider.zip or ''} {provider.city or ''}".strip()
            if provider.street:
                provider_address = f"{provider.street}, {provider_address}".strip()
            slot_address = provider_address
        
        email_body = f"Hallo {name},\n\n"
        email_body += f"du hast einen Termin gebucht:\n\n"
        email_body += f"Termin: {slot.title}\n"
        email_body += f"Kategorie: {slot.category}\n"
        email_body += f"Datum & Zeit: {start_str} - {end_str} Uhr\n"
        if slot_address:
            email_body += f"Ort: {slot_address}\n"
        if provider:
            email_body += f"Anbieter: {provider.company_name or 'Unbekannt'}\n"
        if slot.price_cents:
            price_euro = float(slot.price_cents) / 100
            email_body += f"Preis: {price_euro:.2f} €\n"
        email_body += f"\n"
        email_body += f"Bitte bestätige deine Buchung:\n{confirm_link}\n\n"
        email_body += f"Stornieren:\n{cancel_link}\n"
        
        send_mail(
            email,
            "Bitte Terminbuchung bestätigen",
            text=email_body,
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

                # Slot-Details für Bestätigungs-E-Mail formatieren
                slot_start_local = _as_utc_aware(slot_obj.start_at).astimezone(BERLIN)
                slot_end_local = _as_utc_aware(slot_obj.end_at).astimezone(BERLIN)
                start_str = slot_start_local.strftime("%d.%m.%Y %H:%M")
                end_str = slot_end_local.strftime("%H:%M")
                
                slot_address = slot_obj.public_address() if hasattr(slot_obj, 'public_address') else (slot_obj.location or "")
                if not slot_address and provider_obj:
                    provider_address = f"{provider_obj.zip or ''} {provider_obj.city or ''}".strip()
                    if provider_obj.street:
                        provider_address = f"{provider_obj.street}, {provider_address}".strip()
                    slot_address = provider_address
                
                confirm_email_body = f"Hallo {b.customer_name},\n\n"
                confirm_email_body += f"dein Termin ist bestätigt:\n\n"
                confirm_email_body += f"Termin: {slot_obj.title}\n"
                confirm_email_body += f"Kategorie: {slot_obj.category}\n"
                confirm_email_body += f"Datum & Zeit: {start_str} - {end_str} Uhr\n"
                if slot_address:
                    confirm_email_body += f"Ort: {slot_address}\n"
                if provider_obj:
                    confirm_email_body += f"Anbieter: {provider_obj.company_name or 'Unbekannt'}\n"
                if slot_obj.price_cents:
                    price_euro = float(slot_obj.price_cents) / 100
                    confirm_email_body += f"Preis: {price_euro:.2f} €\n"
                confirm_email_body += f"\n"
                confirm_email_body += f"Wir freuen uns auf deinen Besuch!\n"

                send_mail(
                    b.customer_email,
                    "Termin bestätigt",
                    text=confirm_email_body,
                    tag="booking_confirmed",
                    metadata={"slot_id": str(slot_obj.id)},
                )

                # E-Mail an Provider senden
                if provider_obj and provider_obj.email:
                    try:
                        provider_email_body = f"Hallo {provider_obj.company_name or 'Anbieter'},\n\n"
                        provider_email_body += f"Es wurde eine neue Buchung für einen deiner Termine bestätigt:\n\n"
                        provider_email_body += f"Termin-Details:\n"
                        provider_email_body += f"Titel: {slot_obj.title}\n"
                        if slot_obj.category:
                            provider_email_body += f"Kategorie: {slot_obj.category}\n"
                        provider_email_body += f"Datum & Zeit: {start_str} - {end_str} Uhr\n"
                        if slot_address:
                            provider_email_body += f"Ort: {slot_address}\n"
                        if slot_obj.price_cents:
                            price_euro = float(slot_obj.price_cents) / 100
                            provider_email_body += f"Preis: {price_euro:.2f} €\n"
                        provider_email_body += f"\n"
                        provider_email_body += f"Kunden-Details:\n"
                        provider_email_body += f"Name: {b.customer_name}\n"
                        provider_email_body += f"E-Mail: {b.customer_email}\n"
                        provider_email_body += f"\n"
                        provider_email_body += f"Viele Grüße\n"
                        provider_email_body += f"Terminmarktplatz"

                        send_mail(
                            provider_obj.email,
                            "Neue Buchung bestätigt",
                            text=provider_email_body,
                            tag="booking_confirmed_notify_provider",
                            metadata={
                                "booking_id": str(b.id),
                                "slot_id": str(slot_obj.id),
                                "provider_id": str(provider_obj.id),
                            },
                        )
                    except Exception as e:
                        app.logger.warning("public_confirm: send_mail to provider failed: %r", e)

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
                slot_address = slot_obj.public_address() if hasattr(slot_obj, 'public_address') else (slot_obj.location or "")
                price_euro_str = None
                if slot_obj.price_cents:
                    price_euro = float(slot_obj.price_cents) / 100
                    price_euro_str = f"{price_euro:.2f}"
                slot = {
                    "id": slot_obj.id,
                    "title": slot_obj.title,
                    "category": slot_obj.category,
                    "start_at": slot_obj.start_at,
                    "end_at": slot_obj.end_at,
                    "location": slot_obj.location,
                    "street": slot_obj.street,
                    "house_number": slot_obj.house_number,
                    "zip": slot_obj.zip,
                    "city": slot_obj.city,
                    "address": slot_address,
                    "price_cents": slot_obj.price_cents,
                    "price_euro": price_euro_str,
                    "notes": slot_obj.notes,
                }

            provider = None
            if provider_obj is not None:
                provider = {
                    "company_name": provider_obj.company_name,
                    "zip": provider_obj.zip,
                    "city": provider_obj.city,
                    "street": provider_obj.street,
                }

        # Kalender-Links vorbereiten
        calendar_links = None
        if slot and slot.get("start_at") and slot.get("end_at"):
            try:
                from urllib.parse import quote
                # Datum/Zeit für Kalender-Links
                # slot ist ein Dictionary, start_at/end_at sind datetime-Objekte
                start_dt = _as_utc_aware(slot["start_at"])
                end_dt = _as_utc_aware(slot["end_at"])
                
                # Titel und Ort
                title = quote(slot.get("title") or "Termin")
                location = ""
                if slot.get("address"):
                    location = quote(slot["address"])
                elif slot.get("location"):
                    location = quote(slot["location"])
                elif provider:
                    parts = []
                    if provider.get("street"):
                        parts.append(provider["street"])
                    if provider.get("zip"):
                        parts.append(provider["zip"])
                    if provider.get("city"):
                        parts.append(provider["city"])
                    if parts:
                        location = quote(", ".join(parts))
                
                # Beschreibung
                desc_parts = [f"Termin: {slot.get('title', 'Termin')}"]
                if slot.get("category"):
                    desc_parts.append(f"Kategorie: {slot['category']}")
                if provider and provider.get("company_name"):
                    desc_parts.append(f"Anbieter: {provider['company_name']}")
                description = quote("\n".join(desc_parts))
                
                # Google Calendar Link (direkter Link)
                # Format: YYYYMMDDTHHMMSSZ
                start_google = start_dt.strftime("%Y%m%dT%H%M%SZ")
                end_google = end_dt.strftime("%Y%m%dT%H%M%SZ")
                google_cal_url = (
                    f"https://calendar.google.com/calendar/render?"
                    f"action=TEMPLATE"
                    f"&text={title}"
                    f"&dates={start_google}/{end_google}"
                    f"&details={description}"
                    f"&location={location}"
                )
                
                # Outlook Calendar Link
                start_outlook = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
                end_outlook = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
                outlook_cal_url = (
                    f"https://outlook.live.com/calendar/0/deeplink/compose?"
                    f"subject={title}"
                    f"&startdt={start_outlook}"
                    f"&enddt={end_outlook}"
                    f"&body={description}"
                    f"&location={location}"
                )
                
                # Yahoo Calendar Link
                start_yahoo = start_dt.strftime("%Y%m%dT%H%M%SZ")
                end_yahoo = end_dt.strftime("%Y%m%dT%H%M%SZ")
                yahoo_cal_url = (
                    f"https://calendar.yahoo.com/?v=60&view=d&type=20"
                    f"&title={title}"
                    f"&st={start_yahoo}"
                    f"&dur={int((end_dt - start_dt).total_seconds() / 60)}"
                    f"&desc={description}"
                    f"&in_loc={location}"
                )
                
                calendar_links = {
                    "google": google_cal_url,
                    "outlook": outlook_cal_url,
                    "yahoo": yahoo_cal_url,
                    "ics": f"{BASE_URL}/public/booking/{booking['id']}/calendar.ics?token={token}",
                }
            except Exception as e:
                app.logger.exception("Error generating calendar links: %r", e)
                calendar_links = None
        
        return render_template(
            "buchung_erfolg.html",
            booking=booking,
            slot=slot,
            provider=provider,
            bereits_bestaetigt=already_confirmed,
            frontend_url=FRONTEND_URL,
            base_url=BASE_URL,  # Backend-URL für Kalender-Download
            booking_token=token,  # Token für Kalender-Download
            calendar_links=calendar_links,  # Kalender-Links
        )
    except Exception:
        app.logger.exception("public_confirm failed")
        return jsonify({"error": "server_error"}), 500


@app.get("/public/booking/<booking_id>/calendar.ics")
def public_booking_calendar(booking_id):
    """Generiert eine .ics Datei für den gebuchten Termin."""
    token = request.args.get("token")
    verified_booking_id = _verify_booking_token(token) if token else None
    
    if not verified_booking_id or str(verified_booking_id) != str(booking_id):
        return _json_error("invalid_token", 400)
    
    try:
        with Session(engine) as s:
            b = s.get(Booking, booking_id)
            if not b:
                return _json_error("not_found", 404)
            
            slot_obj = s.get(Slot, b.slot_id) if b.slot_id else None
            provider_obj = s.get(Provider, slot_obj.provider_id) if slot_obj else None
            
            if not slot_obj:
                return _json_error("slot_missing", 404)
            
            # Datum/Zeit konvertieren (DB speichert UTC-naive)
            start_dt = _as_utc_aware(slot_obj.start_at)
            end_dt = _as_utc_aware(slot_obj.end_at)
            
            # iCalendar Format (RFC 5545)
            # Datum/Zeit im UTC-Format für .ics
            start_utc = start_dt.strftime("%Y%m%dT%H%M%SZ")
            end_utc = end_dt.strftime("%Y%m%dT%H%M%SZ")
            created_utc = _now().strftime("%Y%m%dT%H%M%SZ")
            
            # Titel und Beschreibung
            title = slot_obj.title or "Termin"
            description = f"Termin: {title}\n"
            if slot_obj.category:
                description += f"Kategorie: {slot_obj.category}\n"
            if provider_obj and provider_obj.company_name:
                description += f"Anbieter: {provider_obj.company_name}\n"
            if slot_obj.notes:
                description += f"Hinweise: {slot_obj.notes}\n"
            
            # Ort
            location = ""
            if slot_obj.location:
                location = slot_obj.location
            elif slot_obj.street or slot_obj.zip or slot_obj.city:
                parts = []
                if slot_obj.street:
                    parts.append(slot_obj.street)
                if slot_obj.house_number:
                    parts.append(slot_obj.house_number)
                if slot_obj.zip:
                    parts.append(slot_obj.zip)
                if slot_obj.city:
                    parts.append(slot_obj.city)
                location = ", ".join(parts)
            elif provider_obj:
                parts = []
                if provider_obj.street:
                    parts.append(provider_obj.street)
                if provider_obj.zip:
                    parts.append(provider_obj.zip)
                if provider_obj.city:
                    parts.append(provider_obj.city)
                location = ", ".join(parts)
            
            # UID für den Termin (eindeutig)
            uid = f"booking-{booking_id}@terminmarktplatz.de"
            
            # .ics Datei generieren (RFC 5545)
            # Escape-Spezialzeichen für iCalendar
            def escape_ical_text(text):
                if not text:
                    return ""
                # iCalendar-Escape-Regeln
                text = str(text).replace("\\", "\\\\")
                text = text.replace(",", "\\,")
                text = text.replace(";", "\\;")
                text = text.replace("\n", "\\n")
                return text
            
            # Zeilenenden müssen CRLF sein (\r\n)
            lines = [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Terminmarktplatz//Terminbuchung//DE",
                "CALSCALE:GREGORIAN",
                "METHOD:PUBLISH",
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{created_utc}",
                f"DTSTART:{start_utc}",
                f"DTEND:{end_utc}",
                f"SUMMARY:{escape_ical_text(title)}",
                f"DESCRIPTION:{escape_ical_text(description)}",
                f"LOCATION:{escape_ical_text(location)}",
                "STATUS:CONFIRMED",
                "SEQUENCE:0",
                "END:VEVENT",
                "END:VCALENDAR"
            ]
            
            ics_content = "\r\n".join(lines)
            
            response = make_response(ics_content)
            response.headers['Content-Type'] = 'text/calendar; charset=utf-8'
            response.headers['Content-Disposition'] = f'inline; filename="termin-{booking_id[:8]}.ics"'
            return response
            
    except Exception as e:
        app.logger.exception("public_booking_calendar failed")
        return _json_error("server_error", 500)


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
                slot_address = slot_obj.public_address() if hasattr(slot_obj, 'public_address') else (slot_obj.location or "")
                price_euro_str = None
                if slot_obj.price_cents:
                    price_euro = float(slot_obj.price_cents) / 100
                    price_euro_str = f"{price_euro:.2f}"
                slot = {
                    "id": slot_obj.id,
                    "title": slot_obj.title,
                    "category": slot_obj.category,
                    "start_at": slot_obj.start_at,
                    "end_at": slot_obj.end_at,
                    "location": slot_obj.location,
                    "street": slot_obj.street,
                    "house_number": slot_obj.house_number,
                    "zip": slot_obj.zip,
                    "city": slot_obj.city,
                    "address": slot_address,
                    "price_cents": slot_obj.price_cents,
                    "price_euro": price_euro_str,
                    "notes": slot_obj.notes,
                }

            provider = None
            if provider_obj is not None:
                provider = {
                    "company_name": provider_obj.company_name,
                    "zip": provider_obj.zip,
                    "city": provider_obj.city,
                    "street": provider_obj.street,
                }

        if just_canceled:
            try:
                if customer_email:
                    # Slot-Details für E-Mail formatieren
                    slot_detail_lines = []
                    if slot_obj:
                        slot_start_local = _as_utc_aware(slot_obj.start_at).astimezone(BERLIN)
                        slot_end_local = _as_utc_aware(slot_obj.end_at).astimezone(BERLIN)
                        start_str = slot_start_local.strftime("%d.%m.%Y %H:%M")
                        end_str = slot_end_local.strftime("%H:%M")
                        
                        slot_detail_lines.append(f"Termin: {slot_obj.title}")
                        if slot_obj.category:
                            slot_detail_lines.append(f"Kategorie: {slot_obj.category}")
                        slot_detail_lines.append(f"Datum & Zeit: {start_str} - {end_str} Uhr")
                        
                        slot_address = slot_obj.public_address() if hasattr(slot_obj, 'public_address') else (slot_obj.location or "")
                        if not slot_address and provider_obj:
                            provider_address = f"{provider_obj.zip or ''} {provider_obj.city or ''}".strip()
                            if provider_obj.street:
                                provider_address = f"{provider_obj.street}, {provider_address}".strip()
                            slot_address = provider_address
                        if slot_address:
                            slot_detail_lines.append(f"Ort: {slot_address}")
                        if provider_obj:
                            slot_detail_lines.append(f"Anbieter: {provider_obj.company_name or 'Unbekannt'}")
                        if slot_obj.price_cents:
                            price_euro = float(slot_obj.price_cents) / 100
                            slot_detail_lines.append(f"Preis: {price_euro:.2f} €")
                    
                    body_cust = f"Hallo {customer_name},\n\n"
                    body_cust += f"deine Buchung wurde storniert:\n\n"
                    if slot_detail_lines:
                        body_cust += "\n".join(slot_detail_lines)
                        body_cust += "\n\n"
                    body_cust += "Wenn du möchtest, kannst du einen neuen Termin buchen.\n\n"
                    body_cust += "Viele Grüße\n"
                    body_cust += "Terminmarktplatz"
                    
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
                    # Slot-Details für E-Mail formatieren
                    slot_detail_lines = []
                    if slot_obj:
                        slot_start_local = _as_utc_aware(slot_obj.start_at).astimezone(BERLIN)
                        slot_end_local = _as_utc_aware(slot_obj.end_at).astimezone(BERLIN)
                        start_str = slot_start_local.strftime("%d.%m.%Y %H:%M")
                        end_str = slot_end_local.strftime("%H:%M")
                        
                        slot_detail_lines.append(f"Termin: {slot_obj.title}")
                        if slot_obj.category:
                            slot_detail_lines.append(f"Kategorie: {slot_obj.category}")
                        slot_detail_lines.append(f"Datum & Zeit: {start_str} - {end_str} Uhr")
                        
                        slot_address = slot_obj.public_address() if hasattr(slot_obj, 'public_address') else (slot_obj.location or "")
                        if not slot_address and provider_obj:
                            provider_address = f"{provider_obj.zip or ''} {provider_obj.city or ''}".strip()
                            if provider_obj.street:
                                provider_address = f"{provider_obj.street}, {provider_address}".strip()
                            slot_address = provider_address
                        if slot_address:
                            slot_detail_lines.append(f"Ort: {slot_address}")
                        if slot_obj.price_cents:
                            price_euro = float(slot_obj.price_cents) / 100
                            slot_detail_lines.append(f"Preis: {price_euro:.2f} €")
                    
                    body_prov = f"Hallo {provider_name},\n\n"
                    body_prov += f"die Buchung von {customer_name} wurde storniert:\n\n"
                    if slot_detail_lines:
                        body_prov += "\n".join(slot_detail_lines)
                        body_prov += "\n\n"
                    body_prov += "Viele Grüße\n"
                    body_prov += "Terminmarktplatz"
                    
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
