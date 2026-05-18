#!/usr/bin/env python3
"""
Migriert lokale Anbieter-Logos (logo_url beginnt mit ``/static/``) nach Hetzner Object Storage.

Voraussetzung: ``HETZNER_*`` Variablen in ``.env`` wie bei der laufenden App.

Ausführung vom Projektroot::

    python scripts/migrate_logos_to_storage.py

Exit-Codes: 0 bei Erfolg, 1 bei Konfigurations- oder schwerwiegenden Fehlern.
"""
from __future__ import annotations

import io
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

    import app as app_module
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from models import Provider
    from services.storage import configure_storage, hetzner_object_storage_available, upload_logo

    configure_storage()
    if not hetzner_object_storage_available():
        print(
            "[migrate-logos] Hetzner Object Storage nicht konfiguriert "
            "(HETZNER_ACCESS_KEY / SECRET / BUCKET / ENDPOINT_URL). Abbruch.",
            flush=True,
        )
        return 1

    migrated = 0
    skipped = 0
    errors = 0

    with Session(app_module.engine) as session:
        providers = session.execute(select(Provider).where(Provider.logo_url.isnot(None))).scalars().all()

        for p in providers:
            raw = (p.logo_url or "").strip()
            if not raw.startswith("/static/"):
                skipped += 1
                continue
            clean = raw.split("?", 1)[0].strip()
            local_path: Path | None
            if clean.startswith("/static/uploads/"):
                local_path = Path(app_module.UPLOAD_BASE) / clean[len("/static/uploads/") :].lstrip("/")
            else:
                local_path = Path(app_module.STATIC_DIR) / clean[len("/static/") :].lstrip("/")

            if not local_path.is_file():
                print(f"[migrate-logos] überspringe {p.id}: Datei fehlt {local_path}", flush=True)
                errors += 1
                continue

            object_key = f"provider-logos/{local_path.name}"
            try:
                data = local_path.read_bytes()
                buf = io.BytesIO(data)
                public_url = upload_logo(buf, object_key)
            except Exception as e:
                print(f"[migrate-logos] Fehler bei Provider {p.id}: {e!r}", flush=True)
                errors += 1
                continue

            p.logo_url = public_url
            session.commit()
            migrated += 1
            print(f"[migrate-logos] OK {p.id} -> {public_url}", flush=True)

    print(f"[migrate-logos] fertig: migrated={migrated}, skipped={skipped}, errors={errors}", flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
