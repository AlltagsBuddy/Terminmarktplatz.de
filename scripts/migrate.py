#!/usr/bin/env python3
"""
Manuelle Datenbank-Migrationen (DDL).

Die Flask-App startet KEINE ALTER TABLE / CREATE TABLE Migrationen mehr automatisch,
weil der App-DB-Benutzer in Produktion typischerweise keine DDL-Rechte hat.

Ausführung (einmalig oder nach Deploy, als PostgreSQL-Superuser oder Rolle mit DDL-Recht):

    cd /pfad/zum/projekt
    set DATABASE_URL=postgresql+psycopg2://...
    python scripts/migrate.py

Lokal mit SQLite (.env mit DATABASE_URL) ebenfalls möglich.

Exit-Code 0: alle Schritte durchlaufen (einzelne Warnungen können in der Ausgabe stehen).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
    except ImportError:
        pass

    print(f"[migrate] Arbeitsverzeichnis: {root}", flush=True)
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    if db_url:
        safe = db_url.split("@")[-1] if "@" in db_url else db_url
        print(f"[migrate] DATABASE_URL (host/teil nach @): …@{safe}", flush=True)
    else:
        print("[migrate] Hinweis: DATABASE_URL nicht gesetzt.", flush=True)

    import app as app_module

    print("[migrate] Starte Schema-Migrationen …", flush=True)
    app_module.run_schema_migrations()
    print("[migrate] Fertig.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
