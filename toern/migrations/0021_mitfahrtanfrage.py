from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("toern", "0020_tagesplan"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Mitfahrtanfrage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "Angefragt"), ("accepted", "Bestätigt"), ("rejected", "Abgelehnt")], default="pending", max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "angebot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="anfragen",
                        to="toern.mitfahrangebot",
                    ),
                ),
                (
                    "anfragender",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mitfahrt_anfragen",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
                "unique_together": {("angebot", "anfragender")},
            },
        ),
    ]
