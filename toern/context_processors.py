from .models import Teilnahme


def active_boot_dashboard(request):
    if not request.user.is_authenticated:
        return {}

    # Laufender Törn zuerst; sonst der zuletzt abgeschlossene, damit die
    # Bootskasse nach dem Törn erreichbar bleibt.
    teilnahmen = Teilnahme.objects.filter(
        user=request.user, status="bestaetigt", boot__isnull=False,
    ).select_related("boot", "toern")
    teilnahme = (
        teilnahmen.filter(toern__status="ZUTEILUNG_FIXIERT").first()
        or teilnahmen.filter(toern__status="ABGESCHLOSSEN").order_by("-toern__enddatum").first()
    )

    if teilnahme:
        return {"nav_boot_toern_id": teilnahme.toern_id}
    return {}


def briefing_nav(request):
    if not request.user.is_authenticated:
        return {"nav_zeigt_briefing": False}
    from utils.permissions import ist_irgendwo_skipper_oder_anbieter
    return {"nav_zeigt_briefing": ist_irgendwo_skipper_oder_anbieter(request.user)}
