"""Öffentliche Buchungs-Endpunkte (/public/*)."""

from __future__ import annotations

from flask import Blueprint

bp = Blueprint("public_booking", __name__, url_prefix="/public")


def _app():
    import app as application  # noqa: PLC0415

    return application


@bp.get("/slots")
def public_slots():
    return _app().public_slots_view()


@bp.post("/book")
def public_book():
    return _app().public_book_view()


@bp.get("/confirm")
def public_confirm():
    return _app().public_confirm_view()


@bp.get("/booking/<booking_id>/calendar.ics")
def public_booking_calendar(booking_id: str):
    return _app().public_booking_calendar_view(booking_id)


@bp.get("/provider/<provider_id>/calendar.ics")
def public_provider_calendar(provider_id: str):
    return _app().public_provider_calendar_view(provider_id)


@bp.get("/cancel")
def public_cancel():
    return _app().public_cancel_view()
