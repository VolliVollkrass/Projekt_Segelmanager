import os

from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse

from decimal import Decimal

from boote.models import Boot, Kabine
from config import settings
from finance.models import Ausgabe, TopfAusgabe
from finance.utils import berechne_salden, berechne_ausgleich
from logistik.models import Einkaufspunkt, EinkaufslistenEintrag, Gegenstand, Mahlzeit, Mitbringer, PersönlicherGegenstand, Tagesaufgabe, Tagesimpuls, TagesplanBearbeitungsrecht, Tagesthema
from utils.profil_fortschritt import teilnahme_fortschritt
from utils.user_profil_fortschritt import user_profil_fortschritt
from utils.boot_access_allowed import is_boot_access_allowed
from utils.packliste import BASIS_PACKLISTE, BOOT_STANDARD_LISTE, KALT_PACKLISTE, KALT_BOOT_LISTE, SKIPPER_LISTE
from .models import KabinenWunsch, Toern, Teilnahme, CrewPraeferenz, PacklisteVorlage, PacklisteVorlageEintrag, PacklisteStandard, PacklisteStandardEintrag, ErinnerungsMailLog, PinnwandNachricht, Mitfahrangebot, Mitfahrtanfrage
from .emails import mail_zuteilung_fixiert, mail_teilnahme_bestaetigt, mail_teilnahme_abgelehnt, mail_teilnahme_abgesagt, mail_crew_daten_erinnerung, mail_toern_abgeschlossen
from .crew_utils import fehlende_crew_felder
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from utils.permissions import anbieter_required, is_owner
from django.core.exceptions import PermissionDenied
from .forms import TeilnahmeDetailForm, ToernForm, TeilnahmeForm
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_POST
from django.utils.timezone import now
import json
from django.http import JsonResponse, Http404
from datetime import date, timedelta


User = get_user_model()

# =========================
# HELPER FUNCTIONS
# =========================
def get_partner_map(toern):
    pairs = KabinenWunsch.objects.filter(
        toern=toern,
        status="accepted"
    ).select_related("from_user", "to_user")

    partner_map = {}

    for p in pairs:
        partner_map[p.from_user.id] = p.to_user
        partner_map[p.to_user.id] = p.from_user

    return partner_map

def check_privat_zugang(request, toern):
    """Zugriff auf einen privaten Törn prüfen — Http404 wenn nicht berechtigt.

    Berechtigt: Anbieter, Teilnehmer, Staff, oder Besucher mit gültigem
    ?key=<privat_token> (wird in der Session gemerkt, damit Registrierung
    und Anmeldung danach ohne Link funktionieren).
    """
    if not toern.ist_privat:
        return

    session_key = f"toern_privat_key_{toern.pk}"
    key = request.GET.get("key") or request.session.get(session_key)

    ist_anbieter = request.user.is_authenticated and request.user == toern.anbieter
    ist_teilnehmer = request.user.is_authenticated and Teilnahme.objects.filter(
        toern=toern, user=request.user
    ).exists()
    hat_gueltigen_key = key == str(toern.privat_token)

    if not (ist_anbieter or ist_teilnehmer or hat_gueltigen_key or request.user.is_staff):
        raise Http404

    if hat_gueltigen_key:
        request.session[session_key] = str(toern.privat_token)


def toern_detail(request, pk):
    toern = get_object_or_404(Toern, pk=pk)

    # 🔒 Privater Törn: nur Anbieter, Teilnehmer oder Besucher mit gültigem Link
    check_privat_zugang(request, toern)

    # optional: alle Boote des Törns laden
    boote = toern.boote.all()

    # Skipper pro Boot — 1 Query für alle Boote statt 1 pro Boot
    skippers = Teilnahme.objects.filter(
        toern=toern,
        boot__in=boote,
        rolle="skipper",
        status__in=["angemeldet", "bestaetigt"]
    ).select_related("user")
    skipper_pro_boot = {s.boot_id: s for s in skippers}

    user_teilnahme = None

    if request.user.is_authenticated:
        user_teilnahme = Teilnahme.objects.filter(
            user=request.user,
            toern=toern
        ).first()


    rtx = {
        'toern': toern,
        'boote': boote,
        'skipper_pro_boot': skipper_pro_boot,
        'user_teilnahme': user_teilnahme,
    }

    return render(request, 'toern/toern_detail.html', rtx )

def toern_anmeldung(request, pk):
    toern = get_object_or_404(Toern, pk=pk)

    # 🔒 Privater Törn: gleiche Zugangsprüfung wie auf der Detailseite
    check_privat_zugang(request, toern)

    if request.method == "POST":
        form = TeilnahmeForm(request.POST)

        if form.is_valid():

            # =========================
            # USER LOGIK
            # =========================
            if request.user.is_authenticated:
                user = request.user
                if not user.geschlecht:
                    user.geschlecht = form.cleaned_data.get("geschlecht")

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
                        "geschlecht": form.cleaned_data.get("geschlecht"),
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

            # =========================
            # 🆕 WARTELISTE LOGIK
            # =========================
            if toern.freie_plaetze > 0:
                teilnahme.status = "angemeldet"
                messages.success(request, "Erfolgreich angemeldet! 🎉")
            else:
                teilnahme.status = "warteliste"
                messages.warning(request, "Der Törn ist aktuell voll – du stehst auf der Warteliste.")

            teilnahme.save()
            return redirect("crew_dashboard", toern_id=toern.pk)

    else:
        initial = {}
        if request.user.is_authenticated:
            letzte = (
                Teilnahme.objects
                .filter(user=request.user)
                .exclude(toern=toern)
                .order_by("-toern__startdatum")
                .first()
            )
            if letzte and letzte.individuelle_meilen:
                initial["individuelle_meilen"] = letzte.individuelle_meilen
        form = TeilnahmeForm(initial=initial)

    boote = toern.boote.all()
    return render(request, "toern/toern_anmeldung.html", {
        "toern": toern,
        "form": form,
        "boote": boote,
    })

@login_required
@anbieter_required
def anbieter_dashboard(request):

    toerns = (
        Toern.objects
        .filter(anbieter=request.user)
        .order_by("-startdatum")
        .prefetch_related("boote__kabinen", "teilnahmen__user", "teilnahmen__boot")
    )

    ctx = {"toerns": toerns}

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
@login_required
@login_required
@require_POST
def toern_status_abschliessen(request, pk):
    toern = get_object_or_404(Toern, pk=pk)
    is_anbieter = toern.anbieter == request.user
    is_skipper_coskipper = Teilnahme.objects.filter(
        toern=toern, user=request.user, rolle__in=("skipper", "coskipper")
    ).exists()
    if not is_anbieter and not is_skipper_coskipper:
        raise PermissionDenied

    war_bereits_abgeschlossen = toern.status == "ABGESCHLOSSEN"
    toern.status = "ABGESCHLOSSEN"
    toern.save(update_fields=["status"])

    if not war_bereits_abgeschlossen:
        bestaetigt = Teilnahme.objects.filter(
            toern=toern, status="bestaetigt"
        ).select_related("user", "boot")
        mail_toern_abgeschlossen(toern, bestaetigt, request)
        messages.success(request, f'Törn "{toern.titel}" wurde abgeschlossen – alle Crew-Mitglieder wurden informiert.')
    else:
        messages.success(request, f'Törn "{toern.titel}" ist bereits abgeschlossen.')

    return redirect("skipper_dashboard", toern_id=toern.id)


@anbieter_required
@require_POST
def toern_delete(request, pk):
    toern = get_object_or_404(Toern, pk=pk)
    if toern.anbieter != request.user:
        raise PermissionDenied
    titel = toern.titel
    toern.delete()
    messages.success(request, f'Törn "{titel}" wurde gelöscht.')
    return redirect("anbieter_dashboard")


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
def toern_privat_toggle(request, pk):
    toern = get_object_or_404(Toern, pk=pk)

    if toern.anbieter != request.user:
        raise PermissionDenied

    toern.ist_privat = not toern.ist_privat
    toern.save(update_fields=["ist_privat"])

    if toern.ist_privat:
        messages.success(request, f"„{toern.titel}“ ist jetzt privat — nur über den Einladungslink erreichbar.")
    else:
        messages.success(request, f"„{toern.titel}“ ist jetzt öffentlich sichtbar.")

    return redirect("anbieter_dashboard")


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

STATUS_LABELS = {
    "angemeldet":  {"label": "Anmeldung eingegangen", "badge": "badge-warning"},
    "warteliste":  {"label": "Warteliste",             "badge": "badge-ghost"},
    "bestaetigt":  {"label": "Bestätigt",              "badge": "badge-success"},
    "abgesagt":    {"label": "Abgesagt",               "badge": "badge-error"},
    "abgelehnt":   {"label": "Abgelehnt",              "badge": "badge-error"},
}

@login_required
def crew_overview(request):
    teilnahmen = (
        Teilnahme.objects
        .filter(user=request.user)
        .select_related("toern")
        .order_by("toern__startdatum")
    )

    jetzt = now()
    kommende_teilnahmen = []
    vergangene_teilnahmen = []

    for t in teilnahmen:
        t.status_info = STATUS_LABELS.get(t.status, {"label": t.status, "badge": "badge-ghost"})
        if t.toern.startdatum >= jetzt:
            kommende_teilnahmen.append(t)
        else:
            vergangene_teilnahmen.append(t)

    vergangene_teilnahmen.sort(key=lambda t: t.toern.startdatum, reverse=True)

    naechste_teilnahme = kommende_teilnahmen[0] if kommende_teilnahmen else None

    profil_prozent = user_profil_fortschritt(request.user)

    context = {
        "kommende_teilnahmen": kommende_teilnahmen,
        "vergangene_teilnahmen": vergangene_teilnahmen,
        "naechste_teilnahme": naechste_teilnahme,
        "profil_prozent": profil_prozent,
    }

    return render(request, "crew/crew_overview.html", context)


def _mitfahrangebote_mit_anfrage(toern, user):
    angebote = list(
        Mitfahrangebot.objects.filter(toern=toern)
        .select_related("user")
        .prefetch_related("anfragen__anfragender")
    )
    anfragen_map = {
        a.angebot_id: a
        for a in Mitfahrtanfrage.objects.filter(anfragender=user, angebot__toern=toern)
    }
    for a in angebote:
        a.meine_anfrage = anfragen_map.get(a.id)
    return angebote


def crew_dashboard(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    # =========================
    # 1. Teilnahme prüfen
    # =========================
    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=toern
    ).select_related("boot").first()

    if not teilnahme:
        return render(request, "403.html")

    if teilnahme.status == "warteliste":
        messages.warning(request, "Du bist aktuell auf der Warteliste.")
        return redirect("toern_detail", pk=toern.id)
    
    boot_access = is_boot_access_allowed(teilnahme)
    # =========================
    # 2. Rollen
    # =========================
    is_skipper = teilnahme.rolle == "skipper"
    is_coskipper = teilnahme.rolle == "coskipper"

    # =========================
    # 3. Crew
    # =========================
    teilnahmen = Teilnahme.objects.filter(
        toern=toern,
        status__in=["angemeldet", "bestaetigt"]
    ).select_related("user")

    teilnahmen_ohne_mich = teilnahmen.exclude(user=request.user)

    # =========================
    # 4. Kabinen-System
    # =========================
    kabinenwuensche = KabinenWunsch.objects.filter(
        toern=toern
    ).select_related("from_user", "to_user")

    anfragen = kabinenwuensche.filter(
        to_user=request.user,
        status="pending"
    )

    eigene_anfrage = kabinenwuensche.filter(
        from_user=request.user,
        status="pending"
    ).first()

    accepted_pairs = kabinenwuensche.filter(status="accepted")
    pending_requests = kabinenwuensche.filter(status="pending")

    # =========================
    # 5. Status Sets (optimiert)
    # =========================
    vergebene_user_ids = {
        u
        for w in accepted_pairs
        for u in [w.from_user.id, w.to_user.id]
    }

    pending_user_ids = {
        u
        for w in pending_requests
        for u in [w.from_user.id, w.to_user.id]
    }

    # Wer wartet auf wen
    pending_map = {
        w.from_user.id: w.to_user
        for w in pending_requests
    }

    # =========================
    # 6. Eigener Partner
    # =========================
    eigener_partner = None

    eigener_wunsch = accepted_pairs.filter(
        Q(from_user=request.user) | Q(to_user=request.user)
    ).first()

    if eigener_wunsch:
        eigener_partner = (
            eigener_wunsch.to_user
            if eigener_wunsch.from_user == request.user
            else eigener_wunsch.from_user
        )

    # =========================
    # 7. Präferenzen
    # =========================
    praeferenzen = CrewPraeferenz.objects.filter(
        toern=toern,
        from_user=request.user
    )

    exclude_ids = set(
        praeferenzen.filter(typ="exclude")
        .values_list("to_user_id", flat=True)
    )

    avoid_ids = set(
        praeferenzen.filter(typ="avoid")
        .values_list("to_user_id", flat=True)
    )

    # ❗ wichtig: Konflikt vermeiden
    avoid_ids -= exclude_ids

    # =========================
    # 8. Context
    # =========================
    teilnahme.status_info = STATUS_LABELS.get(teilnahme.status, {"label": teilnahme.status, "badge": "badge-ghost"})

    context = {
        "toern": toern,
        "teilnahme": teilnahme,
        "teilnahmen": teilnahmen,
        "teilnahmen_ohne_mich": teilnahmen_ohne_mich,
        "profil_progress": teilnahme_fortschritt(teilnahme),

        "is_skipper": is_skipper,
        "is_coskipper": is_coskipper,

        # Kabinen
        "anfragen": anfragen,
        "eigene_anfrage": eigene_anfrage,
        "accepted_pairs": accepted_pairs,
        "vergebene_user_ids": vergebene_user_ids,
        "pending_user_ids": pending_user_ids,
        "pending_map": pending_map,
        "eigener_partner": eigener_partner,
        "boot_access": boot_access,

        # Präferenzen
        "exclude_ids": exclude_ids,
        "avoid_ids": avoid_ids,
        "praeferenz_modus": toern.praeferenz_modus,
        "boote_count": toern.boote.count(),

        # Abschluss-Daten (Boot des Crew-Mitglieds)
        "abschluss_boot": teilnahme.boot,

        # Schwarzes Brett
        "pinnwand_nachrichten": PinnwandNachricht.objects.filter(toern=toern).select_related("autor"),
        "kann_pinnwand_posten": is_skipper or is_coskipper or (toern.anbieter == request.user),

        # Mitfahrgelegenheiten
        "mitfahrangebote": _mitfahrangebote_mit_anfrage(toern, request.user),
    }

    return render(request, "crew/crew_dashboard.html", context)

@login_required
@anbieter_required
@require_POST
def boot_skipper_assign(request, boot_id):
    boot = get_object_or_404(Boot, id=boot_id)
    toern = boot.toern

    if not is_owner(request.user, toern):
        raise PermissionDenied

    skipper_id = request.POST.get("skipper_id")
    coskipper_id = request.POST.get("coskipper_id")

    # 🔄 Reset nur für dieses Boot
    Teilnahme.objects.filter(
        toern=toern,
        boot=boot,
        rolle="skipper"
    ).update(rolle="crew")

    Teilnahme.objects.filter(
        toern=toern,
        boot=boot,
        rolle="coskipper"
    ).update(rolle="crew")

    # 👨‍✈️ Skipper setzen
    if skipper_id:
        Teilnahme.objects.filter(
            toern=toern,
            user_id=skipper_id
        ).update(
            rolle="skipper",
            boot=boot
        )

    # 🧭 Co-Skipper setzen
    if coskipper_id and coskipper_id != skipper_id:
        Teilnahme.objects.filter(
            toern=toern,
            user_id=coskipper_id
        ).update(
            rolle="coskipper",
            boot=boot
        )

    return redirect("anbieter_dashboard")

def user_has_accepted_partner(user, toern):
    return KabinenWunsch.objects.filter(
        toern=toern,
        status="accepted"
    ).filter(
        Q(from_user=user) | Q(to_user=user)
    ).exists()

