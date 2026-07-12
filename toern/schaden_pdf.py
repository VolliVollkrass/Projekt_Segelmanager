"""Schadensprotokoll als PDF — Gesamt-Protokoll des Boots und Einzel-Eintrag.

Beide Routen enden auf .../pdf/, damit sie in der iOS-WebApp automatisch durch den
In-App-PDF-Viewer (mit Teilen-Button) laufen. Zugriff wie beim Schadens-Tab: bestätigte
Teilnahme an diesem Boot, Törn ZUTEILUNG_FIXIERT.
"""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, portrait
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from boote.models import Boot
from .models import Schadensmeldung
from .schaden_views import _boot_crew_teilnahme

DUNKELBLAU = colors.HexColor("#1E3A5F")
GRAU = colors.HexColor("#666666")
HELLGRAU = colors.HexColor("#F3F4F6")

# Schweregrad → Balkenfarbe (grün → rot), analog zu den Badges im UI
SCHWERE_FARBE = {
    1: colors.HexColor("#16A34A"),
    2: colors.HexColor("#16A34A"),
    3: colors.HexColor("#D97706"),
    4: colors.HexColor("#DC2626"),
    5: colors.HexColor("#DC2626"),
}
STATUS_FARBE = {
    "offen": colors.HexColor("#DC2626"),
    "behoben": colors.HexColor("#16A34A"),
    "gemeldet": colors.HexColor("#2563EB"),
}


def _pdf_response(filename):
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def _fusszeile(boot):
    return Paragraph(
        f"{boot.name} — {boot.toern.titel} · Schadensprotokoll · undmeererleben.de",
        ParagraphStyle("fuss", fontSize=7, leading=9, textColor=GRAU, alignment=1),
    )


def _stile():
    return {
        "titel": ParagraphStyle("titel", fontSize=17, leading=21, fontName="Helvetica-Bold", textColor=DUNKELBLAU),
        "sub": ParagraphStyle("sub", fontSize=9, leading=12, textColor=GRAU),
        "eintrag_titel": ParagraphStyle("etitel", fontSize=12.5, leading=15, fontName="Helvetica-Bold", textColor=DUNKELBLAU),
        "label": ParagraphStyle("label", fontSize=8, leading=10, textColor=GRAU, fontName="Helvetica-Bold"),
        "wert": ParagraphStyle("wert", fontSize=9.5, leading=13),
        "badge": ParagraphStyle("badge", fontSize=9, leading=12, fontName="Helvetica-Bold", textColor=colors.white, alignment=1),
        "klein": ParagraphStyle("klein", fontSize=7.5, leading=9.5, textColor=GRAU),
    }


def _bild_flowable(bild, max_w, max_h):
    """Ein media-Bild als skaliertes ReportLab-Image (Seitenverhältnis erhalten)."""
    try:
        reader = ImageReader(bild.bild.path)
        iw, ih = reader.getSize()
    except Exception:
        return None
    if not iw or not ih:
        return None
    scale = min(max_w / iw, max_h / ih, 1.0)
    return Image(bild.bild.path, width=iw * scale, height=ih * scale)


def _badge(text, farbe, stile):
    """Farbige Badge-Zelle (Table mit Hintergrund)."""
    t = Table([[Paragraph(text, stile["badge"])]], colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), farbe),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _eintrag_flowables(meldung, stile, mit_trenner=True):
    """Alle Flowables für einen Schadenseintrag (Felder, Meta, Fotos)."""
    els = []
    els.append(Paragraph(meldung.titel, stile["eintrag_titel"]))
    els.append(Spacer(1, 1.5 * mm))

    # Badges: Schweregrad + Status nebeneinander
    badges = Table([[
        _badge(f"Schweregrad {meldung.schweregrad}/5", SCHWERE_FARBE.get(meldung.schweregrad, GRAU), stile),
        _badge(meldung.get_status_display(), STATUS_FARBE.get(meldung.status, GRAU), stile),
        "",
    ]], colWidths=[38 * mm, 40 * mm, None])
    badges.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 4),
    ]))
    els.append(badges)
    els.append(Spacer(1, 2 * mm))

    # Ort + Schweregrad-Bedeutung
    els.append(Paragraph("Wo am Boot", stile["label"]))
    els.append(Paragraph(meldung.ort or "—", stile["wert"]))
    els.append(Spacer(1, 1.5 * mm))
    els.append(Paragraph("Beeinträchtigung", stile["label"]))
    els.append(Paragraph(meldung.get_schweregrad_display(), stile["wert"]))

    if meldung.beschreibung:
        els.append(Spacer(1, 1.5 * mm))
        els.append(Paragraph("Beschreibung", stile["label"]))
        els.append(Paragraph(meldung.beschreibung.replace("\n", "<br/>"), stile["wert"]))

    # Fotos (in einem Grid, verkleinert)
    bilder = list(meldung.bilder.all())
    if bilder:
        els.append(Spacer(1, 2 * mm))
        els.append(Paragraph("Fotos", stile["label"]))
        els.append(Spacer(1, 1 * mm))
        zellen = []
        for b in bilder:
            flt = _bild_flowable(b, max_w=55 * mm, max_h=42 * mm)
            if flt is not None:
                zellen.append(flt)
        # in Reihen zu je 3
        reihen = [zellen[i:i + 3] for i in range(0, len(zellen), 3)]
        for r in reihen:
            while len(r) < 3:
                r.append("")
        if reihen:
            grid = Table(reihen, colWidths=[58 * mm, 58 * mm, 58 * mm])
            grid.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            els.append(grid)

    # Protokoll-Meta
    els.append(Spacer(1, 2 * mm))
    erstellt = meldung.erstellt_von.first_name if meldung.erstellt_von else "—"
    geaendert = meldung.geaendert_von.first_name if meldung.geaendert_von else "—"
    meta = (
        f"Erstellt von {erstellt} am {meldung.erstellt_am.strftime('%d.%m.%Y %H:%M')}"
        f" &nbsp;·&nbsp; Zuletzt geändert von {geaendert} am {meldung.geaendert_am.strftime('%d.%m.%Y %H:%M')}"
    )
    els.append(Paragraph(meta, stile["klein"]))

    if mit_trenner:
        els.append(Spacer(1, 3 * mm))
        els.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#DDDDDD")))
        els.append(Spacer(1, 3 * mm))
    return els


