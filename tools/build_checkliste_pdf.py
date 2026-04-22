"""Erzeugt static/checkliste-no-shows-terminmarktplatz.pdf (einmalig / bei Textänderung)."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "checkliste-no-shows-terminmarktplatz.pdf"

BODY = [
    "Termin <b>unmittelbar</b> nach der Buchung per E-Mail (und optional SMS) bestätigen – inkl. Adresse, Anreise, Storno-Regel.",
    "Erinnerungen <b>24 Stunden</b> vorher standardmäßig; bei hohem Ausfall optional zusätzlich 2 Stunden davor (kurz, freundlich, ggf. mit Kalender-Anhang/ICS).",
    "Kund:innen <b>klar sagen, was passiert</b>, wenn sie nicht erscheinen: Nachverfolgung, Warteliste, ggf. erneute Buchung. Kein Überraschungseffekt.",
    "Eine <b>Warteliste</b> führen und kommunizieren, dass kurzfristig frei werdende Termine sichtbar angeboten werden (z. B. per Terminmarktplatz) – Lücken minimieren statt Tisch leer.",
    "Prozesse <b>in 10 Minuten pro Woche</b> prüfen: Ausfallquote, häufigste Gründe, ob Erinnerung ankommt. Kleine Anpassung, messbarer Effekt.",
]


def build() -> None:
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "T",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        spaceAfter=12,
        textColor=colors.HexColor("#1e293b"),
    )
    sub = ParagraphStyle(
        "S",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceAfter=16,
    )
    item = ParagraphStyle(
        "I",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor("#0f172a"),
        leftIndent=14,
        bulletIndent=6,
    )
    foot = ParagraphStyle(
        "F",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8.5,
        textColor=colors.HexColor("#64748b"),
        spaceBefore=18,
    )

    story: list = [
        Paragraph("5 Wege, No-Shows &amp; Terminlücken zu reduzieren", title),
        Paragraph(
            "Kurz-Checkliste für Dienstleister: umsetzbar mit Kalender, E-Mail und klaren Abläufen – ohne neues Werkzeug nötig.",
            sub,
        ),
    ]

    for t in BODY:
        story.append(Paragraph("•&nbsp;&nbsp;" + t, item))
        story.append(Spacer(1, 0.12 * cm))

    story.append(
        Paragraph(
            "Terminmarktplatz.de · Frei werdende Termine sichtbar machen, Lücken füllen, mit 1-Klick buchen lassen.",
            foot,
        ),
    )

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Checkliste: No-Shows reduzieren",
        author="Terminmarktplatz",
    )
    doc.build(story)
    print(f"OK: {OUT}")


if __name__ == "__main__":
    build()