@login_required
@require_POST
def kabinenpartner_anfragen(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    if toern.status in ("ZUTEILUNG_FIXIERT", "ABGESCHLOSSEN"):
        messages.error(request, "Die Zuteilung ist abgeschlossen. Kabinenpartner-Anfragen sind nicht mehr möglich.")
        return redirect(reverse("crew_dashboard", args=[toern_id]) + "?tab=crew")

    partner_id = request.POST.get("partner_id")

    if not partner_id:
        return redirect("crew_dashboard", toern_id=toern.id)

    partner = get_object_or_404(User, id=partner_id)

    # ❌ sich selbst wählen
    if partner == request.user:
        messages.error(request, "Du kannst dich nicht selbst wählen.")
        return redirect("crew_dashboard", toern_id=toern.id)

    # ❌ schon vergeben?
    if user_has_accepted_partner(request.user, toern):
        messages.error(request, "Du hast bereits einen Kabinenpartner.")
        return redirect("crew_dashboard", toern_id=toern.id)

    if user_has_accepted_partner(partner, toern):
        messages.error(request, "Diese Person ist bereits vergeben.")
        return redirect("crew_dashboard", toern_id=toern.id)

    # Anfrage erstellen / updaten
    KabinenWunsch.objects.update_or_create(
        toern=toern,
        from_user=request.user,
        to_user=partner,
        defaults={"status": "pending"}
    )

    messages.success(request, "Anfrage gesendet!")
    return redirect("crew_dashboard", toern_id=toern.id)

@login_required
@require_POST
def kabinenpartner_antwort(request, wunsch_id):
    wunsch = get_object_or_404(KabinenWunsch, id=wunsch_id)

    if wunsch.to_user != request.user:
        raise PermissionDenied

    if wunsch.toern.status in ("ZUTEILUNG_FIXIERT", "ABGESCHLOSSEN"):
        messages.error(request, "Die Zuteilung ist abgeschlossen.")
        return redirect(reverse("crew_dashboard", args=[wunsch.toern.id]) + "?tab=crew")

    action = request.POST.get("action")

    if action == "accept":
        wunsch.status = "accepted"

        # 🔥 alles andere löschen (beide User blockieren)
        KabinenWunsch.objects.filter(
            toern=wunsch.toern
        ).filter(
            Q(from_user=wunsch.from_user) |
            Q(to_user=wunsch.from_user) |
            Q(from_user=wunsch.to_user) |
            Q(to_user=wunsch.to_user)
        ).exclude(id=wunsch.id).delete()

        messages.success(request, "Kabinenpartner bestätigt!")

    elif action == "reject":
        wunsch.status = "rejected"
        messages.info(request, "Anfrage abgelehnt.")

    wunsch.save()

    return redirect("crew_dashboard", toern_id=wunsch.toern.id)

@login_required
@require_POST
def praeferenzen_speichern(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    if toern.status in ("ZUTEILUNG_FIXIERT", "ABGESCHLOSSEN"):
        messages.error(request, "Die Zuteilung ist abgeschlossen. Präferenzen können nicht mehr geändert werden.")
        return redirect(reverse("crew_dashboard", args=[toern_id]) + "?tab=crew")

    if toern.praeferenz_modus == "keiner":
        messages.error(request, "Präferenzen sind für diesen Törn deaktiviert.")
        return redirect(reverse("crew_dashboard", args=[toern_id]) + "?tab=crew")

    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=toern
    ).first()

    if not teilnahme:
        raise PermissionDenied

    # Alte löschen
    CrewPraeferenz.objects.filter(
        toern=toern,
        from_user=request.user
    ).delete()

    # Sets verhindern doppelte Werte
    exclude_ids = set(request.POST.getlist("exclude"))
    avoid_ids = set(request.POST.getlist("avoid")) if toern.praeferenz_modus == "alle" else set()

    # ❗ Konfliktregel: exclude gewinnt
    avoid_ids -= exclude_ids

    # ❌ speichern
    CrewPraeferenz.objects.bulk_create([
        CrewPraeferenz(
            toern=toern,
            from_user=request.user,
            to_user_id=uid,
            typ="exclude"
        )
        for uid in exclude_ids
    ])

    # ⚠️ speichern
    CrewPraeferenz.objects.bulk_create([
        CrewPraeferenz(
            toern=toern,
            from_user=request.user,
            to_user_id=uid,
            typ="avoid"
        )
        for uid in avoid_ids
    ])

    messages.success(request, "Präferenzen gespeichert")
    return redirect("crew_dashboard", toern_id=toern.id)

@login_required
def skipper_dashboard(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    # =========================
    # 1. Berechtigung prüfen
    # =========================
    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=toern
    ).first()

    is_toern_anbieter = toern.anbieter == request.user
    if not is_toern_anbieter and (not teilnahme or teilnahme.rolle not in ["skipper", "coskipper"]):
        raise PermissionDenied

    # =========================
    # 2. Grunddaten laden
    # =========================
    teilnahmen = Teilnahme.objects.filter(
        toern=toern
    ).select_related("user", "boot", "kabine")

    # Fortschritt berechnen
    teilnahme_map = {}

    for t in teilnahmen:
        t.fortschritt = teilnahme_fortschritt(t)
        teilnahme_map[t.user.id] = t

    warteliste = teilnahmen.filter(status="warteliste")

    boote = toern.boote.prefetch_related("kabinen")

    # =========================
    # 3. Kabinenpaare
    # =========================
    accepted_pairs = KabinenWunsch.objects.filter(
        toern=toern,
        status="accepted"
    ).select_related("from_user", "to_user")

    kabinenpaare = []
    pair_lookup = {}

    for w in accepted_pairs:
        kabinenpaare.append({
            "user1": w.from_user,
            "user2": w.to_user
        })

        pair_lookup[w.from_user.id] = w.to_user
        pair_lookup[w.to_user.id] = w.from_user

    # 👉 Partner direkt an Teilnahme hängen
    for t in teilnahmen:
        t.partner = pair_lookup.get(t.user.id)

    # 👉 Fortschritt sauber zentral setzen
    for t in teilnahmen:
        t.user.fortschritt = t.fortschritt

    # 🔥 Partner absichern
    for t in teilnahmen:
        if t.partner:
            partner_t = teilnahme_map.get(t.partner.id)
            if partner_t:
                t.partner.fortschritt = partner_t.fortschritt

    # =========================
    # 4. Präferenzen
    # =========================
    praeferenzen = CrewPraeferenz.objects.filter(
        toern=toern
    ).select_related("from_user", "to_user")

    exclude_map = {}
    avoid_map = {}

    harte_konflikte = []
    kritische_konflikte = []
    gesehen = set()

    for p in praeferenzen:
        # Maps für spätere Logik
        if p.typ == "exclude":
            exclude_map.setdefault(p.from_user.id, []).append(p.to_user)
        elif p.typ == "avoid":
            avoid_map.setdefault(p.from_user.id, []).append(p.to_user)

        # Konfliktlisten für UI (ohne Duplikate)
        key = tuple(sorted([p.from_user.id, p.to_user.id]))
        if key in gesehen:
            continue

        gesehen.add(key)

        if p.typ == "exclude":
            harte_konflikte.append({
                "von": p.from_user,
                "zu": p.to_user
            })
        elif p.typ == "avoid":
            kritische_konflikte.append({
                "von": p.from_user,
                "zu": p.to_user
            })

    # 👉 direkt an Teilnahme hängen
    for t in teilnahmen:
        t.exclude_list = exclude_map.get(t.user.id, [])
        t.avoid_list = avoid_map.get(t.user.id, [])

    # =========================
    # 5. Boot → Kabinen → Crew Struktur
    # =========================
    processed_user_ids = set()
    boots_data = []

    for boot in boote:
        kabinen_data = []

        for kabine in boot.kabinen.all():
            crew = []

            for t in teilnahmen:
                if t.kabine != kabine:
                    continue

                if t.user.id in processed_user_ids:
                    continue

                if t.partner:
                    partner_t = teilnahme_map.get(t.partner.id)

                    # 🔥 Fortschritt sicher setzen
                    t.user.fortschritt = t.fortschritt
                    t.partner.fortschritt = partner_t.fortschritt if partner_t else 0

                    crew.append({
                        "type": "pair",
                        "users": [t.user, t.partner]
                    })
                    processed_user_ids.add(t.user.id)
                    processed_user_ids.add(t.partner.id)

                else:
                    crew.append({
                        "type": "single",
                        "users": [t.user]
                    })
                    processed_user_ids.add(t.user.id)

            kabinen_data.append({
                "kabine": kabine,
                "crew": crew
            })

        boots_data.append({
            "boot": boot,
            "kabinen": kabinen_data
        })

    # =========================
    # 6. Unassigned Crew
    # =========================
    unassigned = []

    for t in teilnahmen:
        if t.user.id in processed_user_ids:
            continue

        if t.partner:
            partner_t = teilnahme_map.get(t.partner.id)

            t.user.fortschritt = t.fortschritt
            t.partner.fortschritt = partner_t.fortschritt if partner_t else 0

            unassigned.append({
                "type": "pair",
                "users": [t.user, t.partner]
            })
            processed_user_ids.add(t.user.id)
            processed_user_ids.add(t.partner.id)

        else:
            unassigned.append({
                "type": "single",
                "users": [t.user]
            })
            processed_user_ids.add(t.user.id)

    # =========================
    # 7. Context
    # =========================
    count_bestaetigt = teilnahmen.filter(status="bestaetigt").count()
    count_angemeldet = teilnahmen.filter(status="angemeldet").count()

    # =========================
    # 8. Abschluss-Daten (je Boot)
    # =========================
    if is_toern_anbieter:
        abschluss_boote_qs = boote
    else:
        user_boot_ids = Teilnahme.objects.filter(
            user=request.user,
            toern=toern,
            rolle__in=["skipper", "coskipper"]
        ).values_list("boot_id", flat=True)
        abschluss_boote_qs = boote.filter(id__in=user_boot_ids)

    abschluss_data = []
    for boot in abschluss_boote_qs:
        crew = Teilnahme.objects.filter(
            toern=toern, boot=boot, status="bestaetigt"
        ).select_related("user").order_by("user__last_name", "user__first_name")
        abschluss_data.append({"boot": boot, "crew": list(crew)})

    # =========================
    # 9. Skipper-Topf
    # =========================
    topf_ausgaben = TopfAusgabe.objects.filter(toern=toern).select_related("erstellt_von")
    topf_summe = sum((a.betrag for a in topf_ausgaben), Decimal("0"))
    topf_rest = toern.skipper_budget - topf_summe

    context = {
        "toern": toern,

        # Drag & Drop
        "boots_data": boots_data,
        "unassigned": unassigned,

        # Übersicht
        "kabinenpaare": kabinenpaare,
        "harte_konflikte": harte_konflikte,
        "kritische_konflikte": kritische_konflikte,
        "teilnahmen": teilnahmen,
        "warteliste": warteliste,
        "teilnahme_map": teilnahme_map,

        # Stats
        "count_bestaetigt": count_bestaetigt,
        "count_angemeldet": count_angemeldet,
        "count_warteliste": warteliste.count(),
        "count_unassigned": len(unassigned),

        # Erinnerungsmail-Log
        "reminder_logs": ErinnerungsMailLog.objects.filter(toern=toern).select_related("empfaenger")[:50],

        # Abschluss
        "abschluss_data": abschluss_data,

        # Präferenz-Modus
        "boote_count": boote.count(),

        # Skipper-Topf
        "topf_ausgaben": topf_ausgaben,
        "topf_summe": topf_summe,
        "topf_rest": topf_rest,
    }

    return render(request, "skipper/skipper_dashboard.html", context)


@login_required
@require_POST
def boot_abschluss_update(request, boot_id):
    boot = get_object_or_404(Boot, id=boot_id)
    toern = boot.toern

    is_anbieter = toern.anbieter == request.user
    is_boot_skipper = Teilnahme.objects.filter(
        user=request.user,
        toern=toern,
        boot=boot,
        rolle__in=["skipper", "coskipper"]
    ).exists()

    if not is_anbieter and not is_boot_skipper:
        raise PermissionDenied

    # Boot-spezifisch: Standard-Seemeilen + Logbuch
    try:
        boot.skipper_meilen = max(0, int(request.POST.get("skipper_meilen", 0) or 0))
    except (ValueError, TypeError):
        pass

    if "logbuch_pdf" in request.FILES:
        boot.logbuch_pdf = request.FILES["logbuch_pdf"]

    boot.save()

    # Individuelle Meilen pro Teilnahme (optionale Ausnahmen)
    crew = Teilnahme.objects.filter(toern=toern, boot=boot, status="bestaetigt")
    for t in crew:
        raw = request.POST.get(f"individuelle_meilen_{t.id}", "").strip()
        if raw:
            try:
                t.individuelle_meilen = max(0, int(raw))
            except (ValueError, TypeError):
                t.individuelle_meilen = None
        else:
            t.individuelle_meilen = None
        t.save(update_fields=["individuelle_meilen"])

    messages.success(request, f'Daten für "{boot.name}" gespeichert.')
    return redirect("skipper_dashboard", toern_id=toern.id)


@login_required
@require_POST
def praeferenz_modus_setzen(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)
    is_anbieter = toern.anbieter == request.user
    is_skipper = Teilnahme.objects.filter(
        toern=toern, user=request.user, rolle__in=("skipper", "coskipper")
    ).exists()
    if not is_anbieter and not is_skipper:
        raise PermissionDenied
    modus = request.POST.get("praeferenz_modus", "alle")
    if modus not in ("keiner", "nur_ausschluss", "alle"):
        modus = "alle"
    toern.praeferenz_modus = modus
    toern.save(update_fields=["praeferenz_modus"])
    messages.success(request, "Präferenz-Einstellung gespeichert.")
    return redirect(reverse("skipper_dashboard", args=[toern_id]) + "?tab=crew")


@login_required
@require_POST
@login_required
@require_POST
def toern_tagesimpulse_toggle(request, pk):
    """Tagesthema & Impulse für einen Törn ein-/ausschalten."""
    toern = get_object_or_404(Toern, pk=pk)
    is_anbieter = toern.anbieter == request.user
    is_skipper = Teilnahme.objects.filter(
        toern=toern, user=request.user, rolle__in=('skipper', 'coskipper')
    ).exists()
    if not is_anbieter and not is_skipper:
        raise PermissionDenied
    toern.tagesimpulse_aktiv = not toern.tagesimpulse_aktiv
    toern.save(update_fields=['tagesimpulse_aktiv'])
    return JsonResponse({'aktiv': toern.tagesimpulse_aktiv})


def toern_foto_links_update(request, pk):
    toern = get_object_or_404(Toern, pk=pk)
    is_anbieter = toern.anbieter == request.user
    is_skipper_coskipper = Teilnahme.objects.filter(
        toern=toern, user=request.user, rolle__in=("skipper", "coskipper")
    ).exists()
    if not is_anbieter and not is_skipper_coskipper:
        raise PermissionDenied

    toern.foto_upload_link = request.POST.get("foto_upload_link", "").strip()
    toern.foto_download_link = request.POST.get("foto_download_link", "").strip()
    toern.save(update_fields=["foto_upload_link", "foto_download_link"])
    messages.success(request, "Foto-Links gespeichert.")
    return redirect("skipper_dashboard", toern_id=toern.id)


@login_required
@require_POST
def kabine_update(request, toern_id):
    try:
        # =========================
        # 1. Törn + Permission
        # =========================
        toern = get_object_or_404(Toern, id=toern_id)

        teilnahme = Teilnahme.objects.filter(
            user=request.user,
            toern=toern
        ).first()

        if not teilnahme or teilnahme.rolle not in ["skipper", "coskipper"]:
            raise PermissionDenied

        # =========================
        # 2. Request Daten
        # =========================
        data = json.loads(request.body.decode("utf-8"))

        user_ids_raw = data.get("user_ids", "")
        kabine_id = data.get("kabine_id")

        user_ids = [uid for uid in user_ids_raw.split(",") if uid]

        if not user_ids:
            return JsonResponse({
                "status": "error",
                "message": "Keine User IDs"
            }, status=400)

        # =========================
        # 3. Partner erzwingen 🔥
        # =========================
        partner_map = get_partner_map(toern)

        all_user_ids = set(user_ids)

        for uid in user_ids:
            partner = partner_map.get(uid)
            if partner:
                all_user_ids.add(str(partner.id))  # wichtig: string!

        # =========================
        # 4. Kabine + Boot bestimmen
        # =========================
        kabine = None
        boot = None

        if kabine_id:
            kabine = Kabine.objects.select_related("boot").get(id=int(kabine_id))
            boot = kabine.boot

        # =========================
        # 4.5 KAPAZITÄT PRÜFEN 🔥
        # =========================

        # 👉 aktuelle Belegung der Ziel-Kabine
        if kabine:
            current_users = Teilnahme.objects.filter(
                toern=toern,
                kabine=kabine
            ).exclude(
                user_id__in=all_user_ids  # wichtig: aktuelle Bewegung ignorieren
            )

            current_count = current_users.count()
            incoming_count = len(all_user_ids)

            if current_count + incoming_count > kabine.betten:
                return JsonResponse({
                    "status": "error",
                    "message": f"Kabine voll ({kabine.betten} Plätze)"
                }, status=400)


        # 👉 Boot Kapazität prüfen
        if boot:
            current_boot_users = Teilnahme.objects.filter(
                toern=toern,
                boot=boot
            ).exclude(
                user_id__in=all_user_ids
            )

            current_boot_count = current_boot_users.count()
            incoming_count = len(all_user_ids)

            if current_boot_count + incoming_count > boot.anzahl_betten_boot:
                return JsonResponse({
                    "status": "error",
                    "message": f"Boot voll ({boot.anzahl_betten_boot} Plätze)"
                }, status=400)

        # =========================
        # 5. DB Update
        # =========================
        teilnahmen = Teilnahme.objects.filter(
            toern=toern,
            user_id__in=all_user_ids
        )

        if not teilnahmen.exists():
            return JsonResponse({
                "status": "error",
                "message": "Teilnahmen nicht gefunden"
            }, status=404)

        for t in teilnahmen:
            t.kabine = kabine
            t.boot = boot
            t.save()

        # =========================
        # 6. Response
        # =========================
        return JsonResponse({
            "status": "ok",
            "updated_users": list(all_user_ids),
            "kabine_id": kabine_id,
            "boot_id": boot.id if boot else None
        })

    except Kabine.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Kabine existiert nicht"
        }, status=400)

    except PermissionDenied:
        return JsonResponse({
            "status": "error",
            "message": "Keine Berechtigung"
        }, status=403)

    except Exception as e:
        print("❌ kabine_update ERROR:", str(e))
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)
    
@login_required
@require_POST
def reset_zuteilung(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=toern
    ).first()

    if not teilnahme or teilnahme.rolle not in ["skipper", "coskipper"]:
        raise PermissionDenied

    # =========================
    # RESET LOGIK
    # =========================
    Teilnahme.objects.filter(
        toern=toern
    ).exclude(
        rolle__in=["skipper", "coskipper"]
    ).update(
        boot=None,
        kabine=None
    )

    messages.success(request, "Zuteilung wurde zurückgesetzt")

    return redirect("skipper_dashboard", toern_id=toern.id)
    
