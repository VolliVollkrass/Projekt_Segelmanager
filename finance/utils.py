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


def berechne_salden(ausgaben, teilnahmen):
    """Netto-Saldo pro Teilnahme über alle Ausgaben.

    Positiv = hat mehr gezahlt als verbraucht (bekommt Geld),
    negativ = schuldet Geld.
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

    salden = []
    for eintrag in daten.values():
        eintrag["saldo"] = eintrag["gezahlt"] - eintrag["anteil"]
        eintrag["gezahlt"] = eintrag["gezahlt"].quantize(CENT, rounding=ROUND_HALF_UP)
        eintrag["anteil"] = eintrag["anteil"].quantize(CENT, rounding=ROUND_HALF_UP)
        salden.append(eintrag)

    salden.sort(key=lambda e: e["saldo"], reverse=True)
    return salden


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
