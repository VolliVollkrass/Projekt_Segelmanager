"""Produktnamen für den Dubletten-Abgleich der Einkaufsliste vereinheitlichen.

Die Liste entsteht aus drei Quellen — Rezeptzutaten, Grundeinkauf-Vorlage und
manuellen Einträgen — die denselben Artikel unterschiedlich schreiben. Hier
wird ein Vergleichsschlüssel gebildet; der angezeigte Name bleibt unberührt.

GRUNDSATZ: lieber eine Dublette stehen lassen als zwei verschiedene Produkte
zusammenwerfen. Ein falsch zusammengeführter Posten verschwindet stillschweigend
vom Einkaufszettel und fällt erst im Hafen auf. Alles, was Sprachwissen braucht
(Karotte/Möhre, Toast/Toastbrot), gehört deshalb nicht hierher, sondern in die
KI-Vorschläge, die der Mensch bestätigt.
"""
import re

_UMLAUTE = str.maketrans({'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 's'})

# Trenner für Alternativen: "Gouda/Emmentaler", "Salami oder Schinken"
_ALTERNATIV = re.compile(r'\s+oder\s+|\s*/\s*', re.IGNORECASE)


def ohne_zusatz(name):
    """Klammerzusätze und Mehrfach-Leerzeichen entfernen — behält die Schreibweise.

    "Kartoffeln (klein gewürfelt)" → "Kartoffeln"
    Wird auch für die Kategorie-Erkennung genutzt: sonst schlägt
    "Olivenöl (nur falls der Speck sehr mager ist)" auf „Fleisch & Fisch" an.
    """
    if not name:
        return ''
    ohne = re.sub(r'\([^)]*\)', ' ', name)
    return re.sub(r'\s{2,}', ' ', ohne).strip(' ,;-')


def _entplural(wort):
    """Konservative Singularform: nur ein abschließendes -n abschneiden.

    "kartoffeln" → "kartoffel", "bananen" → "banane", "tomaten" → "tomate".
    Kurze Wörter bleiben unangetastet, damit aus "huhn" nicht "huh" wird.
    """
    if len(wort) > 4 and wort.endswith('n'):
        return wort[:-1]
    return wort


def normalisiere_produktname(name):
    """Vergleichsschlüssel für zwei Artikelnamen.

    Zwei Namen gelten als derselbe Artikel, wenn ihr Schlüssel übereinstimmt:

    >>> normalisiere_produktname("Kartoffeln (klein gewürfelt)")
    'kartoffel'
    >>> normalisiere_produktname("Kartoffeln")
    'kartoffel'

    Alternativen werden nur dann auf die erste gekürzt, wenn JEDE Alternative
    aus einem einzigen Wort besteht — "Gouda/Emmentaler" → 'gouda'. Bei
    "gekochter oder roher Schinken" wäre die erste Alternative das Adjektiv
    "gekochter"; solche Fälle bleiben unangetastet.
    """
    if not name:
        return ''

    kern = ohne_zusatz(name).lower().translate(_UMLAUTE)

    teile = [t.strip() for t in _ALTERNATIV.split(kern) if t.strip()]
    if len(teile) > 1 and all(' ' not in t for t in teile):
        kern = teile[0]

    kern = re.sub(r'[^\w\s-]', ' ', kern)
    woerter = [_entplural(w) for w in kern.split()]
    return ' '.join(woerter).strip()


def anzeigename(namen):
    """Aus mehreren Schreibweisen desselben Artikels die beste für die Anzeige.

    Der kürzeste Name ist in aller Regel der sauberste ("Kartoffeln" statt
    "Kartoffeln (klein gewürfelt)"). Bei Gleichstand entscheidet die
    Reihenfolge, damit das Ergebnis reproduzierbar bleibt.
    """
    return min(namen, key=lambda n: (len(n), list(namen).index(n)))


def varianten_hinweis(namen, haupt):
    """Die verworfenen Schreibweisen als Text — damit nichts unsichtbar wird."""
    andere = []
    for n in namen:
        if n != haupt and n not in andere:
            andere.append(n)
    return 'auch: ' + ', '.join(andere) if andere else ''
