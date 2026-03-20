from django.contrib import admin
from .models import Charterunternehmen, Boot, Kabine

class KabineInline(admin.TabularInline):
    model = Kabine
    extra = 1

@admin.register(Boot)
class BootAdmin(admin.ModelAdmin):
    list_display = ("name", "typ", "charterunternehmen")
    inlines = [KabineInline]

@admin.register(Charterunternehmen)
class CharterunternehmenAdmin(admin.ModelAdmin):
    list_display = ("name",)

@admin.register(Kabine)
class KabineAdmin(admin.ModelAdmin):
    list_display = ("name", "boot", "betten")