from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

# Seiten, die auch für eingeloggte, aber noch NICHT verifizierte Nutzer erreichbar sind.
ALLOWED_PATHS = (
    "/accounts/email-verifizieren/",
    "/accounts/email-bestaetigung/",
    "/accounts/logout/",
    "/accounts/login/",
    "/admin/",
    "/media/",
    "/static/",
    "/impressum/",
    "/datenschutz/",
)

# Seiten, die OHNE Login erreichbar sein müssen (privates Projekt: alles andere ist gesperrt).
# Registrierung bleibt bewusst offen, damit Freunde selbst beitreten können.
PUBLIC_PATHS = (
    "/accounts/login/",
    "/accounts/register/",
    "/accounts/logout/",
    "/accounts/passwort-reset/",      # deckt alle Reset-Unterseiten ab
    "/accounts/email-verifizieren/",
    "/accounts/email-bestaetigung/",
    "/impressum/",
    "/datenschutz/",
    "/admin/",                        # Django-Admin bringt eigene Anmeldung mit
    "/static/",
    "/media/",                        # Autorisierung übernimmt protected_media_serve
    # Geteilte Törn-Links (?key) sollen ohne Konto funktionieren. Die View
    # (toern_detail / toern_anmeldung) prüft den privaten Zugriff selbst:
    # öffentlich → sichtbar, privat → nur mit gültigem Key/Session, sonst 404.
    "/toern/detail/",
    "/toern/anmeldung/",
)


class LoginRequiredMiddleware:
    """Sperrt die gesamte App hinter Login — bis auf PUBLIC_PATHS.

    Die App ist ein privates Projekt für den Freundeskreis; anonyme Besucher
    werden zur Anmeldung geleitet (mit ?next=). Öffentlich bleiben nur die für
    Anmeldung/Registrierung/Passwort-Reset und die Rechtsseiten nötigen Routen.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            not request.user.is_authenticated
            and not any(request.path.startswith(p) for p in PUBLIC_PATHS)
        ):
            return redirect_to_login(request.get_full_path())

        return self.get_response(request)


class EmailVerificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and not request.user.email_verified
            and not request.user.is_staff
            and not any(request.path.startswith(p) for p in ALLOWED_PATHS)
        ):
            return redirect("verification_pending")

        return self.get_response(request)
