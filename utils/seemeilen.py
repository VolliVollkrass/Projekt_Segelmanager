"""Seemeilen-basierte Erfahrungsbestimmung für die Auto-Zuteilung.

Gesamt-Seemeilen = Summe aus bestätigten Törn-Teilnahmen (individuelle Meilen,
sonst Boot-Standard — gleiche Logik wie im Profil) + manuelles Seemeilen-Logbuch.
"""
from django.db.models import Sum


def stufe_aus_meilen(meilen):
    """Seemeilen → Erfahrungsstufe 1–5 (logarithmisch gebündelt: die ersten
    Meilen zählen viel, ab ~3000 sm macht mehr keinen Unterschied)."""
    if meilen < 100:
        return 1
    if meilen < 500:
        return 2
    if meilen < 1500:
        return 3
    if meilen < 3000:
        return 4
    return 5


def erfahrungs_stufe(meilen, selbsteinschaetzung):
    """Kombinierte Stufe: Maximum aus Seemeilen-Stufe und Selbsteinschätzung.

    Wer (noch) keine Meilen im System hat, aber sich als erfahren einschätzt,
    gilt nicht als Landratte — und umgekehrt kann niemand seine erfassten
    Meilen durch Tiefstapeln verstecken.
    """
    try:
        selbst = int(selbsteinschaetzung)
    except (TypeError, ValueError):
        selbst = 1
    return max(stufe_aus_meilen(meilen), min(max(selbst, 1), 5))


def seemeilen_map(user_ids):
    """Gesamt-Seemeilen pro User-Id — 2 Queries, egal wie viele Nutzer."""
    from accounts.models import ManuellerSeemeilenEintrag
    from toern.models import Teilnahme

    user_ids = list(user_ids)
    meilen = {uid: 0 for uid in user_ids}

    toern_teilnahmen = Teilnahme.objects.filter(
        user_id__in=user_ids, status="bestaetigt"
    ).select_related("boot")
    for t in toern_teilnahmen:
        if t.individuelle_meilen:
            meilen[t.user_id] += t.individuelle_meilen
        elif t.boot and t.boot.skipper_meilen:
            meilen[t.user_id] += t.boot.skipper_meilen

    manuell = (
        ManuellerSeemeilenEintrag.objects.filter(user_id__in=user_ids)
        .values("user_id").annotate(total=Sum("meilen"))
    )
    for row in manuell:
        meilen[row["user_id"]] += row["total"]

    return meilen
