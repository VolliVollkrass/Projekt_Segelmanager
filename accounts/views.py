from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash, authenticate, login
from django.contrib.auth.views import LoginView
from django_ratelimit.decorators import ratelimit

from .forms import RegisterForm, LoginForm, AccountEditForm, LizenzForm, OnboardingForm
from .models import Lizenz

@ratelimit(key='ip', rate='5/h', block=True)
@ratelimit(key='post:email', rate='3/h', block=True)
def register(request):

    if request.method == "POST":
        form = RegisterForm(request.POST, request.FILES)

        if form.is_valid():

            user = form.save()

            # wichtig bei mehreren Backends (axes etc.)
            user = authenticate(
                request,
                username=user.email,
                password=form.cleaned_data["password1"]
            )

            if user is not None:
                login(request, user)
                return redirect("onboarding")

            messages.error(request, "Login nach Registrierung fehlgeschlagen.")

    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


@login_required
def onboarding(request):
    from utils.user_profil_fortschritt import user_profil_fortschritt
    if user_profil_fortschritt(request.user) >= 80:
        return redirect("crew_overview")

    if request.method == "POST":
        form = OnboardingForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil gespeichert – willkommen an Bord!")
            return redirect("crew_overview")
    else:
        form = OnboardingForm(instance=request.user)

    return render(request, "accounts/onboarding.html", {"form": form})


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm


@login_required
def my_account(request):
    from toern.models import Teilnahme
    from django.utils.timezone import now
    from utils.user_profil_fortschritt import user_profil_fortschritt

    jetzt = now()
    teilnahmen = (
        Teilnahme.objects
        .filter(user=request.user)
        .select_related("toern")
        .order_by("toern__startdatum")
    )

    kommende = [t for t in teilnahmen if t.toern.startdatum >= jetzt]
    vergangene = [t for t in teilnahmen if t.toern.startdatum < jetzt]

    naechste = kommende[0] if kommende else None
    tage_bis_naechster = None
    if naechste:
        delta = naechste.toern.startdatum - jetzt
        tage_bis_naechster = max(0, delta.days)

    return render(request, "accounts/my_account.html", {
        "kommende_teilnahmen": kommende,
        "vergangene_teilnahmen": vergangene,
        "naechste_teilnahme": naechste,
        "tage_bis_naechster": tage_bis_naechster,
        "profil_prozent": user_profil_fortschritt(request.user),
    })


@login_required
def account_edit(request):

    user = request.user

    if request.method == "POST":

        form = AccountEditForm(
            request.POST,
            request.FILES,
            instance=user
        )

        if form.is_valid():

            user = form.save()

            update_session_auth_hash(request, user)

            messages.success(
                request,
                "Profil erfolgreich aktualisiert."
            )

            return redirect("my_account")

    else:
        form = AccountEditForm(instance=user)

    return render(
        request,
        "accounts/account_edit.html",
        {"form": form}
    )


@login_required
def lizenz_hinzufuegen(request):

    if request.method == "POST":
        form = LizenzForm(request.POST, request.FILES)

        if form.is_valid():
            lizenz = form.save(commit=False)
            lizenz.user = request.user
            lizenz.save()

            messages.success(request, "Lizenz hinzugefügt.")
            return redirect("my_account")

    else:
        form = LizenzForm()

    return render(
        request,
        "accounts/lizenz_hinzufuegen.html",
        {"form": form}
    )


@login_required
def lizenz_loeschen(request, pk):

    lizenz = get_object_or_404(
        Lizenz,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":

        if lizenz.dokument_vorne:
            lizenz.dokument_vorne.delete()

        if lizenz.dokument_hinten:
            lizenz.dokument_hinten.delete()

        lizenz.delete()

        messages.success(request, "Lizenz gelöscht.")

    return redirect("my_account")