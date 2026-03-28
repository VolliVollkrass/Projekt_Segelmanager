from django.contrib import admin
from .models import User, Lizenz, Notiz
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group



@admin.register(User)
class CustomUserAdmin(UserAdmin):
    filter_horizontal = ("groups", "user_permissions")

    fieldsets = UserAdmin.fieldsets + (
        ("Zusätzliche Informationen", {
            "fields": (
                "geschlecht",
                "geburtsdatum",
                "geburtsort",
                "nationalitaet",
                "identifikationstyp",
                "passnummer",
                "strasse",
                "plz",
                "ort",
                "telefonnummer",
                "profilbild",
            )
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Zusätzliche Informationen", {
            "fields": (
                "geschlecht",
                "geburtsdatum",
                "geburtsort",
                "nationalitaet",
                "identifikationstyp",
                "passnummer",
                "strasse",
                "plz",
                "ort",
                "telefonnummer",
                "profilbild",
            )
        }),
    )


@admin.register(Lizenz)
class LizenzAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "ausstellungsdatum", "ablaufdatum")
    list_filter = ("name",)


@admin.register(Notiz)
class NotizAdmin(admin.ModelAdmin):
    list_display = ("user", "ersteller", "created_at")