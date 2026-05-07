"""JWT: Access-/Refresh-Tokens und kontextlose Buchungs-/Review-/Kalender-Tokens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import jwt

from utils.time_geo import _now

REVIEW_TOKEN_TTL_DAYS = 120
PROVIDER_CALENDAR_TOKEN_TTL_DAYS = 365


@dataclass(frozen=True)
class JWTSettings:
    secret: str
    issuer: str
    audience: str
    access_exp_minutes: int
    refresh_exp_days: int


_settings: JWTSettings | None = None


def configure_jwt(settings: JWTSettings) -> None:
    global _settings
    _settings = settings


def _require_settings() -> JWTSettings:
    if _settings is None:
        raise RuntimeError("JWT not configured: call configure_jwt() first")
    return _settings


def issue_tokens(provider_id: str, is_admin: bool) -> tuple[str, str]:
    cfg = _require_settings()
    now = _now()
    access = jwt.encode(
        {
            "sub": provider_id,
            "adm": is_admin,
            "iss": cfg.issuer,
            "aud": cfg.audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=cfg.access_exp_minutes)).timestamp()),
        },
        cfg.secret,
        algorithm="HS256",
    )
    refresh = jwt.encode(
        {
            "sub": provider_id,
            "iss": cfg.issuer,
            "aud": cfg.audience,
            "typ": "refresh",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=cfg.refresh_exp_days)).timestamp()),
        },
        cfg.secret,
        algorithm="HS256",
    )
    return access, refresh


def decode_access_token_subject(access_token: str | None) -> str | None:
    """Nur Access-Token (mit Audience); kein Refresh-Fallback."""
    if not access_token:
        return None
    cfg = _require_settings()
    try:
        data = jwt.decode(
            access_token,
            cfg.secret,
            algorithms=["HS256"],
            audience=cfg.audience,
            issuer=cfg.issuer,
        )
    except Exception:
        return None
    return data.get("sub")


def booking_token(booking_id: str) -> str:
    cfg = _require_settings()
    return jwt.encode(
        {
            "sub": booking_id,
            "typ": "booking",
            "iss": cfg.issuer,
            "exp": int((_now() + timedelta(hours=6)).timestamp()),
        },
        cfg.secret,
        algorithm="HS256",
    )


def verify_booking_token(token: str) -> str | None:
    cfg = _require_settings()
    try:
        data = jwt.decode(token, cfg.secret, algorithms=["HS256"], issuer=cfg.issuer)
        return data.get("sub") if data.get("typ") == "booking" else None
    except Exception:
        return None


def review_token(booking_id: str) -> str:
    cfg = _require_settings()
    return jwt.encode(
        {
            "sub": booking_id,
            "typ": "review",
            "iss": cfg.issuer,
            "exp": int((_now() + timedelta(days=REVIEW_TOKEN_TTL_DAYS)).timestamp()),
        },
        cfg.secret,
        algorithm="HS256",
    )


def verify_review_token(token: str) -> str | None:
    cfg = _require_settings()
    try:
        data = jwt.decode(token, cfg.secret, algorithms=["HS256"], issuer=cfg.issuer)
        return data.get("sub") if data.get("typ") == "review" else None
    except Exception:
        return None


def provider_calendar_token(provider_id: str) -> str:
    cfg = _require_settings()
    return jwt.encode(
        {
            "sub": provider_id,
            "typ": "provider_calendar",
            "iss": cfg.issuer,
            "exp": int((_now() + timedelta(days=PROVIDER_CALENDAR_TOKEN_TTL_DAYS)).timestamp()),
        },
        cfg.secret,
        algorithm="HS256",
    )


def verify_provider_calendar_token(token: str) -> str | None:
    cfg = _require_settings()
    try:
        data = jwt.decode(token, cfg.secret, algorithms=["HS256"], issuer=cfg.issuer)
        return data.get("sub") if data.get("typ") == "provider_calendar" else None
    except Exception:
        return None
