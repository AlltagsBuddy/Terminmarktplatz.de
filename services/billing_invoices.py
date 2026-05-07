"""Monatsabrechnung (Invoices), PDF-Erstellung und Versand — ohne Flask-request."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Booking, Invoice, Provider, Slot
from utils.time_geo import _now, _to_db_utc_naive

logger = logging.getLogger(__name__)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    A4 = cm = colors = SimpleDocTemplate = Table = TableStyle = Paragraph = Spacer = None  # type: ignore
    getSampleStyleSheet = ParagraphStyle = TA_LEFT = None  # type: ignore


def create_invoices_for_period(session: Session, year: int, month: int) -> dict:
    """
    Erzeugt Sammelrechnungen für alle bestätigten Buchungen (status='confirmed')
    eines Monats, deren fee_status='open' ist.
    """
    period_start_dt = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        next_month_dt = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month_dt = datetime(year, month + 1, 1, 1, 0, 0, tzinfo=timezone.utc)

    start_db = _to_db_utc_naive(period_start_dt)
    end_db = _to_db_utc_naive(next_month_dt)

    bookings = (
        session.execute(
            select(Booking).where(
                Booking.status == "confirmed",
                Booking.fee_status == "open",
                Booking.created_at >= start_db,
                Booking.created_at < end_db,
            )
        )
        .scalars()
        .all()
    )

    by_provider: dict[str, list[Booking]] = {}
    for b in bookings:
        by_provider.setdefault(b.provider_id, []).append(b)

    invoices_summary = []

    for provider_id, blist in by_provider.items():
        total = sum((b.provider_fee_eur or Decimal("0.00")) for b in blist)
        if total <= 0:
            continue

        inv = Invoice(
            provider_id=provider_id,
            period_start=period_start_dt.date(),
            period_end=(next_month_dt - timedelta(days=1)).date(),
            total_eur=total,
            status="open",
        )
        session.add(inv)
        session.flush()

        now = _now()
        for b in blist:
            b.invoice_id = inv.id
            b.fee_status = "invoiced"
            b.is_billed = True
            b.billed_at = now

        invoices_summary.append(
            {
                "provider_id": provider_id,
                "invoice_id": inv.id,
                "booking_count": len(blist),
                "total_eur": float(total),
            }
        )

    return {
        "period": {"year": year, "month": month},
        "invoices_created": len(invoices_summary),
        "items": invoices_summary,
    }


def generate_invoice_pdf(
    invoice: Invoice,
    provider: Provider,
    bookings: list[Booking],
    session: Session | None = None,
) -> bytes:
    """Generiert ein PDF für eine Rechnung."""
    if not REPORTLAB_AVAILABLE:
        raise Exception("reportlab nicht installiert")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=30,
        alignment=TA_LEFT,
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#334155"),
        spaceAfter=12,
        alignment=TA_LEFT,
    )

    normal_style = styles["Normal"]
    normal_style.fontSize = 10
    normal_style.textColor = colors.HexColor("#475569")

    story.append(Paragraph("Terminmarktplatz", title_style))
    story.append(Paragraph("Rechnung", heading_style))
    story.append(Spacer(1, 0.5 * cm))

    invoice_data = [
        ["Rechnungsnummer:", invoice.id[:8].upper()],
        ["Rechnungsdatum:", invoice.created_at.strftime("%d.%m.%Y") if invoice.created_at else "-"],
        ["Zeitraum:", f"{invoice.period_start.strftime('%d.%m.%Y')} - {invoice.period_end.strftime('%d.%m.%Y')}"],
        ["Status:", invoice.status],
    ]

    invoice_table = Table(invoice_data, colWidths=[5 * cm, 10 * cm])
    invoice_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1e293b")),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(invoice_table)
    story.append(Spacer(1, 0.8 * cm))

    story.append(Paragraph("Anbieter", heading_style))
    provider_info = []
    if provider.provider_number:
        provider_info.append(["Anbieter-Nr.:", str(provider.provider_number)])
    if provider.company_name:
        provider_info.append(["Firma:", provider.company_name])
    provider_info.append(["E-Mail:", provider.email])
    if provider.street:
        provider_info.append(["Straße:", provider.street])
    if provider.zip and provider.city:
        provider_info.append(["PLZ/Ort:", f"{provider.zip} {provider.city}"])

    provider_table = Table(provider_info, colWidths=[5 * cm, 10 * cm])
    provider_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1e293b")),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(provider_table)
    story.append(Spacer(1, 0.8 * cm))

    story.append(Paragraph("Buchungsdetails", heading_style))
    booking_data = [["Datum", "Termin", "Kunde", "Betrag"]]

    for b in bookings:
        slot_title = "Termin"
        if session and hasattr(b, "slot_id") and b.slot_id:
            slot = session.get(Slot, b.slot_id)
            if slot:
                slot_title = slot.title or "Termin"

        booking_date = b.created_at.strftime("%d.%m.%Y") if b.created_at else "-"
        customer = (
            b.customer_name
            or (
                b.customer_email[:30] + "..."
                if b.customer_email and len(b.customer_email) > 30
                else b.customer_email
            )
            or "N/A"
        )
        amount = f"{float(b.provider_fee_eur):.2f} €"
        booking_data.append([booking_date, slot_title[:40], customer[:40], amount])

    booking_data.append(["", "", "Gesamtbetrag:", f"{float(invoice.total_eur):.2f} €"])

    booking_table = Table(booking_data, colWidths=[3.5 * cm, 5 * cm, 4 * cm, 2.5 * cm])
    booking_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("TOPPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -2), colors.white),
                ("TEXTCOLOR", (0, 1), (-1, -2), colors.HexColor("#475569")),
                ("FONTNAME", (0, 1), (-1, -2), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -2), 9),
                ("GRID", (0, 0), (-1, -2), 1, colors.HexColor("#e2e8f0")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f8fafc")),
                ("FONTNAME", (0, -1), (-2, -1), "Helvetica"),
                ("FONTNAME", (-1, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, -1), (-1, -1), 10),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#1e293b")),
                ("TOPPADDING", (0, -1), (-1, -1), 10),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
            ]
        )
    )
    story.append(booking_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def send_invoice_email(
    invoice: Invoice,
    provider: Provider,
    bookings: list[Booking],
    session: Session | None = None,
) -> tuple[bool, str]:
    """Sendet eine Rechnung per E-Mail mit PDF-Anhang (SMTP) oder Link-Fallback."""
    import app as app_module

    try:
        if not REPORTLAB_AVAILABLE:
            return False, "reportlab nicht installiert"

        pdf_bytes = generate_invoice_pdf(invoice, provider, bookings, session)
        filename = f"Rechnung_{invoice.id[:8].upper()}_{invoice.period_start.strftime('%Y%m')}.pdf"

        subject = f"Rechnung {invoice.id[:8].upper()} - {invoice.period_start.strftime('%B %Y')}"
        text_body = f"""Hallo {provider.company_name or 'Anbieter/in'},

