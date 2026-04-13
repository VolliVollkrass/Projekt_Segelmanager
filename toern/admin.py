from django.contrib import admin
from .models import Toern, Teilnahme, KabinenWunsch, CrewPraeferenz
from boote.models import Boot


# =========================
# INLINE: Teilnahme im Törn
# =========================
class TeilnahmeInline(admin.TabularInline):
    model = Teilnahme
    extra = 0
    fields = ("user", "rolle", "status", "boot", "kabine")
    readonly_fields = ("user",)


class BootInline(admin.TabularInline):
    model = Boot
    extra = 0


# =========================
# TOERN ADMIN
# =========================
@admin.register(Toern)
class ToernAdmin(admin.ModelAdmin):
    list_display = ("titel", "startdatum", "enddatum", "status")
    inlines = [TeilnahmeInline, BootInline]


# =========================
# TEILNAHME ADMIN
# =========================
@admin.register(Teilnahme)
class TeilnahmeAdmin(admin.ModelAdmin):

    # 🔥 WICHTIG: klare Anzeige
    list_display = (
        "user_fullname",
        "toern",
        "rolle_badge",
        "boot",
        "kabine",
        "status",
    )

    # 🔍 Filter
    list_filter = ("rolle", "boot", "toern", "status")

    # 🔎 Suche
    search_fields = ("user__first_name", "user__last_name", "user__email")

    # 👉 Sortierung
    ordering = ("toern", "boot", "rolle")

    # =========================
    # CUSTOM DISPLAY
    # =========================

    def user_fullname(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}"
    user_fullname.short_description = "Name"

    def rolle_badge(self, obj):
        if obj.rolle == "skipper":
            return "👨‍✈️ Skipper"
        elif obj.rolle == "coskipper":
            return "🧭 Co-Skipper"
        return "Crew"
    rolle_badge.short_description = "Rolle"


# =========================
# KABINENWUNSCH ADMIN
# =========================
@admin.register(KabinenWunsch)
class KabinenWunschAdmin(admin.ModelAdmin):
    list_display = ("from_user", "to_user", "toern", "status")
    list_filter = ("status", "toern")


# =========================
# CREW PRÄFERENZEN ADMIN
# =========================
@admin.register(CrewPraeferenz)
class CrewPraeferenzAdmin(admin.ModelAdmin):
    list_display = ("from_user", "to_user", "typ", "toern")
    list_filter = ("typ", "toern")