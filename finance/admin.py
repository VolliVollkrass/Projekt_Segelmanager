from django.contrib import admin
from .models import Ausgabe

@admin.register(Ausgabe)
class AusgabeAdmin(admin.ModelAdmin):
    list_display = ("beschreibung", "betrag", "boot", "toern", "bezahlt_von")