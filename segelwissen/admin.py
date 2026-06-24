from django.contrib import admin
from .models import Knoten, Segelinformation, Segelvideo


@admin.register(Knoten)
class KnotenAdmin(admin.ModelAdmin):
    list_display  = ['name', 'schwierigkeitsgrad', 'reihenfolge', 'erstellt_am']
    list_filter   = ['schwierigkeitsgrad']
    search_fields = ['name']
    list_editable = ['reihenfolge']


@admin.register(Segelinformation)
class SegelinformationAdmin(admin.ModelAdmin):
    list_display  = ['titel', 'kategorie', 'reihenfolge', 'erstellt_am']
    list_filter   = ['kategorie']
    search_fields = ['titel', 'text']
    list_editable = ['reihenfolge']


@admin.register(Segelvideo)
class SegelvideoAdmin(admin.ModelAdmin):
    list_display  = ['titel', 'reihenfolge', 'erstellt_am']
    search_fields = ['titel']
    list_editable = ['reihenfolge']
