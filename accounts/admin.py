from django.contrib import admin
from .models import User, Lizenz, Notiz
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group



@admin.register(User)
class CustomUserAdmin(UserAdmin):
    filter_horizontal = ("groups", "user_permissions")
    list_display = ("email", "first_name", "last_name", "email_verified", "is_staff", "is_active")
    list_filter = ("email_verified", "is_staff", "is_active")
    list_editable = ("email_verified",)

    fieldsets = UserAdmin.fieldsets + (
        ("E-Mail-Verifikation", {
            "fields": ("email_verified",)
        }),
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