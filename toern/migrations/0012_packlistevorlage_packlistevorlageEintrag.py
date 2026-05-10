from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('toern', '0011_bootpacklistetemplate_personalpacklistetemplate'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PacklisteVorlage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('revier_typ', models.CharField(
                    choices=[('standard', 'Standard'), ('warm', 'Warmes Segelgebiet'), ('kalt', 'Kaltes Segelgebiet')],
                    default='standard', max_length=20
                )),
                ('typ', models.CharField(
                    choices=[('personal', 'Persönlich'), ('boot', 'Boot')],
                    max_length=10
                )),
                ('erstellt_von', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='packliste_vorlagen',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'unique_together': {('erstellt_von', 'revier_typ', 'typ')},
            },
        ),
        migrations.CreateModel(
            name='PacklisteVorlageEintrag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('menge', models.PositiveIntegerField(default=1)),
                ('vorlage', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='eintraege',
                    to='toern.packlistevorlage'
                )),
            ],
        ),
    ]
