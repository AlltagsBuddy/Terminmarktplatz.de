"""Admin-API unter /admin."""

from __future__ import annotations

from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _app():
    import app as application  # noqa: PLC0415

    return application


@admin_bp.get("/providers")
def admin_providers():
    return _app().auth_required(admin=True)(_app().admin_providers_view)()


@admin_bp.post("/providers/<pid>/approve")
def admin_provider_approve(pid: str):
    return _app().auth_required(admin=True)(_app().admin_provider_approve_view)(pid)


@admin_bp.post("/providers/<pid>/reject")
def admin_provider_reject(pid: str):
    return _app().auth_required(admin=True)(_app().admin_provider_reject_view)(pid)


@admin_bp.get("/slots")
def admin_slots():
    return _app().auth_required(admin=True)(_app().admin_slots_view)()


@admin_bp.post("/slots/<sid>/publish")
def admin_slot_publish(sid: str):
    return _app().auth_required(admin=True)(_app().admin_slot_publish_view)(sid)


@admin_bp.post("/slots/<sid>/reject")
def admin_slot_reject(sid: str):
    return _app().auth_required(admin=True)(_app().admin_slot_reject_view)(sid)


@admin_bp.get("/billing_overview")
def admin_billing_overview():
    return _app().auth_required(admin=True)(_app().admin_billing_overview_view)()


@admin_bp.post("/run_billing")
def admin_run_billing():
    return _app().auth_required(admin=True)(_app().admin_run_billing_view)()


@admin_bp.get("/invoices/all")
def admin_invoices_all():
    return _app().auth_required(admin=True)(_app().admin_invoices_all_view)()


@admin_bp.get("/debug/provider-numbers")
def debug_provider_numbers():
    return _app().auth_required(admin=True)(_app().debug_provider_numbers_view)()


@admin_bp.post("/debug/run-provider-number-migration")
def run_provider_number_migration():
    return _app().auth_required(admin=True)(_app().run_provider_number_migration_view)()


@admin_bp.get("/debug/invoices")
def debug_invoices():
    return _app().auth_required(admin=True)(_app().debug_invoices_view)()


@admin_bp.get("/invoices/<invoice_id>")
def admin_invoice_detail(invoice_id: str):
    return _app().auth_required(admin=True)(_app().admin_invoice_detail_view)(invoice_id)


@admin_bp.get("/invoices/<invoice_id>/pdf")
def admin_invoice_pdf(invoice_id: str):
    return _app().auth_required(admin=True)(_app().admin_invoice_pdf_view)(invoice_id)


@admin_bp.post("/invoices/<invoice_id>/send-email")
def admin_invoice_send_email(invoice_id: str):
    return _app().auth_required(admin=True)(_app().admin_invoice_send_email_view)(invoice_id)
