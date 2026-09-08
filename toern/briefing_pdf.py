"""Crew-Briefing als PDF.

Stellt aus den für einen Törn aktiven Briefing-Bausteinen
(toern.BriefingAuswahl -> briefing.BriefingBaustein) ein Handout zusammen.
Die Auszeichnungen im Baustein-Text (Warnung, Hinweis, Merksatz, Liste,
Tabelle) werden über briefing.markup geparst — derselbe Parser, den auch
Web-Ansicht und Vorschau benutzen."""
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
    Image as RLImage, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

from briefing import markup
from briefing.models import BriefingBaustein
from .models import Toern

LOGO_PATH = os.path.join(settings.BASE_DIR, 'static', 'medien', 'Logo_Meer_erleben.png')

_logo_weiss_cache = None


def _logo_weiss():
    """Logo in Weiß, für den dunkelblauen Kopfblock. Die Alpha-Maske der PNG bleibt
    erhalten, nur die Farbkanäle werden auf Weiß gesetzt — dasselbe, was die
    Web-Navigation über den CSS-Filter brightness(0) invert(1) macht."""
    global _logo_weiss_cache
    if _logo_weiss_cache is None:
        from PIL import Image
        original = Image.open(LOGO_PATH).convert('RGBA')
        weiss = Image.new('RGBA', original.size, (255, 255, 255, 0))
        weiss.putalpha(original.getchannel('A'))
        _logo_weiss_cache = ImageReader(weiss)
    return _logo_weiss_cache

PRIMARY = colors.HexColor('#1e3a5f')
SECONDARY = colors.HexColor('#0D9488')
ROT = colors.HexColor('#B91C1C')
ROT_HELL = colors.HexColor('#FDECEC')
TEAL_HELL = colors.HexColor('#E6F4F2')
HELLGRAU = colors.HexColor('#F3F4F6')
GRAY = colors.HexColor('#9ca3af')
GRAY_LIGHT = colors.HexColor('#d1d5db')

RAND = 2.2 * cm
FOOTER_TEXT = 'Crew-Briefing · Segelmanager.undmeererleben.de'

STIL = {
    'deckblatt_titel': ParagraphStyle('DTitel', fontSize=30, leading=35, textColor=colors.white,
                                      fontName='Helvetica-Bold'),
    'deckblatt_unter': ParagraphStyle('DUnter', fontSize=13, leading=18,
                                      textColor=colors.HexColor('#A8C4DC')),
    'kapitel': ParagraphStyle('Kapitel', fontSize=18, leading=22, textColor=PRIMARY,
                              fontName='Helvetica-Bold'),
    'baustein': ParagraphStyle('BausteinTitel', fontSize=12, leading=16, textColor=PRIMARY,
                               fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=4),
    'body': ParagraphStyle('Body', fontSize=10, leading=14.5, spaceAfter=5, alignment=4),
    'boxkopf': ParagraphStyle('BoxKopf', fontSize=8, leading=11, fontName='Helvetica-Bold'),
    'boxtext': ParagraphStyle('BoxText', fontSize=9.8, leading=13.5, spaceAfter=2),
    'merksatz': ParagraphStyle('Merksatz', fontSize=11, leading=15, fontName='Helvetica-Bold',
                               textColor=colors.white),
    'zelle': ParagraphStyle('Zelle', fontSize=9.5, leading=12.5),
    'zellekopf': ParagraphStyle('ZelleKopf', fontSize=9.5, leading=12.5,
                                fontName='Helvetica-Bold', textColor=colors.white),
}


def _fusszeile(canvas, doc):
    canvas.saveState()
    w, _h = A4
    y = RAND - 0.8 * cm
    canvas.setStrokeColor(GRAY_LIGHT)
    canvas.setLineWidth(0.5)
    canvas.line(RAND, y + 0.5 * cm, w - RAND, y + 0.5 * cm)
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(GRAY)
    canvas.drawString(RAND, y, FOOTER_TEXT)
    canvas.drawRightString(w - RAND, y, f'Seite {canvas.getPageNumber() - 1}')
    canvas.restoreState()


