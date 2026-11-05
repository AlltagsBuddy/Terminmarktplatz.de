import os

# Wirkt vor allen API-Tests, die ``app`` importieren: Mail-Stubs & konsistentes TESTING.
os.environ.setdefault("TESTING", "1")

import pytest


# ---------------------------------------------------------------------------
# DATENSICHERHEIT: Schutz vor versehentlichem Loeschen produktiver Datenbanken.
#
# Viele API-Tests rufen ``Base.metadata.drop_all(engine)`` in ihren Fixtures auf.
# Laeuft die Test-Suite versehentlich gegen eine echte PostgreSQL-DB
# (``terminmarktplatz`` = Produktion oder ``terminmarktplatz_test`` = Live-DB von
# test.terminmarktplatz.de), wuerde das ALLE Tabellen samt Kundendaten loeschen.
#
# Dieser Guard patcht ``MetaData.drop_all`` global und bricht VOR dem Loeschen
# mit klarer Meldung ab, sobald das Ziel eine geschuetzte PostgreSQL-DB ist.
# SQLite (CI/lokal) und eine dedizierte Test-DB (z. B. ``terminmarktplatz_pytest``)
# sind weiterhin erlaubt.
# Opt-out nur bewusst ueber ENV ``ALLOW_DESTRUCTIVE_DB_TESTS=1``.
# ---------------------------------------------------------------------------
_PROTECTED_PG_DATABASES = {"terminmarktplatz", "terminmarktplatz_test"}


def _install_drop_all_guard() -> None:
    try:
        from sqlalchemy.sql.schema import MetaData
    except Exception:
        return
    if getattr(MetaData, "_tmp_drop_all_guarded", False):
        return
    _orig_drop_all = MetaData.drop_all

    def _guarded_drop_all(self, bind=None, *args, **kwargs):
        if os.getenv("ALLOW_DESTRUCTIVE_DB_TESTS") != "1":
            engine = bind if bind is not None else kwargs.get("bind")
            url = getattr(engine, "url", None)
            backend = getattr(url, "drivername", "") or ""
            dbname = getattr(url, "database", None)
            if backend.startswith("postgresql") and dbname in _PROTECTED_PG_DATABASES:
                raise RuntimeError(
                    "SICHERHEITS-STOPP: drop_all() gegen geschuetzte PostgreSQL-DB "
                    f"'{dbname}' blockiert (enthaelt echte Daten). "
                    "Tests gegen SQLite oder eine dedizierte Test-DB "
                    "(z. B. terminmarktplatz_pytest) ausfuehren. "
                    "Bewusstes Ueberschreiben nur mit ALLOW_DESTRUCTIVE_DB_TESTS=1."
                )
        return _orig_drop_all(self, bind, *args, **kwargs)

    MetaData.drop_all = _guarded_drop_all
    MetaData._tmp_drop_all_guarded = True


_install_drop_all_guard()


def _get_base_url() -> str:
    # TEST_BASE_URL hat Vorrang (z. B. http://127.0.0.1:5000 für lokale UI-Tests)
    preferred = os.getenv("TEST_BASE_URL") or os.getenv("BASE_URL")
    if preferred:
        return preferred.rstrip("/")
    return "https://testsystem-terminmarktplatz-de.onrender.com"


@pytest.fixture(scope="session")
def app_base_url() -> str:
    return _get_base_url()
