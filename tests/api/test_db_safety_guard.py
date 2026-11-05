"""
Datensicherheits-Guard: ``drop_all`` darf niemals gegen die produktive DB
(``terminmarktplatz``) oder die Live-Test-DB (``terminmarktplatz_test``) laufen.

Diese Tests beruehren KEINE echten Datenbanken: Bei geschuetzten Namen greift der
Guard VOR jedem Verbindungsaufbau; bei nicht-geschuetzten Namen wird lediglich ein
(harmloser) Verbindungsfehler gegen Fake-Zugangsdaten toleriert.
"""
import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine


def _fake_pg_engine(dbname: str):
    # create_engine ist lazy -> ohne drop_all wird nichts verbunden.
    return create_engine(f"postgresql+psycopg://u:x@localhost:5432/{dbname}")


def test_drop_all_blocked_on_live_test_db():
    md = MetaData()
    Table("t_guard_a", md, Column("id", Integer, primary_key=True))
    eng = _fake_pg_engine("terminmarktplatz_test")
    with pytest.raises(RuntimeError, match="SICHERHEITS-STOPP"):
        md.drop_all(eng)


def test_drop_all_blocked_on_production_db():
    md = MetaData()
    Table("t_guard_b", md, Column("id", Integer, primary_key=True))
    eng = _fake_pg_engine("terminmarktplatz")
    with pytest.raises(RuntimeError, match="SICHERHEITS-STOPP"):
        md.drop_all(eng)


def test_drop_all_allowed_on_sqlite():
    md = MetaData()
    Table("t_guard_c", md, Column("id", Integer, primary_key=True))
    eng = create_engine("sqlite://")
    md.create_all(eng)
    md.drop_all(eng)  # darf NICHT blockiert werden


def test_guard_does_not_block_dedicated_test_db():
    """Nicht-geschuetzte DB-Namen (z. B. terminmarktplatz_pytest) sind erlaubt."""
    md = MetaData()
    Table("t_guard_d", md, Column("id", Integer, primary_key=True))
    eng = _fake_pg_engine("terminmarktplatz_pytest")
    try:
        md.drop_all(eng)
    except RuntimeError as e:
        if "SICHERHEITS-STOPP" in str(e):
            pytest.fail("Guard darf nicht-geschuetzte DB nicht blockieren")
    except Exception:
        pass  # Verbindungsfehler gegen Fake-DB ist erwartet und ok


def test_optout_env_disables_guard(monkeypatch):
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_DB_TESTS", "1")
    md = MetaData()
    Table("t_guard_e", md, Column("id", Integer, primary_key=True))
    eng = _fake_pg_engine("terminmarktplatz_test")
    try:
        md.drop_all(eng)
    except RuntimeError as e:
        if "SICHERHEITS-STOPP" in str(e):
            pytest.fail("Opt-out ENV ALLOW_DESTRUCTIVE_DB_TESTS=1 sollte Guard deaktivieren")
    except Exception:
        pass  # Verbindungsfehler gegen Fake-DB ist erwartet und ok
