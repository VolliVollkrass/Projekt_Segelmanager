from django.contrib import admin
from .models import Ausgabe, TopfAusgabe

@admin.register(Ausgabe)
class AusgabeAdmin(admin.ModelAdmin):
    list_display = ("beschreibung", "betrag", "boot", "toern", "bezahlt_von")

@admin.register(TopfAusgabe)
class TopfAusgabeAdmin(admin.ModelAdmin):
    list_display = ("beschreibung", "betrag", "toern", "erstellt_von", "created_at")
