# -*- coding: utf-8 -*-
"""Briefing auf Bootsebene, Teil 3 von 3: Struktur nachziehen + persönliche Vorlagen.

Läuft in eigener Transaktion, nachdem 0039 die Daten umgezogen hat — nur so
lässt PostgreSQL die Schemaänderungen zu (siehe 0038).
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("toern", "0039_briefing_daten_auf_boote"),
        ("boote", "0001_initial"),
        ("briefing", "0004_briefingbaustein_bild_position"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Jetzt ist die Spalte überall gefüllt und kann verpflichtend werden
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
