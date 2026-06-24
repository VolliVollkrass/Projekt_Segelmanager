from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT


def erstelle_andacht_pdf(andacht):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()
    primary = colors.HexColor('#1e3a5f')
    secondary = colors.HexColor('#0D9488')

    titel_style = ParagraphStyle('Titel', parent=styles['Title'], textColor=primary, fontSize=20, spaceAfter=6)
    untertitel_style = ParagraphStyle('Untertitel', parent=styles['Normal'], textColor=secondary, fontSize=11, spaceAfter=16)
    h2_style = ParagraphStyle('H2', parent=styles['Heading2'], textColor=primary, fontSize=13, spaceBefore=14, spaceAfter=6)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, leading=15, spaceAfter=8)
    bibelvers_style = ParagraphStyle('Bibelvers', parent=styles['Normal'], fontSize=11, leading=16,
                                     leftIndent=20, rightIndent=20, textColor=colors.HexColor('#374151'),
                                     spaceAfter=12, spaceBefore=4)
    impuls_style = ParagraphStyle('Impuls', parent=styles['Normal'], fontSize=10, leading=14,
                                  leftIndent=16, spaceAfter=4)

    story = []

    story.append(Paragraph(andacht.titel or andacht.thema, titel_style))
    story.append(Paragraph(
        f'{andacht.get_typ_display()} · {andacht.get_zielgruppe_display()} · ca. {andacht.dauer_minuten} Min.',
        untertitel_style
    ))
    story.append(HRFlowable(width='100%', thickness=1, color=primary, spaceAfter=16))

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

    impulse = andacht.gespraechsimpulse()
    if impulse:
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#d1d5db'), spaceAfter=12))
        story.append(Paragraph('Gesprächsimpulse', h2_style))
        for i, imp in enumerate(impulse, 1):
            story.append(Paragraph(f'{i}. {imp}', impuls_style))

    doc.build(story)
    buffer.seek(0)
    return buffer
