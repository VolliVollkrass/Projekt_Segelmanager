"""Bestehende Tagesaufgaben vom entfernten Typ 'hafenwache' auf 'sonstiges'
umstellen — die Beschreibung 'Hafenwache' bleibt sichtbar erhalten."""
from django.db import migrations


def hafenwache_umstellen(apps, schema_editor):
    Tagesaufgabe = apps.get_model("logistik", "Tagesaufgabe")
    for aufgabe in Tagesaufgabe.objects.filter(typ="hafenwache"):
        aufgabe.typ = "sonstiges"
        if not aufgabe.beschreibung:
            aufgabe.beschreibung = "Hafenwache"
        aufgabe.save(update_fields=["typ", "beschreibung"])


def rueckwaerts(apps, schema_editor):
    Tagesaufgabe = apps.get_model("logistik", "Tagesaufgabe")
    Tagesaufgabe.objects.filter(typ="sonstiges", beschreibung="Hafenwache").update(
        typ="hafenwache", beschreibung=""
    )


class Migration(migrations.Migration):

    dependencies = [
        ("logistik", "0009_alter_tagesaufgabe_typ"),
    ]

    operations = [
        migrations.RunPython(hafenwache_umstellen, rueckwaerts),
    ]