@login_required
@require_POST
def auto_assign(request, toern_id):
    import json

    toern = get_object_or_404(Toern, id=toern_id)
    data = json.loads(request.body or "{}")

    avoid_mode = data.get("avoid_mode", "soft")
    balance = data.get("balance", True)

    teilnahmen = list(
        Teilnahme.objects.filter(
            toern=toern,
            status__in=["angemeldet", "bestaetigt"]
        ).select_related("user", "boot", "kabine")
    )

    boote = list(toern.boote.prefetch_related("kabinen"))

    # =========================
    # 1. PARTNER MAP
    # =========================
    partner_map = get_partner_map(toern)

    # =========================
    # 2. GRUPPEN BAUEN (🔥 CORE)
    # =========================
    assigned = set()
    groups = []

    for t in teilnahmen:

        if t.user.id in assigned:
            continue

        partner = partner_map.get(t.user.id)

        # 👉 Paar
        if partner and partner.id not in assigned:
            groups.append({
                "users": [t.user, partner],
                "size": 2,
                "type": "pair"
            })
            assigned.add(t.user.id)
            assigned.add(partner.id)

        # 👉 Single
        else:
            groups.append({
                "users": [t.user],
                "size": 1,
                "type": "single"
            })
            assigned.add(t.user.id)

    # =========================
    # 3. KAPAZITÄT
    # =========================
    boot_state = {
        b.id: {
            "boot": b,
            "capacity": sum(k.betten for k in b.kabinen.all()),
            "used": 0,
            "groups": []
        }
        for b in boote
    }

    # =========================
    # 4. SKIPPER FIXIEREN
    # =========================
    for g in groups:

        # 👉 prüfe nur EINEN user der gruppe
        u = g["users"][0]

        t = next(x for x in teilnahmen if x.user.id == u.id)

        if t.rolle in ["skipper", "coskipper"] and t.boot:

            state = boot_state[t.boot.id]

            state["groups"].append(g)
            state["used"] += g["size"]

            g["fixed"] = True

    # =========================
    # 5. REST GRUPPEN
    # =========================
    free_groups = [g for g in groups if not g.get("fixed")]

    # größere Gruppen zuerst
    free_groups.sort(key=lambda g: -g["size"])

    # =========================
    # 6. PRÄFERENZEN
    # =========================
    praeferenzen = CrewPraeferenz.objects.filter(toern=toern)

    exclude = set()
    avoid = set()

    for p in praeferenzen:
        key = tuple(sorted([p.from_user.id, p.to_user.id]))
        if p.typ == "exclude":
            exclude.add(key)
        else:
            avoid.add(key)

    teilnahme_map = {
        t.user.id: t
        for t in teilnahmen
    }

    

    def score(group, boot_groups):
        s = 0

        # =========================
        # 🔧 HELPER
        # =========================
        def get_age(user):
            if user.geburtsdatum:
                today = date.today()
                return (
                    today.year
                    - user.geburtsdatum.year
                    - ((today.month, today.day) < (user.geburtsdatum.month, user.geburtsdatum.day))
                )
            return None

        def get_exp(user):
            t = teilnahme_map.get(user.id)
            return int(t.seglerische_erfahrung) if t else 1

        # =========================
        # 🔁 VERGLEICHE
        # =========================
        for other_group in boot_groups:
            for u1 in group["users"]:
                for u2 in other_group["users"]:

                    key = tuple(sorted([u1.id, u2.id]))

                    # ❌ HARD BLOCK
                    if key in exclude:
                        return None

                    # ⚠️ AVOID
                    if key in avoid:
                        s += 20 if avoid_mode == "strict" else 5

                    # =========================
                    # 👥 ALTER
                    # =========================
                    if data.get("age_mode") != "ignore":

                        a1 = get_age(u1)
                        a2 = get_age(u2)

                        if a1 is not None and a2 is not None:
                            diff = abs(a1 - a2)

                            if data.get("age_mode") == "similar":
                                s += diff * 0.5

                            elif data.get("age_mode") == "mixed":
                                s -= diff * 0.3

                    # =========================
                    # ⚓ ERFAHRUNG
                    # =========================
                    if data.get("experience_mode") != "ignore":

                        e1 = get_exp(u1)
                        e2 = get_exp(u2)

                        diff = abs(e1 - e2)

                        if data.get("experience_mode") == "separate":
                            s += diff * 3

                        elif data.get("experience_mode") == "mixed":
                            s -= diff * 2

                    # =========================
                    # 🚻 GESCHLECHT
                    # =========================
                    if data.get("gender_mode") != "ignore":

                        gender1 = u1.geschlecht
                        gender2 = u2.geschlecht

                        if data.get("gender_mode") == "same":
                            if gender1 != gender2:
                                s += 5

                        elif data.get("gender_mode") == "mixed":
                            if gender1 == gender2:
                                s += 2

        return s

    # =========================
    # 7. BOOT ZUWEISUNG
    # =========================
    unassigned = []

    for g in free_groups:

        best = None
        best_score = 9999

        for b_id, state in boot_state.items():

            if state["used"] + g["size"] > state["capacity"]:
                continue

            s = score(g, state["groups"])
            if s is None:
                continue

            if balance:
                s += state["used"] * 0.5

            if s < best_score:
                best_score = s
                best = state

        if not best:
            unassigned.extend(g["users"])
            continue

        best["groups"].append(g)
        best["used"] += g["size"]

    # =========================
    # 8. BOOT SPEICHERN (bulk — 2 Queries statt N)
    # =========================
    Teilnahme.objects.filter(toern=toern).update(boot=None)

    teilnahme_map_for_save = {t.user.id: t for t in teilnahmen}
    for state in boot_state.values():
        for g in state["groups"]:
            for u in g["users"]:
                t = teilnahme_map_for_save.get(u.id)
                if t:
                    t.boot = state["boot"]

    Teilnahme.objects.bulk_update(list(teilnahme_map_for_save.values()), ["boot"])

    # =========================
    # 9. KABINEN ZUWEISUNG (bulk — 2 Queries statt N)
    # =========================
    Teilnahme.objects.filter(toern=toern).update(kabine=None)

    for state in boot_state.values():

        kabinen = list(state["boot"].kabinen.all())

        kabinen_state = [
            {
                "kabine": k,
                "free": k.betten,
                "users": []
            }
            for k in kabinen
        ]

        for g in state["groups"]:

            placed = False

            for k in kabinen_state:

                if k["free"] >= g["size"]:
                    k["users"].extend(g["users"])
                    k["free"] -= g["size"]
                    placed = True
                    break

            if not placed:
                for u in g["users"]:
                    unassigned.append(u)

        for k in kabinen_state:
            for u in k["users"]:
                t = teilnahme_map_for_save.get(u.id)
                if t:
                    t.kabine = k["kabine"]

    Teilnahme.objects.bulk_update(list(teilnahme_map_for_save.values()), ["kabine"])

    return JsonResponse({
        "status": "ok",
        "unassigned": [u.id for u in unassigned]
    })

@login_required
@require_POST
def warteliste_bestaetigen(request, teilnahme_id):
    teilnahme = get_object_or_404(Teilnahme, id=teilnahme_id)

    # Rechte prüfen
    skipper = Teilnahme.objects.filter(
        user=request.user,
        toern=teilnahme.toern
    ).first()

    if not skipper or skipper.rolle not in ["skipper", "coskipper"]:
        raise PermissionDenied

    # Platz prüfen
    if teilnahme.toern.freie_plaetze > 0:
        teilnahme.status = "angemeldet"
        teilnahme.save()
        messages.success(request, "Teilnehmer bestätigt!")
    else:
        messages.error(request, "Kein freier Platz mehr!")

    return redirect("skipper_dashboard", toern_id=teilnahme.toern.id)

@login_required
@require_POST
def warteliste_ablehnen(request, teilnahme_id):
    teilnahme = get_object_or_404(Teilnahme, id=teilnahme_id)

    skipper = Teilnahme.objects.filter(
        user=request.user,
        toern=teilnahme.toern
    ).first()

    if not skipper or skipper.rolle not in ["skipper", "coskipper"]:
        raise PermissionDenied

    teilnahme.status = "abgelehnt"
    teilnahme.save()

    messages.info(request, "Teilnehmer abgelehnt")

    return redirect("skipper_dashboard", toern_id=teilnahme.toern.id)


# toern/views.py

@login_required
def teilnahme_daten_edit(request, toern_id):

    toern = get_object_or_404(Toern, id=toern_id)

    teilnahme = get_object_or_404(
        Teilnahme,
        user=request.user,
        toern=toern
    )

    user = request.user

    if request.method == "POST":
        form = TeilnahmeDetailForm(request.POST, instance=teilnahme)

        if form.is_valid():

            # 👉 TEILNAHME speichern
            teilnahme = form.save()

            # 👉 USER speichern
            user.first_name = form.cleaned_data.get("first_name") or user.first_name
            user.last_name = form.cleaned_data.get("last_name") or user.last_name
            user.geschlecht = form.cleaned_data.get("geschlecht") or user.geschlecht
            user.telefonnummer = form.cleaned_data.get("telefonnummer")
            user.geburtsdatum = form.cleaned_data.get("geburtsdatum")
            user.geburtsort = form.cleaned_data.get("geburtsort")
            user.nationalitaet = form.cleaned_data.get("nationalitaet")
            user.identifikationstyp = form.cleaned_data.get("identifikationstyp")
            user.passnummer = form.cleaned_data.get("passnummer")
            user.strasse = form.cleaned_data.get("strasse")
            user.plz = form.cleaned_data.get("plz")
            user.ort = form.cleaned_data.get("ort")
            user.geburtsland = form.cleaned_data.get("geburtsland")
            user.land = form.cleaned_data.get("land")


            user.save()

            messages.success(request, "Daten gespeichert")
            from django.urls import reverse
            url = reverse("crew_dashboard", kwargs={"toern_id": toern.id})
            return redirect(f"{url}?tab=daten")

    else:
        form = TeilnahmeDetailForm(instance=teilnahme)

        # 🔥 Prefill USER Daten
        form.initial.update({
            "first_name": user.first_name,
            "last_name": user.last_name,
            "geschlecht": user.geschlecht,
            "telefonnummer": user.telefonnummer,
            "geburtsdatum": user.geburtsdatum.strftime("%Y-%m-%d") if user.geburtsdatum else "",
            "geburtsort": user.geburtsort,
            "geburtsland": user.geburtsland,
            "nationalitaet": user.nationalitaet,

            # 👉 HIER FEHLTE ES
            "identifikationstyp": user.identifikationstyp,
            "passnummer": user.passnummer,

            "strasse": user.strasse,
            "plz": user.plz,
            "ort": user.ort,
            "land": user.land,
        })

    return render(request, "crew/crew_teilnahme_daten.html", {
        "form": form,
        "toern": toern,
        "user": user
    })

@login_required
@require_POST
def zuteilung_fixieren(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=toern
    ).first()

    # 🔐 Rechte: Skipper + Co-Skipper
    if not teilnahme or teilnahme.rolle not in ["skipper", "coskipper"]:
        raise PermissionDenied

    # ✅ Status setzen
    toern.status = "ZUTEILUNG_FIXIERT"
    toern.save()

    # 🔥 AUTO CONFIRM
    Teilnahme.objects.filter(
        toern=toern,
        boot__isnull=False
    ).update(status="bestaetigt")

    # Info-Mails an alle bestätigten Crew-Mitglieder
    bestaetigt = Teilnahme.objects.filter(
        toern=toern,
        status="bestaetigt",
    ).select_related("user", "boot", "kabine")
    for t in bestaetigt:
        mail_zuteilung_fixiert(t, request)

    # Erinnerung an alle mit unvollständigen Crewdaten
    erinnerung_count = 0
    for t in bestaetigt:
        fehlend = fehlende_crew_felder(t.user)
        if fehlend:
            mail_crew_daten_erinnerung(t.user, toern, fehlend, request)
            erinnerung_count += 1

    if erinnerung_count:
        messages.warning(request, f"{erinnerung_count} Crew-Mitglied(er) wurden an fehlende Profildaten erinnert.")

    messages.success(request, "Zuteilung wurde abgeschlossen. Crew hat jetzt Zugriff auf ihr Boot.")

    return redirect("skipper_dashboard", toern_id=toern.id)

def _hat_skipper_berechtigung(request, toern):
    if toern.anbieter == request.user:
        return True
    t = Teilnahme.objects.filter(user=request.user, toern=toern).first()
    return t and t.rolle in ["skipper", "coskipper"]


@login_required
@require_POST
def teilnehmer_bestaetigen(request, teilnahme_id):
    teilnahme = get_object_or_404(Teilnahme, id=teilnahme_id)

    if not _hat_skipper_berechtigung(request, teilnahme.toern):
        raise PermissionDenied

    teilnahme.status = "bestaetigt"
    teilnahme.save()
    mail_teilnahme_bestaetigt(teilnahme, request)

    messages.success(request, "Teilnehmer bestätigt")

    return redirect("skipper_dashboard", toern_id=teilnahme.toern.id)


@login_required
@require_POST
def teilnehmer_zuruecksetzen(request, teilnahme_id):
    teilnahme = get_object_or_404(Teilnahme, id=teilnahme_id)

    if not _hat_skipper_berechtigung(request, teilnahme.toern):
        raise PermissionDenied

    teilnahme.status = "angemeldet"
    teilnahme.save()

    messages.info(request, f"{teilnahme.user.get_full_name()} auf 'Angemeldet' zurückgesetzt")

    return redirect("skipper_dashboard", toern_id=teilnahme.toern.id)


@login_required
@require_POST
def teilnehmer_ablehnen(request, teilnahme_id):
    teilnahme = get_object_or_404(Teilnahme, id=teilnahme_id)

    if not _hat_skipper_berechtigung(request, teilnahme.toern):
        raise PermissionDenied

    teilnahme.status = "abgelehnt"
    teilnahme.boot = None
    teilnahme.kabine = None
    teilnahme.save()
    mail_teilnahme_abgelehnt(teilnahme, request)

    messages.info(request, "Teilnehmer abgelehnt")

    return redirect("skipper_dashboard", toern_id=teilnahme.toern.id)

@login_required
@require_POST
def teilnahme_absagen(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)
    teilnahme = get_object_or_404(Teilnahme, toern=toern, user=request.user)

    if teilnahme.rolle in ("skipper", "coskipper"):
        messages.error(request, "Als Skipper/Co-Skipper kannst du nicht über diesen Weg absagen. Bitte wende dich direkt an den Anbieter.")
        return redirect("crew_dashboard", toern_id=toern_id)

    teilnahme.status = "abgesagt"
    teilnahme.boot = None
    teilnahme.kabine = None
    teilnahme.save()
    mail_teilnahme_abgesagt(teilnahme, request)

    messages.info(request, "Deine Teilnahme wurde abgesagt.")
    return redirect("crew_overview")


