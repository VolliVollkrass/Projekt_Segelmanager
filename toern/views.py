from django.shortcuts import render, get_object_or_404, redirect


from boote.models import Boot
from .models import Toern, Teilnahme
from django.contrib.auth.decorators import login_required
from utils.permissions import anbieter_required, is_owner
from django.core.exceptions import PermissionDenied
from .forms import ToernForm
from django.views.decorators.http import require_POST

def toern_detail(request, pk):
    toern = get_object_or_404(Toern, pk=pk)

    # optional: alle Boote des Törns laden
    boote = toern.boote.all()

    # Skipper pro Boot
    skipper_pro_boot = {
        boot.id: Teilnahme.objects.filter(
            toern=toern,
            boot=boot,
            rolle="skipper",
            status__in=["angemeldet", "bestaetigt"]
        ).select_related("user").first()
        for boot in boote
    }


    rtx = {
        'toern': toern,
        'boote': boote,
        'skipper_pro_boot': skipper_pro_boot,
    }

    return render(request, 'toern/toern_detail.html', rtx )

def toern_anmeldung(request, pk):
    toern = get_object_or_404(Toern, pk=pk)
    boote = toern.boote.all()
    # Skipper pro Boot
    skipper_pro_boot = {
        boot.id: Teilnahme.objects.filter(
            toern=toern,
            boot=boot,
            rolle="skipper",
            status__in=["angemeldet", "bestaetigt"]
        ).select_related("user").first()
        for boot in boote
    }

    rtx = {
        'toern': toern,
        'boote': boote,
        'skipper_pro_boot': skipper_pro_boot,
    }

    return render(request, 'toern/toern_anmeldung.html', rtx )

@login_required
@anbieter_required
def anbieter_dashboard(request):

    toerns = Toern.objects.filter(anbieter=request.user).order_by("-startdatum")

    ctx = {
        "toerns": toerns.prefetch_related("boote__kabinen")
    }

    return render(request, "toern/anbieter_dashboard.html", ctx)

@login_required
@anbieter_required
def toern_create(request):

    if request.method == "POST":
        form = ToernForm(request.POST, request.FILES)

        if form.is_valid():
            toern = form.save(commit=False)
            toern.anbieter = request.user
            toern.save()

            return redirect("anbieter_dashboard")

    else:
        form = ToernForm()

    return render(request, "toern/toern_form.html", {
        "form": form,
        "title": "Neuen Törn erstellen"
    })

@login_required
@anbieter_required
def toern_edit(request, pk):

    toern = get_object_or_404(Toern, pk=pk)

    if toern.anbieter != request.user:
        raise PermissionDenied

    if request.method == "POST":
        form = ToernForm(request.POST, request.FILES, instance=toern)

        if form.is_valid():
            form.save()
            return redirect("toern_detail", pk=toern.pk)

    else:
        form = ToernForm(instance=toern)

    return render(request, "toern/toern_form.html", {
        "form": form,
        "title": "Törn bearbeiten"
    })

@login_required
@anbieter_required
@require_POST
def toern_status_update(request, pk):

    toern = get_object_or_404(Toern, pk=pk)

    if not is_owner(request.user, toern):
        raise PermissionDenied

    new_status = request.POST.get("status")

    allowed_transitions = [
        "DRAFT",
        "ANMELDUNG_OFFEN",
        "ANMELDUNG_GESCHLOSSEN",
    ]

    if new_status in allowed_transitions:
        toern.status = new_status
        toern.save()

    return redirect("anbieter_dashboard")