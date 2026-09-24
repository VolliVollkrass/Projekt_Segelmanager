"""Dubletten in der Einkaufsliste finden und zusammenführen.

Die Liste speist sich aus Rezeptzutaten, der Grundeinkauf-Vorlage und manuellen
Einträgen. Dieselbe Ware steht dadurch mehrfach drauf — mal identisch benannt
(„Salami" aus Rezept und Grundeinkauf), mal mit Zusatz („Kartoffeln" vs.
„Kartoffeln (klein gewürfelt)").

Hier wird nur GEPLANT, nicht geändert: `plane_zusammenfuehrung` liefert die
Gruppen, die Views zeigen sie als Vorschau und wenden sie erst nach Bestätigung
an. Was zusammengehört, entscheidet `utils.produktnamen` bewusst konservativ.
"""
from utils.produktnamen import anzeigename, normalisiere_produktname, varianten_hinweis
from utils.rezept_skalierung import summiere_mengen, zerlege_mengen

# Welche Quelle sich durchsetzt, wenn Einträge verschiedener Herkunft
# verschmelzen: Manuell gewinnt, damit der zusammengeführte Posten beim
# nächsten „Generieren" nicht gelöscht wird — jemand hat ihn von Hand erfasst.
_QUELLE_RANG = {'manuell': 0, 'rezept': 1, 'standard': 2}


class Gruppe:
    """Ein Produkt und die Zeilen, die dafür auf der Liste stehen."""

    def __init__(self, schluessel, eintraege):
        self.schluessel = schluessel
        self.eintraege = eintraege
        namen = [e.name for e in eintraege]
        self.name = anzeigename(namen)
        self.hinweis = varianten_hinweis(namen, self.name)
        self.menge = summiere_mengen([e.menge for e in eintraege])
        # Der Eintrag, der bestehen bleibt: der mit dem Anzeigenamen, sonst der erste
        self.behalten = next((e for e in eintraege if e.name == self.name), eintraege[0])
        self.entfernen = [e for e in eintraege if e.id != self.behalten.id]
        self.quelle = min((e.quelle for e in eintraege), key=lambda q: _QUELLE_RANG.get(q, 9))
        # Eigene Menge des zusammengeführten Postens: nur die Anteile, die
        # jemand von Hand erfasst hat. Rezept- und Grundeinkauf-Anteile werden
        # beim nächsten Generieren ohnehin neu berechnet — stünden sie hier
        # drin, würden sie doppelt gezählt.
        self.manuelle_menge = summiere_mengen([
            teil
            for e in eintraege if e.quelle == 'manuell'
            for teil in zerlege_mengen(e.manuelle_menge or e.menge)
        ])
        self.erledigt = any(e.erledigt for e in eintraege)
        self.einkaufer_id = next((e.einkaufer_id for e in eintraege if e.einkaufer_id), None)

    @property
    def rezept_info(self):
        """Rezept-Hinweise aller Zeilen plus die verworfenen Schreibweisen."""
        teile = []
        for e in self.eintraege:
            for stueck in (e.rezept_info or '').split(', '):
                if stueck and stueck not in teile:
                    teile.append(stueck)
        text = ', '.join(teile)
        if self.hinweis:
            text = f"{text} · {self.hinweis}" if text else self.hinweis
        return text[:500]

    def als_json(self):
        """Für die Vorschau im Browser."""
        return {
            'name': self.name,
            'menge': self.menge,
            'anzahl': len(self.eintraege),
            'zeilen': [
                {'id': e.id, 'name': e.name, 'menge': e.menge, 'quelle': e.quelle,
                 'erledigt': e.erledigt}
                for e in self.eintraege
            ],
        }


def plane_zusammenfuehrung(eintraege):
    """Gruppen mit mehr als einer Zeile — nach Anzeigename sortiert.

    Erledigte und offene Zeilen desselben Produkts kommen zusammen; die
    zusammengeführte Zeile gilt als erledigt, sobald eine der Zeilen erledigt
    war (sonst stünde plötzlich wieder etwas offen, das schon im Wagen liegt).
    """
    nach_schluessel = {}
    for e in eintraege:
        schluessel = normalisiere_produktname(e.name)
        if not schluessel:
            continue
        nach_schluessel.setdefault(schluessel, []).append(e)

    gruppen = [
        Gruppe(schluessel, liste)
        for schluessel, liste in nach_schluessel.items()
        if len(liste) > 1
    ]
    gruppen.sort(key=lambda g: g.name.lower())
    return gruppen


def fuehre_zusammen(gruppen):
    """Wendet die geplanten Gruppen an. Gibt die Zahl entfernter Zeilen zurück.

    Der Aufrufer legt VORHER einen Snapshot an — ohne den darf diese Funktion
    nicht laufen.
    """
    entfernt = 0
    for g in gruppen:
        behalten = g.behalten
        behalten.name = g.name
        behalten.menge = g.menge
        behalten.quelle = g.quelle
        behalten.manuelle_menge = g.manuelle_menge
        behalten.erledigt = g.erledigt
        behalten.rezept_info = g.rezept_info
        if g.einkaufer_id and not behalten.einkaufer_id:
            behalten.einkaufer_id = g.einkaufer_id
        behalten.save()

        for e in g.entfernen:
            e.delete()
            entfernt += 1
    return entfernt
