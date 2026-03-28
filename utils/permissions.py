from django.core.exceptions import PermissionDenied

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