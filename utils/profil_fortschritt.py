def teilnahme_fortschritt(teilnahme):

    user = teilnahme.user

    required_fields = [
        user.first_name,
        user.last_name,
        user.geburtsdatum,
        user.nationalitaet,
        user.passnummer,
    ]

    optional_fields = [
        user.strasse,
        user.plz,
        user.ort,
        user.telefonnummer,
        teilnahme.notfallkontakt_name,
        teilnahme.notfallkontakt_telefon,
        teilnahme.notfallkontakt_email,
        teilnahme.allergien,
        teilnahme.essgewohnheiten,
        teilnahme.tshirt_groesse,
    ]

    filled = (
        sum(1 for f in required_fields if f) +
        sum(1 for f in optional_fields if f)
    )

    total = len(required_fields) + len(optional_fields)

    return int((filled / total) * 100)