def _kopf(boot, stile, untertitel):
    toern = boot.toern
    charter = boot.charterbasis_name or (boot.charterunternehmen.name if boot.charterunternehmen else "—")
    els = [
        Paragraph("Schadensprotokoll", stile["titel"]),
        Spacer(1, 1.5 * mm),
        Paragraph(
            f"{boot.name} · {toern.titel} · "
            f"{toern.startdatum.strftime('%d.%m.%Y')} – {toern.enddatum.strftime('%d.%m.%Y')}"
            f" &nbsp;|&nbsp; Charterbasis: {charter}"
            f" &nbsp;|&nbsp; Erstellt: {untertitel}",
            stile["sub"],
        ),
        Spacer(1, 3 * mm),
        HRFlowable(width="100%", thickness=1, color=DUNKELBLAU),
        Spacer(1, 4 * mm),
    ]
    return els


@login_required
def schaden_gesamt_pdf(request, boot_id):
    from django.utils import timezone
    boot = get_object_or_404(Boot, id=boot_id)
    _boot_crew_teilnahme(request, boot)

    meldungen = list(
        Schadensmeldung.objects.filter(boot=boot)
        .select_related("erstellt_von", "geaendert_von")
        .prefetch_related("bilder")
    )

    response = _pdf_response(f"schadensprotokoll_{boot.name.replace(' ', '_')}.pdf")
    doc = SimpleDocTemplate(
        response, pagesize=portrait(A4),
        rightMargin=14 * mm, leftMargin=14 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
    )
    stile = _stile()
    elements = _kopf(boot, stile, timezone.localtime().strftime("%d.%m.%Y %H:%M"))

    if not meldungen:
        elements.append(Paragraph("Keine Schäden erfasst.", stile["wert"]))
    else:
        elements.append(Paragraph(
            f"{len(meldungen)} Eintrag/Einträge", stile["sub"]))
        elements.append(Spacer(1, 3 * mm))
        for i, m in enumerate(meldungen):
            elements += _eintrag_flowables(m, stile, mit_trenner=(i < len(meldungen) - 1))

    elements.append(Spacer(1, 4 * mm))
    elements.append(_fusszeile(boot))
    doc.build(elements)
    return response


@login_required
def schaden_einzel_pdf(request, meldung_id):
    from django.utils import timezone
    meldung = get_object_or_404(
        Schadensmeldung.objects.select_related("boot__toern", "erstellt_von", "geaendert_von"),
        id=meldung_id,
    )
    boot = meldung.boot
    _boot_crew_teilnahme(request, boot)

    response = _pdf_response(f"schaden_{meldung.id}_{boot.name.replace(' ', '_')}.pdf")
    doc = SimpleDocTemplate(
        response, pagesize=portrait(A4),
        rightMargin=14 * mm, leftMargin=14 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
    )
    stile = _stile()
    elements = _kopf(boot, stile, timezone.localtime().strftime("%d.%m.%Y %H:%M"))
    elements += _eintrag_flowables(meldung, stile, mit_trenner=False)
    elements.append(Spacer(1, 4 * mm))
    elements.append(_fusszeile(boot))
    doc.build(elements)
    return response