def _wellen(canvas, y, breite, farbe, alpha):
    canvas.saveState()
    canvas.setStrokeColor(farbe)
    canvas.setLineWidth(1.6)
    canvas.setStrokeAlpha(alpha)
    pfad = canvas.beginPath()
    pfad.moveTo(0, y)
    schritt, x, hoch = 14 * mm, 0, True
    while x < breite:
        versatz = 5 * mm if hoch else -5 * mm
        pfad.curveTo(x + schritt * 0.3, y + versatz, x + schritt * 0.7, y + versatz, x + schritt, y)
        x += schritt
        hoch = not hoch
    canvas.drawPath(pfad, stroke=1, fill=0)
    canvas.restoreState()


def _deckblatt(canvas, doc, toern, boot, skipper_name):
    """Erste Seite: dunkelblauer Kopfblock mit Wellen, darunter die Törndaten."""
    canvas.saveState()
    w, h = A4
    block_h = 11.5 * cm

    canvas.setFillColor(PRIMARY)
    canvas.rect(0, h - block_h, w, block_h, stroke=0, fill=1)
    _wellen(canvas, h - block_h + 1.2 * cm, w, SECONDARY, 0.55)
    _wellen(canvas, h - block_h + 2.0 * cm, w, colors.white, 0.14)

    logo_links_kante = w - RAND   # Rückfallwert, falls kein Logo vorhanden
    if os.path.exists(LOGO_PATH):
        logo_h = 2.8 * cm
        bild = _logo_weiss()
        ow, oh = bild.getSize()
        logo_w = logo_h * ow / oh
        # Mittig zwischen dem Ende der Überschrift und dem rechten Seitenrand
        text_ende = RAND + canvas.stringWidth('Crew-Briefing', 'Helvetica-Bold', 30)
        mitte_x = (text_ende + (w - RAND)) / 2
        logo_x = mitte_x - logo_w / 2
        canvas.drawImage(bild, logo_x, h - 6.1 * cm,
                         width=logo_w, height=logo_h, mask='auto')
        logo_links_kante = logo_x

    canvas.setFillColor(SECONDARY)
    canvas.setFont('Helvetica-Bold', 10)
    canvas.drawString(RAND, h - 3.0 * cm, 'SEGELMANAGER  ·  MEER ERLEBEN')

    canvas.setFillColor(colors.white)
    canvas.setFont('Helvetica-Bold', 30)
    canvas.drawString(RAND, h - 5.0 * cm, 'Crew-Briefing')

    canvas.setFillColor(colors.HexColor('#A8C4DC'))
    canvas.setFont('Helvetica', 13)
    max_breite = logo_links_kante - RAND - 0.6 * cm
    titel = toern.titel
    while titel and canvas.stringWidth(titel, 'Helvetica', 13) > max_breite:
        titel = titel[:-1]
    if titel != toern.titel:
        titel = titel[:-1] + '…'
    canvas.drawString(RAND, h - 6.3 * cm, titel)
    canvas.setFont('Helvetica-Oblique', 10.5)
    canvas.drawString(RAND, h - 7.2 * cm, 'Damit aus unterschiedlichen Erfahrungen eine Crew wird.')

    # Törndaten
    y = h - block_h - 2.2 * cm
    zeilen = [
        ('BOOT', boot.name if boot else '—'),
        ('TÖRN', toern.titel),
        ('SKIPPER', skipper_name),
        ('DATUM', date.today().strftime('%d.%m.%Y')),
    ]
    for label, wert in zeilen:
        canvas.setFillColor(PRIMARY)
        canvas.setFont('Helvetica-Bold', 9)
        canvas.drawString(RAND, y, label)
        canvas.setFillColor(colors.black)
        canvas.setFont('Helvetica', 11)
        canvas.drawString(RAND + 3.6 * cm, y, str(wert)[:60])
        canvas.setStrokeColor(GRAY_LIGHT)
        canvas.setLineWidth(0.5)
        canvas.line(RAND + 3.6 * cm, y - 0.2 * cm, A4[0] - RAND, y - 0.2 * cm)
        y -= 1.3 * cm

    canvas.setFillColor(GRAY)
    canvas.setFont('Helvetica', 8.5)
    canvas.drawString(RAND, 2.4 * cm,
                      'Dieses Briefing ersetzt keine Sicherheitseinweisung an Bord — es strukturiert sie.')
    canvas.drawString(RAND, 1.9 * cm,
                      'Bitte vor dem Ablegen einmal gemeinsam durchgehen und offene Punkte klären.')
    canvas.restoreState()


