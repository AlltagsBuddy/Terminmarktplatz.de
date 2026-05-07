"""Alerts API unter /api/alerts sowie /alerts/verify und /alerts/cancel."""

from __future__ import annotations

import re
from urllib.parse import unquote

from flask import Blueprint, request

alerts_api_bp = Blueprint("alerts_api", __name__, url_prefix="/api/alerts")
alerts_public_bp = Blueprint("alerts_public", __name__, url_prefix="/alerts")


def _norm_token(t: str | None) -> str:
    t = unquote((t or "")).strip()
    t = re.sub(r"\s+", "", t)
    return t


def _app():
    import app as application  # noqa: PLC0415

    return application


@alerts_api_bp.get("/stats")
def alert_stats():
    return _app().alert_stats_view()


@alerts_api_bp.get("/debug/by_zip")
def debug_alerts_by_zip():
    return _app().debug_alerts_by_zip_view()


@alerts_api_bp.get("/debug/raw_by_zip")
def debug_raw_by_zip():
    return _app().debug_raw_by_zip_view()


@alerts_api_bp.get("/debug/active_confirmed_by_zip")
def debug_active_confirmed_by_zip():
    return _app().debug_active_confirmed_by_zip_view()


@alerts_api_bp.post("")
def create_alert():
    return _app().create_alert_view()


@alerts_api_bp.get("/debug/token")
def debug_alert_by_token():
    return _app().debug_alert_by_token_view(_norm_token(request.args.get("t")))


@alerts_public_bp.get("/verify/<path:token>")
def alerts_verify(token: str):
    return _app().alerts_verify_view(_norm_token(token))


@alerts_public_bp.get("/cancel/<path:token>")
def alerts_cancel(token: str):
    return _app().alerts_cancel_view(_norm_token(token))
