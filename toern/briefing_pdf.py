"""Crew-Briefing als PDF: stellt aus den für einen Törn aktiven Briefing-Bausteinen
(toern.BriefingAuswahl -> briefing.BriefingBaustein) ein zusammenhängendes PDF-Handout
zusammen. Farben/Aufbau analog andacht/pdf_export.py (Segelmanager-Theme)."""
import os
from datetime import date
from io import BytesIO

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, HRFlowable,
)

from briefing.models import BriefingBaustein
from .models import Toern

LOGO_PATH = os.path.join(settings.BASE_DIR, 'static', 'medien', 'Logo_Meer_erleben.png')

PRIMARY = colors.HexColor('#1e3a5f')
SECONDARY = colors.HexColor('#0D9488')
GRAY = colors.HexColor('#9ca3af')
GRAY_LIGHT = colors.HexColor('#d1d5db')

FOOTER_TEXT = 'Erstellt mit den Briefing-Bausteinen · Segelmanager.undmeererleben.de'


def _footer(canvas, doc):
    canvas.saveState()
    w, _h = A4
    margin = 2.5 * cm
    footer_y = margin - 0.8 * cm

    canvas.setStrokeColor(GRAY_LIGHT)
    canvas.setLineWidth(0.5)
    canvas.line(margin, footer_y + 0.5 * cm, w - margin, footer_y + 0.5 * cm)

    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(GRAY)
    canvas.drawString(margin, footer_y, FOOTER_TEXT)

    seite_text = f'{date.today().strftime("%d.%m.%Y")}  |  Seite {canvas.getPageNumber()}'
    canvas.drawRightString(w - margin, footer_y, seite_text)
    canvas.restoreState()


def _first_page(canvas, doc):
    canvas.saveState()
    w, h = A4
    margin = 2.5 * cm

    if os.path.exists(LOGO_PATH):
        logo_h = 1.8 * cm
        orig_w, orig_h = ImageReader(LOGO_PATH).getSize()
        logo_w = logo_h * orig_w / orig_h
        canvas.drawImage(
            LOGO_PATH, (w - logo_w) / 2, h - margin - logo_h,
            width=logo_w, height=logo_h, mask='auto',
        )
    canvas.restoreState()
    _footer(canvas, doc)


@login_required
def briefing_pdf(request, toern_id):
    from .views import _hat_skipper_oder_anbieter
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    auswahl = list(
        toern.briefing_auswahl.filter(aktiv=True)
        .select_related('baustein')
        .order_by('reihenfolge', 'id')
    )

    boot = toern.boote.first()
    skipper_name = f'{request.user.first_name} {request.user.last_name}'.strip() or request.user.email

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        topMargin=4.0 * cm, bottomMargin=2.5 * cm,
    )

    titel_style = ParagraphStyle('Titel', fontSize=22, leading=27, textColor=PRIMARY,
                                 fontName='Helvetica-Bold', spaceAfter=4)
    untertitel_style = ParagraphStyle('Untertitel', fontSize=11, leading=15, textColor=SECONDARY, spaceAfter=4)
    meta_style = ParagraphStyle('Meta', fontSize=9, leading=13, textColor=GRAY, spaceAfter=16)
    kapitel_style = ParagraphStyle('Kapitel', fontSize=14, leading=18, textColor=PRIMARY,
                                   fontName='Helvetica-Bold', spaceBefore=16, spaceAfter=8)
    baustein_titel_style = ParagraphStyle('BausteinTitel', fontSize=11.5, leading=15, textColor=PRIMARY,
                                          fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle('Body', fontSize=10, leading=15, spaceAfter=6)

    story = []
    story.append(Paragraph('Crew-Briefing', titel_style))
    story.append(Paragraph(toern.titel, untertitel_style))
    meta_teile = []
    if boot:
        meta_teile.append(boot.name)
    meta_teile.append(f'Skipper: {skipper_name}')
    meta_teile.append(date.today().strftime('%d.%m.%Y'))
    story.append(Paragraph('  ·  '.join(meta_teile), meta_style))
    story.append(HRFlowable(width='100%', thickness=1, color=PRIMARY, spaceAfter=10))

    if not auswahl:
        story.append(Paragraph(
            'Für diesen Törn sind noch keine Briefing-Bausteine ausgewählt. '
            'Im Skipper-Dashboard unter „Briefing“ lassen sich Bausteine aus der '
            'gemeinsamen Bibliothek hinzufügen.',
            body_style,
        ))
    else:
        aktuelle_kategorie = None
        kategorie_labels = dict(BriefingBaustein.KATEGORIE_CHOICES)
        for a in auswahl:
            baustein = a.baustein
            if baustein.kategorie != aktuelle_kategorie:
                aktuelle_kategorie = baustein.kategorie
                story.append(Paragraph(kategorie_labels.get(aktuelle_kategorie, aktuelle_kategorie), kapitel_style))

            story.append(Paragraph(baustein.titel, baustein_titel_style))
            for absatz in baustein.text.split('\n\n'):
                absatz = absatz.strip()
                if absatz:
                    story.append(Paragraph(absatz.replace('\n', '<br/>'), body_style))

            if baustein.bild:
                try:
                    bild_reader = ImageReader(baustein.bild.path)
                    orig_w, orig_h = bild_reader.getSize()
                    max_w = doc.width
                    max_h = 90 * mm
                    scale = min(max_w / orig_w, max_h / orig_h, 1)
                    story.append(Spacer(1, 2 * mm))
                    story.append(RLImage(
                        baustein.bild.path, width=orig_w * scale, height=orig_h * scale,
                    ))
                    story.append(Spacer(1, 3 * mm))
                except Exception:
                    pass

    doc.build(story, onFirstPage=_first_page, onLaterPages=_footer)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Crew-Briefing_{toern.id}.pdf"'
    return response
