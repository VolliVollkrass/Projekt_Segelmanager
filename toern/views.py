from django.shortcuts import render, get_object_or_404, redirect


from boote.models import Boot
from .models import Toern, Teilnahme
from django.contrib.auth.decorators import login_required
from utils.permissions import anbieter_required, is_owner
from django.core.exceptions import PermissionDenied
from .forms import ToernForm, TeilnahmeForm
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_POST
from django.utils.timezone import now

User = get_user_model()

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

    if request.method == "POST":
        form = TeilnahmeForm(request.POST)

        if form.is_valid():

            # =========================
            # USER LOGIK
            # =========================
            if request.user.is_authenticated:
                user = request.user
                if not user.geburtsdatum:
                    user.geburtsdatum = form.cleaned_data.get("geburtsdatum")
                    user.save()
            else:
                email = request.POST.get("email")

                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "username": email,
                        "first_name": request.POST.get("first_name"),
                        "last_name": request.POST.get("last_name"),
                        "geburtsdatum": form.cleaned_data.get("geburtsdatum"),
                    }
                )

                # nur wenn neu → Passwort setzen
                if created:
                    password = form.cleaned_data.get("password1")
                    user.set_password(password)
                    user.save()

                    user = authenticate(
                        request,
                        username=user.email,
                        password=password
                    )

                    if user:
                        login(request, user)

                else:
                    # 👉 User existiert aber ist nicht eingeloggt
                    messages.error(request, "Bitte logge dich zuerst ein.")
                    return redirect("login")
            # =========================
            # Teilnahme erstellen
            # =========================
            if Teilnahme.objects.filter(user=user, toern=toern).exists():
                messages.warning(request, "Du bist bereits angemeldet.")
                return redirect("toern_detail", pk=toern.pk)

            teilnahme = form.save(commit=False)
            teilnahme.user = user
            teilnahme.toern = toern
            teilnahme.rolle = "crew"
            teilnahme.save()

            messages.success(request, "Erfolgreich angemeldet!")
            return redirect("toern_detail", pk=toern.pk)

    else:
        form = TeilnahmeForm()

    return render(request, "toern/toern_anmeldung.html", {
        "toern": toern,
        "form": form
    })

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

def crew_overview(request):
    teilnahmen = Teilnahme.objects.filter(user=request.user).select_related("toern")

    kommende_toerns = []
    vergangene_toerns = []

    jetzt = now()  # <-- datetime!

    for t in teilnahmen:
        if t.toern.startdatum >= jetzt:
            kommende_toerns.append(t.toern)
        else:
            vergangene_toerns.append(t.toern)

    context = {
        "kommende_toerns": kommende_toerns,
        "vergangene_toerns": vergangene_toerns,
    }

    return render(request, "crew/crew_overview.html", context)

def crew_dashboard(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    # Teilnahme prüfen (Crew darf nur eigene sehen!)
    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=toern
    ).first()

    # Berechtigungslogik
    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=toern
    ).first()

    is_skipper = teilnahme and teilnahme.rolle == "skipper"
    is_coskipper = teilnahme and teilnahme.rolle == "coskipper"

    if not teilnahme:
        return render(request, "403.html")

    # Alle Teilnahmen für diesen Törn
    teilnahmen = Teilnahme.objects.filter(toern=toern).select_related("user")

    crew_liste = [t.user for t in teilnahmen]

    context = {
        "toern": toern,
        "teilnahmen": teilnahmen,
        "crew_liste": crew_liste,
        "is_skipper": is_skipper,
        "is_coskipper": is_coskipper,
    }

    return render(request, "crew/crew_dashboard.html", context)
