from django.contrib import admin
from .models import Toern, Teilnahme
from boote.models import Boot

class TeilnahmeInline(admin.TabularInline):
    model = Teilnahme
    extra = 0

class BootInline(admin.TabularInline):
    model = Boot
    extra = 0

@admin.register(Toern)
class ToernAdmin(admin.ModelAdmin):
    list_display = ("titel", "startdatum", "enddatum", "status")
    inlines = [TeilnahmeInline, BootInline]


@admin.register(Teilnahme)
class TeilnahmeAdmin(admin.ModelAdmin):
    list_display = ("user", "toern", "rolle", "status", "boot", "kabine")
    list_filter = ("rolle", "status")