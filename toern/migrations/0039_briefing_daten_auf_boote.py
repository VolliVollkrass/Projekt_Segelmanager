# -*- coding: utf-8 -*-
"""Briefing auf Bootsebene, Teil 2 von 3: Bestandsdaten umziehen.

Bewusst allein in dieser Migration — siehe 0038 zur Begründung (PostgreSQL
erlaubt keine Schemaänderung in derselben Transaktion, in der Daten geändert
wurden). Hier passiert deshalb ausschließlich DML, kein DDL.

Bestehende törnweite Auswahlen werden auf alle Boote ihres Törns übertragen,
damit keine Zusammenstellung verloren geht.
"""
from django.db import migrations


def auswahl_auf_boote_verteilen(apps, schema_editor):
    BriefingAuswahl = apps.get_model("toern", "BriefingAuswahl")
    Boot = apps.get_model("boote", "Boot")

    for auswahl in list(BriefingAuswahl.objects.all()):
        boote = list(Boot.objects.filter(toern_id=auswahl.toern_id))
        if not boote:
            auswahl.delete()          # Törn ohne Boot: Auswahl hat kein Ziel
            continue
        auswahl.boot_id = boote[0].id
        auswahl.save(update_fields=["boot"])
        # Weitere Boote bekommen eine eigene Kopie derselben Zusammenstellung.
        # toern_id muss hier noch mitgegeben werden — die Spalte fällt erst in
        # 0040 weg und ist bis dahin Pflichtfeld.
        for boot in boote[1:]:
            BriefingAuswahl.objects.create(
                toern_id=auswahl.toern_id,
                boot_id=boot.id, baustein_id=auswahl.baustein_id,
                aktiv=auswahl.aktiv, reihenfolge=auswahl.reihenfolge,
            )


def zurueck_auf_toern(apps, schema_editor):
    """Rückwärts: pro Törn die Auswahl des ersten Boots behalten."""
    BriefingAuswahl = apps.get_model("toern", "BriefingAuswahl")
    gesehen = set()
    for auswahl in list(BriefingAuswahl.objects.select_related("boot")):
        if auswahl.boot_id is None:
            continue
        schluessel = (auswahl.boot.toern_id, auswahl.baustein_id)
        if schluessel in gesehen:
            auswahl.delete()
            continue
        gesehen.add(schluessel)
        auswahl.toern_id = auswahl.boot.toern_id
        auswahl.save(update_fields=["toern"])


class Migration(migrations.Migration):

    dependencies = [
        ("toern", "0038_briefing_auf_bootsebene"),
        ("boote", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(auswahl_auf_boote_verteilen, zurueck_auf_toern),
    ]
