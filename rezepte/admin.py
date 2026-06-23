from django.contrib import admin
from .models import Rezept, RezeptZutat, RezeptSchritt, RezeptStern


class ZutatInline(admin.TabularInline):
    model = RezeptZutat
    extra = 0


class SchrittInline(admin.TabularInline):
    model = RezeptSchritt
    extra = 0


@admin.register(Rezept)
class RezeptAdmin(admin.ModelAdmin):
    list_display = ["name", "kategorie", "autor", "portionen", "zubereitungszeit", "stern_anzahl", "erstellt_am"]
    list_filter = ["kategorie"]
    search_fields = ["name", "autor__email"]
    inlines = [ZutatInline, SchrittInline]
