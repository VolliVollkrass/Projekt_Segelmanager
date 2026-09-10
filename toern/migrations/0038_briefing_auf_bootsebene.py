# -*- coding: utf-8 -*-
"""Briefing-Auswahl vom Törn auf das Boot umhängen + persönliche Vorlagen.

Bei Flottentörns hängen mehrere Boote am selben Törn, jedes mit eigener Crew.
Eine törnweite Auswahl zwang alle Skipper auf dieselben Inhalte. Bestehende
Auswahlen werden auf alle Boote ihres Törns übertragen, damit niemand seine
Zusammenstellung verliert.

Teil 1 von 3: nur die Boot-Spalte anlegen.

Die Dreiteilung ist keine Kosmetik, sondern von PostgreSQL erzwungen: Es
verweigert Schemaänderungen an einer Tabelle, in der in derselben Transaktion
Daten geändert wurden ("pending trigger events"). Django hängt das CREATE INDEX
einer neuen Spalte ans *Ende* der Migration — stünde der Datenumzug in derselben
Migration, liefe der Index hinter dem UPDATE und schlüge fehl. Also: Spalte hier,
Daten in 0039, restliche Struktur in 0040. Jede Migration eine Transaktion.

SQLite kennt diese Einschränkung nicht, weshalb ein rein lokaler Test das nicht
findet — dieser Umbau ist gegen echtes PostgreSQL geprüft.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion



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
    ]
