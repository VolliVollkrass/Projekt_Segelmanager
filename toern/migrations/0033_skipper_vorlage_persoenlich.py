"""Die Skipper-Packlisten-Vorlage ist jetzt persönlich (pro Skipper/Co-Skipper).
Alte törn-geteilte Skipper-Vorlagen (user=None) werden entfernt — jede/r Skipper
bekommt beim nächsten Zugriff die eigene Vorlage, geseedet aus dem persönlichen
Packlisten-Standard (ist_default) bzw. der SKIPPER_LISTE. Bereits erzeugte
persönliche Packlisten-Items (PersönlicherGegenstand) bleiben unberührt."""
from django.db import migrations


def geteilte_skipper_vorlagen_entfernen(apps, schema_editor):
    PacklisteVorlage = apps.get_model("toern", "PacklisteVorlage")
    PacklisteVorlage.objects.filter(typ="skipper", user__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("toern", "0032_alter_packlistevorlage_unique_together_and_more"),
    ]

    operations = [
        migrations.RunPython(geteilte_skipper_vorlagen_entfernen, migrations.RunPython.noop),
    ]