@login_required
def boot_dashboard(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=toern
    ).select_related("boot").first()

    if not teilnahme:
        raise PermissionDenied

    # 🔐 Zugriff
    if not (
        teilnahme.status == "bestaetigt"
        and teilnahme.boot
        and toern.status == "ZUTEILUNG_FIXIERT"
    ):
        raise PermissionDenied

    # 🔥 Persönliche Packliste nur einmal erstellen — aus der Törn-Vorlage
    # (respektiert Warm/Kalt und Anpassungen des Skippers)
    if not teilnahme.persoenliche_packliste.exists():
        vorlage = _get_or_create_vorlage(toern, 'personal', user=request.user)
        PersönlicherGegenstand.objects.bulk_create([
            PersönlicherGegenstand(
                participation=teilnahme,
                name=name,
                menge=menge
            )
            for name, menge in vorlage.eintraege.values_list('name', 'menge')
        ])

    # 🔥 Skipper/Co-Skipper bekommen zusätzlich die Skipper-Ausrüstung
    if teilnahme.rolle in ("skipper", "coskipper"):
        skipper_vorlage = _get_or_create_vorlage(toern, 'skipper', user=request.user)
        existing = set(teilnahme.persoenliche_packliste.values_list('name', flat=True))
        PersönlicherGegenstand.objects.bulk_create([
            PersönlicherGegenstand(
                participation=teilnahme,
                name=name,
                menge=menge,
                ist_skipper=True
            )
            for name, menge in skipper_vorlage.eintraege.values_list('name', 'menge')
            if name not in existing
        ])

    boot = teilnahme.boot

    # 🔥 Boots-Gemeinschaftsliste erstellen, wenn leer — ebenfalls aus der Vorlage
    if not Gegenstand.objects.filter(boot=boot, toern=toern).exists():
        boot_vorlage = _get_or_create_vorlage(toern, 'boot', user=request.user)
        Gegenstand.objects.bulk_create([
            Gegenstand(
                boot=boot,
                toern=toern,
                name=name,
                menge=menge
            )
            for name, menge in boot_vorlage.eintraege.values_list('name', 'menge')
        ])

    # 👥 Crew
    kabinen = boot.kabinen.all()

    kabinen_data = []

    for kabine in kabinen:
        crew_in_kabine = Teilnahme.objects.filter(
            toern=toern,
            boot=boot,
            kabine=kabine,
            status="bestaetigt"
        ).select_related("user")

        kabinen_data.append({
            "kabine": kabine,
            "crew": crew_in_kabine
        })

    packitems = teilnahme.persoenliche_packliste.all()

    total_items = packitems.count()
    done_items = packitems.filter(erledigt=True).count()

    progress = int((done_items / total_items) * 100) if total_items > 0 else 0
    
        # 🎒 Packliste (WICHTIG angepasst)
    gegenstaende = Gegenstand.objects.filter(
        boot=boot,
        toern=toern
    ).prefetch_related("mitbringer__participation__user").order_by("name")

    # 🛒 Einkauf
    einkaufsliste = Einkaufspunkt.objects.filter(
        boot=boot,
        toern=toern
    ).select_related("verantwortlich__user")

    for g in gegenstaende:
        total = sum(m.menge for m in g.mitbringer.all())
        g.vergeben = total
        g.offen = max(g.menge - total, 0)

    gegenstaende = sorted(gegenstaende, key=lambda g: g.offen == 0)

    # 🍽️ Mahlzeiten
    mahlzeiten = Mahlzeit.objects.filter(
        boot=boot, toern=toern
    ).select_related("kochverantwortlich__user")

    # Crew-Mitglieder für Kochverantwortlichen-Dropdown + Ess-Statistik
    crew_bestaetigt = Teilnahme.objects.filter(
        toern=toern, boot=boot, status="bestaetigt"
    ).select_related("user")

    ess_stats = {
        "alles": crew_bestaetigt.filter(essgewohnheiten="alles").count(),
        "vegetarisch": crew_bestaetigt.filter(essgewohnheiten="vegetarisch").count(),
        "vegan": crew_bestaetigt.filter(essgewohnheiten="vegan").count(),
        "keine_angabe": crew_bestaetigt.filter(essgewohnheiten="").count(),
    }

    # ─── Tagesplan ───
    _TYP_ORDER = {'fruehstueck': 0, 'mittag': 1, 'abend': 2, 'essen_gehen': 3, 'snack': 4}

    tagesthemen_map = {
        t.datum: t
        for t in Tagesthema.objects.filter(boot=boot, toern=toern)
    }

    aufgaben_qs = list(
        Tagesaufgabe.objects.filter(boot=boot, toern=toern)
        .select_related('verantwortlich__user')
    )
    impulse_qs = list(
        Tagesimpuls.objects.filter(boot=boot, toern=toern)
        .select_related('verantwortlich__user')
    )
    mahlzeiten_qs = list(
        Mahlzeit.objects.filter(boot=boot, toern=toern)
        .select_related('kochverantwortlich__user', 'rezept')
    )

    tagesplan_tage = []
    if toern.startdatum and toern.enddatum:
        _start = toern.startdatum.date() if hasattr(toern.startdatum, 'date') else toern.startdatum
        _end   = toern.enddatum.date()   if hasattr(toern.enddatum,   'date') else toern.enddatum
        delta = (_end - _start).days
        for i in range(delta + 1):
            datum = _start + timedelta(days=i)
            tagesthema_obj = tagesthemen_map.get(datum)
            tagesplan_tage.append({
                'datum': datum,
                'is_anfahrt': i == 0,
                'is_abfahrt': i == delta,
                'tagesthema': tagesthema_obj.thema if tagesthema_obj else '',
                'mahlzeiten': sorted(
                    [m for m in mahlzeiten_qs if m.datum == datum],
                    key=lambda m: _TYP_ORDER.get(m.typ, 99)
                ),
                'aufgaben': [a for a in aufgaben_qs if a.datum == datum],
                'impulse': sorted(
                    [imp for imp in impulse_qs if imp.datum == datum],
                    key=lambda imp: 0 if imp.slot == 'vormittag' else 1
                ),
            })

    tagesplan_edit_rechte = set(
        TagesplanBearbeitungsrecht.objects.filter(boot=boot, toern=toern)
        .values_list('teilnahme_id', flat=True)
    )
    hat_tagesplan_edit = (
        teilnahme.rolle in ['skipper', 'coskipper']
        or request.user == toern.anbieter
        or teilnahme.id in tagesplan_edit_rechte
    )
    hat_rechte_vergeben = (
        teilnahme.rolle in ['skipper', 'coskipper']
        or request.user == toern.anbieter
    )

    # Einkaufsliste (neu)
    einkaufs_qs = EinkaufslistenEintrag.objects.filter(
        boot=boot, toern=toern
    ).select_related('einkaufer__user', 'erledigt_von')
    einkaufs_by_kat = {k: [] for k in EINKAUF_KATEGORIE_ORDER}
    for e in einkaufs_qs:
        einkaufs_by_kat.setdefault(e.kategorie, []).append(e)
    einkauf_gruppen = [
        (kat, EINKAUF_KATEGORIE_LABEL[kat], einkaufs_by_kat[kat])
        for kat in EINKAUF_KATEGORIE_ORDER
        if einkaufs_by_kat.get(kat)
    ]
    einkauf_gesamt   = einkaufs_qs.count()
    einkauf_erledigt = einkaufs_qs.filter(erledigt=True).count()

    # 💰 Bootskasse
    kasse_ausgaben = Ausgabe.objects.filter(
        boot=boot, toern=toern
    ).select_related("bezahlt_von__user", "erstellt_von").prefetch_related("beteiligt__user")

    crew_liste = list(crew_bestaetigt)
    kasse_salden = berechne_salden(kasse_ausgaben, crew_liste)
    kasse_transfers = berechne_ausgleich(kasse_salden)
    kasse_gesamt = sum((a.betrag for a in kasse_ausgaben), Decimal("0"))
    kasse_pro_person = (
        (kasse_gesamt / len(crew_liste)).quantize(Decimal("0.01"))
        if crew_liste else Decimal("0")
    )
    mein_kasse_saldo = next(
        (s["saldo"].quantize(Decimal("0.01")) for s in kasse_salden
         if s["teilnahme"].id == teilnahme.id),
        Decimal("0"),
    )
    kasse_darf_verwalten = (
        teilnahme.rolle in ("skipper", "coskipper")
        or request.user == toern.anbieter
    )

    context = {
        "toern": toern,
        "boot": boot,
        "kabinen_data": kabinen_data,
        "gegenstaende": gegenstaende,
        "einkaufsliste": einkaufsliste,
        "mahlzeiten": mahlzeiten,
        "crew_bestaetigt": crew_bestaetigt,
        "ess_stats": ess_stats,
        "teilnahme": teilnahme,
        "progress": progress,
        "done_items": done_items,
        "total_items": total_items,
        # Tagesplan
        "tagesplan_tage": tagesplan_tage,
        "hat_tagesplan_edit": hat_tagesplan_edit,
        "hat_rechte_vergeben": hat_rechte_vergeben,
        "tagesplan_edit_rechte": tagesplan_edit_rechte,
        "aufgabe_typen": Tagesaufgabe.TYP_CHOICES,
        # Einkaufsliste (neu)
        "einkauf_gruppen": einkauf_gruppen,
        "einkauf_gesamt": einkauf_gesamt,
        "einkauf_erledigt": einkauf_erledigt,
        # Bootskasse
        "kasse_ausgaben": kasse_ausgaben,
        "kasse_salden": kasse_salden,
        "kasse_transfers": kasse_transfers,
        "kasse_gesamt": kasse_gesamt,
        "kasse_pro_person": kasse_pro_person,
        "mein_kasse_saldo": mein_kasse_saldo,
        "kasse_darf_verwalten": kasse_darf_verwalten,
    }

    return render(request, "boot/boot_dashboard.html", context)

@login_required
@require_POST
def take_gegenstand(request, gegenstand_id):

    gegenstand = get_object_or_404(Gegenstand, id=gegenstand_id)

    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=gegenstand.toern
    ).first()

    if not teilnahme:
        raise PermissionDenied

    menge = int(request.POST.get("menge", 1))

    # 🔥 bereits vergebene Menge
    total = sum(m.menge for m in gegenstand.mitbringer.all())
    offen = gegenstand.menge - total

    if offen <= 0:
        return JsonResponse({"error": "Schon vollständig verteilt"}, status=400)

    if menge > offen:
        menge = offen

    # 🔁 existiert schon?
    existing = Mitbringer.objects.filter(
        gegenstand=gegenstand,
        participation=teilnahme
    ).first()

    if existing:
        existing.menge += menge
        existing.save()
    else:
        Mitbringer.objects.create(
            gegenstand=gegenstand,
            participation=teilnahme,
            menge=menge
        )

    # 🔥 persönliche Liste sauber updaten
    item, created = PersönlicherGegenstand.objects.get_or_create(
        participation=teilnahme,
        name=gegenstand.name,
        defaults={
            "menge": menge,
            "ist_vom_boot": True
        }
    )

    if not created:
        item.menge += menge
        item.ist_vom_boot = True
        item.save()

    return JsonResponse({"status": "ok"})

@login_required
@require_POST
def toggle_packitem(request, item_id):
    item = get_object_or_404(PersönlicherGegenstand, id=item_id)

    if item.participation.user != request.user:
        raise PermissionDenied

    item.erledigt = not item.erledigt
    item.save()

    return JsonResponse({
        "status": "ok",
        "done": item.erledigt
    })

@login_required
@require_POST
def delete_packitem(request, item_id):
    item = get_object_or_404(PersönlicherGegenstand, id=item_id)

    if item.participation.user != request.user:
        raise PermissionDenied

    item.delete()

    return JsonResponse({"status": "ok"})

@login_required
@require_POST
def add_packitem(request, toern_id):
    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern_id=toern_id
    ).first()

    if not teilnahme:
        raise PermissionDenied

    name = (request.POST.get("name") or "").strip()
    menge = request.POST.get("menge") or 1

    if not name:
        return JsonResponse({"error": "Name fehlt"}, status=400)

    item = PersönlicherGegenstand.objects.create(
        participation=teilnahme,
        name=name,
        menge=int(menge)
    )

    return JsonResponse({"status": "ok", "id": item.id})

@login_required
@require_POST
def update_packitem(request, item_id):
    item = get_object_or_404(PersönlicherGegenstand, id=item_id)

    if item.participation.user != request.user:
        raise PermissionDenied

    item.name = request.POST.get("name")
    item.menge = int(request.POST.get("menge") or 1)
    item.save()

    return JsonResponse({"status": "ok"})

@login_required
@require_POST
def add_boot_item(request, toern_id):
    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern_id=toern_id
    ).first()

    if not teilnahme or teilnahme.rolle not in ["skipper", "coskipper"]:
        raise PermissionDenied

    name = request.POST.get("name")
    menge = int(request.POST.get("menge") or 1)

    Gegenstand.objects.create(
        boot=teilnahme.boot,
        toern_id=toern_id,
        name=name,
        menge=menge
    )

    return JsonResponse({"status": "ok"})

@login_required
@require_POST
def update_boot_item(request, item_id):
    item = get_object_or_404(Gegenstand, id=item_id)

    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=item.toern
    ).first()

    if not teilnahme or teilnahme.rolle not in ["skipper", "coskipper"]:
        raise PermissionDenied

    item.name = request.POST.get("name")
    item.menge = int(request.POST.get("menge") or 1)
    item.save()

    return JsonResponse({"status": "ok"})

@login_required
@require_POST
def delete_boot_item(request, item_id):
    item = get_object_or_404(Gegenstand, id=item_id)

    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=item.toern
    ).first()

    if not teilnahme or teilnahme.rolle not in ["skipper", "coskipper"]:
        raise PermissionDenied

    item.delete()

    return JsonResponse({"status": "ok"})

@login_required
@require_POST
def reduce_gegenstand(request, gegenstand_id):

    gegenstand = get_object_or_404(Gegenstand, id=gegenstand_id)

    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=gegenstand.toern
    ).first()

    if not teilnahme:
        raise PermissionDenied

    menge = int(request.POST.get("menge", 1))

    mitbringer = Mitbringer.objects.filter(
        gegenstand=gegenstand,
        participation=teilnahme
    ).first()

    if not mitbringer:
        return JsonResponse({"error": "Nicht vorhanden"}, status=400)

    # 🔥 reduzieren
    if menge >= mitbringer.menge:
        mitbringer.delete()
        removed = True
    else:
        mitbringer.menge -= menge
        mitbringer.save()
        removed = False

    # 🔥 persönliche Liste anpassen
    item = PersönlicherGegenstand.objects.filter(
        participation=teilnahme,
        name=gegenstand.name
    ).first()

    if item:
        if removed or item.menge <= menge:
            item.delete()
        else:
            item.menge -= menge
            item.save()

    return JsonResponse({"status": "ok"})


from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Image, KeepTogether
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4, portrait
from django.http import HttpResponse
from datetime import date, timedelta
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

def crewlist_pdf(request, boot_id):

    boot = Boot.objects.select_related("toern").get(id=boot_id)
    toern = boot.toern

    teilnahmen = Teilnahme.objects.filter(
        boot=boot,
        status__in=["angemeldet", "bestaetigt"]
    ).select_related("user")

    # =========================
    # SORTIERUNG
    # =========================
    def sort_key(t):
        if t.rolle == "skipper":
            return (0, "")
        elif t.rolle == "coskipper":
            return (1, "")
        return (2, t.user.last_name.lower())

    teilnahmen = sorted(teilnahmen, key=sort_key)

    # =========================
    # RESPONSE
    # =========================
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="crewlist_{boot.name}.pdf"'

    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(A4),
        rightMargin=15,
        leftMargin=15,
        topMargin=35,
        bottomMargin=15
    )

    elements = []
    styles = getSampleStyleSheet()

    small_style = styles["Normal"]
    small_style.fontSize = 8
    small_style.leading = 9  # Zeilenabstand
    # =========================
    # HEADER (wie Vorlage)
    # =========================
    start = toern.startdatum.strftime("%d.%m.%Y")
    end = toern.enddatum.strftime("%d.%m.%Y")
    header_data = [
        

        ["CREW LIST / CREWLISTE  -  {} | {} - {}".format(toern.titel, start, end), "", "", ""],
        ["Name of Yacht", boot.name, "Home port", boot.hafen or ""],
        ["Registration number", "", "Country of registration", ""],
        ["Call Sign", "", "", ""],
    ]

    header_table = Table(header_data, colWidths=[120, 200, 150, 200])

    header_table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("SPAN", (0,0), (-1,0)),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))

    elements.append(header_table)
    elements.append(Spacer(1, 12))

    # =========================
    # HILFSFUNKTIONEN
    # =========================
    def calc_age(birthdate):
        today = date.today()
        return (
            today.year - birthdate.year -
            ((today.month, today.day) < (birthdate.month, birthdate.day))
        )

    icon_path = os.path.join(settings.BASE_DIR, "static/medien/icons/cake.png")

    def has_birthday_in_toern(birthdate):
        if not birthdate:
            return False

        start = toern.startdatum.date()
        end = toern.enddatum.date()

        bday_this_year = birthdate.replace(year=start.year)

        return start <= bday_this_year <= end

    def ident_label(code):
        return dict(User.IDENTIFIKATIONSTYPEN).get(code, code)

    def role_label(code):
        return dict(Teilnahme.ROLE_CHOICES).get(code, code)

    # =========================
    # TABELLE
    # =========================
    data = [[
        "Nr",
        "Surname, first name",
        "Place and date of birth",
        "Identification",
        "Passport number",
        "Nationality",
        "Address",
        "Rank"
    ]]

    for i, t in enumerate(teilnahmen, start=1):
        u = t.user

        birth_text = ""

        if u.geburtsdatum:
            birth_str = u.geburtsdatum.strftime("%d.%m.%Y")
            age = calc_age(u.geburtsdatum)

            # 🎂 Inline Image
            cake_html = ""
            if has_birthday_in_toern(u.geburtsdatum):
                cake_html = f'&nbsp; <img src="{icon_path}" width="10" height="10"/>'

            birth_text = f"{birth_str} ({age}){cake_html}"

        # Geburtsland kombinieren
        if u.geburtsland and birth_text:
            full_text = f"{u.geburtsland}<br/>{birth_text}"
        elif u.geburtsland:
            full_text = u.geburtsland
        else:
            full_text = birth_text

        birth_cell = Paragraph(full_text, small_style) if full_text else ""

        data.append([
            i,
            Paragraph(
                f"{u.last_name}<br/>{u.first_name}",
                small_style
            ) if (u.last_name or u.first_name) else "",
            birth_cell,
            ident_label(u.identifikationstyp) if u.identifikationstyp else "",
            u.passnummer or "",
            u.nationalitaet or "",
            Paragraph(
                f"{u.strasse}<br/>{u.plz} {u.ort}",
                small_style
            ) if (u.strasse or u.plz or u.ort) else "",
            role_label(t.rolle)
        ])

    table = Table(data, repeatRows=1, colWidths=[
        25,   # Nr
        120,  # Name
        150,  # Birth
        90,   # ID
        90,   # Passport
        80,   # Nation
        140,  # Address
        80    # Role
    ])

    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.25, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),  # 👈 kleiner = passt sicher
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 50))

    signature_table = Table([
        ["", "", ""],
        ["Signature Skipper", "", "Signature Co-Skipper"]
    ], colWidths=[250, 100, 250])

    signature_table.setStyle(TableStyle([
        ("LINEABOVE", (0,0), (0,0), 0.5, colors.black),
        ("LINEABOVE", (2,0), (2,0), 0.5, colors.black),
        ("ALIGN", (0,1), (-1,-1), "CENTER"),
    ]))

    elements.append(signature_table)

    elements.append(Spacer(1, 10))

    
    doc.build(elements)

    return response


