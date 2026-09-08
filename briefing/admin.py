from django.contrib import admin

from .models import BriefingBaustein


@admin.register(BriefingBaustein)
class BriefingBausteinAdmin(admin.ModelAdmin):
    list_display = ("titel", "kategorie", "ist_standard", "reihenfolge", "autor", "aktualisiert_am")
    list_filter = ("kategorie", "ist_standard")
    search_fields = ("titel", "text")
