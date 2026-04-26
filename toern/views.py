from django.shortcuts import render, get_object_or_404, redirect

from boote.models import Boot, Kabine
from logistik.models import Einkaufspunkt, Gegenstand, Mitbringer, PersönlicherGegenstand
from utils.profil_fortschritt import teilnahme_fortschritt
from utils.boot_access_allowed import is_boot_access_allowed
from utils.packliste import BASIS_PACKLISTE, BOOT_STANDARD_LISTE
from .models import KabinenWunsch, Toern, Teilnahme, CrewPraeferenz
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
from django.http import JsonResponse
from datetime import date


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

            #messages.success(request, "Erfolgreich angemeldet!")  Ich glaube das wird nicht mehr benötigt, da die Meldungen jetzt direkt in der Logik oben gesetzt werden. 
            #return redirect("toern_detail", pk=toern.pk)

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

    # =========================
    # 1. Teilnahme prüfen
    # =========================
    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=toern
    ).first()

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
    context = {
        "toern": toern,
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
    avoid_ids = set(request.POST.getlist("avoid"))

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

    if not teilnahme or teilnahme.rolle not in ["skipper", "coskipper"]:
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

    # 👉 Fortschritt auf User spiegeln
    for t in teilnahmen:
        t.user.fortschritt = t.fortschritt

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
    }

    return render(request, "skipper/skipper_dashboard.html", context)

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
    # 8. BOOT SPEICHERN
    # =========================
    Teilnahme.objects.filter(toern=toern).update(boot=None)

    for state in boot_state.values():
        for g in state["groups"]:
            for u in g["users"]:
                Teilnahme.objects.filter(
                    toern=toern,
                    user=u
                ).update(boot=state["boot"])

    # =========================
    # 9. KABINEN ZUWEISUNG
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

        # speichern
        for k in kabinen_state:
            for u in k["users"]:
                Teilnahme.objects.filter(
                    toern=toern,
                    user=u
                ).update(kabine=k["kabine"])

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
            return redirect("crew_dashboard", toern_id=toern.id)

    else:
        form = TeilnahmeDetailForm(instance=teilnahme)

        # 🔥 Prefill USER Daten
        form.initial.update({
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

    messages.success(request, "Zuteilung wurde abgeschlossen. Crew hat jetzt Zugriff auf ihr Boot.")

    return redirect("skipper_dashboard", toern_id=toern.id)

@login_required
@require_POST
def teilnehmer_bestaetigen(request, teilnahme_id):
    teilnahme = get_object_or_404(Teilnahme, id=teilnahme_id)

    skipper = Teilnahme.objects.filter(
        user=request.user,
        toern=teilnahme.toern
    ).first()

    if not skipper or skipper.rolle not in ["skipper", "coskipper"]:
        raise PermissionDenied

    teilnahme.status = "bestaetigt"
    teilnahme.save()

    messages.success(request, "Teilnehmer bestätigt")

    return redirect("skipper_dashboard", toern_id=teilnahme.toern.id)

@login_required
@require_POST
def teilnehmer_ablehnen(request, teilnahme_id):
    teilnahme = get_object_or_404(Teilnahme, id=teilnahme_id)

    skipper = Teilnahme.objects.filter(
        user=request.user,
        toern=teilnahme.toern
    ).first()

    if not skipper or skipper.rolle not in ["skipper", "coskipper"]:
        raise PermissionDenied

    teilnahme.status = "abgelehnt"
    teilnahme.boot = None
    teilnahme.kabine = None
    teilnahme.save()

    messages.info(request, "Teilnehmer abgelehnt")

    return redirect("skipper_dashboard", toern_id=teilnahme.toern.id)

@login_required
def boot_dashboard(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    teilnahme = Teilnahme.objects.filter(
        user=request.user,
        toern=toern
    ).select_related("boot").first()

    if not teilnahme:
        raise PermissionDenied

    # 🔥 Basis-Packliste nur einmal erstellen
    if not teilnahme.persoenliche_packliste.exists():
        PersönlicherGegenstand.objects.bulk_create([
            PersönlicherGegenstand(
                participation=teilnahme,
                name=name,
                menge=menge
            )
            for name, menge in BASIS_PACKLISTE
        ])

    # 🔐 Zugriff
    if not (
        teilnahme.status == "bestaetigt"
        and teilnahme.boot
        and toern.status == "ZUTEILUNG_FIXIERT"
    ):
        raise PermissionDenied

    boot = teilnahme.boot

    # 🔥 Standardliste erstellen, wenn leer
    if not Gegenstand.objects.filter(boot=boot, toern=toern).exists():

        Gegenstand.objects.bulk_create([
            Gegenstand(
                boot=boot,
                toern=toern,
                name=name,
                menge=menge
            )
            for name, menge in BOOT_STANDARD_LISTE
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

    context = {
        "toern": toern,
        "boot": boot,
        "kabinen_data": kabinen_data,
        "gegenstaende": gegenstaende,
        "einkaufsliste": einkaufsliste,
        "teilnahme": teilnahme,
        "progress": progress,
        "done_items": done_items,
        "total_items": total_items,
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

    name = request.POST.get("name")
    menge = request.POST.get("menge") or 1

    PersönlicherGegenstand.objects.create(
        participation=teilnahme,
        name=name,
        menge=int(menge)
    )

    name = request.POST.get("name")
    if not name:
        return JsonResponse({"error": "Name fehlt"}, status=400)

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