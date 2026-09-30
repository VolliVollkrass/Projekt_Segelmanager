import io
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from boote.models import Boot
from toern.models import Teilnahme, Toern
from .models import Ausgabe, Ausgleichszahlung, TopfAusgabe, TopfBeleg, Umlage, UmlageAnteil
from .utils import rate_kategorie, verteile_umlage

# Maximal pro Upload angenommene Belegfotos (gegen versehentliche Massen-Uploads).
MAX_BELEGE_PRO_UPLOAD = 20


def _gueltige_kategorie(raw):
    """Kategorie-Schlüssel validieren, sonst None."""
    gueltig = {k for k, _ in TopfAusgabe.KATEGORIE_CHOICES}
    return raw if raw in gueltig else None


def _speichere_belege(ausgabe, dateien, user):
    """Hochgeladene Belegfotos an eine Ausgabe hängen. Gibt Anzahl gespeicherter
    Belege zurück; ungültige Dateien werden übersprungen."""
    start = ausgabe.belege.count()
    gespeichert = 0
    for datei in dateien[:MAX_BELEGE_PRO_UPLOAD]:
        if not datei:
            continue
        try:
            TopfBeleg.objects.create(
                ausgabe=ausgabe,
                bild=datei,
                hochgeladen_von=user,
                order=start + gespeichert,
            )
            gespeichert += 1
        except Exception:
            # z.B. beschädigte Datei / kein Bild — überspringen
            continue
    return gespeichert


def _parse_betrag(raw):
    """Betrag aus dem Formular parsen (Komma oder Punkt), None wenn ungültig."""
    try:
        betrag = Decimal(str(raw).strip().replace(",", ".")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, AttributeError):
        return None
    if betrag <= 0:
        return None
    return betrag


def _ist_toern_skipper(user, toern):
    return Teilnahme.objects.filter(
        toern=toern, user=user, rolle__in=("skipper", "coskipper")
    ).exists()


# ───────────────────────── Ausgleichszahlungen ─────────────────────────

@login_required
@require_POST
def ausgleich_beglichen(request, toern_id, boot_id):
    """Festhalten, dass zwischen zwei Personen wirklich Geld geflossen ist.

    Erfassen darf es jede der beiden Seiten: wer überwiesen hat, und wer den
    Eingang auf dem Konto sieht. Die Zahlung fließt in die Salden ein, wodurch
    der zugehörige Vorschlag verschwindet.
    """
    toern = get_object_or_404(Toern, id=toern_id)
    boot = get_object_or_404(Boot, id=boot_id, toern=toern)
    kasse_url = f"{reverse('boot_dashboard', args=[toern.id])}?tab=kasse"

    meine_teilnahme = Teilnahme.objects.filter(
        toern=toern, boot=boot, user=request.user, status="bestaetigt"
    ).first()
    if not meine_teilnahme:
        raise PermissionDenied

    von = Teilnahme.objects.filter(
        id=request.POST.get("von"), toern=toern, boot=boot, status="bestaetigt"
    ).first()
    an = Teilnahme.objects.filter(
        id=request.POST.get("an"), toern=toern, boot=boot, status="bestaetigt"
    ).first()
    betrag = _parse_betrag(request.POST.get("betrag"))

    if not von or not an or von.id == an.id or betrag is None or betrag <= 0:
        messages.error(request, "Diese Zahlung konnte nicht zugeordnet werden.")
        return redirect(kasse_url)

    # Nur die beiden Beteiligten dürfen die Zahlung bestätigen — sie sind die
    # Einzigen, die wissen können, ob das Geld angekommen ist.
    if meine_teilnahme.id not in (von.id, an.id):
        messages.error(
            request,
            "Nur die beiden Beteiligten können diese Zahlung als beglichen markieren.",
        )
        return redirect(kasse_url)

    Ausgleichszahlung.objects.create(
        boot=boot, toern=toern, von=von, an=an, betrag=betrag,
        erfasst_von=request.user,
    )
    messages.success(
        request,
        f"Zahlung über {betrag} € von {von.user.first_name} an {an.user.first_name} "
        f"ist eingetragen.",
    )
    return redirect(kasse_url)


@login_required
@require_POST
def ausgleich_zuruecknehmen(request, zahlung_id):
    """Eine eingetragene Zahlung wieder entfernen — für den Fall, dass sie
    versehentlich oder zu früh bestätigt wurde."""
    zahlung = get_object_or_404(
        Ausgleichszahlung.objects.select_related("toern", "von", "an"), id=zahlung_id
    )
    toern = zahlung.toern
    kasse_url = f"{reverse('boot_dashboard', args=[toern.id])}?tab=kasse"

    meine_teilnahme = Teilnahme.objects.filter(
        toern=toern, boot=zahlung.boot, user=request.user, status="bestaetigt"
    ).first()
    if not meine_teilnahme:
        raise PermissionDenied
    if meine_teilnahme.id not in (zahlung.von_id, zahlung.an_id):
        messages.error(request, "Nur die beiden Beteiligten können diese Zahlung zurücknehmen.")
        return redirect(kasse_url)

    zahlung.delete()
    messages.success(request, "Die Zahlung wurde zurückgenommen.")
    return redirect(kasse_url)


