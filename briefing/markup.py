"""Leichtgewichtiges Markup für Briefing-Bausteine.

Eine einzige Quelle der Wahrheit für die Syntax: `parse()` zerlegt den Text
eines Bausteins in Blöcke, `als_html()` rendert sie für Web-Ansicht und
Live-Vorschau. Das PDF (toern/briefing_pdf.py) rendert dieselben Blöcke mit
ReportLab. Damit gibt es keine zweite Parser-Implementierung, die auseinander-
laufen könnte — auch die Vorschau im Bearbeiten-Formular geht über diesen Code.

Syntax (jeweils am Zeilenanfang, alle Zeichen sind Nicht-Buchstaben, damit
normaler Fließtext nie versehentlich ausgezeichnet wird):

    !  Warnung        rote Box — für alles, wo Fehler wehtun
    >  Hinweis        eingefärbte Box — Ergänzungen, Tipps
    *  Merksatz       dunkelblauer Balken — der eine Satz, der hängenbleiben soll
    -  Aufzählung     Punkt in einer Liste
    |  Tabelle        Spalten mit | getrennt: | Kommando | Antwort |

Aufeinanderfolgende Zeilen mit demselben Präfix werden zu einem Block
zusammengefasst. Alles ohne Präfix ist Fließtext; Leerzeilen trennen Absätze.
"""
from django.utils.html import escape

WARNUNG = "warnung"
HINWEIS = "hinweis"
MERKSATZ = "merksatz"
LISTE = "liste"
TABELLE = "tabelle"
ABSATZ = "absatz"

PRAEFIXE = {
    "!": WARNUNG,
    ">": HINWEIS,
    "*": MERKSATZ,
    "-": LISTE,
    "|": TABELLE,
}

# Für die Toolbar im Formular und die Syntax-Hilfe
BLOCK_LABELS = [
    ("!", "Warnung", WARNUNG),
    (">", "Hinweis", HINWEIS),
    ("*", "Merksatz", MERKSATZ),
    ("-", "Aufzählung", LISTE),
    ("|", "Tabelle", TABELLE),
]


def _zeilen_typ(zeile):
    """(typ, restinhalt) für eine Zeile. Präfix muss von Leerzeichen gefolgt sein
    (außer bei Tabellen, wo | direkt die Spalte eröffnet)."""
    gestrippt = zeile.strip()
    if not gestrippt:
        return None, ""
    zeichen = gestrippt[0]
    typ = PRAEFIXE.get(zeichen)
    if typ is None:
        return ABSATZ, gestrippt
    if typ == TABELLE:
        return TABELLE, gestrippt
    rest = gestrippt[1:]
    # "!Achtung" und "! Achtung" beide erlauben, aber "*Sternchen im Text" nicht
    # fälschlich als Merksatz lesen, wenn direkt ein Buchstabe folgt? — doch,
    # das ist gewollt: das Präfix steht immer am Zeilenanfang und ist eindeutig.
    return typ, rest.strip()


def _tabellenzeile(inhalt):
    """| a | b | -> ['a', 'b']"""
    zellen = [z.strip() for z in inhalt.strip().strip("|").split("|")]
    return zellen


def parse(text):
    """Text -> Liste von Blöcken.

    Jeder Block ist ein dict mit 'typ' und je nach Typ:
      absatz/warnung/hinweis/merksatz -> 'zeilen' (Liste von Strings)
      liste                           -> 'punkte' (Liste von Strings)
      tabelle                         -> 'zeilen' (Liste von Zell-Listen)
    """
    bloecke = []
    aktueller_typ = None
    puffer = []

    def abschliessen():
        nonlocal aktueller_typ, puffer
        if aktueller_typ is None or not puffer:
            aktueller_typ, puffer = None, []
            return
        if aktueller_typ == LISTE:
            bloecke.append({"typ": LISTE, "punkte": puffer})
        elif aktueller_typ == TABELLE:
            bloecke.append({"typ": TABELLE, "zeilen": [_tabellenzeile(z) for z in puffer]})
        else:
            bloecke.append({"typ": aktueller_typ, "zeilen": puffer})
        aktueller_typ, puffer = None, []

    for zeile in (text or "").splitlines():
        typ, inhalt = _zeilen_typ(zeile)
        if typ is None:                 # Leerzeile beendet jeden Block
            abschliessen()
            continue
        if typ != aktueller_typ:
            abschliessen()
            aktueller_typ = typ
        puffer.append(inhalt)

    abschliessen()
    return bloecke


# ---------------------------------------------------------------- HTML-Ausgabe

_BOX_KLASSEN = {
    WARNUNG: ("border-error/40 bg-error/5", "text-error", "Warnung"),
    HINWEIS: ("border-secondary/40 bg-secondary/5", "text-secondary", "Hinweis"),
}


def als_html(text):
    """Gerendertes HTML für Detailansicht und Live-Vorschau."""
    teile = []
    for block in parse(text):
        typ = block["typ"]

        if typ == ABSATZ:
            inhalt = "<br>".join(escape(z) for z in block["zeilen"])
            teile.append(f'<p class="text-sm leading-relaxed mb-3">{inhalt}</p>')

        elif typ in (WARNUNG, HINWEIS):
            rahmen, farbe, label = _BOX_KLASSEN[typ]
            inhalt = "<br>".join(escape(z) for z in block["zeilen"])
            teile.append(
                f'<div class="border-l-4 {rahmen} rounded-r-lg px-4 py-3 mb-3">'
                f'<p class="text-xs font-bold uppercase tracking-widest {farbe} mb-1">{label}</p>'
                f'<p class="text-sm leading-relaxed">{inhalt}</p></div>'
            )

        elif typ == MERKSATZ:
            inhalt = "<br>".join(escape(z) for z in block["zeilen"])
            teile.append(
                f'<div class="bg-primary text-primary-content rounded-lg px-4 py-3 mb-3">'
                f'<p class="text-sm font-bold leading-relaxed">{inhalt}</p></div>'
            )

        elif typ == LISTE:
            punkte = "".join(
                f'<li class="text-sm leading-relaxed">{escape(p)}</li>' for p in block["punkte"]
            )
            teile.append(f'<ul class="list-disc pl-5 space-y-1 mb-3">{punkte}</ul>')

        elif typ == TABELLE:
            zeilen = block["zeilen"]
            if not zeilen:
                continue
            kopf, rest = zeilen[0], zeilen[1:]
            kopf_html = "".join(
                f'<th class="text-left px-3 py-2 font-semibold">{escape(z)}</th>' for z in kopf
            )
            rest_html = "".join(
                "<tr>" + "".join(
                    f'<td class="px-3 py-2 align-top">{escape(z)}</td>' for z in zeile
                ) + "</tr>"
                for zeile in rest
            )
            teile.append(
                '<div class="overflow-x-auto mb-3"><table class="table table-sm w-full">'
                f'<thead class="bg-base-200"><tr>{kopf_html}</tr></thead>'
                f'<tbody>{rest_html}</tbody></table></div>'
            )

    return "".join(teile)
