from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("toern", "0018_pinnwandnachricht"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Mitfahrangebot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("typ", models.CharField(choices=[("angebot", "Mitfahrangebot"), ("gesuch", "Mitfahrgesuch")], max_length=10)),
                ("abfahrtsort", models.CharField(max_length=200)),
                ("abfahrtszeit", models.DateTimeField(blank=True, null=True)),
                ("freie_plaetze", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("anmerkung", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "toern",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mitfahrangebote",
                        to="toern.toern",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mitfahrangebote",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
