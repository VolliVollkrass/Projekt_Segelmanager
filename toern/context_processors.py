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


def briefing_nav(request):
    if not request.user.is_authenticated:
        return {"nav_zeigt_briefing": False}
    from utils.permissions import ist_irgendwo_skipper_oder_anbieter
    return {"nav_zeigt_briefing": ist_irgendwo_skipper_oder_anbieter(request.user)}
