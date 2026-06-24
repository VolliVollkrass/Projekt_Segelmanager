from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('toern', '0023_toern_praeferenz_modus'),
    ]

    operations = [
        # 1. Neues Feld am Törn
        migrations.AddField(
            model_name='toern',
            name='packliste_revier_typ',
            field=models.CharField(
                max_length=10,
                choices=[('warm', 'Warm (Mittelmeer)'), ('kalt', 'Kalt (Nordsee)')],
                default='warm',
                verbose_name='Segelgebiet Packliste',
            ),
        ),

        # 2. Alte unique_together aufheben (muss VOR dem Felddrop sein)
        migrations.AlterUniqueTogether(
            name='packlistevorlage',
            unique_together=set(),
        ),

        # 3. Alle alten Einträge + Vorlagen löschen (werden per Törn neu angelegt)
        migrations.RunSQL(
            "DELETE FROM toern_packlistevorlageeintrag; DELETE FROM toern_packlistevorlage;",
            reverse_sql=migrations.RunSQL.noop,
        ),

        # 4. Alte Felder entfernen
        migrations.RemoveField(
            model_name='packlistevorlage',
            name='revier_typ',
        ),
        migrations.RemoveField(
            model_name='packlistevorlage',
            name='erstellt_von',
        ),

        # 5. Neues toern-FK hinzufügen (nullable für leere Tabelle kein Problem)
        migrations.AddField(
            model_name='packlistevorlage',
            name='toern',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='packliste_vorlagen',
                to='toern.toern',
                null=True,
            ),
        ),

        # 6. Neue unique_together setzen
        migrations.AlterUniqueTogether(
            name='packlistevorlage',
            unique_together={('toern', 'typ')},
        ),

        # 7. toern NOT NULL setzen
        migrations.AlterField(
            model_name='packlistevorlage',
            name='toern',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='packliste_vorlagen',
                to='toern.toern',
            ),
        ),
    ]