@login_required
def teilnehmerliste_pdf(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    teilnahme = Teilnahme.objects.filter(user=request.user, toern=toern).first()
    is_anbieter = toern.anbieter == request.user
    if not is_anbieter and (not teilnahme or teilnahme.rolle not in ["skipper", "coskipper"]):
        raise PermissionDenied

    teilnahmen = (
        Teilnahme.objects
        .filter(toern=toern, status__in=["angemeldet", "bestaetigt"])
        .select_related("user", "boot")
        .order_by("boot__name", "rolle", "user__last_name")
    )

    # Boots-Gruppen aufbauen; ohne Boot am Ende
    boots_order = list(toern.boote.order_by("name"))
    gruppen = {b.id: {"boot": b, "crew": []} for b in boots_order}
    ohne_boot = []

    def rolle_sort(t):
        return {"skipper": 0, "coskipper": 1}.get(t.rolle, 2)

    for t in teilnahmen:
        if t.boot_id and t.boot_id in gruppen:
            gruppen[t.boot_id]["crew"].append(t)
        else:
            ohne_boot.append(t)

    for g in gruppen.values():
        g["crew"].sort(key=rolle_sort)
    ohne_boot.sort(key=rolle_sort)

    # Essgewohnheiten-Übersicht
    ess_counts = {"alles": 0, "vegetarisch": 0, "vegan": 0, "": 0}
    for t in teilnahmen:
        ess_counts[t.essgewohnheiten if t.essgewohnheiten in ess_counts else ""] += 1

    # PDF aufbauen
    response = HttpResponse(content_type="application/pdf")
    filename = f"teilnehmerliste_{toern.titel.replace(' ', '_')}.pdf"
    response["Content-Disposition"] = f'inline; filename="{filename}"'

    doc = SimpleDocTemplate(
        response,
        pagesize=portrait(A4),
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    xs = ParagraphStyle("xs", fontSize=7, leading=9)
    sm = ParagraphStyle("sm", fontSize=8, leading=10)
    bold_sm = ParagraphStyle("bold_sm", fontSize=8, leading=10, fontName="Helvetica-Bold")
    section_header = ParagraphStyle("section_header", fontSize=9, leading=11, fontName="Helvetica-Bold")

    logo_path = os.path.join(settings.BASE_DIR, "static/medien/Logo_Meer_erleben.png")
    cake_path = os.path.join(settings.BASE_DIR, "static/medien/icons/cake.png")

    def has_birthday_in_toern(birthdate):
        if not birthdate:
            return False
        start_d = toern.startdatum.date()
        end_d = toern.enddatum.date()
        try:
            bday = birthdate.replace(year=start_d.year)
        except ValueError:
            return False
        return start_d <= bday <= end_d

    elements = []

    # === KOPF: Titel links, Logo rechts ===
    title_style = ParagraphStyle("title", fontSize=13, leading=16, fontName="Helvetica-Bold")
    sub_style = ParagraphStyle("sub", fontSize=9, leading=12, textColor=colors.HexColor("#666666"))

    title_cell = [
        Paragraph(f"Teilnehmerliste — {toern.titel}", title_style),
        Spacer(1, 2 * mm),
        Paragraph(
            f"{toern.revier} &nbsp;|&nbsp; {toern.startdatum.strftime('%d.%m.%Y')} – {toern.enddatum.strftime('%d.%m.%Y')}",
            sub_style
        ),
    ]

    logo_cell = Image(logo_path, width=35 * mm, height=35 * mm, kind="proportional") \
        if os.path.exists(logo_path) else ""

    header_tbl = Table([[title_cell, logo_cell]], colWidths=[130 * mm, 50 * mm])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    elements.append(header_tbl)
    elements.append(Spacer(1, 4 * mm))

    # === ÜBERSICHT ESSGEWOHNHEITEN ===
    ess_labels = {"alles": "Kein Fleischverzicht", "vegetarisch": "Vegetarisch", "vegan": "Vegan", "": "Keine Angabe"}
    ess_parts = [
        f"{ess_labels[k]}: <b>{v}</b>"
        for k, v in ess_counts.items() if v > 0
    ]
    elements.append(Paragraph(
        "Essgewohnheiten: &nbsp;" + " &nbsp;·&nbsp; ".join(ess_parts),
        ParagraphStyle("ess", fontSize=8, leading=10, backColor=colors.HexColor("#F3F4F6"),
                       borderPadding=(4, 6, 4, 6))
    ))
    elements.append(Spacer(1, 6 * mm))

    # === PRO BOOT ===
    def crew_block(gruppe_label, crew_liste):
        block = []
        block.append(Paragraph(gruppe_label, section_header))
        block.append(Spacer(1, 2 * mm))

        header = [
            Paragraph("<b>Name</b>", bold_sm),
            Paragraph("<b>Kontakt</b>", bold_sm),
            Paragraph("<b>Essen / Allergien</b>", bold_sm),
            Paragraph("<b>Notfall / T-Shirt</b>", bold_sm),
        ]
        rows = [header]

        for t in crew_liste:
            u = t.user
            rolle_str = {"skipper": "Skipper", "coskipper": "Co-Skipper", "crew": "Crew"}.get(t.rolle, t.rolle)

            name_lines = f"<b>{u.last_name}, {u.first_name}</b><br/>{rolle_str}"
            if u.geburtsdatum:
                bday_str = u.geburtsdatum.strftime('%d.%m.%Y')
                if has_birthday_in_toern(u.geburtsdatum) and os.path.exists(cake_path):
                    name_lines += f'<br/>* {bday_str} &nbsp;<img src="{cake_path}" width="9" height="9"/>'
                else:
                    name_lines += f"<br/>* {bday_str}"
            name_cell = Paragraph(name_lines, sm)

            kontakt_lines = u.email or ""
            if u.telefonnummer:
                kontakt_lines += f"<br/>{u.telefonnummer}"
            kontakt_cell = Paragraph(kontakt_lines, xs) if kontakt_lines else ""

            ess_lines = ess_labels.get(t.essgewohnheiten, "") or "–"
            if t.lebensmittelunvertraeglichkeiten:
                ess_lines += f"<br/><i>Unvertr.: {t.lebensmittelunvertraeglichkeiten}</i>"
            if t.allergien:
                ess_lines += f"<br/><i>Allergie: {t.allergien}</i>"
            ess_cell = Paragraph(ess_lines, xs)

            notfall_lines = ""
            if t.notfallkontakt_name:
                notfall_lines = f"{t.notfallkontakt_name}"
                if t.notfallkontakt_telefon:
                    notfall_lines += f"<br/>{t.notfallkontakt_telefon}"
            if t.tshirt_groesse:
                notfall_lines += f"<br/>T-Shirt: {t.tshirt_groesse}"
            notfall_cell = Paragraph(notfall_lines, xs) if notfall_lines else ""

            rows.append([name_cell, kontakt_cell, ess_cell, notfall_cell])

        PAGE_WIDTH = 180 * mm
        col_widths = [PAGE_WIDTH * 0.27, PAGE_WIDTH * 0.28, PAGE_WIDTH * 0.26, PAGE_WIDTH * 0.19]
        tbl = Table(rows, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]))
        block.append(tbl)
        block.append(Spacer(1, 6 * mm))
        return block

    for g in gruppen.values():
        if g["crew"]:
            elements += crew_block(f"Boot: {g['boot'].name}", g["crew"])

    if ohne_boot:
        elements += crew_block("Ohne Boot-Zuteilung", ohne_boot)

    doc.build(elements)
    return response


# =========================
# PACKLISTEN-VORLAGEN
# =========================

def _get_or_create_vorlage(toern, typ, user=None):
    """Törn-Vorlage holen oder anlegen. Quelle beim Anlegen (in dieser Reihenfolge):
    Default-Standard des Users (falls Skipper/Co-Skipper/Anbieter des Törns),
    sonst die statische Standard-Liste des Reviers."""
    revier_typ = toern.packliste_revier_typ
    vorlage, created = PacklisteVorlage.objects.get_or_create(toern=toern, typ=typ)
    if created:
        source = None
        if user is not None and _ist_skipper_oder_anbieter(user, toern):
            default = PacklisteStandard.objects.filter(user=user, typ=typ, ist_default=True).first()
            if default:
                source = list(default.eintraege.values_list('name', 'menge'))
        if source is None:
            if typ == 'personal':
                source = KALT_PACKLISTE if revier_typ == 'kalt' else BASIS_PACKLISTE
            elif typ == 'skipper':
                source = SKIPPER_LISTE
            else:
                source = KALT_BOOT_LISTE if revier_typ == 'kalt' else BOOT_STANDARD_LISTE
        PacklisteVorlageEintrag.objects.bulk_create([
            PacklisteVorlageEintrag(vorlage=vorlage, name=name, menge=menge)
            for name, menge in source
        ])
    return vorlage


def _ist_skipper_oder_anbieter(user, toern):
    if toern.anbieter == user:
        return True
    t = Teilnahme.objects.filter(user=user, toern=toern).first()
    return bool(t and t.rolle in ["skipper", "coskipper"])


def _hat_skipper_oder_anbieter(request, toern):
    if not _ist_skipper_oder_anbieter(request.user, toern):
        raise PermissionDenied


