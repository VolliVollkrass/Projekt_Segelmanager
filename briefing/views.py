import json
import re

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from utils.permissions import briefing_required

from . import markup
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
        "text_html": markup.als_html(baustein.text),
        "next": _safe_next(request),
    })


@login_required
@briefing_required
def baustein_erstellen(request):
    if request.method == "POST":
        return _baustein_speichern(request, baustein=None)
    return render(request, "briefing/form.html", {
        "kategorien": BriefingBaustein.KATEGORIE_CHOICES,
        "bild_positionen": BriefingBaustein.BILD_POSITION_CHOICES,
        "block_labels": markup.BLOCK_LABELS,
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
        "bild_positionen": BriefingBaustein.BILD_POSITION_CHOICES,
        "block_labels": markup.BLOCK_LABELS,
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
            "bild_positionen": BriefingBaustein.BILD_POSITION_CHOICES,
            "block_labels": markup.BLOCK_LABELS,
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

    baustein.bild_position = request.POST.get("bild_position", "unten")

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


@login_required
@briefing_required
@require_POST
def vorschau(request):
    """Rendert Baustein-Markup als HTML für die Live-Vorschau im Formular.

    Bewusst serverseitig: so gibt es nur eine Parser-Implementierung
    (briefing/markup.py), die Vorschau, Detailansicht und PDF gemeinsam nutzen.
    Kein Datenbankzugriff, keine KI — reine Funktion."""
    data = json.loads(request.body)
    return JsonResponse({"html": markup.als_html(data.get("text", ""))})


KORREKTUR_SYSTEM = """Du bist Korrektor für Crew-Briefings auf Segelbooten.

Deine einzige Aufgabe ist Rechtschreibung, Grammatik und Zeichensetzung.

Absolut verbindliche Regeln:
- Ändere NIEMALS den Inhalt, die Aussage oder die Reihenfolge der Informationen.
- Formuliere NICHT um, kürze nicht, ergänze nichts. Auch nicht "zur Verbesserung".
- Fachbegriffe aus der Seemannssprache bleiben unangetastet (fieren, belegen,
  aufschießen, Backbord, Luv, Lee, Mooring, Palstek, Webleinstek, Marinero ...).
- Die persönliche Anrede und der Ton des Autors bleiben erhalten.
- Sicherheitsrelevante Anweisungen bleiben wortgleich, sofern sie korrekt geschrieben sind.

Zusätzlich darfst du vorhandene Absätze auszeichnen, wenn es eindeutig passt.
Auszeichnung geschieht durch ein Zeichen am Zeilenanfang:
  !  Warnung — nur bei echter Gefahr für Menschen oder Boot
  >  Hinweis — Ergänzung, Tipp
  *  Merksatz — ein einzelner einprägsamer Satz
  -  Aufzählungspunkt
  #  Schritt in einem nummerierten Ablauf
  |  Tabellenzeile, Spalten mit | getrennt

Zeichne sparsam aus. Im Zweifel lässt du einen Absatz als normalen Fließtext.
Bereits vorhandene Auszeichnungen behältst du bei.

Antworte ausschließlich mit JSON, ohne Markdown-Codeblock:
{"text": "<korrigierter Text>", "aenderungen": ["kurze Stichpunkte, was du geändert hast"]}"""


@login_required
@briefing_required
@ratelimit(key="user", rate="30/h", block=True)
@require_POST
def ki_korrektur(request):
    """Rechtschreib-/Grammatikkorrektur eines Baustein-Textes.

    Das Ergebnis wird dem Skipper nur vorgeschlagen — übernommen wird es erst,
    wenn er im Formular auf "Übernehmen" klickt."""
    from django.conf import settings as django_settings
    import anthropic

    api_key = django_settings.ANTHROPIC_API_KEY
    if not api_key:
        return JsonResponse({"error": "KI ist nicht konfiguriert."}, status=503)

    data = json.loads(request.body)
    text = (data.get("text") or "").strip()
    if not text:
        return JsonResponse({"error": "Kein Text zum Korrigieren."}, status=400)
    if len(text) > 8000:
        return JsonResponse({"error": "Text ist zu lang (max. 8000 Zeichen)."}, status=400)

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=4000,
        system=KORREKTUR_SYSTEM,
        messages=[{"role": "user", "content": text}],
    )

    roh = message.content[0].text.strip()
    roh = re.sub(r"^```(?:json)?\s*", "", roh)
    roh = re.sub(r"\s*```$", "", roh)
    try:
        ergebnis = json.loads(roh)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Antwort der KI war unlesbar."}, status=502)

    korrigiert = ergebnis.get("text", "")
    return JsonResponse({
        "text": korrigiert,
        "aenderungen": ergebnis.get("aenderungen", []),
        "unveraendert": korrigiert.strip() == text,
        "html": markup.als_html(korrigiert),
    })
