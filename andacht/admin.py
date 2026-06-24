from django.contrib import admin
from .models import Andacht


@admin.register(Andacht)
class AndachtAdmin(admin.ModelAdmin):
    list_display = ('titel', 'user', 'typ', 'zielgruppe', 'dauer_minuten', 'erstellt_am')
    list_filter = ('typ', 'zielgruppe', 'kirchenjahr')
    search_fields = ('titel', 'thema', 'user__email')
    readonly_fields = ('erstellt_am',)
