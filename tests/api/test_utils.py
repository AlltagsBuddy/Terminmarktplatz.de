import os
import tempfile
from datetime import datetime, timezone

import pytest


_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")

import app as app_module
from models import Provider


def test_parse_iso_utc():
    dt = app_module.parse_iso_utc("2026-01-01T10:00:00Z")
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timezone.utc.utcoffset(dt)

    dt2 = app_module.parse_iso_utc("2026-01-01T10:00:00+01:00")
    assert dt2.tzinfo is not None

    dt3 = app_module.parse_iso_utc("2026-01-01T10:00:00")
    assert dt3.tzinfo is not None


def test_normalize_zip():
    assert app_module.normalize_zip("96191 Viereth") == "96191"
    assert app_module.normalize_zip("12-345") == "12345"
    assert app_module.normalize_zip("") == ""


def test_split_street_and_number():
    street, num = app_module.split_street_and_number("Musterstrasse 12a")
    assert street == "Musterstrasse"
    assert num == "12a"

    street2, num2 = app_module.split_street_and_number("OhneNummer")
    assert street2 == "OhneNummer"
    assert num2 == ""


def test_is_profile_complete():
    p = Provider(
        email="pc@example.com",
        pw_hash="x",
        company_name="Firma",
        branch="Friseur",
        street="Teststrasse 1",
        zip="12345",
        city="Teststadt",
        phone="1234567",
    )
    assert app_module.is_profile_complete(p) is True

    p.phone = ""
    assert app_module.is_profile_complete(p) is False