anbei erhalten Sie Ihre Rechnung für den Zeitraum {invoice.period_start.strftime('%d.%m.%Y')} bis {invoice.period_end.strftime('%d.%m.%Y')}.

Rechnungsnummer: {invoice.id[:8].upper()}
Rechnungsdatum: {invoice.created_at.strftime('%d.%m.%Y') if invoice.created_at else '-'}
Betrag: {float(invoice.total_eur):.2f} €

Das PDF finden Sie im Anhang dieser E-Mail.

Bei Fragen stehen wir Ihnen gerne zur Verfügung.

Viele Grüße
Terminmarktplatz
"""

        if app_module.MAIL_PROVIDER == "smtp":
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.base import MIMEBase
            from email import encoders

            if (
                not app_module.SMTP_USER
                or not app_module.SMTP_PASS
                or not app_module.SMTP_HOST
            ):
                return False, "SMTP nicht konfiguriert"

            msg = MIMEMultipart()
            msg["From"] = app_module.MAIL_FROM or app_module.SMTP_USER
            msg["To"] = provider.email
            msg["Subject"] = subject
            if app_module.MAIL_REPLY_TO:
                msg["Reply-To"] = app_module.MAIL_REPLY_TO

            msg.attach(MIMEText(text_body, "plain", "utf-8"))

            attachment = MIMEBase("application", "pdf")
            attachment.set_payload(pdf_bytes)
            encoders.encode_base64(attachment)
            attachment.add_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
            msg.attach(attachment)

            try:
                if app_module.SMTP_USE_TLS:
                    with smtplib.SMTP(
                        app_module.SMTP_HOST, app_module.SMTP_PORT, timeout=20
                    ) as smtp:
                        smtp.starttls()
                        smtp.login(app_module.SMTP_USER, app_module.SMTP_PASS)
                        smtp.send_message(msg, from_addr=app_module.SMTP_USER)
                else:
                    with smtplib.SMTP_SSL(
                        app_module.SMTP_HOST, app_module.SMTP_PORT, timeout=20
                    ) as smtp:
                        smtp.login(app_module.SMTP_USER, app_module.SMTP_PASS)
                        smtp.send_message(msg, from_addr=app_module.SMTP_USER)
                return True, "smtp"
            except Exception as e:
                logger.exception("SMTP send_invoice_email failed")
                return False, str(e)
        else:
            app_module.send_mail(
                provider.email,
                subject,
                text=text_body
                + f"\n\nPDF-Download: {app_module.BASE_URL}/admin/invoices/{invoice.id}/pdf",
                tag="invoice",
                metadata={"invoice_id": invoice.id},
            )
            return True, "sent_without_attachment"

    except Exception as e:
        logger.exception("send_invoice_email failed")
        return False, str(e)
