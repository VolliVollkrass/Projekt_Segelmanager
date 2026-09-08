from django.core.exceptions import PermissionDenied


def andacht_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied
        if not request.user.is_andacht and not request.user.is_superuser:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def anbieter_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied

        if not request.user.is_anbieter() and not request.user.is_superuser:
            raise PermissionDenied

        return view_func(request, *args, **kwargs)

    return _wrapped_view

def is_owner(user, toern):
    return user.is_superuser or toern.anbieter == user

def ist_irgendwo_skipper_oder_anbieter(user):
    """Törn-unabhängig: darf der User grundsätzlich auf Skipper-Features zugreifen
    (Briefing-Bibliothek u.ä.)? Anders als _ist_skipper_oder_anbieter(user, toern)
    in toern/views.py, das einen konkreten Törn braucht."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_anbieter():
        return True
    from toern.models import Teilnahme
    return Teilnahme.objects.filter(user=user, rolle__in=["skipper", "coskipper"]).exists()


def briefing_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not ist_irgendwo_skipper_oder_anbieter(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped_view
