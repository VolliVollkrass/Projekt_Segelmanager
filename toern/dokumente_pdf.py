"""Boots-Dokumente als PDF: Mayday-Plakat (fürs Funkgerät) und Notrollen-Plakat (Aushang)."""
import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, portrait
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from boote.models import Boot
from .models import Teilnahme

ROT = colors.HexColor("#B91C1C")
DUNKELBLAU = colors.HexColor("#1E3A5F")
GRAU = colors.HexColor("#666666")
HELLGRAU = colors.HexColor("#F3F4F6")

LOGO_PATH = os.path.join(settings.BASE_DIR, "static/medien/Logo_Meer_erleben.png")


def _hat_dokument_zugang(user, boot):
    if boot.toern.anbieter == user or user.is_superuser:
        return True
    return Teilnahme.objects.filter(
        user=user, toern=boot.toern, rolle__in=["skipper", "coskipper"]
    ).exists()


def _pdf_response(filename):
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def _fusszeile(boot):
    return Paragraph(
        f"{boot.name} — {boot.toern.titel} · undmeererleben.de",
        ParagraphStyle("fuss", fontSize=7, leading=9, textColor=GRAU, alignment=1),
    )


# =========================
# MAYDAY-PLAKAT
# =========================

@login_required
def mayday_plakat_pdf(request, boot_id):
    boot = get_object_or_404(Boot, id=boot_id)
    if not _hat_dokument_zugang(request.user, boot):
        raise PermissionDenied

    rufzeichen = boot.funkrufzeichen or "____________"
    mmsi = boot.mmsi or "____________"
    personen = Teilnahme.objects.filter(
        toern=boot.toern, boot=boot, status="bestaetigt"
    ).count()
    personen_text = str(personen) if personen else "____"
    name_upper = boot.name.upper()

    response = _pdf_response(f"mayday_{boot.name.replace(' ', '_')}.pdf")
    doc = SimpleDocTemplate(
        response, pagesize=portrait(A4),
        rightMargin=15 * mm, leftMargin=15 * mm, topMargin=12 * mm, bottomMargin=10 * mm,
    )

    titel = ParagraphStyle("titel", fontSize=30, leading=34, fontName="Helvetica-Bold",
                           textColor=colors.white, alignment=1)
    untertitel = ParagraphStyle("untertitel", fontSize=11, leading=14, textColor=colors.white, alignment=1)
    box_kopf = ParagraphStyle("box_kopf", fontSize=13, leading=16, fontName="Helvetica-Bold",
                              textColor=DUNKELBLAU)
    normal = ParagraphStyle("normal", fontSize=11, leading=16)
    funkspruch = ParagraphStyle("funkspruch", fontSize=13, leading=22, fontName="Helvetica-Bold")
    hinweis = ParagraphStyle("hinweis", fontSize=9, leading=12, textColor=GRAU)

    elements = []

    # Roter Kopf
    kopf = Table(
        [[Paragraph("MAYDAY — NOTRUF", titel)],
         [Paragraph(f"{boot.name} · Bitte gut sichtbar am Funkgerät aufhängen", untertitel)]],
        colWidths=[180 * mm],
    )
    kopf.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ROT),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
    ]))
    elements.append(kopf)
    elements.append(Spacer(1, 5 * mm))

    # Schiffsdaten
    daten = Table([
        [Paragraph("<b>Schiffsname</b>", normal), Paragraph(boot.name, funkspruch)],
        [Paragraph("<b>Rufzeichen</b>", normal), Paragraph(rufzeichen, funkspruch)],
        [Paragraph("<b>MMSI</b>", normal), Paragraph(mmsi, funkspruch)],
        [Paragraph("<b>Personen an Bord</b>", normal), Paragraph(f"{personen_text} (vor Abfahrt prüfen!)", normal)],
    ], colWidths=[50 * mm, 130 * mm])
    daten.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HELLGRAU),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.white),
    ]))
    elements.append(daten)
    elements.append(Spacer(1, 5 * mm))

    # Schritt 1: DSC
    elements.append(Paragraph("SCHRITT 1 — DSC-SEENOTALARM (UKW Kanal 70)", box_kopf))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(
        "Rote <b>DISTRESS-Taste</b> am Funkgerät <b>5 Sekunden gedrückt halten</b>, "
        "bis der Alarm bestätigt wird. Danach Sprechfunk-Notruf auf Kanal 16 absetzen.",
        normal,
    ))
    elements.append(Spacer(1, 5 * mm))

    # Schritt 2: Sprechfunk
    elements.append(Paragraph("SCHRITT 2 — SPRECHFUNK-NOTRUF (UKW Kanal 16)", box_kopf))
    elements.append(Spacer(1, 2 * mm))

    spruch_zeilen = [
        "MAYDAY — MAYDAY — MAYDAY",
        f"HIER IST {name_upper} — {name_upper} — {name_upper}",
        f"RUFZEICHEN {rufzeichen} — MMSI {mmsi}",
        f"MAYDAY {name_upper}",
        "MEINE POSITION IST …&nbsp;&nbsp;<font size=9 color='#666666'>(Breite / Länge vom GPS oder Kartenplotter ablesen)</font>",
        "WIR HABEN …&nbsp;&nbsp;<font size=9 color='#666666'>(Art der Notlage: Wassereinbruch, Feuer, Person über Bord …)</font>",
        "WIR BENÖTIGEN SOFORTIGE HILFE",
        f"AN BORD SIND {personen_text} PERSONEN",
        "OVER",
    ]
    spruch = Table([[Paragraph(z, funkspruch)] for z in spruch_zeilen], colWidths=[180 * mm])
    spruch.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.5, ROT),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    elements.append(spruch)
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph(
        "Langsam und deutlich sprechen. Nach dem Notruf auf Kanal 16 hörbereit bleiben. "
        "Keine Antwort? Notruf wiederholen. Entwarnung ebenfalls über Funk melden.",
        hinweis,
    ))
    elements.append(Spacer(1, 6 * mm))

    if os.path.exists(LOGO_PATH):
        elements.append(Image(LOGO_PATH, width=22 * mm, height=22 * mm, kind="proportional"))
        elements.append(Spacer(1, 2 * mm))
    elements.append(_fusszeile(boot))

    doc.build(elements)
    return response


