# -*- coding: utf-8 -*-
"""Briefing-Auswahl vom Törn auf das Boot umhängen + persönliche Vorlagen.

Bei Flottentörns hängen mehrere Boote am selben Törn, jedes mit eigener Crew.
Eine törnweite Auswahl zwang alle Skipper auf dieselben Inhalte. Bestehende
Auswahlen werden auf alle Boote ihres Törns übertragen, damit niemand seine
Zusammenstellung verliert.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def auswahl_auf_boote_verteilen(apps, schema_editor):
    BriefingAuswahl = apps.get_model("toern", "BriefingAuswahl")
    Boot = apps.get_model("boote", "Boot")

    for auswahl in list(BriefingAuswahl.objects.select_related("toern")):
        boote = list(Boot.objects.filter(toern_id=auswahl.toern_id))
        if not boote:
            auswahl.delete()          # Törn ohne Boot: Auswahl hat kein Ziel
            continue
        auswahl.boot_id = boote[0].id
        auswahl.save(update_fields=["boot"])
        # Weitere Boote bekommen eine eigene Kopie derselben Zusammenstellung.
        # toern_id muss hier noch mitgegeben werden — die Spalte fällt erst
        # nach dieser Datenwanderung weg und ist bis dahin Pflichtfeld.
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
        schluessel = (auswahl.boot.toern_id, auswahl.baustein_id)
        if schluessel in gesehen:
            auswahl.delete()
            continue
        gesehen.add(schluessel)
        auswahl.toern_id = auswahl.boot.toern_id
        auswahl.save(update_fields=["toern"])


class Migration(migrations.Migration):

    dependencies = [
        ("toern", "0037_briefingauswahl"),
        ("boote", "0001_initial"),
        ("briefing", "0004_briefingbaustein_bild_position"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Alte Eindeutigkeit lösen, bevor die Spalte wechselt
        migrations.AlterUniqueTogether(name="briefingauswahl", unique_together=set()),
        # 2. Boot-Spalte zunächst optional anlegen, damit Bestandsdaten passen
        migrations.AddField(
            model_name="briefingauswahl",
            name="boot",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="briefing_auswahl", to="boote.boot",
            ),
        ),
        # 3. Bestandsdaten auf die Boote verteilen
        migrations.RunPython(auswahl_auf_boote_verteilen, zurueck_auf_toern),
        # 4. Jetzt ist die Spalte überall gefüllt und kann verpflichtend werden
        migrations.AlterField(
            model_name="briefingauswahl",
            name="boot",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="briefing_auswahl", to="boote.boot",
            ),
        ),
        migrations.RemoveField(model_name="briefingauswahl", name="toern"),
        migrations.AlterField(
            model_name="briefingauswahl",
            name="baustein",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="boot_auswahl", to="briefing.briefingbaustein",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="briefingauswahl", unique_together={("boot", "baustein")}),

        # Persönliche Vorlagen
        migrations.CreateModel(
            name="BriefingStandard",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("ist_default", models.BooleanField(
                    default=False,
                    help_text="Wird bei neuen Booten automatisch als Start-Briefing verwendet (max. eine)")),
                ("aktualisiert_am", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="briefing_standards", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-ist_default", "name"],
                     "unique_together": {("user", "name")}},
        ),
        migrations.CreateModel(
            name="BriefingStandardEintrag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("reihenfolge", models.PositiveIntegerField(default=0)),
                ("baustein", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="+", to="briefing.briefingbaustein")),
                ("standard", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="eintraege", to="toern.briefingstandard")),
            ],
            options={"ordering": ["reihenfolge", "id"],
                     "unique_together": {("standard", "baustein")}},
        ),
    ]