# ───────────────────────── Törn-Umlage ─────────────────────────

def _darf_umlage_anlegen(user, toern):
    return user == toern.anbieter or _ist_toern_skipper(user, toern)


def _darf_umlage_bearbeiten(user, umlage):
    return (
        _darf_umlage_anlegen(user, umlage.toern)
        or user == umlage.erstellt_von
        or user == umlage.bezahlt_von.user
    )


def _parse_optionaler_betrag(raw):
    """Extra/Anzahlung: leer = 0, sonst ≥ 0. None, wenn ungültig."""
    raw = str(raw or "").strip()
    if not raw:
        return Decimal("0")
    try:
        betrag = Decimal(raw.replace(",", ".")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None
    return betrag if betrag >= 0 else None


def _kasse_url(user, toern):
    """Zurück in die Bootskasse — wer (als Anbieter) auf keinem Boot sitzt,
    landet im Kasse-Tab des Skipper-Dashboards."""
    auf_boot = Teilnahme.objects.filter(
        toern=toern, user=user, status="bestaetigt", boot__isnull=False
    ).exists()
    if auf_boot:
        return f"{reverse('boot_dashboard', args=[toern.id])}?tab=kasse"
    return f"{reverse('skipper_dashboard', args=[toern.id])}?tab=kasse"


def _umlage_teilnehmer(toern):
    return list(
        Teilnahme.objects.filter(toern=toern, status="bestaetigt")
        .select_related("user", "boot")
        .order_by("boot__name", "user__first_name", "user__last_name")
    )


@login_required
def umlage_formular(request, toern_id, umlage_id=None):
    """Umlage anlegen oder bearbeiten.

    Eigene Seite statt Klappformular: bei 30 Leuten mit je zwei Feldern
    braucht es Platz, und bei einem Eingabefehler bleibt alles Eingetippte
    stehen.
    """
    toern = get_object_or_404(Toern, id=toern_id)
    umlage = None
    if umlage_id is not None:
        umlage = get_object_or_404(
            Umlage.objects.select_related("bezahlt_von__user", "toern"),
            id=umlage_id, toern=toern,
        )
        if not _darf_umlage_bearbeiten(request.user, umlage):
            raise PermissionDenied
    elif not _darf_umlage_anlegen(request.user, toern):
        raise PermissionDenied

    teilnehmer = _umlage_teilnehmer(toern)
    nach_id = {t.id: t for t in teilnehmer}
    meine = next((t for t in teilnehmer if t.user_id == request.user.id), None)
    fehler = None

    if request.method == "POST":
        beschreibung = request.POST.get("beschreibung", "").strip()
        betrag = _parse_betrag(request.POST.get("betrag"))
        zahler = nach_id.get(_int_oder_none(request.POST.get("bezahlt_von")))
        # Reihenfolge der Liste, nicht der POST-Daten — sie bestimmt, wer
        # übrige Cents bekommt, und muss zur Vorschau im Browser passen.
        gewaehlte_ids = {_int_oder_none(x) for x in request.POST.getlist("teilnehmer")}
        ausgewaehlt = [t for t in teilnehmer if t.id in gewaehlte_ids]
        extras, gegeben = {}, {}
        for t in ausgewaehlt:
            extras[t.id] = _parse_optionaler_betrag(request.POST.get(f"extra_{t.id}"))
            gegeben[t.id] = _parse_optionaler_betrag(request.POST.get(f"gegeben_{t.id}"))

        if not beschreibung or betrag is None:
            fehler = "Bitte Beschreibung und einen gültigen Gesamtbetrag angeben."
        elif not zahler:
            fehler = "Bitte auswählen, wer die Rechnung bezahlt hat."
        elif any(v is None for v in list(extras.values()) + list(gegeben.values())):
            fehler = "Extras und Anzahlungen müssen Beträge ab 0 € sein."
        else:
            try:
                anteile = verteile_umlage(betrag, [t.id for t in ausgewaehlt], extras)
            except ValueError as e:
                fehler = str(e)

        if not fehler:
            # Der Zahler zahlt sich nichts selbst an
            gegeben[zahler.id] = Decimal("0")
            zurueckgesetzt = _speichere_umlage(
                request.user, toern, umlage, beschreibung, betrag, zahler,
                ausgewaehlt, extras, gegeben, anteile,
            )
            text = f"Umlage „{beschreibung}“ ({betrag} €) gespeichert."
            if zurueckgesetzt:
                text += (
                    f" Bei {zurueckgesetzt} Person(en) hat sich der offene Betrag geändert"
                    " — „beglichen“ wurde dort zurückgesetzt."
                )
            messages.success(request, text)
            return redirect(_kasse_url(request.user, toern))

        werte = {
            "beschreibung": beschreibung,
            "betrag": request.POST.get("betrag", ""),
            "bezahlt_von": zahler.id if zahler else None,
            "ausgewaehlt": {t.id for t in ausgewaehlt},
            "extra": {t.id: request.POST.get(f"extra_{t.id}", "") for t in teilnehmer},
            "gegeben": {t.id: request.POST.get(f"gegeben_{t.id}", "") for t in teilnehmer},
        }
    elif umlage:
        bestehend = {a.teilnahme_id: a for a in umlage.anteile.all()}
        werte = {
            "beschreibung": umlage.beschreibung,
            "betrag": f"{umlage.betrag:.2f}".replace(".", ","),
            "bezahlt_von": umlage.bezahlt_von_id,
            "ausgewaehlt": set(bestehend),
            "extra": {i: _fmt(a.extra) for i, a in bestehend.items()},
            "gegeben": {i: _fmt(a.schon_gegeben) for i, a in bestehend.items()},
        }
    else:
        werte = {
            "beschreibung": "",
            "betrag": "",
            "bezahlt_von": meine.id if meine else None,
            "ausgewaehlt": {t.id for t in teilnehmer},
            "extra": {},
            "gegeben": {},
        }

    gruppen = {}
    for t in teilnehmer:
        t.ist_ausgewaehlt = t.id in werte["ausgewaehlt"]
        t.wert_extra = werte["extra"].get(t.id, "")
        t.wert_gegeben = werte["gegeben"].get(t.id, "")
        gruppen.setdefault(t.boot.name if t.boot else "Ohne Boot", []).append(t)

    return render(request, "finance/umlage_formular.html", {
        "toern": toern,
        "umlage": umlage,
        "teilnehmer": teilnehmer,
        "gruppen": list(gruppen.items()),
        "werte": werte,
        "fehler": fehler,
        "zurueck_url": _kasse_url(request.user, toern),
    })


def _int_oder_none(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _fmt(betrag):
    """0 → leeres Feld, sonst deutsches Komma."""
    return "" if not betrag else f"{betrag:.2f}".replace(".", ",")


@transaction.atomic
def _speichere_umlage(user, toern, umlage, beschreibung, betrag, zahler,
                      ausgewaehlt, extras, gegeben, anteile):
    """Legt die Umlage an bzw. aktualisiert sie. Rückgabe: Anzahl der Anteile,
    deren „beglichen“ zurückgesetzt wurde, weil sich der offene Betrag geändert hat."""
    if umlage is None:
        umlage = Umlage(toern=toern, erstellt_von=user)
    umlage.beschreibung = beschreibung
    umlage.betrag = betrag
    umlage.bezahlt_von = zahler
    umlage.save()

    bestehend = {a.teilnahme_id: a for a in umlage.anteile.all()}
    zurueckgesetzt = 0
    for t in ausgewaehlt:
        a = bestehend.pop(t.id, None) or UmlageAnteil(umlage=umlage, teilnahme=t)
        neu_offen = anteile[t.id] - gegeben[t.id]
        # Beglichen gilt für einen bestimmten Betrag. Ändert der sich, ist die
        # Bestätigung nichts mehr wert.
        if a.pk and a.beglichen_am and a.offen != neu_offen:
            a.beglichen_am = None
            a.beglichen_von = None
            zurueckgesetzt += 1
        a.anteil = anteile[t.id]
        a.extra = extras[t.id]
        a.schon_gegeben = gegeben[t.id]
        a.save()
    # Wer nicht mehr ausgewählt ist, fällt raus
    UmlageAnteil.objects.filter(id__in=[a.id for a in bestehend.values()]).delete()
    return zurueckgesetzt


@login_required
@require_POST
def umlage_loeschen(request, umlage_id):
    umlage = get_object_or_404(
        Umlage.objects.select_related("toern", "bezahlt_von__user"), id=umlage_id
    )
    if not _darf_umlage_bearbeiten(request.user, umlage):
        raise PermissionDenied
    toern = umlage.toern
    beschreibung = umlage.beschreibung
    umlage.delete()
    messages.success(request, f"Umlage „{beschreibung}“ gelöscht.")
    return redirect(_kasse_url(request.user, toern))


@login_required
@require_POST
def umlage_anteil_beglichen(request, anteil_id):
    """Anteil als beglichen markieren bzw. zurücknehmen.

    Wie beim Ausgleich dürfen das beide Seiten: wer schuldet und wer die
    Rechnung bezahlt hat.
    """
    anteil = get_object_or_404(
        UmlageAnteil.objects.select_related("umlage__toern", "umlage__bezahlt_von", "teilnahme"),
        id=anteil_id,
    )
    umlage = anteil.umlage
    if request.user.id not in (anteil.teilnahme.user_id, umlage.bezahlt_von.user_id):
        raise PermissionDenied

    if anteil.beglichen_am:
        anteil.beglichen_am = None
        anteil.beglichen_von = None
        messages.success(request, f"„{umlage.beschreibung}“: wieder als offen markiert.")
    else:
        anteil.beglichen_am = timezone.now()
        anteil.beglichen_von = request.user
        messages.success(request, f"„{umlage.beschreibung}“: als beglichen markiert.")
    anteil.save(update_fields=["beglichen_am", "beglichen_von"])
    return redirect(_kasse_url(request.user, umlage.toern))


# ───────────────────────── Bootskasse ─────────────────────────

@login_required
@require_POST
def ausgabe_erstellen(request, toern_id, boot_id):
    toern = get_object_or_404(Toern, id=toern_id)
    boot = get_object_or_404(Boot, id=boot_id, toern=toern)

    meine_teilnahme = Teilnahme.objects.filter(
        toern=toern, boot=boot, user=request.user, status="bestaetigt"
    ).first()
    if not meine_teilnahme:
        raise PermissionDenied

    kasse_url = f"{reverse('boot_dashboard', args=[toern.id])}?tab=kasse"

    beschreibung = request.POST.get("beschreibung", "").strip()
    betrag = _parse_betrag(request.POST.get("betrag"))
    bezahlt_von_id = request.POST.get("bezahlt_von")
    beteiligt_ids = request.POST.getlist("beteiligt")

    if not beschreibung or betrag is None:
        messages.error(request, "Bitte Beschreibung und einen gültigen Betrag angeben.")
        return redirect(kasse_url)

    zahler = Teilnahme.objects.filter(
        id=bezahlt_von_id, toern=toern, boot=boot, status="bestaetigt"
    ).first()
    if not zahler:
        messages.error(request, "Ungültiger Zahler.")
        return redirect(kasse_url)

    beteiligte = Teilnahme.objects.filter(
        id__in=beteiligt_ids, toern=toern, boot=boot, status="bestaetigt"
    )
    if not beteiligte.exists():
        messages.error(request, "Bitte mindestens eine beteiligte Person auswählen.")
        return redirect(kasse_url)

    ausgabe = Ausgabe.objects.create(
        boot=boot,
        toern=toern,
        beschreibung=beschreibung,
        betrag=betrag,
        bezahlt_von=zahler,
        erstellt_von=request.user,
    )
    ausgabe.beteiligt.set(beteiligte)

    messages.success(request, f"Ausgabe „{beschreibung}“ ({betrag} €) gespeichert.")
    return redirect(kasse_url)


@login_required
@require_POST
def ausgabe_bearbeiten(request, ausgabe_id):
    ausgabe = get_object_or_404(
        Ausgabe.objects.select_related("toern", "boot", "bezahlt_von__user"),
        id=ausgabe_id,
    )
    toern, boot = ausgabe.toern, ausgabe.boot

    darf_bearbeiten = (
        request.user == ausgabe.erstellt_von
        or request.user == ausgabe.bezahlt_von.user
        or request.user == toern.anbieter
        or _ist_toern_skipper(request.user, toern)
    )
    if not darf_bearbeiten:
        raise PermissionDenied

    kasse_url = f"{reverse('boot_dashboard', args=[toern.id])}?tab=kasse"

    beschreibung = request.POST.get("beschreibung", "").strip()
    betrag = _parse_betrag(request.POST.get("betrag"))
    bezahlt_von_id = request.POST.get("bezahlt_von")
    beteiligt_ids = request.POST.getlist("beteiligt")

    if not beschreibung or betrag is None:
        messages.error(request, "Bitte Beschreibung und einen gültigen Betrag angeben.")
        return redirect(kasse_url)

    zahler = Teilnahme.objects.filter(
        id=bezahlt_von_id, toern=toern, boot=boot, status="bestaetigt"
    ).first()
    if not zahler:
        messages.error(request, "Ungültiger Zahler.")
        return redirect(kasse_url)

    beteiligte = Teilnahme.objects.filter(
        id__in=beteiligt_ids, toern=toern, boot=boot, status="bestaetigt"
    )
    if not beteiligte.exists():
        messages.error(request, "Bitte mindestens eine beteiligte Person auswählen.")
        return redirect(kasse_url)

    ausgabe.beschreibung = beschreibung
    ausgabe.betrag = betrag
    ausgabe.bezahlt_von = zahler
    ausgabe.save()
    ausgabe.beteiligt.set(beteiligte)

    messages.success(request, f"Ausgabe „{beschreibung}“ aktualisiert.")
    return redirect(kasse_url)


@login_required
@require_POST
def ausgabe_loeschen(request, ausgabe_id):
    ausgabe = get_object_or_404(
        Ausgabe.objects.select_related("toern", "boot", "bezahlt_von__user"),
        id=ausgabe_id,
    )
    toern = ausgabe.toern

    darf_loeschen = (
        request.user == ausgabe.erstellt_von
        or request.user == ausgabe.bezahlt_von.user
        or request.user == toern.anbieter
        or _ist_toern_skipper(request.user, toern)
    )
    if not darf_loeschen:
        raise PermissionDenied

    ausgabe.delete()
    messages.success(request, "Ausgabe gelöscht.")
    return redirect(f"{reverse('boot_dashboard', args=[toern.id])}?tab=kasse")


# ───────────────────────── Skipper-Topf ─────────────────────────

@login_required
@require_POST
def topf_ausgabe_erstellen(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    if request.user != toern.anbieter and not _ist_toern_skipper(request.user, toern):
        raise PermissionDenied

    kasse_url = f"{reverse('skipper_dashboard', args=[toern.id])}?tab=kasse"

    beschreibung = request.POST.get("beschreibung", "").strip()
    betrag = _parse_betrag(request.POST.get("betrag"))

    if not beschreibung or betrag is None:
        messages.error(request, "Bitte Beschreibung und einen gültigen Betrag angeben.")
        return redirect(kasse_url)

    # Kategorie: explizit gewählt, sonst automatisch aus der Beschreibung vorschlagen.
    kategorie = _gueltige_kategorie(request.POST.get("kategorie")) or rate_kategorie(beschreibung)

    ausgabe = TopfAusgabe.objects.create(
        toern=toern,
        erstellt_von=request.user,
        beschreibung=beschreibung,
        betrag=betrag,
        kategorie=kategorie,
    )

    anzahl = _speichere_belege(ausgabe, request.FILES.getlist("belege"), request.user)

    beleg_hinweis = f" · {anzahl} Beleg(e)" if anzahl else ""
    messages.success(
        request, f"Topf-Ausgabe „{beschreibung}“ ({betrag} €){beleg_hinweis} gespeichert."
    )
    return redirect(kasse_url)


@login_required
@require_POST
def topf_ausgabe_loeschen(request, ausgabe_id):
    ausgabe = get_object_or_404(
        TopfAusgabe.objects.select_related("toern"), id=ausgabe_id
    )
    toern = ausgabe.toern

    darf_loeschen = (
        request.user == ausgabe.erstellt_von
        or request.user == toern.anbieter
        or _ist_toern_skipper(request.user, toern)
    )
    if not darf_loeschen:
        raise PermissionDenied

    ausgabe.delete()
    messages.success(request, "Topf-Ausgabe gelöscht.")
    return redirect(f"{reverse('skipper_dashboard', args=[toern.id])}?tab=kasse")


def _darf_topf_verwalten(user, toern):
    """Skipper, Co-Skipper oder Anbieter dürfen den Topf verwalten & exportieren."""
    return user == toern.anbieter or _ist_toern_skipper(user, toern)


@login_required
@require_POST
def topf_ausgabe_bearbeiten(request, ausgabe_id):
    ausgabe = get_object_or_404(
        TopfAusgabe.objects.select_related("toern"), id=ausgabe_id
    )
    toern = ausgabe.toern

    if not (request.user == ausgabe.erstellt_von or _darf_topf_verwalten(request.user, toern)):
        raise PermissionDenied

    kasse_url = f"{reverse('skipper_dashboard', args=[toern.id])}?tab=kasse"

    beschreibung = request.POST.get("beschreibung", "").strip()
    betrag = _parse_betrag(request.POST.get("betrag"))
    if not beschreibung or betrag is None:
        messages.error(request, "Bitte Beschreibung und einen gültigen Betrag angeben.")
        return redirect(kasse_url)

    ausgabe.beschreibung = beschreibung
    ausgabe.betrag = betrag
    ausgabe.kategorie = _gueltige_kategorie(request.POST.get("kategorie")) or ausgabe.kategorie
    ausgabe.save()

    # Optional beim Bearbeiten direkt weitere Belege mitschicken.
    _speichere_belege(ausgabe, request.FILES.getlist("belege"), request.user)

    messages.success(request, f"Topf-Ausgabe „{beschreibung}“ aktualisiert.")
    return redirect(kasse_url)


@login_required
@require_POST
def topf_beleg_add(request, ausgabe_id):
    ausgabe = get_object_or_404(
        TopfAusgabe.objects.select_related("toern"), id=ausgabe_id
    )
    toern = ausgabe.toern

    if not (request.user == ausgabe.erstellt_von or _darf_topf_verwalten(request.user, toern)):
        raise PermissionDenied

    kasse_url = f"{reverse('skipper_dashboard', args=[toern.id])}?tab=kasse"
    anzahl = _speichere_belege(ausgabe, request.FILES.getlist("belege"), request.user)

    if anzahl:
        messages.success(request, f"{anzahl} Beleg(e) hinzugefügt.")
    else:
        messages.error(request, "Keine gültigen Belegfotos empfangen.")
    return redirect(kasse_url)


@login_required
@require_POST
def topf_beleg_loeschen(request, beleg_id):
    beleg = get_object_or_404(
        TopfBeleg.objects.select_related("ausgabe__toern"), id=beleg_id
    )
    toern = beleg.ausgabe.toern

    if not (request.user == beleg.ausgabe.erstellt_von or _darf_topf_verwalten(request.user, toern)):
        raise PermissionDenied

    beleg.delete()
    messages.success(request, "Beleg gelöscht.")
    return redirect(f"{reverse('skipper_dashboard', args=[toern.id])}?tab=kasse")


# ───────────────────────── Abrechnung: gemeinsame Daten ─────────────────────────

def _abrechnung_struktur(toern):
    """Ausgaben des Topfs nach Kategorie gruppiert, mit fortlaufenden Beleg-Nummern.

    Dieselbe Reihenfolge/Nummerierung wird von PDF und Excel genutzt, damit die
    Beleg-Nr. in der Excel-Liste auf die richtige Seite im PDF verweist.
    """
    reihenfolge = [k for k, _ in TopfAusgabe.KATEGORIE_CHOICES]
    labels = dict(TopfAusgabe.KATEGORIE_CHOICES)

    ausgaben = list(
        TopfAusgabe.objects.filter(toern=toern)
        .select_related("erstellt_von")
        .prefetch_related("belege")
    )
    # Nach Kategorie-Reihenfolge, dann chronologisch (älteste zuerst).
    ausgaben.sort(key=lambda a: (reihenfolge.index(a.kategorie) if a.kategorie in reihenfolge else 999, a.created_at))

    gruppen = []
    beleg_nr = 0
    for key in reihenfolge:
        gruppe_ausgaben = [a for a in ausgaben if a.kategorie == key]
        if not gruppe_ausgaben:
            continue
        eintraege = []
        summe = Decimal("0")
        for a in gruppe_ausgaben:
            summe += a.betrag
            belege = []
            for b in a.belege.all():
                beleg_nr += 1
                belege.append({"beleg": b, "nummer": f"B-{beleg_nr:03d}"})
            eintraege.append({"ausgabe": a, "belege": belege})
        gruppen.append({
            "key": key,
            "label": labels[key],
            "summe": summe,
            "eintraege": eintraege,
        })

    gesamt = sum((g["summe"] for g in gruppen), Decimal("0"))
    return gruppen, gesamt


def _dateiname(toern, endung):
    basis = re.sub(r"[^\w\-]", "_", toern.titel or "Toern")[:50]
    return f"Abrechnung_{basis}.{endung}"


@login_required
def topf_belege_pdf(request, toern_id):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.platypus import Image as RLImage
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from PIL import Image as PILImage

    toern = get_object_or_404(Toern, id=toern_id)
    if not _darf_topf_verwalten(request.user, toern):
        raise PermissionDenied

    gruppen, gesamt = _abrechnung_struktur(toern)

    buffer = io.BytesIO()
    MAR = 18 * mm
    USABLE_W = A4[0] - 2 * MAR
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MAR, rightMargin=MAR, topMargin=MAR, bottomMargin=MAR,
        title=f"Belegsammlung – {toern.titel}",
    )

    PRIMARY = colors.HexColor("#1e3a5f")
    TEAL = colors.HexColor("#0D9488")

    title_s = ParagraphStyle("t", fontSize=20, leading=24, textColor=PRIMARY, fontName="Helvetica-Bold")
    sub_s = ParagraphStyle("s", fontSize=10, leading=14, textColor=colors.HexColor("#64748b"))
    cat_s = ParagraphStyle("c", fontSize=13, leading=17, textColor=TEAL, fontName="Helvetica-Bold", spaceBefore=6*mm, spaceAfter=1*mm)
    exp_s = ParagraphStyle("e", fontSize=10, leading=14, fontName="Helvetica-Bold", textColor=colors.black)
    meta_s = ParagraphStyle("m", fontSize=8, leading=11, textColor=colors.HexColor("#64748b"))
    num_s = ParagraphStyle("n", fontSize=8, leading=11, fontName="Helvetica-Bold", textColor=TEAL)
    note_s = ParagraphStyle("no", fontSize=9, leading=12, fontName="Helvetica-Oblique", textColor=colors.HexColor("#b45309"))

    elements = []
    elements.append(Paragraph("Belegsammlung – Skipper-Topf", title_s))
    elements.append(Paragraph(
        f"{toern.titel} · Stand {timezone.localdate().strftime('%d.%m.%Y')} · "
        f"Budget {toern.skipper_budget:.2f} € · Ausgegeben {gesamt:.2f} € · "
        f"Verbleibend {(toern.skipper_budget - gesamt):.2f} €",
        sub_s,
    ))
    elements.append(HRFlowable(width=USABLE_W, thickness=0.5, color=TEAL, spaceBefore=2*mm, spaceAfter=1*mm))

    if not gruppen:
        elements.append(Spacer(1, 6*mm))
        elements.append(Paragraph("Noch keine Ausgaben erfasst.", meta_s))

    MAX_IMG_H = 150 * mm
    for g in gruppen:
        elements.append(Paragraph(f"{g['label']}  ·  {g['summe']:.2f} €", cat_s))
        elements.append(HRFlowable(width=USABLE_W, thickness=0.3, color=colors.HexColor("#e2e8f0")))
        for eintrag in g["eintraege"]:
            a = eintrag["ausgabe"]
            erfasser = f"{a.erstellt_von.first_name} {a.erstellt_von.last_name}".strip() if a.erstellt_von else "—"
            elements.append(Spacer(1, 2*mm))
            elements.append(Paragraph(f"{a.beschreibung} — {a.betrag:.2f} €", exp_s))
            elements.append(Paragraph(f"{a.created_at.strftime('%d.%m.%Y')} · {erfasser}", meta_s))
            if not eintrag["belege"]:
                elements.append(Paragraph("⚠ Kein Beleg vorhanden", note_s))
                continue
            for bl in eintrag["belege"]:
                try:
                    path = bl["beleg"].bild.path
                    with PILImage.open(path) as im:
                        iw, ih = im.size
                    ratio = ih / iw if iw else 1
                    w = USABLE_W
                    h = w * ratio
                    if h > MAX_IMG_H:
                        h = MAX_IMG_H
                        w = h / ratio
                    elements.append(Spacer(1, 1.5*mm))
                    elements.append(Paragraph(bl["nummer"], num_s))
                    elements.append(RLImage(path, width=w, height=h))
                except Exception:
                    elements.append(Paragraph(f"{bl['nummer']} · Beleg konnte nicht geladen werden", meta_s))

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{_dateiname(toern, "pdf")}"'
    return response


@login_required
def topf_abrechnung_xlsx(request, toern_id):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.chart import PieChart, Reference
    from openpyxl.chart.label import DataLabelList
    from openpyxl.worksheet.properties import PageSetupProperties

    toern = get_object_or_404(Toern, id=toern_id)
    if not _darf_topf_verwalten(request.user, toern):
        raise PermissionDenied

    gruppen, gesamt = _abrechnung_struktur(toern)

    wb = Workbook()
    ws = wb.active
    ws.title = "Abrechnung"
    ws.sheet_view.showGridLines = False  # Gitternetz aus → weißes Blatt

    PRIMARY = "1E3A5F"
    TEAL = "0D9488"
    LIGHT = "E2E8F0"
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor=PRIMARY)
    cat_font = Font(bold=True, color="FFFFFF")
    cat_fill = PatternFill("solid", fgColor=TEAL)
    bold = Font(bold=True)
    thin = Side(style="thin", color=LIGHT)
    border = Border(bottom=thin)
    euro = '#,##0.00\\ €'

    # Spalte A bleibt als Rand frei; Inhalt beginnt in Spalte B (col_index 2).
    # Zeile 1 bleibt leer (Rand oben), Titel in Zeile 2.
    ws.append([])  # Zeile 1: leer
    ws.append([None, f"Abrechnung Skipper-Topf – {toern.titel}"])  # Zeile 2: Titel
    ws["B2"].font = Font(bold=True, size=14, color=PRIMARY)
    ws.append([None, f"Stand {timezone.localdate().strftime('%d.%m.%Y')}"])  # Zeile 3: Stand
    ws["B3"].font = Font(italic=True, color="64748B")
    ws.append([])  # Zeile 4: leer
    ws.append([])  # Zeile 5: leer  (2 Leerzeilen unter dem Stand)

    # Datenspalten: B=Datum C=Kategorie D=Beschreibung E=Betrag F=Erfasst G=Belege
    COL_KAT, COL_BESCHR, COL_BETRAG = 3, 4, 5
    spalten = ["Datum", "Kategorie", "Beschreibung", "Betrag", "Erfasst von", "Belege (siehe PDF)"]
    ws.append([None] + spalten)
    # Zeilennummer NACH dem append lesen: ein leeres ws.append([]) schiebt zwar
    # den Schreib-Cursor weiter, erhöht aber max_row nicht (es entstehen keine
    # Zellen). Vorher gerechnet landete die Formatierung auf einer leeren Zeile.
    header_row = ws.max_row
    for col in range(2, 2 + len(spalten)):
        c = ws.cell(row=header_row, column=col)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")

    for g in gruppen:
        # Kategorie-Zeile
        ws.append([None, g["label"], "", "", g["summe"], "", ""])
        r = ws.max_row
        for col in range(2, 8):
            ws.cell(row=r, column=col).fill = cat_fill
            ws.cell(row=r, column=col).font = cat_font
        ws.cell(row=r, column=COL_BETRAG).number_format = euro
        ws.cell(row=r, column=COL_BETRAG).alignment = Alignment(horizontal="right")

        for eintrag in g["eintraege"]:
            a = eintrag["ausgabe"]
            erfasser = f"{a.erstellt_von.first_name} {a.erstellt_von.last_name}".strip() if a.erstellt_von else ""
            belege_ref = ", ".join(bl["nummer"] for bl in eintrag["belege"]) or "— kein Beleg —"
            ws.append([
                None,
                a.created_at.strftime("%d.%m.%Y"),
                g["label"],
                a.beschreibung,
                float(a.betrag),
                erfasser,
                belege_ref,
            ])
            rr = ws.max_row
            ws.cell(row=rr, column=COL_BETRAG).number_format = euro
            ws.cell(row=rr, column=COL_BETRAG).alignment = Alignment(horizontal="right")
            for col in range(2, 8):
                ws.cell(row=rr, column=col).border = border

    # Summenblock
    ws.append([])
    def summenzeile(label, wert, fett=True):
        ws.append([None, "", "", label, float(wert), "", ""])
        r = ws.max_row
        ws.cell(row=r, column=COL_BESCHR).font = bold if fett else Font()
        c = ws.cell(row=r, column=COL_BETRAG)
        c.number_format = euro
        c.font = bold if fett else Font()
        c.alignment = Alignment(horizontal="right")
        return r

    # Zeilen der Kategorie-Summen merken — das Tortendiagramm referenziert sie
    # später. Die Nummern kommen aus summenzeile selbst, damit sie auch dann
    # stimmen, wenn davor eine Leerzeile eingefügt wurde.
    kat_summen_zeilen = [summenzeile(g["label"], g["summe"], fett=False) for g in gruppen]
    ws.append([])
    summenzeile("Gesamt ausgegeben", gesamt)
    summenzeile("Budget", toern.skipper_budget)
    rest_row = summenzeile("Verbleibend", toern.skipper_budget - gesamt)
    if toern.skipper_budget - gesamt < 0:
        ws.cell(row=rest_row, column=COL_BETRAG).font = Font(bold=True, color="DC2626")

    # Diagramm rechts: Aufteilung der Kosten nach Kategorie (aus dem Summenblock)
    if gruppen:
        chart = PieChart()
        chart.title = "Kostenaufteilung"
        chart.height = 8
        chart.width = 12
        labels = Reference(ws, min_col=COL_BESCHR,
                           min_row=kat_summen_zeilen[0], max_row=kat_summen_zeilen[-1])
        data = Reference(ws, min_col=COL_BETRAG,
                         min_row=kat_summen_zeilen[0], max_row=kat_summen_zeilen[-1])
        chart.add_data(data, titles_from_data=False)
        chart.set_categories(labels)
        chart.dataLabels = DataLabelList()
        chart.dataLabels.showPercent = True
        ws.add_chart(chart, "I2")

    # Spaltenbreiten: A schmaler Rand, dann B..G
    breiten = {"A": 3, "B": 12, "C": 28, "D": 40, "E": 14, "F": 22, "G": 26}
    for spalte, w in breiten.items():
        ws.column_dimensions[spalte].width = w

    # Druck: A4 hochkant, Tabelle (Spalten A–G) auf Seitenbreite skaliert.
    # Diagramm liegt in Spalte I und damit außerhalb des Druckbereichs.
    letzte_zeile = ws.max_row
    ws.print_area = f"A1:G{letzte_zeile}"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = 9  # A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0  # Breite fix auf 1 Seite, Höhe nach Bedarf
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{_dateiname(toern, "xlsx")}"'
    return response
