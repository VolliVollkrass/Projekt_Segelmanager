def user_profil_fortschritt(user):
    """Returns profile completeness as integer 0–100."""
    felder = [
        user.first_name,
        user.last_name,
        user.geburtsdatum,
        user.nationalitaet,
        user.passnummer,
        user.strasse,
        user.plz,
        user.ort,
        user.telefonnummer,
        user.profilbild,
    ]
    gefuellt = sum(1 for f in felder if f)
    return int((gefuellt / len(felder)) * 100)