@login_required
@require_POST
def packl_revier_set(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    data = json.loads(request.body)
    revier_typ = data.get('revier_typ')
    reset = data.get('reset', False)

    if revier_typ not in ('warm', 'kalt'):
        return JsonResponse({'error': 'Ungültiger Reviertyp'}, status=400)

    toern.packliste_revier_typ = revier_typ
    toern.save(update_fields=['packliste_revier_typ'])

    if reset:
        for typ in ('personal', 'boot'):
            PacklisteVorlage.objects.filter(toern=toern, typ=typ).delete()
            _get_or_create_vorlage(toern, typ)

    return JsonResponse({'status': 'ok', 'revier_typ': revier_typ})


@login_required
def vorlage_items_get(request, toern_id, typ):
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    if typ not in ('personal', 'boot', 'skipper'):
        return JsonResponse({'error': 'Ungültiger Typ'}, status=400)

    vorlage = _get_or_create_vorlage(toern, typ, user=request.user)
    items = list(vorlage.eintraege.values('id', 'name', 'menge').order_by('id'))
    return JsonResponse({'items': items, 'vorlage_id': vorlage.id, 'revier_typ': toern.packliste_revier_typ})


@login_required
@require_POST
def vorlage_item_add(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    data = json.loads(request.body)
    vorlage_id = data.get('vorlage_id')
    name = data.get('name', '').strip()
    menge = max(1, int(data.get('menge', 1)))

    if not name:
        return JsonResponse({'error': 'Name fehlt'}, status=400)

    vorlage = get_object_or_404(PacklisteVorlage, id=vorlage_id, toern=toern)
    eintrag = PacklisteVorlageEintrag.objects.create(vorlage=vorlage, name=name, menge=menge)
    return JsonResponse({'status': 'ok', 'id': eintrag.id, 'name': eintrag.name, 'menge': eintrag.menge})


@login_required
@require_POST
def vorlage_item_update(request, toern_id, item_id):
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    eintrag = get_object_or_404(PacklisteVorlageEintrag, id=item_id, vorlage__toern=toern)
    data = json.loads(request.body)
    eintrag.name = data.get('name', eintrag.name).strip()
    eintrag.menge = max(1, int(data.get('menge', eintrag.menge)))
    eintrag.save()
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def vorlage_item_delete(request, toern_id, item_id):
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    eintrag = get_object_or_404(PacklisteVorlageEintrag, id=item_id, vorlage__toern=toern)
    eintrag.delete()
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def vorlage_anwenden(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    data = json.loads(request.body)
    apply_personal = data.get('apply_personal', True)
    apply_boot = data.get('apply_boot', True)
    apply_skipper = data.get('apply_skipper', True)

    added = {'personal': 0, 'boot': 0, 'skipper': 0}

    if apply_personal:
        vorlage = _get_or_create_vorlage(toern, 'personal', user=request.user)
        template_items = list(vorlage.eintraege.values_list('name', 'menge'))
        for t in toern.teilnahmen.filter(status='bestaetigt'):
            existing = set(t.persoenliche_packliste.values_list('name', flat=True))
            to_create = [
                PersönlicherGegenstand(participation=t, name=name, menge=menge)
                for name, menge in template_items
                if name not in existing
            ]
            PersönlicherGegenstand.objects.bulk_create(to_create)
            added['personal'] += len(to_create)

    if apply_skipper:
        vorlage = _get_or_create_vorlage(toern, 'skipper', user=request.user)
        template_items = list(vorlage.eintraege.values_list('name', 'menge'))
        for t in toern.teilnahmen.filter(status='bestaetigt', rolle__in=['skipper', 'coskipper']):
            existing = set(t.persoenliche_packliste.values_list('name', flat=True))
            to_create = [
                PersönlicherGegenstand(participation=t, name=name, menge=menge, ist_skipper=True)
                for name, menge in template_items
                if name not in existing
            ]
            PersönlicherGegenstand.objects.bulk_create(to_create)
            added['skipper'] += len(to_create)

    if apply_boot:
        vorlage = _get_or_create_vorlage(toern, 'boot', user=request.user)
        template_items = list(vorlage.eintraege.values_list('name', 'menge'))
        for boot in toern.boote.all():
            existing = set(Gegenstand.objects.filter(boot=boot, toern=toern).values_list('name', flat=True))
            to_create = [
                Gegenstand(boot=boot, toern=toern, name=name, menge=menge)
                for name, menge in template_items
                if name not in existing
            ]
            Gegenstand.objects.bulk_create(to_create)
            added['boot'] += len(to_create)

    return JsonResponse({'status': 'ok', 'added': added})


# =========================
# PERSÖNLICHE PACKLISTEN-STANDARDS
# =========================

@login_required
def packl_standard_list(request):
    typ = request.GET.get('typ')
    if typ not in ('personal', 'boot', 'skipper'):
        return JsonResponse({'error': 'Ungültiger Typ'}, status=400)
    standards = [
        {'id': s.id, 'name': s.name, 'ist_default': s.ist_default, 'anzahl': s.eintraege.count()}
        for s in PacklisteStandard.objects.filter(user=request.user, typ=typ).order_by('name')
    ]
    return JsonResponse({'standards': standards})


@login_required
@require_POST
def packl_standard_speichern(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    data = json.loads(request.body)
    typ = data.get('typ')
    name = (data.get('name') or '').strip()
    ist_default = bool(data.get('ist_default', False))

    if typ not in ('personal', 'boot', 'skipper'):
        return JsonResponse({'error': 'Ungültiger Typ'}, status=400)
    if not name:
        return JsonResponse({'error': 'Name fehlt'}, status=400)

    vorlage = _get_or_create_vorlage(toern, typ, user=request.user)
    standard, created = PacklisteStandard.objects.get_or_create(user=request.user, typ=typ, name=name)
    standard.eintraege.all().delete()
    PacklisteStandardEintrag.objects.bulk_create([
        PacklisteStandardEintrag(standard=standard, name=n, menge=m)
        for n, m in vorlage.eintraege.values_list('name', 'menge')
    ])
    if ist_default:
        PacklisteStandard.objects.filter(user=request.user, typ=typ).exclude(id=standard.id).update(ist_default=False)
    standard.ist_default = ist_default
    standard.save()
    return JsonResponse({'status': 'ok', 'id': standard.id, 'created': created})


@login_required
@require_POST
def packl_standard_laden(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    data = json.loads(request.body)
    standard = get_object_or_404(PacklisteStandard, id=data.get('standard_id'), user=request.user)

    vorlage, _ = PacklisteVorlage.objects.get_or_create(toern=toern, typ=standard.typ)
    vorlage.eintraege.all().delete()
    PacklisteVorlageEintrag.objects.bulk_create([
        PacklisteVorlageEintrag(vorlage=vorlage, name=n, menge=m)
        for n, m in standard.eintraege.values_list('name', 'menge')
    ])
    return JsonResponse({'status': 'ok', 'typ': standard.typ})


@login_required
@require_POST
def packl_standard_loeschen(request, standard_id):
    standard = get_object_or_404(PacklisteStandard, id=standard_id, user=request.user)
    standard.delete()
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def packl_standard_default(request, standard_id):
    standard = get_object_or_404(PacklisteStandard, id=standard_id, user=request.user)
    standard.ist_default = not standard.ist_default
    if standard.ist_default:
        PacklisteStandard.objects.filter(user=request.user, typ=standard.typ).exclude(id=standard.id).update(ist_default=False)
    standard.save()
    return JsonResponse({'status': 'ok', 'ist_default': standard.ist_default})


# ========================= MAHLZEITEN =========================

@login_required
@require_POST
def add_mahlzeit(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)
    teilnahme = Teilnahme.objects.filter(user=request.user, toern=toern).first()
    if not teilnahme or teilnahme.rolle not in ["skipper", "coskipper"]:
        raise PermissionDenied

    datum = request.POST.get("datum")
    typ = request.POST.get("typ")
    name = request.POST.get("name", "").strip()
    kochverantwortlich_id = request.POST.get("kochverantwortlich") or None

    if not datum or not typ or not name:
        return JsonResponse({"status": "error", "message": "Pflichtfelder fehlen"}, status=400)

    koch = None
    if kochverantwortlich_id:
        koch = Teilnahme.objects.filter(id=kochverantwortlich_id, toern=toern).first()

    Mahlzeit.objects.create(
        boot=teilnahme.boot,
        toern=toern,
        datum=datum,
        typ=typ,
        name=name,
        kochverantwortlich=koch,
    )
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
def delete_mahlzeit(request, mahlzeit_id):
    mahlzeit = get_object_or_404(Mahlzeit, id=mahlzeit_id)
    teilnahme = Teilnahme.objects.filter(user=request.user, toern=mahlzeit.toern).first()
    if not teilnahme or teilnahme.rolle not in ["skipper", "coskipper"]:
        raise PermissionDenied
    mahlzeit.delete()
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
def send_reminder_toern(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    teilnahme = Teilnahme.objects.filter(user=request.user, toern=toern).first()
    if not teilnahme or teilnahme.rolle not in ["skipper", "coskipper"]:
        raise PermissionDenied

    empfaenger_teilnahmen = Teilnahme.objects.filter(
        toern=toern,
        status__in=["angemeldet", "bestaetigt"],
        user__email_verified=True,
    ).select_related("user")

    versandt = 0
    for t in empfaenger_teilnahmen:
        fehlend = fehlende_crew_felder(t.user)
        if not fehlend:
            continue

        mail_crew_daten_erinnerung(t.user, toern, fehlend, request)
        ErinnerungsMailLog.objects.create(
            toern=toern,
            empfaenger=t.user,
            fehlende_felder=", ".join(fehlend),
        )
        versandt += 1

    if versandt:
        messages.success(request, f"{versandt} Erinnerungsmail(s) versendet.")
    else:
        messages.info(request, "Alle Crewmitglieder haben ihre Daten vollstaendig angegeben.")

    return redirect("skipper_dashboard", toern_id=toern_id)


# =========================
# KI-TEXTGENERATOR
# =========================
@login_required
@require_POST
def toern_beschreibung_generieren(request):
    from django.conf import settings as django_settings
    import anthropic

    if not request.user.is_anbieter:
        return JsonResponse({"error": "Keine Berechtigung."}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Ungültige JSON-Daten."}, status=400)

    stichpunkte = data.get("stichpunkte", "").strip()
    revier = data.get("revier", "").strip()
    startdatum = data.get("startdatum", "").strip()
    enddatum = data.get("enddatum", "").strip()

    if not stichpunkte:
        return JsonResponse({"error": "Bitte Stichpunkte eingeben."}, status=400)

    api_key = django_settings.ANTHROPIC_API_KEY
    if not api_key:
        return JsonResponse({"error": "Kein API-Key konfiguriert. Bitte ANTHROPIC_API_KEY in der .env setzen."}, status=503)

    zeitraum = f"{startdatum} – {enddatum}" if startdatum and enddatum else "unbekannt"

    prompt = (
        f"Erstelle aus diesen Stichpunkten zwei Texte:\n"
        f"1. Eine ausführliche Beschreibung (3-4 Absätze, maritime Sprache, einladend)\n"
        f"2. Eine Kurzbeschreibung (max. 480 Zeichen, prägnant)\n\n"
        f"Revier: {revier or 'nicht angegeben'}, Zeitraum: {zeitraum}\n"
        f"Stichpunkte: {stichpunkte}\n\n"
        f'Antworte ausschließlich als JSON ohne Markdown-Codeblöcke: {{"beschreibung": "...", "kurzbeschreibung": "..."}}'
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system="Du bist ein erfahrener Redakteur für Segelreise-Beschreibungen. Schreibe ansprechende, enthusiastische Texte für Crew-Mitglieder die mitsegeln wollen.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        result = json.loads(raw)
        beschreibung = result.get("beschreibung", "")
        kurzbeschreibung = result.get("kurzbeschreibung", "")[:500]
        return JsonResponse({"beschreibung": beschreibung, "kurzbeschreibung": kurzbeschreibung})
    except json.JSONDecodeError:
        return JsonResponse({"error": "Claude hat kein gültiges JSON zurückgegeben."}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"API-Fehler: {str(e)}"}, status=500)


@login_required
@require_POST
def pinnwand_nachricht_erstellen(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)
    teilnahme = Teilnahme.objects.filter(user=request.user, toern=toern).first()

    ist_skipper_oder_coskipper = teilnahme and teilnahme.rolle in ("skipper", "coskipper")
    ist_anbieter = toern.anbieter == request.user

    if not (ist_skipper_oder_coskipper or ist_anbieter):
        raise PermissionDenied

    text = request.POST.get("text", "").strip()
    if text:
        PinnwandNachricht.objects.create(toern=toern, autor=request.user, text=text)
        messages.success(request, "Nachricht gepostet.")
    return redirect(reverse("crew_dashboard", args=[toern_id]) + "?tab=info")


@login_required
@require_POST
def pinnwand_nachricht_loeschen(request, nachricht_id):
    nachricht = get_object_or_404(PinnwandNachricht, id=nachricht_id)
    toern = nachricht.toern

    ist_autor = nachricht.autor == request.user
    ist_anbieter = toern.anbieter == request.user

    if not (ist_autor or ist_anbieter):
        raise PermissionDenied

    nachricht.delete()
    messages.success(request, "Nachricht gelöscht.")
    from django.urls import reverse
    return redirect(reverse("crew_dashboard", args=[toern.id]) + "?tab=info")


@login_required
@require_POST
def mitfahrangebot_erstellen(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)
    teilnahme = Teilnahme.objects.filter(user=request.user, toern=toern, status__in=["angemeldet", "bestaetigt"]).first()

    if not teilnahme:
        raise PermissionDenied

    typ = request.POST.get("typ")
    abfahrtsort = request.POST.get("abfahrtsort", "").strip()
    abfahrtszeit_raw = request.POST.get("abfahrtszeit", "").strip()
    freie_plaetze_raw = request.POST.get("freie_plaetze", "").strip()
    anmerkung = request.POST.get("anmerkung", "").strip()

    if not abfahrtsort or typ not in ("angebot", "gesuch"):
        messages.error(request, "Bitte alle Pflichtfelder ausfüllen.")
        return redirect(reverse("crew_dashboard", args=[toern_id]) + "?tab=mitfahrt")

    from django.utils.dateparse import parse_datetime
    abfahrtszeit = parse_datetime(abfahrtszeit_raw) if abfahrtszeit_raw else None

    freie_plaetze = None
    if typ == "angebot" and freie_plaetze_raw:
        try:
            freie_plaetze = int(freie_plaetze_raw)
        except ValueError:
            pass

    Mitfahrangebot.objects.create(
        toern=toern,
        user=request.user,
        typ=typ,
        abfahrtsort=abfahrtsort,
        abfahrtszeit=abfahrtszeit,
        freie_plaetze=freie_plaetze,
        anmerkung=anmerkung,
    )
    messages.success(request, "Eintrag hinzugefügt.")
    return redirect(reverse("crew_dashboard", args=[toern_id]) + "?tab=mitfahrt")


@login_required
@require_POST
def mitfahrangebot_loeschen(request, eintrag_id):
    eintrag = get_object_or_404(Mitfahrangebot, id=eintrag_id)
    toern = eintrag.toern

    if eintrag.user != request.user:
        raise PermissionDenied

    eintrag.delete()
    messages.success(request, "Eintrag gelöscht.")
    return redirect(reverse("crew_dashboard", args=[toern.id]) + "?tab=mitfahrt")


# ========================= TAGESPLAN =========================

def _hat_tagesplan_edit(request, toern, boot, teilnahme):
    """True wenn der User Tagesplan-Bearbeitungsrecht hat."""
    if request.user == toern.anbieter:
        return True
    if not teilnahme:
        return False
    if teilnahme.rolle in ['skipper', 'coskipper']:
        return True
    return TagesplanBearbeitungsrecht.objects.filter(
        boot=boot, toern=toern, teilnahme=teilnahme
    ).exists()


def _get_tagesplan_teilnahme(request, toern_id, boot_id):
    """Gemeinsamer Zugriffs-Check für alle Tagesplan-Views."""
    toern = get_object_or_404(Toern, id=toern_id)
    boot = get_object_or_404(Boot, id=boot_id)
    teilnahme = Teilnahme.objects.filter(
        user=request.user, toern=toern, boot=boot
    ).first()
    if not teilnahme:
        # Anbieter ohne eigene Boot-Teilnahme: holt irgendeine Teilnahme im Törn
        if request.user == toern.anbieter:
            teilnahme = Teilnahme.objects.filter(user=request.user, toern=toern).first()
        if not teilnahme:
            raise PermissionDenied
    return toern, boot, teilnahme


@login_required
@require_POST
def tagesaufgabe_add(request, toern_id, boot_id):
    toern, boot, teilnahme = _get_tagesplan_teilnahme(request, toern_id, boot_id)
    if not _hat_tagesplan_edit(request, toern, boot, teilnahme):
        raise PermissionDenied

    datum = request.POST.get('datum')
    typ = request.POST.get('typ', 'abwasch')
    beschreibung = request.POST.get('beschreibung', '').strip()
    verantwortlich_id = request.POST.get('verantwortlich') or None

    if not datum:
        return JsonResponse({'status': 'error', 'msg': 'Datum fehlt'}, status=400)

    verantwortlich = None
    if verantwortlich_id:
        verantwortlich = Teilnahme.objects.filter(id=verantwortlich_id, toern=toern, boot=boot).first()

    aufgabe = Tagesaufgabe.objects.create(
        boot=boot, toern=toern, datum=datum,
        typ=typ, beschreibung=beschreibung,
        verantwortlich=verantwortlich
    )
    person_name = ''
    if aufgabe.verantwortlich:
        person_name = f"{aufgabe.verantwortlich.user.first_name} {aufgabe.verantwortlich.user.last_name}"
    return JsonResponse({
        'status': 'ok',
        'id': aufgabe.id,
        'typ': aufgabe.typ,
        'typ_display': aufgabe.get_typ_display(),
        'beschreibung': aufgabe.beschreibung,
        'person': person_name,
    })


@login_required
@require_POST
def tagesaufgabe_delete(request, aufgabe_id):
    aufgabe = get_object_or_404(Tagesaufgabe, id=aufgabe_id)
    toern = aufgabe.toern
    boot = aufgabe.boot
    teilnahme = Teilnahme.objects.filter(
        user=request.user, toern=toern
    ).first()
    if not teilnahme or not _hat_tagesplan_edit(request, toern, boot, teilnahme):
        raise PermissionDenied
    aufgabe.delete()
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def tagesimpuls_add(request, toern_id, boot_id):
    toern, boot, teilnahme = _get_tagesplan_teilnahme(request, toern_id, boot_id)
    if not _hat_tagesplan_edit(request, toern, boot, teilnahme):
        raise PermissionDenied

    datum = request.POST.get('datum')
    slot = request.POST.get('slot', 'vormittag')
    thema = request.POST.get('thema', '').strip()
    verantwortlich_id = request.POST.get('verantwortlich') or None

    if not datum:
        return JsonResponse({'status': 'error', 'msg': 'Datum fehlt'}, status=400)

    verantwortlich = None
    if verantwortlich_id:
        verantwortlich = Teilnahme.objects.filter(id=verantwortlich_id, toern=toern, boot=boot).first()

    impuls, created = Tagesimpuls.objects.get_or_create(
        boot=boot, toern=toern, datum=datum, slot=slot,
        defaults={'thema': thema, 'verantwortlich': verantwortlich}
    )
    if not created:
        impuls.thema = thema
        impuls.verantwortlich = verantwortlich
        impuls.save()

    person_name = ''
    if impuls.verantwortlich:
        person_name = f"{impuls.verantwortlich.user.first_name} {impuls.verantwortlich.user.last_name}"
    return JsonResponse({
        'status': 'ok',
        'id': impuls.id,
        'slot': impuls.slot,
        'slot_display': impuls.get_slot_display(),
        'thema': impuls.thema,
        'person': person_name,
    })


@login_required
@require_POST
def tagesimpuls_delete(request, impuls_id):
    impuls = get_object_or_404(Tagesimpuls, id=impuls_id)
    toern = impuls.toern
    boot = impuls.boot
    teilnahme = Teilnahme.objects.filter(user=request.user, toern=toern).first()
    if not teilnahme or not _hat_tagesplan_edit(request, toern, boot, teilnahme):
        raise PermissionDenied
    impuls.delete()
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def tagesplan_recht_toggle(request, toern_id, boot_id, teilnahme_id):
    toern = get_object_or_404(Toern, id=toern_id)
    boot = get_object_or_404(Boot, id=boot_id)
    eigene_teilnahme = Teilnahme.objects.filter(user=request.user, toern=toern).first()

    if not eigene_teilnahme:
        raise PermissionDenied
    if eigene_teilnahme.rolle not in ['skipper', 'coskipper'] and request.user != toern.anbieter:
        raise PermissionDenied

    ziel = get_object_or_404(Teilnahme, id=teilnahme_id, toern=toern, boot=boot)
    recht, created = TagesplanBearbeitungsrecht.objects.get_or_create(
        boot=boot, toern=toern, teilnahme=ziel
    )
    if not created:
        recht.delete()
        aktiv = False
    else:
        aktiv = True

    return JsonResponse({'status': 'ok', 'aktiv': aktiv, 'teilnahme_id': ziel.id})


# ========================= TAGESPLAN PDF =========================

@login_required
def tagesplan_pdf(request, toern_id, boot_id):
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, Image
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from django.http import HttpResponse
    from io import BytesIO

    toern = get_object_or_404(Toern, id=toern_id)
    boot = get_object_or_404(Boot, id=boot_id)

    teilnahme = Teilnahme.objects.filter(user=request.user, toern=toern).first()
    if not teilnahme and request.user != toern.anbieter:
        raise PermissionDenied

    _TYP_ORDER = {'fruehstueck': 0, 'mittag': 1, 'abend': 2, 'essen_gehen': 3, 'snack': 4}
    aufgaben_qs = list(
        Tagesaufgabe.objects.filter(boot=boot, toern=toern).select_related('verantwortlich__user')
    )
    impulse_qs = list(
        Tagesimpuls.objects.filter(boot=boot, toern=toern).select_related('verantwortlich__user')
    )
    mahlzeiten_qs = list(
        Mahlzeit.objects.filter(boot=boot, toern=toern).select_related('kochverantwortlich__user')
    )
    tagesthemen_map = {t.datum: t.thema for t in Tagesthema.objects.filter(boot=boot, toern=toern)}

    # ── Farbpalette (aus DaisyUI-Theme "segelmanager") ───────────────────────
    DARK_BLUE  = colors.HexColor('#0F172A')   # base-content / neutral
    MID_BLUE   = colors.HexColor('#1E293B')   # neutral
    HEADER_BG  = colors.HexColor('#1E293B')   # neutral – Tabellenkopf
    TEAL       = colors.HexColor('#0D9488')   # secondary
    ROW_ODD    = colors.HexColor('#F8FAFC')   # base-100
    ROW_EVEN   = colors.white
    DATE_COL   = colors.HexColor('#E2F2F1')   # helles Teal für Datumsspalte
    BORDER     = colors.HexColor('#E2E8F0')   # base-300
    GRAY_TXT   = colors.HexColor('#64748B')

    # ── Seitengeometrie ──────────────────────────────────────────────────────
    PAGE     = landscape(A4)
    L_MAR = R_MAR = T_MAR = B_MAR = 12 * mm
    USABLE_W = PAGE[0] - L_MAR - R_MAR   # ≈ 273 mm

    # ── Törndaten ────────────────────────────────────────────────────────────
    if toern.startdatum and toern.enddatum:
        _start = toern.startdatum.date() if hasattr(toern.startdatum, 'date') else toern.startdatum
        _end   = toern.enddatum.date()   if hasattr(toern.enddatum,   'date') else toern.enddatum
        num_days = (_end - _start).days + 1
    else:
        _start = _end = None
        num_days = 1

    # ── Styles (feste 8 pt – gut lesbar beim Drucken) ────────────────────────
    styles = getSampleStyleSheet()
    def _ps(name, **kw):
        return ParagraphStyle(name, parent=styles['Normal'], **kw)

    title_s = _ps('T',  fontSize=14, fontName='Helvetica-Bold', textColor=MID_BLUE, leading=17)
    sub_s   = _ps('S',  fontSize=8,  textColor=GRAY_TXT,  leading=11, spaceAfter=2*mm)
    head_s  = _ps('H',  fontSize=8,  fontName='Helvetica-Bold', textColor=colors.white)
    day_s   = _ps('D',  fontSize=9,  fontName='Helvetica-Bold', textColor=MID_BLUE, leading=13)
    thema_s = _ps('TH', fontSize=7,  textColor=TEAL, fontName='Helvetica-Oblique', leading=10)
    cell_s  = _ps('C',  fontSize=8,  leading=11.5, textColor=colors.HexColor('#222222'))
    badge_s = _ps('B',  fontSize=6.5, textColor=TEAL, fontName='Helvetica-Bold', leading=9)
    empty_s = _ps('E',  fontSize=8,  textColor=colors.HexColor('#AAAAAA'))
    more_s  = _ps('M',  fontSize=6.5, textColor=colors.HexColor('#999999'),
                  fontName='Helvetica-Oblique', leading=9)

    LOCALE_DE  = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
    # Helvetica kennt keine Unicode-Symbole → farbige Text-Kürzel in Teal
    TEAL_HEX = '#0D9488'
    MEAL_LABEL = {
        'fruehstueck': f"<font color='{TEAL_HEX}'><b>Fr</b></font> ",
        'mittag':      f"<font color='{TEAL_HEX}'><b>Mi</b></font> ",
        'abend':       f"<font color='{TEAL_HEX}'><b>Ab</b></font> ",
        'essen_gehen': f"<font color='{TEAL_HEX}'><b>EG</b></font> ",
        'snack':       f"<font color='{TEAL_HEX}'><b>Sn</b></font> ",
    }

    # ── Buffer / Doc ─────────────────────────────────────────────────────────
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=PAGE,
        leftMargin=L_MAR, rightMargin=R_MAR,
        topMargin=T_MAR, bottomMargin=B_MAR,
    )

    # ── Logo ─────────────────────────────────────────────────────────────────
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'medien', 'Logo_Meer_erleben.png')
    logo_cell = Image(logo_path, width=18*mm, height=18*mm, kind='proportional') \
        if os.path.exists(logo_path) else Paragraph('', cell_s)

    # ── Kopfzeile ────────────────────────────────────────────────────────────
    start_str = toern.startdatum.strftime('%d.%m.%Y') if toern.startdatum else '–'
    end_str   = toern.enddatum.strftime('%d.%m.%Y')   if toern.enddatum   else '–'
    header_content = [[
        [Paragraph(f"Tagesplan – {boot.name}", title_s),
         Paragraph(f"{toern.titel}  ·  {toern.revier}  ·  {start_str} – {end_str}", sub_s)],
        logo_cell,
    ]]
    header_tbl = Table(header_content, colWidths=[USABLE_W - 24*mm, 24*mm])
    header_tbl.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',         (1, 0), (1, 0),   'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2*mm),
    ]))
    elements = [header_tbl]

    # ── Spaltenstruktur ───────────────────────────────────────────────────────
    # Immer 5 Spalten, immer 3 Task-Spalten (Aufg.A | Aufg.B | Aufg.C).
    # Ohne Impulse: Datum (schmal)   | Mahlzeiten | Aufg.A | Aufg.B | Aufg.C
    # Mit Impulse:  Datum+Thema+Imp. | Mahlzeiten | Aufg.A | Aufg.B | Aufg.C
    #               (Datum-Spalte breiter; Impulse Vm/Nm stehen unter dem Thema)
    mit_impulse = toern.tagesimpulse_aktiv

    if mit_impulse:
        COL_W = [46*mm, 52*mm, 58*mm, 58*mm, USABLE_W - 46*mm - 52*mm - 58*mm - 58*mm]
    else:
        COL_W = [36*mm, 57*mm, 60*mm, 60*mm, USABLE_W - 36*mm - 57*mm - 60*mm - 60*mm]

    # ── Tabellen-Header (Aufgaben-Titel spannt alle 3 Task-Spalten) ───────────
    col_headers = [
        Paragraph('Datum', head_s),
        Paragraph('Mahlzeiten', head_s),
        Paragraph('Aufgaben &amp; Verantwortliche', head_s),
        Paragraph('', head_s),
        Paragraph('', head_s),
    ]
    rows = [col_headers]

    # ── Hilfsfunktionen ───────────────────────────────────────────────────────
    def _split(items, n):
        """Verteilt items sequentiell auf n Spalten."""
        if not items:
            return [[] for _ in range(n)]
        per = (len(items) + n - 1) // n
        return [items[c * per:(c + 1) * per] for c in range(n)]

    def _cell(lst):
        return lst if lst else [Paragraph('–', empty_s)]

    imp_s = _ps('I', fontSize=7, textColor=MID_BLUE, leading=10)

    # ── Datenzeilen ──────────────────────────────────────────────────────────
    if _start:
        for i in range(num_days):
            datum      = _start + timedelta(days=i)
            is_anfahrt = i == 0
            is_abfahrt = i == num_days - 1

            day_mahlzeiten = sorted(
                [m for m in mahlzeiten_qs if m.datum == datum],
                key=lambda m: _TYP_ORDER.get(m.typ, 99)
            )
            day_aufgaben = [a for a in aufgaben_qs if a.datum == datum]
            day_impulse  = [imp for imp in impulse_qs if imp.datum == datum]
            thema        = tagesthemen_map.get(datum, '')

            # Datum-Zelle (mit Impulse: Thema + Vm/Nm-Einträge darunter)
            wochentag = LOCALE_DE[datum.weekday()]
            date_cell = [Paragraph(f"{wochentag}<br/>{datum.strftime('%d.%m.%Y')}", day_s)]
            if is_anfahrt:
                date_cell.append(Paragraph('½ Anfahrt', badge_s))
            if is_abfahrt:
                date_cell.append(Paragraph('½ Abreise', badge_s))
            if mit_impulse:
                if thema:
                    date_cell.append(Paragraph(f'„{thema}"', thema_s))
                for imp in sorted(day_impulse, key=lambda x: 0 if x.slot == 'vormittag' else 1):
                    slot = 'Vm' if imp.slot == 'vormittag' else 'Nm'
                    txt  = f" {imp.thema}" if imp.thema else ''
                    pers = f" → {imp.verantwortlich.user.first_name}" if imp.verantwortlich else ''
                    date_cell.append(Paragraph(f"<b>{slot}:</b>{txt}{pers}", imp_s))

            # Mahlzeiten-Zelle
            meal_cell = []
            for m in day_mahlzeiten:
                icon = MEAL_LABEL.get(m.typ, f"<font color='{TEAL_HEX}'><b>--</b></font> ")
                koch = f"  <font color='#888888'>({m.kochverantwortlich.user.first_name})</font>" \
                       if m.kochverantwortlich else ''
                meal_cell.append(Paragraph(f"{icon}<b>{m.name}</b>{koch}", cell_s))

            # Aufgaben auf 3 Spalten verteilen
            auf_items = []
            for a in day_aufgaben:
                label = a.beschreibung if a.typ == 'sonstiges' and a.beschreibung else a.get_typ_display()
                if a.beschreibung and a.typ != 'sonstiges':
                    label += f' ({a.beschreibung})'
                person = f"  <font color='#0D9488'><b>→ {a.verantwortlich.user.first_name}</b></font>" \
                         if a.verantwortlich else ''
                auf_items.append(Paragraph(f"• {label}{person}", cell_s))

            task_cols = _split(auf_items, 3)
            auf_a = _cell(task_cols[0])
            auf_b = _cell(task_cols[1] if len(task_cols) > 1 else [])
            auf_c = _cell(task_cols[2] if len(task_cols) > 2 else [])

            rows.append([date_cell, _cell(meal_cell), auf_a, auf_b, auf_c])

    # ── Tabelle (fließt natürlich auf max. 2 Seiten) ─────────────────────────
    main_table = Table(rows, colWidths=COL_W, repeatRows=1)
    row_count  = len(rows)
    main_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), HEADER_BG),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 8),
        ('TOPPADDING',    (0, 0), (-1, 0), 3),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 3),
        ('SPAN', (2, 0), (4, 0)),   # Aufgaben-Header über alle 3 Task-Spalten
        *[('BACKGROUND', (0, r), (-1, r), ROW_ODD if r % 2 else ROW_EVEN)
          for r in range(1, row_count)],
        ('BOX',           (0, 0), (-1, -1), 0.8, DARK_BLUE),
        ('INNERGRID',     (0, 0), (-1, -1), 0.3, BORDER),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('BACKGROUND',    (0, 1), (0, -1), DATE_COL),
        ('FONTNAME',      (0, 1), (0, -1), 'Helvetica-Bold'),
    ]))

    elements.append(main_table)

    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    safe_name = boot.name.replace(' ', '_')
    response['Content-Disposition'] = f'inline; filename="Tagesplan_{safe_name}.pdf"'
    return response