def _kapitelkopf(titel, breite):
    """Kapitelüberschrift mit Teal-Balken links."""
    t = Table([[Paragraph(titel, STIL['kapitel'])]], colWidths=[breite])
    t.setStyle(TableStyle([
        ('LINEBEFORE', (0, 0), (0, -1), 3.2 * mm, SECONDARY),
        ('LEFTPADDING', (0, 0), (-1, -1), 5 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 3 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3 * mm),
    ]))
    return t


def _box(zeilen, label, bg, akzent, breite):
    inhalt = [Paragraph(label.upper(), ParagraphStyle('bk', parent=STIL['boxkopf'], textColor=akzent))]
    inhalt += [Paragraph(z, STIL['boxtext']) for z in zeilen]
    t = Table([[inhalt]], colWidths=[breite])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('LINEBEFORE', (0, 0), (0, -1), 3.2 * mm, akzent),
        ('LEFTPADDING', (0, 0), (-1, -1), 6 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 3 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3 * mm),
    ]))
    return t


def _bloecke_zu_flowables(text, breite):
    """Markup-Blöcke (briefing.markup) in ReportLab-Flowables übersetzen."""
    out = []
    for block in markup.parse(text):
        typ = block['typ']

        if typ == markup.ABSATZ:
            out.append(Paragraph('<br/>'.join(block['zeilen']), STIL['body']))

        elif typ == markup.WARNUNG:
            out.append(_box(block['zeilen'], 'Warnung', ROT_HELL, ROT, breite))
            out.append(Spacer(1, 3 * mm))

        elif typ == markup.HINWEIS:
            out.append(_box(block['zeilen'], 'Hinweis', TEAL_HELL, SECONDARY, breite))
            out.append(Spacer(1, 3 * mm))

        elif typ == markup.MERKSATZ:
            p = Paragraph('<br/>'.join(block['zeilen']), STIL['merksatz'])
            t = Table([[p]], colWidths=[breite])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), PRIMARY),
                ('LEFTPADDING', (0, 0), (-1, -1), 5 * mm),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5 * mm),
                ('TOPPADDING', (0, 0), (-1, -1), 3.5 * mm),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5 * mm),
            ]))
            out.append(t)
            out.append(Spacer(1, 3 * mm))

        elif typ == markup.LISTE:
            zeilen = [[Paragraph('•', ParagraphStyle('bl', fontSize=10, leading=14.5,
                                                     textColor=SECONDARY)),
                       Paragraph(p, STIL['body'])] for p in block['punkte']]
            t = Table(zeilen, colWidths=[5 * mm, breite - 5 * mm])
            t.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            out.append(t)
            out.append(Spacer(1, 2 * mm))

        elif typ == markup.TABELLE:
            zeilen = block['zeilen']
            if not zeilen:
                continue
            spalten = max(len(z) for z in zeilen)
            spaltenbreite = breite / spalten
            daten = []
            for i, zeile in enumerate(zeilen):
                gefuellt = list(zeile) + [''] * (spalten - len(zeile))
                stil = STIL['zellekopf'] if i == 0 else STIL['zelle']
                daten.append([Paragraph(z, stil) for z in gefuellt])
            t = Table(daten, colWidths=[spaltenbreite] * spalten, repeatRows=1)
            stil_cmds = [
                ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('LINEBELOW', (0, 1), (-1, -2), 0.4, GRAY_LIGHT),
            ]
            for i in range(1, len(daten)):
                if i % 2 == 1:
                    stil_cmds.append(('BACKGROUND', (0, i), (-1, i), HELLGRAU))
            t.setStyle(TableStyle(stil_cmds))
            out.append(t)
            out.append(Spacer(1, 3 * mm))

    return out


