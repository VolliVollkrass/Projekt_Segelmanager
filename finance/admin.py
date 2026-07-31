from django.contrib import admin
from .models import Ausgabe, TopfAusgabe, TopfBeleg

@admin.register(Ausgabe)
class AusgabeAdmin(admin.ModelAdmin):
    list_display = ("beschreibung", "betrag", "boot", "toern", "bezahlt_von")


class TopfBelegInline(admin.TabularInline):
    model = TopfBeleg
    extra = 0


@admin.register(TopfAusgabe)
class TopfAusgabeAdmin(admin.ModelAdmin):
    list_display = ("beschreibung", "betrag", "kategorie", "toern", "erstellt_von", "created_at")
    list_filter = ("kategorie", "toern")
    inlines = [TopfBelegInline]