@login_required
@require_POST
def tagesplan_mahlzeit_add(request, toern_id, boot_id):
    """Mahlzeit für den Tagesplan hinzufügen — AJAX, gibt Mahlzeit-Daten zurück."""
    toern, boot, teilnahme = _get_tagesplan_teilnahme(request, toern_id, boot_id)
    if not _hat_tagesplan_edit(request, toern, boot, teilnahme):
        raise PermissionDenied

    from rezepte.models import Rezept as KochbuchRezept

    datum = request.POST.get('datum')
    typ = request.POST.get('typ', 'abend')
    name = request.POST.get('name', '').strip()
    koch_id = request.POST.get('kochverantwortlich') or None
    rezept_id = request.POST.get('rezept_id') or None

    if not datum:
        return JsonResponse({'status': 'error', 'msg': 'Datum fehlt'}, status=400)

    rezept = None
    if rezept_id:
        rezept = KochbuchRezept.objects.filter(id=rezept_id).first()

    if not name:
        name = rezept.name if rezept else dict(Mahlzeit.TYP_CHOICES).get(typ, typ)

    koch = None
    if koch_id:
        koch = Teilnahme.objects.filter(id=koch_id, toern=toern, boot=boot).first()

    mahlzeit = Mahlzeit.objects.create(
        boot=boot, toern=toern, datum=datum,
        typ=typ, name=name, kochverantwortlich=koch,
        rezept=rezept,
    )
    person = ''
    if mahlzeit.kochverantwortlich:
        person = f"{mahlzeit.kochverantwortlich.user.first_name} {mahlzeit.kochverantwortlich.user.last_name}"

    return JsonResponse({
        'status': 'ok',
        'id': mahlzeit.id,
        'typ': mahlzeit.typ,
        'typ_display': mahlzeit.get_typ_display(),
        'name': mahlzeit.name,
        'person': person,
        'rezept_id': mahlzeit.rezept_id,
    })


@login_required
def rezept_suche(request, toern_id, boot_id):
    """Rezept-Suche für Tagesplan — AJAX GET, gibt Kochbuch-Treffer zurück."""
    from rezepte.models import Rezept as KochbuchRezept
    from django.db.models import Count, Q

    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'results': []})

    qs = (
        KochbuchRezept.objects
        .annotate(anzahl_sterne=Count('sterne'))
        .filter(Q(name__icontains=q) | Q(zutaten__name__icontains=q))
        .distinct()
        .order_by('-anzahl_sterne', 'name')[:8]
    )
    results = [
        {
            'id': r.id,
            'name': r.name,
            'kategorie': r.get_kategorie_display(),
            'portionen': r.portionen,
            'zubereitungszeit': r.zubereitungszeit,
        }
        for r in qs
    ]
    return JsonResponse({'results': results})


@login_required
@require_POST
def tagesthema_set(request, toern_id, boot_id):
    """Tagesthema setzen oder aktualisieren — AJAX."""
    toern, boot, teilnahme = _get_tagesplan_teilnahme(request, toern_id, boot_id)
    if not _hat_tagesplan_edit(request, toern, boot, teilnahme):
        raise PermissionDenied

    datum = request.POST.get('datum')
    thema = request.POST.get('thema', '').strip()

    if not datum:
        return JsonResponse({'status': 'error', 'msg': 'Datum fehlt'}, status=400)

    obj, _ = Tagesthema.objects.update_or_create(
        boot=boot, toern=toern, datum=datum,
        defaults={'thema': thema}
    )
    return JsonResponse({'status': 'ok', 'thema': obj.thema})


# ========================= MITFAHRTANFRAGE =========================

@login_required
@require_POST
def mitfahrt_anfrage_senden(request, angebot_id):
    angebot = get_object_or_404(Mitfahrangebot, id=angebot_id)
    toern = angebot.toern

    teilnahme = Teilnahme.objects.filter(user=request.user, toern=toern, status__in=["angemeldet", "bestaetigt"]).first()
    if not teilnahme:
        raise PermissionDenied

    if angebot.user == request.user:
        messages.error(request, "Das geht leider nicht bei deinem eigenen Eintrag.")
        return redirect(reverse("crew_dashboard", args=[toern.id]) + "?tab=mitfahrt")

    if angebot.typ == "angebot" and angebot.verbleibende_plaetze is not None and angebot.verbleibende_plaetze <= 0:
        messages.error(request, "Leider sind keine Plätze mehr frei.")
        return redirect(reverse("crew_dashboard", args=[toern.id]) + "?tab=mitfahrt")

    _, created = Mitfahrtanfrage.objects.get_or_create(angebot=angebot, anfragender=request.user)
    if created:
        if angebot.typ == "angebot":
            messages.success(request, "Anfrage gesendet – der Fahrer wird sie bestätigen.")
        else:
            messages.success(request, "Angebot gesendet – die Person wird es bestätigen.")
    else:
        messages.info(request, "Du hast bereits eine Anfrage/Angebot gestellt.")
    return redirect(reverse("crew_dashboard", args=[toern.id]) + "?tab=mitfahrt")


@login_required
@require_POST
def mitfahrt_anfrage_antworten(request, anfrage_id):
    anfrage = get_object_or_404(Mitfahrtanfrage, id=anfrage_id)
    toern = anfrage.angebot.toern

    if anfrage.angebot.user != request.user:
        raise PermissionDenied

    aktion = request.POST.get("aktion")
    if aktion == "accept":
        if anfrage.angebot.verbleibende_plaetze is not None and anfrage.angebot.verbleibende_plaetze <= 0:
            messages.error(request, "Keine freien Plätze mehr vorhanden.")
        else:
            anfrage.status = "accepted"
            anfrage.save()
            messages.success(request, f"{anfrage.anfragender.first_name} wurde bestätigt.")
    elif aktion == "reject":
        anfrage.status = "rejected"
        anfrage.save()
        messages.success(request, f"Anfrage von {anfrage.anfragender.first_name} abgelehnt.")
    return redirect(reverse("crew_dashboard", args=[toern.id]) + "?tab=mitfahrt")


@login_required
@require_POST
def mitfahrt_anfrage_zurueckziehen(request, anfrage_id):
    anfrage = get_object_or_404(Mitfahrtanfrage, id=anfrage_id)
    toern = anfrage.angebot.toern

    if anfrage.anfragender != request.user:
        raise PermissionDenied

    anfrage.delete()
    messages.success(request, "Anfrage zurückgezogen.")
    return redirect(reverse("crew_dashboard", args=[toern.id]) + "?tab=mitfahrt")


