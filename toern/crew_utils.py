CREWLISTE_FELDER = [
    ("first_name", "Vorname"),
    ("last_name", "Nachname"),
    ("telefonnummer", "Telefonnummer"),
    ("geburtsdatum", "Geburtsdatum"),
    ("geburtsort", "Geburtsort"),
    ("geburtsland", "Geburtsland"),
    ("passnummer", "Ausweis-/Passnummer"),
    ("nationalitaet", "Nationalitaet"),
    ("strasse", "Strasse"),
    ("plz", "Postleitzahl"),
    ("ort", "Wohnort"),
    ("land", "Land"),
]


def fehlende_crew_felder(user):
    return [label for attr, label in CREWLISTE_FELDER if not getattr(user, attr, None)]
