"""Skalierung freier Mengenangaben aus Rezepten ("250g", "ca. 1 kg", "½ Bund", "1/2 TL", "2-3 EL").

Wird vom Einzel-Rezept-PDF (rezepte/views.py) und vom Kochplan-PDF (toern/views.py) genutzt.
"""
import re

_UNICODE_BRUECHE = {'½': 0.5, '⅓': 1 / 3, '⅔': 2 / 3, '¼': 0.25, '¾': 0.75, '⅛': 0.125}


def _fmt_zahl(n):
    if n != n:  # NaN guard
        return ""
    if n == int(n):
        return str(int(n))
    return str(round(n, 1)).replace('.', ',')


def parse_menge(menge):
    """Zerlegt eine Mengenangabe in (zahl, einheit, ist_ca) — None wenn nicht parsebar.

    "250 g" → (250.0, "g", False) · "ca. 1,5 kg" → (1.5, "kg", True) ·
    "½ Bund" → (0.5, "Bund", False) · "1/2 TL" → (0.5, "TL", False) ·
    "2-3 EL" → (3.0, "EL", True)  (Bereich: obere Grenze, als ca. markiert)
    """
    if not menge:
        return None
    menge = menge.strip()

    ist_ca = False
    prefix_m = re.match(r'^(ca\.?|etwa|gut|knapp)\s+(.+)$', menge, re.IGNORECASE)
    if prefix_m:
        ist_ca = True
        menge = prefix_m.group(2)

    uni_m = re.match(r'^(\d+)?\s*([½⅓⅔¼¾⅛])\s*(.*)$', menge)
    if uni_m:
        zahl = float(uni_m.group(1) or 0) + _UNICODE_BRUECHE[uni_m.group(2)]
        return (zahl, uni_m.group(3).strip(), ist_ca)

    frac_m = re.match(r'^(\d+)\s*/\s*(\d+)\s*(.*)$', menge)
    if frac_m and int(frac_m.group(2)) != 0:
        return (int(frac_m.group(1)) / int(frac_m.group(2)), frac_m.group(3).strip(), ist_ca)

    range_m = re.match(r'^(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)\s*(.*)$', menge)
    if range_m:
        hi = float(range_m.group(2).replace(',', '.'))
        return (hi, range_m.group(3).strip(), True)

    single_m = re.match(r'^(\d+(?:[.,]\d+)?)\s*(.*)$', menge)
    if single_m:
        return (float(single_m.group(1).replace(',', '.')), single_m.group(2).strip(), ist_ca)

    return None


def summiere_mengen(menge_list):
    """Fasst Mengenangaben derselben Zutat zusammen (für die Einkaufsliste).

    Parsebare Angaben werden pro Einheit summiert ("250 g" + "ca. 1,5 kg×parse" …),
    nicht parsebare ("nach Belieben") bleiben als Text erhalten.
    """
    totals = {}   # einheit -> [summe, ist_ca]
    leftovers = []
    for raw in menge_list:
        if not raw:
            continue
        parsed = parse_menge(raw)
        if parsed:
            zahl, einheit, ist_ca = parsed
            eintrag = totals.setdefault(einheit, [0.0, False])
            eintrag[0] += zahl
            eintrag[1] = eintrag[1] or ist_ca
        else:
            raw = raw.strip()
            if raw not in leftovers:
                leftovers.append(raw)
    parts = [
        f"{'ca. ' if ist_ca else ''}{_fmt_zahl(summe)} {einheit}".strip()
        for einheit, (summe, ist_ca) in totals.items()
    ]
    parts += leftovers
    return " + ".join(parts)


def skaliere_menge(menge, faktor):
    """Multipliziert die Zahl in einer Mengenangabe mit `faktor`.

    Unterstützt: führende Zahl ("250g"), Dezimalzahl ("0,5 Zitrone"),
    Bereich ("2-3 EL"), Unicode-Bruch ("½ Bund", "1½ EL"), ASCII-Bruch ("1/2 TL")
    sowie Präfixe wie "ca.", "etwa", "gut", "knapp".
    Nicht parsebare Angaben ("nach Belieben", "etwas") bleiben unverändert.
    """
    if not menge:
        return ""
    menge = menge.strip()
    if faktor == 1:
        return menge

    # Präfix wie "ca." erhalten und dahinter weiterparsen
    prefix = ""
    prefix_m = re.match(r'^(ca\.?|etwa|gut|knapp)\s+(.+)$', menge, re.IGNORECASE)
    if prefix_m:
        prefix, menge = prefix_m.group(1) + " ", prefix_m.group(2)

    # Unicode-Bruch: "½ Bund", "1½ EL"
    uni_m = re.match(r'^(\d+)?\s*([½⅓⅔¼¾⅛])(.*)$', menge)
    if uni_m:
        zahl = float(uni_m.group(1) or 0) + _UNICODE_BRUECHE[uni_m.group(2)]
        return f"{prefix}{_fmt_zahl(zahl * faktor)}{uni_m.group(3)}"

    # ASCII-Bruch: "1/2 TL"
    frac_m = re.match(r'^(\d+)\s*/\s*(\d+)(.*)$', menge)
    if frac_m and int(frac_m.group(2)) != 0:
        zahl = int(frac_m.group(1)) / int(frac_m.group(2))
        return f"{prefix}{_fmt_zahl(zahl * faktor)}{frac_m.group(3)}"

    # Bereich: "2-3 EL", "2–3"
    range_m = re.match(r'^(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)(.*)$', menge)
    if range_m:
        lo = float(range_m.group(1).replace(',', '.')) * faktor
        hi = float(range_m.group(2).replace(',', '.')) * faktor
        return f"{prefix}{_fmt_zahl(lo)}–{_fmt_zahl(hi)}{range_m.group(3)}"

    # Einzelne Zahl am Anfang: "250g", "0,5 Zitrone"
    single_m = re.match(r'^(\d+(?:[.,]\d+)?)(.*)$', menge)
    if single_m:
        zahl = float(single_m.group(1).replace(',', '.')) * faktor
        return f"{prefix}{_fmt_zahl(zahl)}{single_m.group(2)}"

    return prefix + menge
