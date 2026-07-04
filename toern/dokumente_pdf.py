"""Boots-Dokumente als PDF: Mayday-Plakat (fürs Funkgerät) und Notrollen-Plakat (Aushang)."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, portrait
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from boote.models import Boot
from utils.dokumente import DOKUMENT_MIT_UNTERSCHRIFT
from .models import Teilnahme

ROT = colors.HexColor("#B91C1C")
DUNKELBLAU = colors.HexColor("#1E3A5F")
GRAU = colors.HexColor("#666666")
HELLGRAU = colors.HexColor("#F3F4F6")


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
        rightMargin=15 * mm, leftMargin=15 * mm, topMargin=9 * mm, bottomMargin=7 * mm,
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
    elements.append(Spacer(1, 4 * mm))

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
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.white),
    ]))
    elements.append(daten)
    elements.append(Spacer(1, 4 * mm))

    # Schritt 1: DSC-Alarm (deutsche Anleitung)
    elements.append(Paragraph("SCHRITT 1 — DSC-SEENOTALARM AUSLÖSEN", box_kopf))
    elements.append(Spacer(1, 2 * mm))
    dsc_schritte = [
        "Sicherstellen, dass das Funkgerät <b>eingeschaltet</b> ist.",
        "Abdeckung über der <b>ROTEN DISTRESS-Taste</b> öffnen.",
        "ROTE DISTRESS-Taste <b>EINMAL drücken</b> und loslassen.",
        "Zur passenden Notfall-Meldung scrollen (FIRE = Feuer, SINKING = Sinken, MOB = Person über Bord …). "
        "Wird das übersprungen, sendet das Gerät einen allgemeinen Notalarm — das ist in Ordnung.",
        "ROTE DISTRESS-Taste <b>5 Sekunden gedrückt halten</b>, um den Alarm zu senden.",
        "<b>Höchstens 15 Sekunden</b> auf die Bestätigung warten (Anzeige auf dem Display), "
        "dann die folgende Meldung auf <b>KANAL 16</b> mit <b>HOHER SENDELEISTUNG (HIGH / 25 W)</b> absetzen.",
    ]
    dsc_stil = ParagraphStyle("dsc", fontSize=10, leading=13)
    dsc_tbl = Table(
        [[Paragraph(f"<b>{i}.</b>", dsc_stil), Paragraph(text, dsc_stil)]
         for i, text in enumerate(dsc_schritte, start=1)],
        colWidths=[8 * mm, 172 * mm],
    )
    dsc_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
    ]))
    elements.append(dsc_tbl)
    elements.append(Spacer(1, 4 * mm))

    # Schritt 2: Sprechfunk-Notruf — im internationalen englischen Original,
    # mit deutscher Lesehilfe unter jeder Zeile
    elements.append(Paragraph("SCHRITT 2 — SPRECHFUNK-NOTRUF (KANAL 16, ENGLISCH ABLESEN)", box_kopf))
    elements.append(Spacer(1, 2 * mm))

    englisch = ParagraphStyle("englisch", fontSize=13, leading=16, fontName="Helvetica-Bold")
    deutsch = ParagraphStyle("deutsch", fontSize=8.5, leading=10.5, textColor=GRAU)

    spruch_zeilen = [
        ("MAYDAY, MAYDAY, MAYDAY",
         None),
        (f"THIS IS {name_upper}, {name_upper}, {name_upper}",
         "Hier ist … (Schiffsname dreimal sprechen)"),
        (f"MAYDAY {name_upper}",
         "Mayday + Schiffsname einmal"),
        (f"MMSI {mmsi}",
         "MMSI-Nummer vorlesen"),
        ("MY POSITION IS …",
         "Meine Position: Breite / Länge vom GPS oder Kartenplotter ablesen — "
         "oder Peilung &amp; Abstand zu einem bekannten Punkt (z.B. Leuchtturm)"),
        ("WE ARE …",
         "Art der Notlage einsetzen: SINKING (wir sinken) · ON FIRE (Feuer an Bord) · "
         "MAN OVERBOARD (Person über Bord) · ADRIFT (manövrierunfähig)"),
        ("I REQUIRE IMMEDIATE ASSISTANCE",
         "Wir benötigen sofortige Hilfe"),
        (f"WE HAVE {personen_text} PERSONS ON BOARD",
         f"Wir haben {personen_text} Personen an Bord — Zahl auf Englisch sprechen"),
        ("ANY OTHER INFORMATION …",
         "Weitere Angaben, z.B. TYPE OF VESSEL: SAILING YACHT (Segelyacht) · HULL COLOUR (Rumpffarbe): WHITE (weiß)"),
        ("OVER",
         "Ende — auf Antwort warten, hörbereit bleiben"),
    ]
    spruch_rows = []
    for eng, ger in spruch_zeilen:
        zelle = [Paragraph(eng, englisch)]
        if ger:
            zelle.append(Paragraph(ger, deutsch))
        spruch_rows.append([zelle])
    spruch = Table(spruch_rows, colWidths=[180 * mm])
    spruch.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.5, ROT),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    elements.append(spruch)
    elements.append(Spacer(1, 3 * mm))

    elements.append(Paragraph(
        "Langsam und deutlich sprechen — einfach Zeile für Zeile ablesen. Keine Antwort? Notruf wiederholen. "
        "Entwarnung ebenfalls über Funk melden.",
        hinweis,
    ))
    elements.append(Spacer(1, 3 * mm))
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


# =========================
# CHECKLISTEN (Übernahme, Ablegen, Anlegen, Rückgabe)
# =========================

@login_required
def dokument_checkliste_pdf(request, boot_id, typ):
    from .dokumente_views import DOKUMENT_TYPEN_KEYS, get_or_create_dokument_vorlage

    boot = get_object_or_404(Boot, id=boot_id)
    if not _hat_dokument_zugang(request.user, boot):
        raise PermissionDenied
    if typ not in DOKUMENT_TYPEN_KEYS:
        raise PermissionDenied

    vorlage = get_or_create_dokument_vorlage(boot.toern, typ)
    typ_label = vorlage.get_typ_display()

    # Einträge nach Sektion gruppieren (Reihenfolge des ersten Auftretens)
    sektionen = {}
    for e in vorlage.eintraege.all():
        sektionen.setdefault(e.sektion, []).append(e.text)

    response = _pdf_response(f"{typ}_{boot.name.replace(' ', '_')}.pdf")
    doc = SimpleDocTemplate(
        response, pagesize=portrait(A4),
        rightMargin=14 * mm, leftMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
    )

    titel = ParagraphStyle("titel", fontSize=17, leading=21, fontName="Helvetica-Bold",
                           textColor=DUNKELBLAU)
    sub = ParagraphStyle("sub", fontSize=9, leading=12, textColor=GRAU)
    sektion_stil = ParagraphStyle("sektion", fontSize=10.5, leading=13, fontName="Helvetica-Bold",
                                  textColor=colors.white)
    item_stil = ParagraphStyle("item", fontSize=9.5, leading=12)
    klein = ParagraphStyle("klein", fontSize=7.5, leading=9, textColor=GRAU)

    elements = []

    toern = boot.toern
    charter = boot.charterunternehmen.name if boot.charterunternehmen else "—"
    elements.append(Paragraph(f"{typ_label} — {boot.name}", titel))
    elements.append(Spacer(1, 1.5 * mm))
    elements.append(Paragraph(
        f"{toern.titel} · {toern.startdatum.strftime('%d.%m.%Y')} – {toern.enddatum.strftime('%d.%m.%Y')}"
        f" &nbsp;|&nbsp; Charter: {charter}"
        f" &nbsp;|&nbsp; Hafen: {boot.hafen or '—'}"
        f" &nbsp;|&nbsp; Datum: ______________",
        sub,
    ))
    elements.append(Spacer(1, 4 * mm))

    # Tabelle: Checkbox | Punkt | Bemerkung/Zuständigkeit — Sektionen als Trennzeilen
    rows = [[
        "",
        Paragraph("<b>Punkt</b>", item_stil),
        Paragraph("<b>Bemerkung / Zuständigkeit</b>", item_stil),
    ]]
    stil = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 0), (-1, 0), HELLGRAU),
    ]
    for sektion, texte in sektionen.items():
        rows.append([Paragraph(sektion, sektion_stil), "", ""])
        zeile = len(rows) - 1
        stil.append(("BACKGROUND", (0, zeile), (-1, zeile), DUNKELBLAU))
        stil.append(("SPAN", (0, zeile), (-1, zeile)))
        for text in texte:
            rows.append(["", Paragraph(text, item_stil), ""])

    tbl = Table(rows, colWidths=[9 * mm, 108 * mm, 65 * mm], repeatRows=1)
    tbl.setStyle(TableStyle(stil))
    elements.append(tbl)

    if typ in DOKUMENT_MIT_UNTERSCHRIFT:
        elements.append(Spacer(1, 10 * mm))
        unterschrift = Table([
            [Paragraph("_______________________________", item_stil),
             Paragraph("_______________________________", item_stil)],
            [Paragraph("Ort, Datum, Unterschrift Charterbasis", klein),
             Paragraph("Ort, Datum, Unterschrift Skipper", klein)],
        ], colWidths=[91 * mm, 91 * mm])
        unterschrift.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        elements.append(unterschrift)

    elements.append(Spacer(1, 5 * mm))
    elements.append(_fusszeile(boot))

    doc.build(elements)
    return response
