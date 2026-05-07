"""UTC-/Zeitzonen-Hilfen und einfache Geo-Distanz."""

from __future__ import annotations

from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Backport nur bei sehr alter Python-Version
    from backports.zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


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


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    from math import atan2, cos, radians, sin, sqrt

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
