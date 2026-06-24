import os
from datetime import date
from io import BytesIO

from django.conf import settings

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Image, Table, TableStyle


LOGO_PATH = os.path.join(settings.BASE_DIR, 'static', 'medien', 'Logo_Meer_erleben.png')

PRIMARY = colors.HexColor('#1e3a5f')
SECONDARY = colors.HexColor('#0D9488')
AMBER = colors.HexColor('#92400e')
GRAY = colors.HexColor('#9ca3af')
GRAY_LIGHT = colors.HexColor('#d1d5db')
AMBER_GOLD = colors.HexColor('#fcd34d')


def _header_footer(canvas, doc, andacht):
    canvas.saveState()
    w, h = A4
    margin = 2.5 * cm

    # ── Header: Logo links ──────────────────────────────────────
    if os.path.exists(LOGO_PATH):
        logo_h = 1.0 * cm
        canvas.drawImage(
            LOGO_PATH,
            margin,
            h - margin - logo_h + 0.15 * cm,
            height=logo_h,
            preserveAspectRatio=True,
            mask='auto',
        )

    # ── Footer ──────────────────────────────────────────────────
    footer_y = margin - 0.8 * cm
    canvas.setStrokeColor(GRAY_LIGHT)
    canvas.setLineWidth(0.5)
    canvas.line(margin, footer_y + 0.5 * cm, w - margin, footer_y + 0.5 * cm)

    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(GRAY)

    # Links: App-Referenz
    canvas.drawString(
        margin,
        footer_y,
        f'Erstellt mit dem Andachtsgenerator · Meer erleben · undmeererleben.de',
    )

    # Rechts: Datum + Seite
    seite_text = f'{date.today().strftime("%d.%m.%Y")}  |  Seite {canvas.getPageNumber()}'
    canvas.drawRightString(w - margin, footer_y, seite_text)

    canvas.restoreState()


def erstelle_andacht_pdf(andacht):
    buffer = BytesIO()

    # Etwas mehr oben für Logo-Platz
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=3.5 * cm,
        bottomMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()

    titel_style = ParagraphStyle('Titel', parent=styles['Title'], textColor=PRIMARY, fontSize=20, spaceAfter=6)
    untertitel_style = ParagraphStyle('Untertitel', parent=styles['Normal'], textColor=SECONDARY, fontSize=11, spaceAfter=16)
    h2_style = ParagraphStyle('H2', parent=styles['Heading2'], textColor=PRIMARY, fontSize=13, spaceBefore=14, spaceAfter=6)
    h2_amber_style = ParagraphStyle('H2Amber', parent=styles['Heading2'], textColor=AMBER, fontSize=12, spaceBefore=14, spaceAfter=6)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, leading=15, spaceAfter=8)
    exegese_style = ParagraphStyle('Exegese', parent=styles['Normal'], fontSize=9, leading=14,
                                   textColor=AMBER, leftIndent=12, rightIndent=12, spaceAfter=8)
    bibelvers_style = ParagraphStyle('Bibelvers', parent=styles['Normal'], fontSize=11, leading=16,
                                     leftIndent=20, rightIndent=20, textColor=colors.HexColor('#374151'),
                                     spaceAfter=12, spaceBefore=4)
    impuls_style = ParagraphStyle('Impuls', parent=styles['Normal'], fontSize=10, leading=14,
                                  leftIndent=16, spaceAfter=4)
    quelle_style = ParagraphStyle('Quelle', parent=styles['Normal'], fontSize=8, leading=12,
                                  textColor=GRAY, spaceAfter=6)

    story = []

    story.append(Paragraph(andacht.titel or andacht.thema, titel_style))
    story.append(Paragraph(
        f'{andacht.get_typ_display()} · {andacht.get_zielgruppe_display()} · ca. {andacht.dauer_minuten} Min.',
        untertitel_style
    ))
    story.append(HRFlowable(width='100%', thickness=1, color=PRIMARY, spaceAfter=16))

    lieder = andacht.lieder()
    einstiegslied = next((l for l in lieder if l.get('position') == 'einstieg'), None)
    if einstiegslied:
        story.append(Paragraph('Eröffnungslied', h2_style))
        eg = f' (EG {einstiegslied["eg_nummer"]})' if einstiegslied.get('eg_nummer') else ''
        story.append(Paragraph(f'{einstiegslied.get("titel", "")}{eg}', body_style))

    gebete = andacht.gebete()
    if gebete.get('eroeffnung'):
        story.append(Paragraph('Eröffnungsgebet', h2_style))
        story.append(Paragraph(gebete['eroeffnung'].replace('\n', '<br/>'), body_style))

    story.append(Paragraph('Bibelstelle', h2_style))
    story.append(Paragraph(f'<b>{andacht.bibelstelle}</b>', body_style))
    if andacht.bibeltext:
        story.append(Paragraph(andacht.bibeltext.replace('\n', '<br/>'), bibelvers_style))

    if andacht.geschichte:
        story.append(Paragraph('Geschichte / Illustration', h2_style))
        story.append(Paragraph(andacht.geschichte.replace('\n', '<br/>'), body_style))
        if andacht.geschichte_quelle:
            story.append(Paragraph(f'Quelle: {andacht.geschichte_quelle}', quelle_style))

    story.append(Paragraph('Andacht', h2_style))
    if andacht.einstieg:
        story.append(Paragraph(andacht.einstieg.replace('\n', '<br/>'), body_style))
    if andacht.entfaltung:
        story.append(Spacer(1, 4))
        story.append(Paragraph(andacht.entfaltung.replace('\n', '<br/>'), body_style))
    if andacht.abschluss:
        story.append(Spacer(1, 4))
        story.append(Paragraph(andacht.abschluss.replace('\n', '<br/>'), body_style))

    if gebete.get('fuerbitten'):
        story.append(Paragraph('Fürbitten', h2_style))
        story.append(Paragraph(gebete['fuerbitten'].replace('\n', '<br/>'), body_style))

    if gebete.get('abschluss'):
        story.append(Paragraph('Abschlussgebet', h2_style))
        story.append(Paragraph(gebete['abschluss'].replace('\n', '<br/>'), body_style))

    schlusslied = next((l for l in lieder if l.get('position') == 'schluss'), None)
    if schlusslied:
        story.append(Paragraph('Schlusslied', h2_style))
        eg = f' (EG {schlusslied["eg_nummer"]})' if schlusslied.get('eg_nummer') else ''
        story.append(Paragraph(f'{schlusslied.get("titel", "")}{eg}', body_style))

    if andacht.exegese:
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width='100%', thickness=0.5, color=AMBER_GOLD, spaceAfter=10))
        story.append(Paragraph('Exegese – Nur für den Andachtshaltenden', h2_amber_style))
        story.append(Paragraph(andacht.exegese.replace('\n', '<br/>'), exegese_style))
        story.append(HRFlowable(width='100%', thickness=0.5, color=AMBER_GOLD, spaceAfter=10))

    impulse = andacht.gespraechsimpulse()
    if impulse:
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width='100%', thickness=0.5, color=GRAY_LIGHT, spaceAfter=12))
        story.append(Paragraph('Gesprächsimpulse', h2_style))
        for i, imp in enumerate(impulse, 1):
            story.append(Paragraph(f'{i}. {imp}', impuls_style))

    doc.build(
        story,
        onFirstPage=lambda c, d: _header_footer(c, d, andacht),
        onLaterPages=lambda c, d: _header_footer(c, d, andacht),
    )
    buffer.seek(0)
    return buffer