# =========================
# NOTROLLEN-PLAKAT
# =========================

NOTROLLEN = [
    ("PERSON ÜBER BORD (MOB)", [
        "Koordination übernehmen / MOB-Manöver fahren",
        "Boot in den Wind bringen",
        "„Mensch über Bord!“ rufen — Person nicht aus den Augen lassen",
        "Rettungsring + Boje werfen",
        "MOB-Taste am Plotter drücken (Position speichern)",
        "Funkmeldung absetzen (Kanal 16)",
        "Bergen vorbereiten — Hilfsmittel bereitlegen",
        "Erstversorgung nach der Bergung",
    ]),
    ("FEUER AN BORD", [
        "Koordination übernehmen",
        "Luken schließen (Rauch absperren!)",
        "Feuerlöscher gezielt einsetzen",
        "Löschdecke bei Fettbränden",
        "Batteriehauptschalter aus",
        "Dieselabsperrung aktivieren",
        "Navigation sichern",
        "Funk — DSC / Notantenne / Funkspruch",
    ]),
    ("WASSEREINBRUCH", [
        "Koordination übernehmen",
        "Pumpen aktivieren, Pützen / Eimer einsetzen",
        "See- und Absperrventile prüfen",
        "Maschinenraum kontrollieren",
        "Salon, Vorschiff, Kojen, Toilettenräume checken",
        "Leck suchen und abdichten",
        "Navigation und Lage beobachten",
        "Funkmeldung absetzen",
    ]),
    ("BOOT VERLASSEN", [
        "Koordination übernehmen",
        "Funk — DSC / Notantenne / Funkspruch",
        "Signalmunition bereithalten",
        "EPIRB / SART aktivieren",
        "Rettungsinsel klar machen",
        "Notpack mitnehmen — Erste Hilfe, Wasser, Essen",
        "Navigation / Position weitergeben",
        "Verletzte versorgen",
    ]),
]


@login_required
def notrollen_plakat_pdf(request, boot_id):
    boot = get_object_or_404(Boot, id=boot_id)
    if not _hat_dokument_zugang(request.user, boot):
        raise PermissionDenied

    response = _pdf_response(f"notrollen_{boot.name.replace(' ', '_')}.pdf")
    doc = SimpleDocTemplate(
        response, pagesize=portrait(A4),
        rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=10 * mm,
    )

    titel = ParagraphStyle("titel", fontSize=22, leading=26, fontName="Helvetica-Bold",
                           textColor=colors.white, alignment=1)
    untertitel = ParagraphStyle("untertitel", fontSize=10, leading=13, textColor=colors.white, alignment=1)
    box_kopf = ParagraphStyle("box_kopf", fontSize=12, leading=15, fontName="Helvetica-Bold",
                              textColor=colors.white)
    item = ParagraphStyle("item", fontSize=9, leading=13)
    merksatz = ParagraphStyle("merksatz", fontSize=11, leading=14, fontName="Helvetica-Bold",
                              textColor=DUNKELBLAU, alignment=1)

    elements = []

    kopf = Table(
        [[Paragraph("NOTFALL-SOFORTMASSNAHMEN", titel)],
         [Paragraph(f"{boot.name} · Jeder an Bord muss wissen, was zu tun ist — bitte aushängen",
                    untertitel)]],
        colWidths=[186 * mm],
    )
    kopf.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DUNKELBLAU),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
    ]))
    elements.append(kopf)
    elements.append(Spacer(1, 4 * mm))

    def szenario_zelle(name, punkte):
        inner = [[Paragraph(name, box_kopf)]]
        inner += [[Paragraph(f"– {p}", item)] for p in punkte]
        t = Table(inner, colWidths=[88 * mm])
        style = [
            ("BACKGROUND", (0, 0), (0, 0), ROT),
            ("BOX", (0, 0), (-1, -1), 1, DUNKELBLAU),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ]
        t.setStyle(TableStyle(style))
        return t

    grid = Table(
        [
            [szenario_zelle(*NOTROLLEN[0]), szenario_zelle(*NOTROLLEN[1])],
            [Spacer(1, 4 * mm), Spacer(1, 4 * mm)],
            [szenario_zelle(*NOTROLLEN[2]), szenario_zelle(*NOTROLLEN[3])],
        ],
        colWidths=[93 * mm, 93 * mm],
    )
    grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(grid)
    elements.append(Spacer(1, 5 * mm))

    elements.append(Paragraph("MERKSATZ: „Koordination, Kommunikation, Sicherheit zuerst!“", merksatz))
    elements.append(Spacer(1, 4 * mm))
    elements.append(_fusszeile(boot))

    doc.build(elements)
    return response
