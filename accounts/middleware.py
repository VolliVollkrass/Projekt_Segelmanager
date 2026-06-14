from django.shortcuts import redirect

ALLOWED_PATHS = (
    "/accounts/email-verifizieren/",
    "/accounts/email-bestaetigung/",
    "/accounts/logout/",
    "/accounts/login/",
    "/admin/",
    "/media/",
    "/static/",
)


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
