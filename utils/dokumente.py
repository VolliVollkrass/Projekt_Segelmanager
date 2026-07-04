"""Standard-Inhalte für die editierbaren Boots-Checklisten (Dokumente-Tab).

Struktur: typ → Liste von (Sektion, [Einträge]).
"""

DOKUMENT_TYPEN = [
    ('uebernahme', 'Charterübernahme'),
    ('ablegen', 'Bevor wir ablegen'),
    ('anlegen', 'Nach dem Anlegen'),
    ('rueckgabe', 'Rückgabe'),
]

# Übernahme + Rückgabe bekommen im PDF Unterschriftenzeilen
DOKUMENT_MIT_UNTERSCHRIFT = ('uebernahme', 'rueckgabe')

DOKUMENT_DEFAULTS = {
    'uebernahme': [
        ("Papiere & Formales", [
            "Chartervertrag an Bord",
            "Schiffspapiere / Zulassung",
            "Versicherungsnachweis",
            "Crewliste abgegeben",
            "Kaution hinterlegt",
            "Übernahmeprotokoll der Basis erhalten",
        ]),
        ("Sicherheitsausrüstung", [
            "Rettungswesten (Anzahl passend zur Crew)",
            "Lifebelts / Sorgleinen",
            "Rettungsinsel (Prüfdatum!)",
            "Rettungsring mit Licht",
            "Feuerlöscher (Prüfdatum, Standorte)",
            "Löschdecke",
            "Erste-Hilfe-Kasten",
            "Signalmittel (Prüfdatum)",
            "EPIRB",
            "Nebelhorn",
            "Notpinne",
            "Bolzenschneider",
        ]),
        ("Deck & Rigg", [
            "Segelzustand Groß / Genua",
            "Reffanlage",
            "Fallen & Schoten",
            "Winschen + Kurbeln",
            "Anker + Kettenlänge",
            "Festmacher (Anzahl)",
            "Fender (Anzahl)",
            "Bootshaken",
            "Sprayhood / Bimini",
            "Badeleiter",
            "Dingi + Außenborder",
        ]),
        ("Motor & Technik", [
            "Motorstunden notieren",
            "Ölstand",
            "Kühlwasser / Impeller",
            "Keilriemen",
            "Tankfüllstand Diesel",
            "Batterien / Ladezustand",
            "Landstromkabel",
            "Bugstrahlruder",
            "Gasanlage + Reserveflasche",
            "Seeventile zeigen lassen",
        ]),
        ("Navigation", [
            "Plotter / GPS",
            "Log / Lot / Wind",
            "Funkgerät-Check",
            "Kompass",
            "Seekarten Revier",
            "Hafenhandbuch",
            "Fernglas",
        ]),
        ("Unter Deck", [
            "Wassertanks voll",
            "Warmwasser / Boiler",
            "Toiletten + Fäkalientank",
            "Kühlschrank",
            "Herd / Backofen",
            "Bilge trocken",
            "Inventarliste komplett",
            "Polster / Bettzeug",
        ]),
        ("Schäden & Abschluss", [
            "Vorschäden dokumentieren (Fotos!)",
            "Unterwasserschiff / Kiel geklärt",
            "Übernahmeprotokoll unterschrieben",
        ]),
    ],
    'ablegen': [
        ("Pantry", [
            "Abwasch gemacht, Pantry & Salon krängungssicher aufgeräumt",
            "Schubladen und Schränke geschlossen",
            "Gashahn geschlossen",
            "Getränke für unterwegs bereit",
        ]),
        ("Unter Deck", [
            "Alle Luken dicht",
            "Seeventile geschlossen / offen wie benötigt",
            "Bilge gecheckt",
            "Batterie gecheckt",
        ]),
        ("Persönliche Vorbereitung", [
            "Persönliche Sachen in Kabine und Salon krängungssicher verstaut",
            "Rettungswesten und Lifebelts griffbereit",
            "Kleidung und Schuhe für die nächsten Stunden richtig gewählt",
            "Sonnencreme, Sonnenhut, Sonnenbrille",
            "Segelhandschuhe bereit",
        ]),
        ("Kartentisch & Motor", [
            "Hafengebühren bezahlt, Schiffspapiere an Bord",
            "Wetter gecheckt: Luftdruck, Wind (Stärke, Richtung), Bewölkung",
            "Zielort gewählt, Route geplant",
            "Elektrik eingeschaltet: Navigation, Plotter, Tracking, Funk",
            "Kartentisch aufgeräumt, Seekarten bereit",
            "Logbuch bereit",
            "Motor kontrolliert: Ölstand, kein Öl ausgetreten",
            "Seeventil für Kühlwasser offen",
        ]),
        ("Auf Deck", [
            "Schiff zum Segeln bereit (Segel, Großfall, Leinen, Instrumenten-Abdeckungen)",
            "Leinen bereit zum Auslaufen",
            "Wäsche aufgeräumt",
            "Landstromkabel abgehängt und verstaut",
            "Wasser aufgefüllt",
            "Dingi versorgt / festgezurrt",
            "Im Cockpit alles krängungssicher verstaut",
        ]),
    ],
    'anlegen': [
        ("Nach dem Anlegen", [
            "Leinen + Springs kontrolliert",
            "Fender richtig gesetzt",
            "Motor aus, Kraftstoffhahn zu",
            "Landstrom angeschlossen",
            "Elektrik / Instrumente aus",
            "Seeventile geschlossen",
            "Logbuch vervollständigt",
            "Segel aufgeklart / Persenning drauf",
            "Hafengebühr geklärt",
            "Boot aufgeklart",
            "Müll entsorgt",
        ]),
    ],
    'rueckgabe': [
        ("Rückgabe", [
            "Tank voll (Beleg aufheben!)",
            "Fäkalientank geleert",
            "Boot besenrein",
            "Inventar vollständig",
            "Schäden gemeldet",
            "Persönliche Sachen von Bord",
            "Müll entsorgt",
            "Rückgabeprotokoll unterschrieben",
            "Kaution zurückerhalten",
        ]),
    ],
}