def briefing_boot(user, toern):
    """Das Boot, auf das sich dieses Briefing bezieht: das des anfragenden Skippers.

    Bei Flotten-Törns hängen mehrere Boote am selben Törn, jedes mit eigener Crew.
    Einfach `toern.boote.first()` zu nehmen zeigt dann das falsche Boot auf dem
    Deckblatt. Fällt nur zurück, wenn der Nutzer keinem Boot zugeordnet ist."""
    from .models import Teilnahme
    teilnahme = (
        Teilnahme.objects.filter(user=user, toern=toern, boot__isnull=False)
        .select_related('boot').first()
    )
    return teilnahme.boot if teilnahme else toern.boote.first()


def _bild_flowable(baustein, max_breite, max_hoehe=85 * mm):
    """Skaliertes Bild-Flowable oder None, wenn kein Bild da ist / es nicht lesbar ist."""
    if not baustein.bild:
        return None
    try:
        ow, oh = ImageReader(baustein.bild.path).getSize()
    except Exception:
        return None
    skalierung = min(max_breite / ow, max_hoehe / oh, 1)
    return RLImage(baustein.bild.path, width=ow * skalierung, height=oh * skalierung)


def _baustein_flowables(baustein, breite):
    """Titel, Text und Bild eines Bausteins — angeordnet nach baustein.bild_position."""
    titel = Paragraph(baustein.titel, STIL['baustein'])
    text = _bloecke_zu_flowables(baustein.text, breite)
    position = baustein.bild_position or 'unten'

    if position in ('links', 'rechts'):
        bild_breite = breite * 0.38
        spalte = breite - bild_breite - 4 * mm
        bild = _bild_flowable(baustein, bild_breite, max_hoehe=120 * mm)
        if bild is not None:
            text_spalte = _bloecke_zu_flowables(baustein.text, spalte)
            zellen = ([bild, text_spalte] if position == 'links' else [text_spalte, bild])
            breiten = ([bild_breite, spalte + 4 * mm] if position == 'links'
                       else [spalte + 4 * mm, bild_breite])
            tabelle = Table([zellen], colWidths=breiten)
            tabelle.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (0, -1), 0),
                ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
                ('LEFTPADDING', (1, 0), (1, -1), 4 * mm),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            return [titel, tabelle, Spacer(1, 3 * mm)]

    bild = _bild_flowable(baustein, breite)
    if bild is None:
        return [titel] + text

    if position == 'oben':
        return [titel, bild, Spacer(1, 3 * mm)] + text
    return [titel] + text + [Spacer(1, 2 * mm), bild, Spacer(1, 3 * mm)]


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

    boot = briefing_boot(request.user, toern)
    skipper_name = f'{request.user.first_name} {request.user.last_name}'.strip() or request.user.email

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=RAND, rightMargin=RAND, topMargin=RAND, bottomMargin=RAND,
        title=f'Crew-Briefing — {toern.titel}',
    )
    breite = doc.width

    story = [PageBreak()]  # Seite 1 ist das Deckblatt (rein per Canvas gezeichnet)

    if not auswahl:
        story.append(Paragraph(
            'Für diesen Törn sind noch keine Briefing-Bausteine ausgewählt. '
            'Im Skipper-Dashboard unter „Briefing“ lassen sich Bausteine aus der '
            'gemeinsamen Bibliothek hinzufügen.',
            STIL['body'],
        ))
    else:
        kategorie_labels = dict(BriefingBaustein.KATEGORIE_CHOICES)
        aktuelle_kategorie = None
        for a in auswahl:
            baustein = a.baustein
            if baustein.kategorie != aktuelle_kategorie:
                aktuelle_kategorie = baustein.kategorie
                story.append(Spacer(1, 4 * mm))
                story.append(_kapitelkopf(
                    kategorie_labels.get(aktuelle_kategorie, aktuelle_kategorie), breite))
                story.append(Spacer(1, 2 * mm))

            # Titel und ersten Block zusammenhalten, damit keine Überschrift allein steht
            teile = _baustein_flowables(baustein, breite)
            story.append(KeepTogether(teile[:2]))
            story.extend(teile[2:])

    doc.build(
        story,
        onFirstPage=lambda c, d: _deckblatt(c, d, toern, boot, skipper_name),
        onLaterPages=_fusszeile,
    )
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Crew-Briefing_{toern.id}.pdf"'
    return response
