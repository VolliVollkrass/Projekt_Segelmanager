import uuid

from django.db import migrations, models


def fill_privat_token(apps, schema_editor):
    Toern = apps.get_model("toern", "Toern")
    for toern in Toern.objects.filter(privat_token__isnull=True):
        toern.privat_token = uuid.uuid4()
        toern.save(update_fields=["privat_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("toern", "0025_toern_skipper_budget"),
    ]

    operations = [
        migrations.AddField(
            model_name="toern",
            name="ist_privat",
            field=models.BooleanField(
                default=False,
                help_text="Nur über den geheimen Einladungslink erreichbar, nicht öffentlich gelistet",
                verbose_name="Privater Törn",
            ),
        ),
        migrations.AddField(
            model_name="toern",
            name="privat_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.RunPython(fill_privat_token, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="toern",
            name="privat_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
