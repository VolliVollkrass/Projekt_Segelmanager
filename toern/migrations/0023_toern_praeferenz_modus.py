from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('toern', '0022_tagesimpulse_aktiv'),
    ]

    operations = [
        migrations.AddField(
            model_name='toern',
            name='praeferenz_modus',
            field=models.CharField(
                choices=[
                    ('alle', 'Beide Präferenztypen'),
                    ('nur_ausschluss', 'Nur Ausschlüsse'),
                    ('keiner', 'Deaktiviert'),
                ],
                default='alle',
                max_length=20,
                verbose_name='Kabinenpartner-Präferenzen',
            ),
        ),
    ]
