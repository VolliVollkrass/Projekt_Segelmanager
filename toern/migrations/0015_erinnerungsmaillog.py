from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("toern", "0014_teilnahme_lebensmittelunvertraeglichkeiten_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ErinnerungsMailLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("gesendet_am", models.DateTimeField(auto_now_add=True)),
                ("fehlende_felder", models.TextField(blank=True)),
                (
                    "empfaenger",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="erinnerungsmails_erhalten",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "toern",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="erinnerungsmails",
                        to="toern.toern",
                    ),
                ),
            ],
            options={
                "ordering": ["-gesendet_am"],
            },
        ),
    ]
