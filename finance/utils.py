from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


# Stichwort → Kategorie-Schlüssel (siehe TopfAusgabe.KATEGORIE_CHOICES).
# Reihenfolge egal; der erste Treffer im Text gewinnt nach Prioritätsliste unten.
_KATEGORIE_STICHWORTE = [
    ("versicherung", ["versicherung", "haftpflicht", "unfall", "kaution", "police"]),
    ("treibstoff", ["diesel", "bootstank", "tanken schiff", "schiffsdiesel", "bordtank"]),
    ("anreise", [
        "vignette", "maut", "autobahn", "fähre", "faehre", "parken", "parkplatz",
        "hotel", "übernachtung", "uebernachtung", "unterkunft", "benzin", "sprit auto",
        "flug", "bahn", "zug", "transfer", "auto",
    ]),
    ("hafen", [
        "hafen", "marina", "liegeplatz", "liege", "steg", "strom", "wasser", "müll",
        "muell", "kurtaxe", "touristensteuer", "nationalpark", "kornati", "krka",
        "einklarier", "leuchtturm", "abgabe", "gebühr", "gebuehr",
    ]),
    ("charter", [
        "endreinigung", "reinigung", "gasflasche", "gas", "bettwäsche", "bettwaesche",
        "handtuch", "selbstbehalt", "schaden", "charter", "außenborder", "aussenborder",
        "dinghy",
    ]),
    ("verpflegung", [
        "restaurant", "essen", "konoba", "trinkgeld", "supermarkt", "lebensmittel",
        "getränk", "getraenk", "einkauf", "kaffee", "eis", "bäcker", "baecker", "markt",
    ]),
    ("crew", ["shirt", "t-shirt", "tshirt", "fahne", "flagge", "gimmick", "crew-shirt"]),
    ("ausruestung", [
        "reparatur", "ersatzteil", "material", "ausrüstung", "ausruestung", "apotheke",
        "medikament", "seekarte", "revierführer", "revierfuehrer", "karte", "werkzeug",
    ]),
]


def rate_kategorie(beschreibung):
    """Schlägt anhand von Stichwörtern in der Beschreibung eine Kategorie vor.
    Kein Treffer → 'sonstiges'."""
    text = (beschreibung or "").lower()
    for schluessel, woerter in _KATEGORIE_STICHWORTE:
        if any(w in text for w in woerter):
            return schluessel
    return "sonstiges"


def berechne_salden(ausgaben, teilnahmen, umlage_anteile=()):
    """Netto-Saldo pro Teilnahme über alle Ausgaben.

    Positiv = hat mehr gezahlt als verbraucht (bekommt Geld),
    negativ = schuldet Geld.
    `umlage_anteile`: Anteile an Törn-Umlagen, die über diese Bootskasse
    laufen (Zahler und Person auf demselben Boot). Sie zählen wie eine
    Ausgabe mit festem Betrag pro Person; Anzahlungen kommen über
    `umlage_zahlungen` als geflossenes Geld dazu.
    Rückgabe: Liste von Dicts {teilnahme, gezahlt, anteil, saldo},
    sortiert nach Saldo absteigend.
    """
    daten = {
        t.id: {"teilnahme": t, "gezahlt": Decimal("0"), "anteil": Decimal("0")}
        for t in teilnahmen
    }

    for ausgabe in ausgaben:
        beteiligte = list(ausgabe.beteiligt.all())
        if not beteiligte:
            continue

        if ausgabe.bezahlt_von_id in daten:
            daten[ausgabe.bezahlt_von_id]["gezahlt"] += ausgabe.betrag

        # Anteile mit voller Decimal-Präzision — gerundet wird erst am Ende
        anteil = ausgabe.betrag / len(beteiligte)
        for teilnahme in beteiligte:
            if teilnahme.id in daten:
                daten[teilnahme.id]["anteil"] += anteil

    for a in umlage_anteile:
        if a.umlage.bezahlt_von_id in daten and a.teilnahme_id in daten:
            daten[a.umlage.bezahlt_von_id]["gezahlt"] += a.anteil
            daten[a.teilnahme_id]["anteil"] += a.anteil

    salden = []
    for eintrag in daten.values():
        eintrag["saldo"] = eintrag["gezahlt"] - eintrag["anteil"]
        eintrag["gezahlt"] = eintrag["gezahlt"].quantize(CENT, rounding=ROUND_HALF_UP)
        eintrag["anteil"] = eintrag["anteil"].quantize(CENT, rounding=ROUND_HALF_UP)
        salden.append(eintrag)

    salden.sort(key=lambda e: e["saldo"], reverse=True)
    return salden


