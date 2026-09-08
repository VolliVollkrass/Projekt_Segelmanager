from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from utils.permissions import briefing_required

from .models import BriefingBaustein, kategorie_sortierung


def _safe_next(request):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return ""


@login_required
@briefing_required
def bibliothek(request):
    qs = BriefingBaustein.objects.select_related("autor", "zuletzt_bearbeitet_von")

    q = request.GET.get("q", "").strip()
    kategorie = request.GET.get("kategorie", "")

    if q:
        qs = qs.filter(Q(titel__icontains=q) | Q(text__icontains=q))
    if kategorie:
        qs = qs.filter(kategorie=kategorie)

    qs = qs.order_by(kategorie_sortierung(), 'reihenfolge', 'id')

    paginator = Paginator(qs, 18)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "briefing/liste.html", {
        "page_obj": page,
        "q": q,
        "kategorie": kategorie,
        "kategorien": BriefingBaustein.KATEGORIE_CHOICES,
        "next": _safe_next(request),
    })


@login_required
@briefing_required
def baustein_detail(request, pk):
    baustein = get_object_or_404(
        BriefingBaustein.objects.select_related("autor", "zuletzt_bearbeitet_von"), pk=pk,
    )
    return render(request, "briefing/detail.html", {
        "baustein": baustein,
        "next": _safe_next(request),
    })


@login_required
@briefing_required
def baustein_erstellen(request):
    if request.method == "POST":
        return _baustein_speichern(request, baustein=None)
    return render(request, "briefing/form.html", {
        "kategorien": BriefingBaustein.KATEGORIE_CHOICES,
        "action": "erstellen",
        "next": _safe_next(request),
    })


@login_required
@briefing_required
def baustein_bearbeiten(request, pk):
    baustein = get_object_or_404(BriefingBaustein, pk=pk)
    if request.method == "POST":
        return _baustein_speichern(request, baustein=baustein)
    return render(request, "briefing/form.html", {
        "baustein": baustein,
        "kategorien": BriefingBaustein.KATEGORIE_CHOICES,
        "action": "bearbeiten",
        "next": _safe_next(request),
    })


def _baustein_speichern(request, baustein):
    titel = request.POST.get("titel", "").strip()
    kategorie = request.POST.get("kategorie", "sonstiges")
    text = request.POST.get("text", "").strip()

    if not titel or not text:
        kontext = {
            "baustein": baustein,
            "kategorien": BriefingBaustein.KATEGORIE_CHOICES,
            "action": "bearbeiten" if baustein else "erstellen",
            "next": _safe_next(request),
            "fehler": "Titel und Text sind Pflichtfelder.",
        }
        return render(request, "briefing/form.html", kontext)

    neu = baustein is None
    if neu:
        baustein = BriefingBaustein(autor=request.user)

    baustein.titel = titel
    baustein.kategorie = kategorie
    baustein.text = text
    baustein.zuletzt_bearbeitet_von = request.user

    if "bild" in request.FILES:
        baustein.bild = request.FILES["bild"]
    elif request.POST.get("bild_entfernen") == "1":
        baustein.bild = None

    baustein.save()

    nxt = _safe_next(request)
    if nxt:
        from urllib.parse import quote
        return redirect(f"{reverse('briefing_baustein_detail', args=[baustein.pk])}?next={quote(nxt)}")
    return redirect("briefing_baustein_detail", pk=baustein.pk)


@login_required
@require_POST
def baustein_loeschen(request, pk):
    baustein = get_object_or_404(BriefingBaustein, pk=pk)
    if baustein.autor != request.user and not request.user.is_staff:
        raise PermissionDenied
    baustein.delete()
    return redirect("briefing_bibliothek")
