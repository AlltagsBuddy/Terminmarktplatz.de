"""Stripe-, CopeCart- und WareVision-Webhooks (/webhook/*)."""

from __future__ import annotations

from flask import Blueprint

bp = Blueprint("webhooks", __name__, url_prefix="/webhook")


def _app():
    import app as application  # noqa: PLC0415 — Modul ist nach bind/register initialisiert

    return application


@bp.route("/stripe", methods=["GET", "POST"])
def stripe_webhook():
    return _app().stripe_webhook_view()


@bp.post("/copecart")
def copecart_webhook():
    return _app().copecart_webhook_view()


@bp.post("/warevision")
def webhook_warevision():
    return _app().webhook_warevision_view()
