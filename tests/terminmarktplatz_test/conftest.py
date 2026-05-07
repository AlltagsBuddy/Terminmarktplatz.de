"""
pytest fixtures für die Postgres-Test-DB „terminmarktplatz_test“.

Wichtig: Dieses Paket soll **isoliert** ausgeführt werden (die Flask-App wird nur einmal
mit dieser DATABASE_URL geladen):

    pytest tests/terminmarktplatz_test -q

Überschreiben der DB-URL:

    set TEST_DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/terminmarktplatz_test
    pytest tests/terminmarktplatz_test -q

Mit anderen Suites kombiniert (z. B. gesamt „pytest tests/“) kann „app“ bereits mit SQLite
importiert sein — dann werden diese Tests mit Hinweis übersprungen.
"""

from __future__ import annotations

import os
import sys

import pytest
from sqlalchemy import text


DEFAULT_TERMINMARKTPLATZ_TEST_DB = (
    "postgresql+psycopg://127.0.0.1:5432/terminmarktplatz_test"
)


@pytest.fixture(scope="session")
def app_module():
    if "app" in sys.modules:
        pytest.skip(
            "terminmarktplatz_test-Suite: App wurde bereits importiert.\n"
            "Separat ausführen: pytest tests/terminmarktplatz_test -q"
        )

    # Immer die Postgres-Test-DB verwenden (nicht eine evtl. gesetzte DATABASE_URL=sqlite aus der Shell).
    db_url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TERMINMARKTPLATZ_TEST_DB)
    os.environ["DATABASE_URL"] = db_url
    os.environ.setdefault("BASE_URL", "http://127.0.0.1:5000")
    os.environ.setdefault("FRONTEND_URL", "http://127.0.0.1:5000")
    os.environ.setdefault("SECRET_KEY", "pytest-secret-key-terminmarktplatz-test")

    # Keine echten Mails / keine Stripe-Zahlungen während dieser Suite
    os.environ.setdefault("EMAILS_ENABLED", "false")
    os.environ.setdefault("MAIL_PROVIDER", "console")
    os.environ["STRIPE_SECRET_KEY"] = ""

    import app as m

    try:
        with m.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Datenbank nicht erreichbar ({db_url[:56]}…): {exc}")

    return m


@pytest.fixture(scope="session", autouse=True)
def prepare_database(app_module):
    """Sauberes Schema auf dedizierter Test-PG (analog andere API-Tests)."""
    from models import Base

    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)


@pytest.fixture(scope="session")
def client(app_module):
    return app_module.app.test_client()