def wende_zahlungen_an(salden, zahlungen):
    """Bereits geflossene Ausgleichszahlungen in die Salden einrechnen.

    Wer bezahlt hat, hat seine Schuld getilgt — sein Saldo steigt um den
    Betrag; beim Empfänger sinkt er entsprechend. Dadurch verschwindet der
    zugehörige Vorschlag aus `berechne_ausgleich`, ohne dass irgendwo ein
    „erledigt"-Häkchen an einem Vorschlag kleben müsste, den es als Datensatz
    gar nicht gibt.
    """
    nach_id = {e["teilnahme"].id: e for e in salden}
    for zahlung in zahlungen:
        if zahlung.von_id in nach_id:
            nach_id[zahlung.von_id]["saldo"] += zahlung.betrag
        if zahlung.an_id in nach_id:
            nach_id[zahlung.an_id]["saldo"] -= zahlung.betrag

    salden.sort(key=lambda e: e["saldo"], reverse=True)
    return salden


@dataclass
class _Zahlung:
    von_id: int
    an_id: int
    betrag: Decimal


def umlage_zahlungen(umlage_anteile):
    """Schon geflossenes Geld zu Umlage-Anteilen, die über die Bootskasse
    laufen — im Format, das `wende_zahlungen_an` versteht.

    Die Anzahlung ist an den Zahler gegangen. Wurde ein Anteil schon in der
    Umlage als beglichen markiert (bevor er über die Bootskasse lief), ist
    auch der Rest geflossen — sonst würde er hier ein zweites Mal verlangt.
    """
    zahlungen = []
    for a in umlage_anteile:
        if a.ist_zahler:
            continue
        betrag = a.anteil if a.beglichen_am else a.schon_gegeben
        if betrag:
            zahlungen.append(_Zahlung(a.teilnahme_id, a.umlage.bezahlt_von_id, betrag))
    return zahlungen


def berechne_ausgleich(salden):
    """Minimale Überweisungen zum Ausgleich der Salden (Greedy).

    Matcht jeweils den größten Schuldner mit dem größten Gläubiger.
    Rückgabe: Liste von Dicts {von, an, betrag} (von/an = Teilnahme).
    """
    glaeubiger = [
        [e["teilnahme"], e["saldo"]] for e in salden if e["saldo"] > CENT / 2
    ]
    schuldner = [
        [e["teilnahme"], -e["saldo"]] for e in salden if e["saldo"] < -CENT / 2
    ]
    glaeubiger.sort(key=lambda x: x[1], reverse=True)
    schuldner.sort(key=lambda x: x[1], reverse=True)

    transfers = []
    gi, si = 0, 0
    while gi < len(glaeubiger) and si < len(schuldner):
        betrag = min(glaeubiger[gi][1], schuldner[si][1])
        gerundet = betrag.quantize(CENT, rounding=ROUND_HALF_UP)
        if gerundet >= CENT:
            transfers.append({
                "von": schuldner[si][0],
                "an": glaeubiger[gi][0],
                "betrag": gerundet,
            })

        glaeubiger[gi][1] -= betrag
        schuldner[si][1] -= betrag
        if glaeubiger[gi][1] <= CENT / 2:
            gi += 1
        if schuldner[si][1] <= CENT / 2:
            si += 1

    return transfers


def verteile_umlage(betrag, teilnehmer_ids, extras=None):
    """Verteilt eine Umlage auf die Teilnehmer.

    Extras (z. B. Haralds Wein) stecken schon im Gesamtbetrag: Sie werden
    vorab herausgerechnet und nur der jeweiligen Person zugeschlagen, der Rest
    geht zu gleichen Teilen an alle. Übrige Cents bekommen die ersten in der
    Liste, damit die Summe exakt dem Betrag entspricht.

    Rückgabe: {teilnehmer_id: anteil}. ValueError, wenn niemand ausgewählt ist
    oder die Extras den Betrag übersteigen.
    """
    extras = extras or {}
    if not teilnehmer_ids:
        raise ValueError("Bitte mindestens eine Person auswählen.")
    summe_extras = sum((extras.get(i, Decimal("0")) for i in teilnehmer_ids), Decimal("0"))
    rest_cent = int(((betrag - summe_extras) * 100).to_integral_value(rounding=ROUND_HALF_UP))
    if rest_cent < 0:
        raise ValueError("Die Extras sind zusammen höher als der Gesamtbetrag.")

    basis, uebrig = divmod(rest_cent, len(teilnehmer_ids))
    anteile = {}
    for pos, tid in enumerate(teilnehmer_ids):
        cent = basis + (1 if pos < uebrig else 0)
        anteile[tid] = (Decimal(cent) / 100).quantize(CENT) + extras.get(tid, Decimal("0"))
    return anteile
