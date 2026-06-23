from .models import Teilnahme


def active_boot_dashboard(request):
    if not request.user.is_authenticated:
        return {}

    teilnahme = (
        Teilnahme.objects.filter(
            user=request.user,
            status="bestaetigt",
            boot__isnull=False,
            toern__status="ZUTEILUNG_FIXIERT",
        )
        .select_related("boot", "toern")
        .first()
    )

    if teilnahme:
        return {"nav_boot_toern_id": teilnahme.toern_id}
    return {}
