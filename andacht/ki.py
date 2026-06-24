import json
import anthropic
from django.conf import settings


ZIELGRUPPE_BESCHREIBUNG = {
    'maritim': 'Menschen auf einem Segelboot – maritime Metaphern aus der Segelwelt sind ausdrücklich erwünscht und sollen natürlich und treffend eingesetzt werden',
    'kinder': 'Kinder (ca. 6–12 Jahre) – einfache, bildreiche Sprache, kurze Sätze, anschauliche Beispiele aus der Kinderwelt',
    'jugendliche': 'Jugendliche (ca. 13–17 Jahre) – zeitgemäße Sprache, lebensnahe Themen, Fragen die bewegen',
    'junge_erwachsene': 'Junge Erwachsene (ca. 18–30 Jahre) – relevante Alltagsthemen, Aufbruch, Identität, moderne Sprache',
    'erwachsene': 'Erwachsene – tiefgehend, theologisch ausgereift, spirituell anspruchsvoll',
    'gemischt': 'Gemischte Gruppe aller Altersgruppen – inklusiv, mehrere Ebenen, sowohl einfach zugänglich als auch tiefgründig',
}

KIRCHENJAHR_BEZEICHNUNG = {
    'advent': 'Adventszeit (Warten, Erwartung, Vorbereitung)',
    'weihnacht': 'Weihnachtszeit (Menschwerdung Gottes, Licht in der Dunkelheit)',
    'passion': 'Passions- und Fastenzeit (Besinnung, Umkehr, Nachfolge)',
    'ostern': 'Osterzeit (Auferstehung, neues Leben, Hoffnung)',
    'pfingsten': 'Pfingstzeit (Heiliger Geist, Gemeinschaft, Sendung)',
    'normale_zeit': 'Trinitatiszeit / Normale Kirchenzeit',
}

STIL_BESCHREIBUNG = {
    'meditativ': 'meditativ und besinnlich – ruhige Töne, Raum für Stille und innere Einkehr',
    'erzaehlend': 'erzählend und narrativ – eine Geschichte entfaltet die Botschaft lebendig',
    'liturgisch': 'liturgisch strukturiert – klassischer Gottesdienstcharakter mit klaren Elementen',
}


def generiere_andacht(andacht_obj):
    """Ruft die Claude API auf und gibt das geparste Ergebnis-Dict zurück oder None bei Fehler."""
    api_key = getattr(settings, 'ANTHROPIC_API_KEY', '')
    if not api_key:
        return None

    bibelstelle_info = (
        f'Die Bibelstelle wurde vorgegeben: **{andacht_obj.bibelstelle_eingabe}** – '
        'verwende genau diese Stelle.'
        if andacht_obj.bibelstelle_eingabe
        else 'Wähle eine Bibelstelle, die thematisch hervorragend zum Thema passt.'
    )

    optionale_teile = []
    if andacht_obj.mit_liedern:
        liedwunsch = (
            f' Der Nutzer wünscht sich folgendes Lied: "{andacht_obj.eigener_liedwunsch}".'
            if andacht_obj.eigener_liedwunsch
            else ''
        )
        optionale_teile.append(
            f'lieder: Array mit 2 Liedvorschlägen (Eröffnungs- und Schlusslied), '
            f'je mit "position" (einstieg/schluss), "titel" und "eg_nummer" (EG-Nummer, falls vorhanden).{liedwunsch}'
        )
    if andacht_obj.mit_geschichte:
        optionale_teile.append(
            'geschichte: Eine kurze, passende Geschichte oder Anekdote (ca. 80–120 Wörter) '
            'die als Illustration oder Einstieg dient.'
        )
        optionale_teile.append(
            'geschichte_quelle: Kurze Quellenangabe — entweder "KI-generierte Illustration" '
            'wenn die Geschichte frei erfunden ist, oder z.B. "Angelehnt an: [Name/Ereignis/Werk]" '
            'wenn sie auf einer realen Begebenheit basiert.'
        )
    if andacht_obj.mit_gebeten:
        optionale_teile.append(
            'gebete: Objekt mit drei Gebeten: "eroeffnung" (kurzes Eröffnungsgebet), '
            '"fuerbitten" (3–4 Fürbitten zum Thema), "abschluss" (Abschlussgebet/Segen).'
        )
    if andacht_obj.mit_gespraechsimpulsen:
        optionale_teile.append(
            'gespraechsimpulse: Array mit 3 konkreten Diskussionsfragen für die Gruppe.'
        )

    kirchenjahr_hinweis = ''
    if andacht_obj.kirchenjahr:
        bez = KIRCHENJAHR_BEZEICHNUNG.get(andacht_obj.kirchenjahr, '')
        kirchenjahr_hinweis = f'\n- Kirchenjahr/Saison: {bez}'

    stil_hinweis = ''
    if andacht_obj.stil:
        bez = STIL_BESCHREIBUNG.get(andacht_obj.stil, '')
        stil_hinweis = f'\n- Stilrichtung: {bez}'

    stichpunkte_hinweis = ''
    if andacht_obj.stichpunkte:
        stichpunkte_hinweis = f'\n- Gedanken/Stichpunkte des Nutzers: {andacht_obj.stichpunkte}'

    kontext_hinweis = ''
    if andacht_obj.kontext:
        kontext_hinweis = f'\n- Kontext / Gruppe: {andacht_obj.kontext}'

    optionale_felder_text = '\n'.join(f'- {t}' for t in optionale_teile)

    prompt = f"""Du bist ein erfahrener evangelischer Gemeindepädagoge und Prediger.
Erstelle eine vollständige, inhaltlich reiche {andacht_obj.get_typ_display()} mit folgenden Vorgaben:

**Vorgaben:**
- Zielgruppe: {ZIELGRUPPE_BESCHREIBUNG.get(andacht_obj.zielgruppe, andacht_obj.zielgruppe)}
- Geplante Dauer: ca. {andacht_obj.dauer_minuten} Minuten{kirchenjahr_hinweis}{stil_hinweis}
- Thema: {andacht_obj.thema}{stichpunkte_hinweis}{kontext_hinweis}
- Bibelstelle: {bibelstelle_info}

**Pflichtfelder im JSON:**
- titel: Kurzer, treffender Titel der Andacht (max. 60 Zeichen)
- bibelstelle: Die Bibelstelle in Kurzform (z.B. "Johannes 3,16")
- bibeltext: Den vollständigen Bibeltext nach Luther 2017
- exegese: Fachliche Auslegung FÜR DEN ANDACHTSHALTENDEN – historischer Entstehungskontext, theologische Kernaussage, Bezug zum Thema (150–200 Wörter)
- einstieg: Einleitungsgedanke der Andacht (~100 Wörter)
- entfaltung: Hauptteil – entfaltet das Thema an der Bibelstelle, auf die Dauer von {andacht_obj.dauer_minuten} Min. abgestimmt (~{max(150, andacht_obj.dauer_minuten * 18)} Wörter)
- abschluss: Schlussgedanke und Überleitung (~80 Wörter)

**Optionale Felder (MÜSSEN enthalten sein wenn hier gelistet):**
{optionale_felder_text if optionale_felder_text else "– keine optionalen Felder gewählt –"}

Antworte ausschließlich als gültiges JSON-Objekt ohne Markdown-Codeblöcke."""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=4096,
        system='Du bist ein kompetenter evangelischer Prediger und Theologe. Du erstellst hochwertige Andachten auf Deutsch.',
        messages=[{'role': 'user', 'content': prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith('```'):
        raw = raw.split('```')[1]
        if raw.startswith('json'):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)