@login_required
def tagesplan_kochplan_pdf(request, toern_id, boot_id):
    """Kochplan-PDF: alle Mahlzeiten nach Tag, Zutaten auf Crew-Größe skaliert."""
    import re
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.platypus import Image as RLImage
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from io import BytesIO

    toern = get_object_or_404(Toern, id=toern_id)
    boot = get_object_or_404(Boot, id=boot_id)

    teilnahme = Teilnahme.objects.filter(user=request.user, toern=toern).first()
    if not teilnahme and request.user != toern.anbieter:
        raise PermissionDenied

    crew_anzahl = Teilnahme.objects.filter(
        toern=toern, boot=boot, status="bestaetigt"
    ).count() or 1

    _TYP_ORDER = {'fruehstueck': 0, 'mittag': 1, 'abend': 2, 'essen_gehen': 3, 'snack': 4}
    _TYP_LABEL = {
        'fruehstueck': 'Frühstück', 'mittag': 'Mittagessen',
        'abend': 'Abendessen', 'essen_gehen': 'Essen gehen', 'snack': 'Snack',
    }

    mahlzeiten_qs = list(
        Mahlzeit.objects.filter(boot=boot, toern=toern)
        .select_related('kochverantwortlich__user', 'rezept')
        .prefetch_related('rezept__zutaten')
    )

    # Mengen skalieren: versucht führende Zahl zu parsen und mit Faktor zu multiplizieren
    def _fmt(n):
        if n != n:  # NaN guard
            return ""
        if n == int(n):
            return str(int(n))
        return str(round(n, 1)).replace('.', ',')

    def scale_menge(menge, factor):
        if not menge:
            return ""
        menge = menge.strip()
        # Bereich "2-3" oder "2–3"
        range_m = re.match(r'^(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)(.*)', menge)
        if range_m:
            lo = float(range_m.group(1).replace(',', '.')) * factor
            hi = float(range_m.group(2).replace(',', '.')) * factor
            return f"{_fmt(lo)}–{_fmt(hi)}{range_m.group(3)}"
        # Einzelne Zahl am Anfang
        single_m = re.match(r'^(\d+(?:[.,]\d+)?)(.*)', menge)
        if single_m:
            num = float(single_m.group(1).replace(',', '.')) * factor
            return f"{_fmt(num)}{single_m.group(2)}"
        return menge  # kein parse-barer Wert → unverändert

    # Tage aufbauen
    tage = []
    if toern.startdatum and toern.enddatum:
        _start = toern.startdatum.date() if hasattr(toern.startdatum, 'date') else toern.startdatum
        _end   = toern.enddatum.date()   if hasattr(toern.enddatum,   'date') else toern.enddatum
        for i in range((_end - _start).days + 1):
            datum = _start + timedelta(days=i)
            meals = sorted(
                [m for m in mahlzeiten_qs if m.datum == datum],
                key=lambda m: _TYP_ORDER.get(m.typ, 99),
            )
            if meals:
                tage.append({'datum': datum, 'is_anfahrt': i == 0,
                             'is_abfahrt': i == (_end - _start).days, 'mahlzeiten': meals})

    # ── PDF aufbauen ─────────────────────────────────────────────────────────
    TEAL    = colors.HexColor("#0D9488")
    PRIMARY = colors.HexColor("#1e3a5f")
    GRAY    = colors.HexColor("#64748b")
    LIGHT   = colors.HexColor("#E2F2F1")

    MAR = 18 * mm
    USABLE_W = A4[0] - 2 * MAR

    def sty(name, **kw):
        return ParagraphStyle(name, **kw)

    title_s  = sty("kp_title",  fontSize=16, leading=20, fontName="Helvetica-Bold", textColor=PRIMARY)
    sub_s    = sty("kp_sub",    fontSize=9,  leading=13, fontName="Helvetica",      textColor=GRAY, spaceAfter=4*mm)
    day_s    = sty("kp_day",    fontSize=11, leading=14, fontName="Helvetica-Bold", textColor=colors.white)
    meal_s   = sty("kp_meal",   fontSize=10, leading=14, fontName="Helvetica-Bold", textColor=PRIMARY, spaceBefore=3*mm)
    cook_s   = sty("kp_cook",   fontSize=8,  leading=11, fontName="Helvetica",      textColor=GRAY)
    rezept_s = sty("kp_rname",  fontSize=8,  leading=11, fontName="Helvetica-Oblique", textColor=TEAL, spaceAfter=2*mm)
    menge_s  = sty("kp_menge",  fontSize=9,  leading=13, fontName="Helvetica-Bold", textColor=colors.HexColor("#475569"))
    zutat_s  = sty("kp_zutat",  fontSize=9,  leading=13, fontName="Helvetica",      textColor=colors.black)
    nomeal_s = sty("kp_nomeal", fontSize=9,  leading=13, fontName="Helvetica-Oblique", textColor=GRAY)
    foot_s   = sty("kp_foot",   fontSize=7,  leading=10, fontName="Helvetica",      textColor=GRAY, alignment=TA_CENTER)
    scale_s  = sty("kp_scale",  fontSize=7,  leading=10, fontName="Helvetica-Oblique", textColor=TEAL)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MAR, rightMargin=MAR,
        topMargin=MAR, bottomMargin=MAR,
    )

    elements = []

    # ── Kopf ─────────────────────────────────────────────────────────────────
    logo_path = os.path.join(settings.BASE_DIR, "static", "medien", "Logo_Meer_erleben.png")
    logo_cell = RLImage(logo_path, width=14*mm, height=14*mm, kind="proportional") \
        if os.path.exists(logo_path) else Paragraph("", zutat_s)

    start_str = toern.startdatum.strftime('%d.%m.%Y') if toern.startdatum else "–"
    end_str   = toern.enddatum.strftime('%d.%m.%Y')   if toern.enddatum   else "–"
    hdr_tbl = Table(
        [[Paragraph(f"Kochplan – {boot.name}", title_s), logo_cell],
         [Paragraph(f"{toern.titel}  ·  {start_str} – {end_str}  ·  Crew: {crew_anzahl} Personen", sub_s), ""]],
        colWidths=[USABLE_W - 16*mm, 16*mm],
    )
    hdr_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN",  (1, 0), (1, 0),   "RIGHT"),
        ("SPAN",   (1, 0), (1, 1)),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    elements.append(hdr_tbl)
    elements.append(HRFlowable(width=USABLE_W, thickness=0.8, color=TEAL, spaceBefore=2*mm, spaceAfter=4*mm))

    LOCALE_DE = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

    if not tage:
        elements.append(Paragraph("Keine Mahlzeiten im Tagesplan vorhanden.", nomeal_s))
    else:
        for tag in tage:
            datum = tag['datum']
            wt = LOCALE_DE[datum.weekday()]
            label_parts = [f"{wt}, {datum.strftime('%d.%m.%Y')}"]
            if tag['is_anfahrt']:
                label_parts.append("  – Anfahrtstag")
            if tag['is_abfahrt']:
                label_parts.append("  – Abreisetag")

            # Tag-Header (teal Balken)
            day_tbl = Table(
                [[Paragraph("  " + "".join(label_parts), day_s)]],
                colWidths=[USABLE_W],
            )
            day_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), TEAL),
                ("TOPPADDING",    (0, 0), (-1, -1), 3*mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3*mm),
                ("LEFTPADDING",   (0, 0), (-1, -1), 3*mm),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 3*mm),
            ]))
            elements.append(day_tbl)

            for mahlzeit in tag['mahlzeiten']:
                typ_label = _TYP_LABEL.get(mahlzeit.typ, mahlzeit.typ)
                cook_name = ""
                if mahlzeit.kochverantwortlich:
                    u = mahlzeit.kochverantwortlich.user
                    cook_name = f"{u.first_name} {u.last_name}".strip()

                elements.append(Paragraph(f"{typ_label}: {mahlzeit.name}", meal_s))
                if cook_name:
                    elements.append(Paragraph(f"Koch/Köchin: {cook_name}", cook_s))

                rezept = mahlzeit.rezept
                if rezept:
                    factor = crew_anzahl / (rezept.portionen or 1)
                    elements.append(Paragraph(
                        f"Rezept: {rezept.name}  "
                        f"(Originalrezept für {rezept.portionen} Port. → skaliert auf {crew_anzahl} Pers.)",
                        rezept_s,
                    ))
                    zutaten = list(rezept.zutaten.all())
                    if zutaten:
                        rows = []
                        for z in zutaten:
                            scaled = scale_menge(z.menge, factor)
                            rows.append([
                                Paragraph(scaled, menge_s),
                                Paragraph(z.name, zutat_s),
                            ])
                        ztbl = Table(rows, colWidths=[24*mm, USABLE_W - 24*mm])
                        ztbl.setStyle(TableStyle([
                            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
                            ("TOPPADDING",   (0, 0), (-1, -1), 1),
                            ("BOTTOMPADDING",(0, 0), (-1, -1), 1),
                            ("LEFTPADDING",  (0, 0), (-1, -1), 2),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                            ("BACKGROUND",   (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                            ("BOX",          (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
                        ]))
                        elements.append(ztbl)
                        if factor != 1:
                            elements.append(Paragraph(
                                f"Skalierungsfaktor: ×{round(factor, 2)}", scale_s,
                            ))

                elements.append(Spacer(1, 2*mm))

            elements.append(Spacer(1, 3*mm))

    # ── Footer ────────────────────────────────────────────────────────────────
    elements.append(HRFlowable(width=USABLE_W, thickness=0.3, color=colors.HexColor("#e2e8f0"), spaceBefore=4*mm))
    elements.append(Spacer(1, 1*mm))
    elements.append(Paragraph(f"Kochplan  –  Meer erleben  –  {boot.name}  –  Crew: {crew_anzahl} Personen", foot_s))

    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type="application/pdf")
    safe = boot.name.replace(" ", "_")
    response["Content-Disposition"] = f'inline; filename="Kochplan_{safe}.pdf"'
    return response


# ─── Einkaufsliste — Utilities ────────────────────────────────────────────────

EINKAUF_KATEGORIE_ORDER = [
    'obst_gemuese', 'fleisch_fisch', 'milch_kase', 'brot',
    'nudeln_reis', 'konserven', 'gewurze_ol', 'getranke',
    'tiefkuhl', 'haushalt', 'sonstiges',
]
EINKAUF_KATEGORIE_LABEL = {
    'obst_gemuese':  'Obst & Gemüse',
    'fleisch_fisch': 'Fleisch & Fisch',
    'milch_kase':    'Milch, Käse & Eier',
    'brot':          'Brot & Backwaren',
    'nudeln_reis':   'Nudeln, Reis & Hülsenfrüchte',
    'konserven':     'Konserven & Saucen',
    'gewurze_ol':    'Gewürze, Öle & Essig',
    'getranke':      'Getränke',
    'tiefkuhl':      'Tiefkühlprodukte',
    'haushalt':      'Haushalt & Hygiene',
    'sonstiges':     'Sonstiges',
}

_KAT_KEYWORDS = [
    ('obst_gemuese',  ['zwiebel', 'tomate', 'kartoffel', 'paprika', 'gurke', 'salat',
                        'spinat', 'zucchini', 'aubergine', 'knoblauch', 'möhre', 'karotte',
                        'lauch', 'sellerie', 'brokkoli', 'erbse', 'bohne', 'pilz',
                        'champignon', 'apfel', 'birne', 'banane', 'orange', 'zitrone',
                        'limette', 'traube', 'erdbeere', 'avocado', 'mais', 'porree',
                        'fenchel', 'kohl', 'kräuter', 'petersilie', 'basilikum',
                        'schnittlauch', 'dill', 'thymian', 'rosmarin', 'minze', 'ingwer',
                        'kürbis', 'rettich', 'radieschen', 'spargel', 'rucola', 'feldsalat',
                        'rote bete', 'pak choi', 'artischocke', 'mangold']),
    ('fleisch_fisch', ['fleisch', 'huhn', 'hähnchen', 'rind', 'hackfleisch', 'hack',
                        'speck', 'wurst', 'schinken', 'lachs', 'forelle', 'thunfisch',
                        'sardine', 'hering', 'garnele', 'shrimp', 'fisch', 'meeresfrüchte',
                        'krabben', 'salami', 'chorizo', 'lamm', 'kalb', 'ente', 'truthahn',
                        'lachsfilet', 'dosenthunfisch']),
    ('milch_kase',    ['milch', 'butter', 'sahne', 'joghurt', 'käse', 'mozzarella',
                        'parmesan', 'feta', 'quark', 'frischkäse', 'schmand', 'creme fraiche',
                        'crème fraîche', 'ei ', 'eier', 'kondensmilch', 'schlagsahne', 'gouda',
                        'emmentaler', 'ricotta', 'mascarpone', 'skyr', 'kefir', 'rahm']),
    ('brot',          ['brot', 'brötchen', 'toast', 'semmel', 'croissant', 'mehl',
                        'backpulver', 'hefe', 'paniermehl', 'semmelbrösel', 'wrap', 'pita',
                        'tortilla', 'ciabatta', 'baguette', 'laugenstange']),
    ('nudeln_reis',   ['nudel', 'pasta', 'spaghetti', 'penne', 'fusilli', 'tagliatelle',
                        'rigatoni', 'farfalle', 'tortellini', 'reis', 'linse', 'kichererbse',
                        'bulgur', 'couscous', 'quinoa', 'haferflocken', 'hirse', 'polenta',
                        'lasagne', 'cannelloni']),
    ('konserven',     ['dose', 'konserve', 'passierte', 'tomatensauce', 'tomatensoße',
                        'kokosmilch', 'kidneybohne', 'mais dose', 'thunfisch dose',
                        'tomatenpüree', 'tomatenmark']),
    ('gewurze_ol',    ['salz', 'pfeffer', 'zucker', 'öl', 'olivenöl', 'sonnenblumenöl',
                        'rapsöl', 'essig', 'balsamico', 'senf', 'ketchup', 'sojasoße',
                        'worcester', 'tabasco', 'curry', 'paprikapulver', 'zimt', 'muskat',
                        'oregano', 'majoran', 'lorbeer', 'chili', 'cumin', 'kurkuma',
                        'gewürz', 'brühwürfel', 'brühe', 'honig', 'sirup', 'vanille',
                        'stärke', 'gelatine']),
    ('getranke',      ['wasser', 'saft', 'cola', 'limo', 'bier', 'wein', 'sekt',
                        'prosecco', 'kaffee', 'tee', 'smoothie', 'limonade', 'sprudel',
                        'mineralwasser', 'apfelsaft', 'orangensaft', 'kakao']),
    ('tiefkuhl',      ['tiefkühl', 'gefroren', 'tk ']),
    ('haushalt',      ['klopapier', 'toilettenpapier', 'küchenrolle', 'spüllappen',
                        'spülmittel', 'waschmittel', 'putzmittel', 'müllbeutel', 'müllsack',
                        'backpapier', 'schwamm', 'reiniger', 'folie']),
]

def _detect_kategorie(name):
    n = name.lower()
    for kat, keywords in _KAT_KEYWORDS:
        if any(kw in n for kw in keywords):
            return kat
    return 'sonstiges'

def _fmt_einkauf_num(n):
    return str(int(n)) if n == int(n) else str(round(n, 1)).replace('.', ',')

def _scale_einkauf_menge(menge, factor):
    import re as _re
    if not menge or factor == 1:
        return menge or ''
    menge = menge.strip()
    m = _re.match(r'^(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)(.*)', menge)
    if m:
        lo = float(m.group(1).replace(',', '.')) * factor
        hi = float(m.group(2).replace(',', '.')) * factor
        return f"{_fmt_einkauf_num(lo)}–{_fmt_einkauf_num(hi)}{m.group(3)}"
    m = _re.match(r'^(\d+(?:[.,]\d+)?)(.*)', menge)
    if m:
        num = float(m.group(1).replace(',', '.')) * factor
        return f"{_fmt_einkauf_num(num)}{m.group(2)}"
    return menge

def _merge_mengen(menge_list):
    import re as _re
    totals = {}   # unit -> float
    leftovers = []
    for raw in menge_list:
        if not raw:
            continue
        raw = raw.strip()
        m = _re.match(r'^(\d+(?:[.,]\d+)?)\s*(.*)', raw)
        if m:
            num  = float(m.group(1).replace(',', '.'))
            unit = m.group(2).strip()
            totals[unit] = totals.get(unit, 0.0) + num
        else:
            if raw not in leftovers:
                leftovers.append(raw)
    parts = [f"{_fmt_einkauf_num(v)} {k}".strip() for k, v in totals.items()]
    parts += leftovers
    return " + ".join(parts) if parts else ""

_STANDARD_ARTIKEL = [
    # (name, menge_template, kategorie)  — {crew} = crew count, {wasser} = crew*5
    ('Klopapier',      '{crew} Rolle(n)',   'haushalt'),
    ('Küchenrolle',    '1 Packung',          'haushalt'),
    ('Spüllappen',     '1 Packung',          'haushalt'),
    ('Spülmittel',     '1 Flasche',          'haushalt'),
    ('Wasser',         '{wasser} Liter',     'getranke'),
    ('Kaffee',         '2 Packungen',        'getranke'),
    ('Salz',           '1 Packung',          'gewurze_ol'),
    ('Müllbeutel 5L',  '1 Rolle',            'haushalt'),
    ('Müllbeutel 20L', '1 Rolle',            'haushalt'),
]


# ─── Einkaufsliste — Views ────────────────────────────────────────────────────

@login_required
@require_POST
def einkaufsliste_generieren(request, toern_id, boot_id):
    from collections import defaultdict
    toern = get_object_or_404(Toern, id=toern_id)
    boot  = get_object_or_404(Boot,  id=boot_id)
    if not Teilnahme.objects.filter(user=request.user, toern=toern).exists() \
            and request.user != toern.anbieter:
        raise PermissionDenied

    crew_anzahl = Teilnahme.objects.filter(
        toern=toern, boot=boot, status='bestaetigt'
    ).count() or 1

    # Löscht alle nicht-manuellen Einträge
    EinkaufslistenEintrag.objects.filter(boot=boot, toern=toern).exclude(quelle='manuell').delete()

    # Zutaten aus Rezepten sammeln + skalieren
    raw = defaultdict(lambda: {'mengen': [], 'rezepte': [], 'name': ''})
    for mz in Mahlzeit.objects.filter(boot=boot, toern=toern).select_related('rezept').prefetch_related('rezept__zutaten'):
        if not mz.rezept:
            continue
        factor = crew_anzahl / (mz.rezept.portionen or 1)
        for z in mz.rezept.zutaten.all():
            key = z.name.lower().strip()
            raw[key]['name'] = raw[key]['name'] or z.name
            raw[key]['mengen'].append(_scale_einkauf_menge(z.menge, factor))
            if mz.rezept.name not in raw[key]['rezepte']:
                raw[key]['rezepte'].append(mz.rezept.name)

    to_create = [
        EinkaufslistenEintrag(
            boot=boot, toern=toern,
            name=data['name'],
            menge=_merge_mengen(data['mengen']),
            kategorie=_detect_kategorie(data['name']),
            quelle='rezept',
            rezept_info=', '.join(data['rezepte']),
        )
        for data in raw.values()
    ]

    # Standard-Artikel
    for name, tpl, kat in _STANDARD_ARTIKEL:
        to_create.append(EinkaufslistenEintrag(
            boot=boot, toern=toern,
            name=name,
            menge=tpl.format(crew=crew_anzahl, wasser=crew_anzahl * 5),
            kategorie=kat,
            quelle='standard',
        ))

    EinkaufslistenEintrag.objects.bulk_create(to_create)
    return JsonResponse({'ok': True, 'count': len(to_create)})


@login_required
@require_POST
def einkaufsliste_toggle(request, eintrag_id):
    from django.utils.timezone import now as tz_now
    eintrag = get_object_or_404(EinkaufslistenEintrag, id=eintrag_id)
    if not Teilnahme.objects.filter(user=request.user, toern=eintrag.toern).exists() \
            and request.user != eintrag.toern.anbieter:
        raise PermissionDenied
    eintrag.erledigt = not eintrag.erledigt
    if eintrag.erledigt:
        eintrag.erledigt_von = request.user
        eintrag.erledigt_am  = tz_now()
    else:
        eintrag.erledigt_von = None
        eintrag.erledigt_am  = None
    eintrag.save()
    von = ''
    if eintrag.erledigt_von:
        von = f"{eintrag.erledigt_von.first_name} {eintrag.erledigt_von.last_name}".strip()
    return JsonResponse({'ok': True, 'erledigt': eintrag.erledigt, 'erledigt_von': von})


@login_required
@require_POST
def einkaufsliste_add(request, toern_id, boot_id):
    toern = get_object_or_404(Toern, id=toern_id)
    boot  = get_object_or_404(Boot,  id=boot_id)
    if not Teilnahme.objects.filter(user=request.user, toern=toern).exists() \
            and request.user != toern.anbieter:
        raise PermissionDenied
    name  = request.POST.get('name', '').strip()
    menge = request.POST.get('menge', '').strip()
    if not name:
        return JsonResponse({'error': 'Name fehlt'}, status=400)
    e = EinkaufslistenEintrag.objects.create(
        boot=boot, toern=toern,
        name=name, menge=menge,
        kategorie=_detect_kategorie(name),
        quelle='manuell',
    )
    return JsonResponse({
        'ok': True,
        'id': e.id,
        'name': e.name,
        'menge': e.menge,
        'kategorie': e.kategorie,
        'kategorie_label': EINKAUF_KATEGORIE_LABEL.get(e.kategorie, 'Sonstiges'),
    })


@login_required
@require_POST
def einkaufsliste_delete(request, eintrag_id):
    eintrag = get_object_or_404(EinkaufslistenEintrag, id=eintrag_id)
    if not Teilnahme.objects.filter(user=request.user, toern=eintrag.toern).exists() \
            and request.user != eintrag.toern.anbieter:
        raise PermissionDenied
    eintrag.delete()
    return JsonResponse({'ok': True})


@login_required
@require_POST
def einkaufsliste_aufteilen(request, toern_id, boot_id):
    from collections import defaultdict
    toern = get_object_or_404(Toern, id=toern_id)
    boot  = get_object_or_404(Boot,  id=boot_id)
    if not Teilnahme.objects.filter(user=request.user, toern=toern).exists() \
            and request.user != toern.anbieter:
        raise PermissionDenied

    data       = json.loads(request.body)
    shopper_ids = data.get('shopper_ids', [])
    if len(shopper_ids) < 1:
        return JsonResponse({'error': 'Mindestens 1 Person angeben'}, status=400)

    shoppers = list(Teilnahme.objects.filter(id__in=shopper_ids, toern=toern, boot=boot))
    if not shoppers:
        return JsonResponse({'error': 'Keine gültigen Personen'}, status=400)
    n = len(shoppers)

    items = list(EinkaufslistenEintrag.objects.filter(boot=boot, toern=toern, erledigt=False))

    # Kategorien in Supermarkt-Reihenfolge, dann per round-robin auf Einkäufer verteilen
    by_cat = defaultdict(list)
    for item in items:
        by_cat[item.kategorie].append(item)

    ordered_cats = [by_cat[k] for k in EINKAUF_KATEGORIE_ORDER if k in by_cat]
    for k, v in by_cat.items():
        if k not in EINKAUF_KATEGORIE_ORDER:
            ordered_cats.append(v)

    assignment = {}  # item.id -> Teilnahme
    for i, cat_items in enumerate(ordered_cats):
        shopper = shoppers[i % n]
        for item in cat_items:
            item.einkaufer = shopper
            assignment[item.id] = {'shopper_id': shopper.id, 'name': shopper.user.first_name}

    EinkaufslistenEintrag.objects.bulk_update(items, ['einkaufer'])
    return JsonResponse({'ok': True, 'assignment': assignment})


@login_required
def einkaufsliste_status(request, toern_id, boot_id):
    toern = get_object_or_404(Toern, id=toern_id)
    boot  = get_object_or_404(Boot,  id=boot_id)
    if not Teilnahme.objects.filter(user=request.user, toern=toern).exists() \
            and request.user != toern.anbieter:
        raise PermissionDenied
    qs = EinkaufslistenEintrag.objects.filter(boot=boot, toern=toern).select_related('erledigt_von', 'einkaufer__user')
    items = []
    for e in qs:
        von = ''
        if e.erledigt_von:
            von = f"{e.erledigt_von.first_name} {e.erledigt_von.last_name}".strip()
        shopper = ''
        shopper_id = None
        if e.einkaufer:
            shopper = e.einkaufer.user.first_name
            shopper_id = e.einkaufer_id
        items.append({'id': e.id, 'erledigt': e.erledigt, 'erledigt_von': von,
                      'shopper': shopper, 'shopper_id': shopper_id})
    return JsonResponse({'items': items})
