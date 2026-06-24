import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Andacht',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('typ', models.CharField(choices=[('morgen', 'Morgenandacht'), ('abend', 'Abendandacht')], max_length=10)),
                ('zielgruppe', models.CharField(choices=[('maritim', 'Maritime Andacht'), ('kinder', 'Kinder'), ('jugendliche', 'Jugendliche'), ('junge_erwachsene', 'Junge Erwachsene'), ('erwachsene', 'Erwachsene'), ('gemischt', 'Gemischt / Alle')], max_length=20)),
                ('dauer_minuten', models.PositiveIntegerField()),
                ('thema', models.CharField(max_length=300)),
                ('stichpunkte', models.TextField(blank=True)),
                ('bibelstelle_eingabe', models.CharField(blank=True, max_length=100)),
                ('tageslosung_verwendet', models.BooleanField(default=False)),
                ('kirchenjahr', models.CharField(blank=True, choices=[('', 'Keine Angabe'), ('advent', 'Advent'), ('weihnacht', 'Weihnacht'), ('passion', 'Passion / Fastenzeit'), ('ostern', 'Ostern'), ('pfingsten', 'Pfingsten'), ('normale_zeit', 'Trinitatiszeit / Normale Zeit')], max_length=20)),
                ('stil', models.CharField(blank=True, choices=[('', 'Kein Vorgabe'), ('meditativ', 'Meditativ'), ('erzaehlend', 'Erzählend'), ('liturgisch', 'Liturgisch')], max_length=20)),
                ('eigener_liedwunsch', models.CharField(blank=True, max_length=200)),
                ('mit_liedern', models.BooleanField(default=True)),
                ('mit_gespraechsimpulsen', models.BooleanField(default=True)),
                ('mit_geschichte', models.BooleanField(default=True)),
                ('mit_gebeten', models.BooleanField(default=True)),
                ('titel', models.CharField(blank=True, max_length=300)),
                ('bibelstelle', models.CharField(blank=True, max_length=100)),
                ('bibeltext', models.TextField(blank=True)),
                ('exegese', models.TextField(blank=True)),
                ('einstieg', models.TextField(blank=True)),
                ('entfaltung', models.TextField(blank=True)),
                ('abschluss', models.TextField(blank=True)),
                ('geschichte', models.TextField(blank=True)),
                ('lieder_json', models.TextField(blank=True)),
                ('gebete_json', models.TextField(blank=True)),
                ('gespraechsimpulse_json', models.TextField(blank=True)),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='andachten', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Andacht',
                'verbose_name_plural': 'Andachten',
                'ordering': ['-erstellt_am'],
            },
        ),
    ]
