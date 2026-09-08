# -*- coding: utf-8 -*-
"""Startbestand des wachsenden Erfahrungsbuchs: zerlegt das ursprünglich als
einmaliges PDF geschriebene Crew-Briefing ("Neue Crew zum Segeln bringen") in
Einzelbausteine mit ist_standard=True, damit neue Törns nicht bei null anfangen."""
import os

from django.conf import settings
from django.db import migrations


SEED_ASSETS = os.path.join(os.path.dirname(__file__), 'seed_assets')

# (titel, kategorie, text, reihenfolge, bilddatei_oder_None)
BAUSTEINE = [
    (
        "Warum ich mir diese Stunde nehme", "kommunikation",
        "Ihr bekommt in den nächsten Minuten sehr viele Informationen auf einmal, und ein Teil davon "
        "wird sich beim ersten Hören nach deutlich zu viel anfühlen. Das ist normal und es ist auch "
        "kein Problem. Ich erwarte nicht, dass ihr euch heute alles merkt. Ich erwarte, dass ihr wisst, "
        "dass es diese Dinge gibt, und dass ihr fragt, sobald ihr an einer Stelle unsicher seid.\n\n"
        "Der Grund für diesen Aufwand ist einfach: Unfälle auf einem Segelboot entstehen so gut wie nie "
        "aus einem einzelnen Fehler. Sie entstehen dann, wenn mehrere kleine Fehler unbemerkt "
        "hintereinanderfallen und niemand die Kette unterbricht. Jeder Einzelne von euch kann diese "
        "Kette an jeder Stelle unterbrechen, und genau darum geht es mir.\n\n"
        "Wir werden auf diesem Törn viel Quatsch machen und viel Spaß haben, dafür sind wir hier. Bei "
        "Manövern hört das für ein paar Minuten auf. Manöver haben immer mit Sicherheit zu tun, und da "
        "mache ich keine Kompromisse. Was ich ausdrücklich nicht möchte, ist, dass sich hier jemand "
        "durchbeißen muss — niemand muss an Bord etwas beweisen.",
        0, None,
    ),
    (
        "Die wichtigste Regel: jedes Kommando bekommt eine Antwort", "kommunikation",
        "Manche von euch waren schon mehrfach segeln, andere stehen heute zum ersten Mal an Deck. "
        "Unterschiedliche Menschen machen dieselben Dinge unterschiedlich — deshalb legen wir sehr "
        "großen Wert auf Kommunikation.\n\n"
        "Beim Ablegen und beim Anlegen passiert sehr viel gleichzeitig. Ich stehe in dieser Zeit am "
        "Steuer und kann nicht überall gleichzeitig hinschauen. Ich bin darauf angewiesen, dass ich "
        "höre, was an Deck passiert, statt es sehen zu müssen.\n\n"
        "Deshalb gilt: Auf jedes Kommando folgt eine Bestätigung — nicht ein Nicken, sondern ein laut "
        "gesprochener Satz. Erst wenn ich die Bestätigung gehört habe, weiß ich, dass die Aufgabe "
        "angekommen und erledigt ist. Während eines Manövers habe ich das Kommando über alle Vorgänge "
        "an Bord; alle anderen konzentrieren sich in dieser Zeit auf mich und bleiben ansprechbar.",
        1, None,
    ),
    (
        "So klingt das in der Praxis", "kommunikation",
        "Ein paar Beispiele, wie Kommando und Bestätigung an Bord zusammengehören — von „Leine lösen“ "
        "und „Leine ist los“ bis zu „Klar zur Wende?“ und „Klar!“. Wenn du etwas nicht verstanden hast, "
        "sag einfach laut „Nochmal!“ — das ist ein vollwertiges Kommando und kostet uns zwei Sekunden. "
        "Ein falsch ausgeführtes Manöver kostet deutlich mehr.",
        2, "kommando_tabelle.png",
    ),
    (
        "Kommandosprache klingt unhöflich — ist sie aber nicht", "kommunikation",
        "Die Sprache, die wir bei Manövern benutzen, ist sehr knapp. Sie ist knapp, weil sie schnell, "
        "eindeutig und über Entfernung verständlich sein muss. Ihr werdet dabei kein „bitte“ und kein "
        "„danke“ von mir hören, und ihr werdet von mir vermutlich auch keine Erklärung hören, warum "
        "gerade jetzt genau das dran ist.\n\n"
        "Das hat nichts mit Wertschätzung oder Abneigung zu tun. Ich habe in diesem Moment nur keine "
        "Kapazität für Höflichkeitsformen. Nehmt das, was ich sage, deshalb bitte immer auf dem "
        "Sachohr — als reine Information darüber, was zu tun ist. Sobald wir fest liegen oder ruhig "
        "segeln, bin ich wieder der ganz normale Mensch von vorhin.",
        3, None,
    ),
    (
        "Wenn Rufen nicht mehr reicht: Handzeichen", "kommunikation",
        "Zwischen Vorschiff und Steuerstand liegen mehr als zehn Meter, dazwischen ein laufender Motor "
        "und der Wind. Gerufene Worte gehen dort regelmäßig unter, und zwar genau dann, wenn es eng "
        "wird. Wir benutzen deshalb ein paar wenige, unmissverständliche Handzeichen: Daumen hoch für "
        "verstanden/erledigt, eine flache Hand ruhig auf und ab für langsamer, beide Hände gekreuzt "
        "über dem Kopf für sofortiges Stoppen, ein ausgestreckter Arm für die Richtung, ein gezeigter "
        "Abstand für die verbleibende Distanz, eine Faust für „halt so, wie es jetzt ist“. Wichtig ist "
        "dabei nur eines: Wer ein Zeichen gibt, schaut den anderen dabei an.",
        4, None,
    ),
    (
        "Steuerbord, Backbord und der Rest", "orientierung",
        "An Land funktioniert „links“ und „rechts“ deshalb, weil beide meistens in dieselbe Richtung "
        "schauen. An Bord ist genau das nicht gegeben: Ich stehe am Steuer und blicke nach vorn, du "
        "kniest auf dem Vorschiff und blickst zu mir zurück — dein „links“ ist dann mein „rechts“. In "
        "einem Moment, in dem es auf Sekunden ankommt, ist das gefährlich.\n\n"
        "Deshalb sind Richtungsangaben an Bord immer auf das Boot bezogen und nie auf eine Person. Von "
        "hinten nach vorn geschaut ist Steuerbord die rechte und Backbord die linke Seite. Vorne heißt "
        "Bug, hinten heißt Heck. Dazu kommen Luv (die Seite, von der der Wind kommt) und Lee (die "
        "windabgewandte Seite) — beim Ablegen wichtig, weil die Lee-Leinen meist unbelastet sind, "
        "während die Luv-Leinen das Boot am Platz halten.",
        0, "boot_schema.png",
    ),
    (
        "Die Wörter, die ich benutzen werde", "orientierung",
        "Ein kurzes Nachschlage-Vokabular für die ersten Tage: Cockpit ist der offene Sitzbereich "
        "hinten, Salon und Pantry sind Wohnraum und Bordküche unter Deck, der Niedergang ist die Treppe "
        "dorthin. Vorschiff und Achterschiff sind der vordere und hintere Bereich des Decks, die Reling "
        "ist das Geländer außen — eine Absicherung, kein Haltegriff. Die Winsch ist die Kurbeltrommel "
        "für Leinen unter Last, die Schot stellt ein Segel ein, das Fall zieht es hoch. Groß und Fock "
        "beziehungsweise Genua sind die Segel am Mast und vorn am Bug, Fender sind die Kunststoffwürste, "
        "die das Boot vor dem Steg schützen.",
        1, None,
    ),
    (
        "Rettungsweste und Lifebelt", "sicherheit",
        "Jede und jeder bekommt eine eigene Rettungsweste, die auf die eigene Körpergröße eingestellt "
        "wird. Angelegt wird sie bei Dunkelheit, bei Welle oder mehr Wind, bei allen Manövern an Deck — "
        "und immer dann, wenn du dich damit wohler fühlst. Dafür braucht niemand eine Begründung.\n\n"
        "Bei Nachtfahrten und bei rauer See leinen wir uns mit dem Lifebelt am Strecktau an, bevor wir "
        "das Cockpit verlassen. An Deck gilt: eine Hand für das Schiff, eine Hand für dich. Bewegt euch "
        "möglichst auf der Luv-Seite und haltet euch immer an etwas Festem fest, nie an einer Leine.",
        0, None,
    ),
    (
        "Mann über Bord", "sicherheit",
        "Wenn jemand über Bord geht: Zuerst laut rufen — „Mann über Bord!“ — so laut, dass es alle "
        "hören. Eine Person zeigt danach ununterbrochen mit dem ausgestreckten Arm auf die Person im "
        "Wasser und macht ab sofort nichts anderes mehr; wer den Blickkontakt verliert, findet den "
        "Menschen bei Welle oft nicht wieder. Rettungsring oder Rettungsboje werden sofort "
        "hinterhergeworfen, auch als Positionsmarkierung. Die MOB-Taste am Plotter wird gedrückt, damit "
        "die Position gespeichert ist. Danach übernehme ich das Manöver — alle anderen bleiben auf "
        "ihren Plätzen und warten auf Anweisungen.",
        1, None,
    ),
    (
        "Feuer, Gas und Notruf", "sicherheit",
        "Der Gashahn wird nach jedem Kochen geschlossen — Gas ist schwerer als Luft und sammelt sich "
        "unten im Boot. Wir schauen uns gemeinsam an, wo Feuerlöscher, Löschdecke und Bordapotheke "
        "liegen; wichtig ist, sich die Orte zu merken, nicht nur die Namen. Am Funkgerät hängt eine "
        "Mayday-Karte mit dem Wortlaut des Notrufs und den Bootsdaten, die auch ohne Funkschein "
        "abzulesen ist. Wer Medikamente nimmt, Allergien hat oder eine im Notfall wichtige "
        "Vorerkrankung, sagt das bitte unter vier Augen dem Skipper.",
        2, None,
    ),
    (
        "Der Sicherheits-Rundgang", "sicherheit",
        "Diese Liste gehen wir gemeinsam ab, bevor wir zum ersten Mal ablegen: Feuerlöscher, "
        "Löschdecke, Bordapotheke, Rettungsinsel, Hauptgashahn, Seeventile und Lenzpumpe, "
        "Rettungsringe/-boje, Signalmittel, Werkzeug/Bolzenschneider und Notpinne. Jede und jeder fasst "
        "die Ausrüstung einmal selbst an — was man einmal in der Hand hatte, findet man auch im Dunkeln "
        "wieder.",
        3, None,
    ),
    (
        "Wer macht was im Notfall", "sicherheit",
        "Im Ernstfall soll niemand überlegen müssen, ob er gerade zuständig ist. Wir verteilen die "
        "Aufgaben deshalb schon beim Briefing: wer auf die Person im Wasser zeigt, wer die "
        "Rettungsmittel wirft, wer Funk und Plotter bedient, wer Erste Hilfe leistet und wer sich um "
        "alle anderen kümmert. Wer eine Aufgabe hat, macht ausschließlich diese eine Aufgabe. Am ersten "
        "Tag üben wir bei ruhigem Wetter einmal kurz, indem wir einen Fender über Bord werfen und "
        "gemeinsam anfahren — zehn Minuten, die sich immer lohnen.",
        4, None,
    ),
    (
        "Die drei Knoten, die wir brauchen", "leinen",
        "Drei Knoten decken praktisch alles ab, was wir in den nächsten Tagen brauchen, und die üben "
        "wir in Ruhe im Cockpit. Der Palstek erzeugt eine feste Schlaufe, die sich unter Last nicht "
        "zuzieht und sich trotzdem wieder öffnen lässt — für Leinen um einen Poller oder Ring an Land. "
        "Der Webleinstek ist schnell gelegt und gelöst, gut für Fender an der Reling. Beim Klampe "
        "Belegen kommt ein Rundtörn um die Klampe, dann zwei bis drei Kreuzschläge — bei Leinen, die "
        "wir schnell lösen müssen, ohne Kopfschlag obendrauf, sonst geht sie unter Last nicht mehr auf.",
        0, None,
    ),
    (
        "Fünf Wörter, die wir nicht verwechseln dürfen", "leinen",
        "Fieren heißt kontrolliert nachgeben — die Leine bleibt in der Hand, wird nur langsam länger. "
        "Losmachen heißt, die Leine ist frei und komplett gelöst, danach hält sie gar nichts mehr. "
        "Dichtholen heißt, die Leine straff durchholen. Belegen heißt, sie auf einer Klampe festmachen, "
        "sodass sie ohne Hand hält. Aufschießen heißt, sie ordentlich zu Buchten aufnehmen. Wenn ich "
        "„fieren“ sage und du machst stattdessen los, verliert das Boot in diesem Moment seinen letzten "
        "Halt — im Zweifelsfall lieber einmal zu viel nachfragen als eine Leine zu früh freigeben.",
        1, None,
    ),
    (
        "Aufschießen ohne Dreher, und was an Deck wehtut", "leinen",
        "Eine Leine, die beim Aufschießen Drall bekommen hat, verhakt sich später genau dann, wenn es "
        "schnell gehen muss. Der Trick: Bei jedem Schlag, den du aufnimmst, gibst du der Leine mit den "
        "Fingern eine kleine halbe Drehung mit, dann legt sich jede Bucht flach auf die vorherige.\n\n"
        "Drei Dinge tun an Deck wirklich weh: nie mit Hand oder Fingern in eine Schlaufe greifen, die "
        "unter Last geraten kann; nie zwischen Leine und Klampe oder Poller stehen; nie eine Leine um "
        "die Hand wickeln, um besser ziehen zu können.",
        2, None,
    ),
    (
        "Ablauf beim Ablegen", "ablegen",
        "Wir haben Zeit, wir kennen die Situation — wichtig ist vor allem die Reihenfolge. Rollen "
        "vorher verteilen, Boot klarmachen, „Klar zum Ablegen?“ von beiden Seiten bestätigen lassen, "
        "zuerst die Lee-Leinen lösen, zuletzt die Luv-Leine auf mein Kommando. Aufgeräumt wird erst, "
        "wenn wir frei sind und ich es freigebe.",
        0, "ablauf_ablegen.png",
    ),
    (
        "Zweimal anfassen, dann melden", "ablegen",
        "Bevor du meldest, dass eine Leine los ist, fass sie ein zweites Mal an und verfolge sie mit "
        "der Hand bis zum Ende. Erst dann ist sicher, dass sie wirklich frei ist und sich nirgends mehr "
        "eingehakt hat. Eine Leine, die noch irgendwo hängt, während wir schon Fahrt aufnehmen, ist "
        "eines der ärgerlichsten Probleme überhaupt.",
        1, None,
    ),
    (
        "Ablauf beim Anlegen", "anlegen",
        "Wir fahren mit dem Boot sehr nah heran — das Timing gebe ich vor. Anlegeplan vorher ansagen, "
        "Leinen ohne Dreher vorbereiten, Fender richtig setzen, warten bis wir maximal nah dran sind "
        "oder ich es sage, dann erst werfen — Ziel ist der Arm, nie das Gesicht —, danach belegen und "
        "laut melden, sobald die Leine hält.",
        0, "ablauf_anlegen.png",
    ),
    (
        "Die Marineros meinen es gut — aber sie kennen unseren Plan nicht", "anlegen",
        "In den meisten Häfen kommen Hafenmitarbeiter an den Steg und machen laute Ansagen, oft mit "
        "großen Gesten. Diese Ansagen gelten dem Schiffsführer, nicht der Crew — sie sehen den Steg, "
        "aber nicht, was das Boot gerade unter Wasser macht. Der Weg ist deshalb immer derselbe: Der "
        "Marinero sagt es dem Skipper, der Skipper sagt es der Crew, und erst dann wird geworfen. Ein "
        "abgebrochenes Anlegemanöver ist kein misslungenes, sondern ein souveränes — wir haben Zeit, im "
        "Zweifelsfall drehen wir eine Runde und fahren neu an.",
        1, None,
    ),
    (
        "Die Leine gehört nicht ins Wasser", "anlegen",
        "Unter dem Heck sitzt ein Propeller, der eine erhebliche Menge Wasser ansaugt — und alles, was "
        "darin schwimmt, wird mitgezogen. Eine Leine, die ins Wasser fällt, wickelt sich in Sekunden um "
        "die Welle, besonders kritisch beim Rückwärtsfahren am Dock. Ein Boot ohne Antrieb ist im Hafen "
        "manövrierunfähig.\n\n"
        "Wenn es doch passiert: sofort und laut melden, nicht erst versuchen, sie unauffällig "
        "herauszuziehen. Der Antrieb bleibt neutral, bis die Leine vollständig wieder an Deck ist und "
        "das gemeldet wurde. Eine Leine im Wasser ist erst einmal schlecht, aber harmlos, solange sie "
        "gemeldet wird — gefährlich wird sie nur durch Schweigen. Fehler passieren auf jeder "
        "Erfahrungsstufe, und ein gemeldeter Fehler ist ein gelöster Fehler.",
        2, None,
    ),
    (
        "Die Wende — der Bug geht durch den Wind", "segeln",
        "Bei der Wende drehen wir den Bug durch den Wind. Das Vorsegel schlägt kurz, dann füllt es "
        "sich auf der anderen Seite — ein ruhiges, gut vorhersehbares Manöver nach festem Muster: "
        "„Klar zur Wende?“ — „Klar!“, dann „Ree!“, worauf die alte Fockschot gelöst und die neue "
        "durchgeholt wird, während das Segel noch nicht unter Druck steht. Wer dabei nichts zu tun hat, "
        "wechselt einfach die Sitzseite.",
        0, None,
    ),
    (
        "Die Halse — Vorsicht beim Großbaum", "segeln",
        "Bei der Halse geht das Heck durch den Wind, und der Großbaum wandert mit Schwung von einer "
        "Seite zur anderen — genau auf Kopfhöhe. Deshalb: Köpfe runter, Hände weg vom Baum, niemand "
        "steht in seiner Bahn. Die Halse wird immer laut angesagt, bevor sie beginnt, und wir fahren "
        "sie bewusst langsam und kontrolliert, mit vorher dichtgeholter Großschot, damit der Baum nicht "
        "durchschlagen kann.",
        1, None,
    ),
    (
        "Krängung und Seekrankheit", "segeln",
        "Wenn das Boot unter Segeln zur Seite geneigt fährt, heißt das Krängung, und sie ist völlig "
        "normal — der schwere Kiel richtet das Boot immer wieder auf. Wenn es zu viel wird, sag es "
        "ruhig, die Krängung lässt sich über Kurs oder weniger Segelfläche jederzeit reduzieren.\n\n"
        "Seekrankheit ist keine Schwäche. Früh Bescheid sagen hilft mehr als abwarten. Was hilft: an "
        "Deck bleiben, den Horizont anschauen, frische Luft, etwas im Magen haben — und selbst steuern, "
        "denn wer steuert, wird selten seekrank.",
        2, None,
    ),
    (
        "Wasser und Strom", "bordalltag",
        "Der Wassertank ist begrenzt, Nachfüllen geht nur im Hafen — bitte kurz duschen und beim "
        "Einseifen das Wasser abdrehen. Solange wir am Landstrom hängen, ist Strom kein Thema; sobald "
        "wir abgelegt haben, arbeitet die Batterie, die wir nachts für Positionslichter und Navigation "
        "brauchen. Geräte deshalb bevorzugt im Hafen laden, und den Kühlschrank — den größten Verbraucher "
        "an Bord — nicht unnötig lange offen stehen lassen.",
        0, None,
    ),
    (
        "Die Seetoilette", "bordalltag",
        "Die wichtigste Regel des ganzen Törns: In die Toilette darf ausschließlich das, was vorher "
        "durch den menschlichen Körper gegangen ist. Papier gehört in den Eimer daneben, ebenso "
        "Hygieneartikel und Feuchttücher. Die Pumpe und Schläuche sind eng — eine verstopfte "
        "Bordtoilette ist der unbeliebteste Job an Bord. Der Skipper zeigt jeder und jedem einmal "
        "persönlich, wie gepumpt wird; lieber ein zweites Mal nachfragen als raten.",
        1, None,
    ),
    (
        "Backschaft, Müll und Ordnung", "bordalltag",
        "Backschaft heißt Küchendienst — kochen, abwaschen, Pantry aufräumen — und rotiert täglich in "
        "festen Teams, sodass niemand hängen bleibt. Müll wird an Bord gesammelt und an Land entsorgt, "
        "über Bord geht grundsätzlich nichts. An Bord hat alles einen festen Platz, nicht aus "
        "Pedanterie: Was bei ruhigem Wetter lose herumliegt, wird bei Welle zum Geschoss. Wer von Bord "
        "geht, sagt kurz Bescheid, wohin und für wie lange.",
        2, None,
    ),
    (
        "Die zehn Sätze für den Törn", "sonstiges",
        "Kommunikation ist alles — auf jedes Kommando folgt eine laut gesprochene Bestätigung. Kurz "
        "heißt nicht unfreundlich. Nachfragen ist erwünscht — „Nochmal!“ ist ein vollwertiges Kommando. "
        "Steuerbord ist grün, die langen Wörter gehören zusammen. Fieren ist nicht losmachen. Erst auf "
        "Kommando werfen, auch wenn der Marinero schon ruft. Die Leine gehört nicht ins Wasser — und "
        "wenn doch, sofort melden. Wir haben Zeit; ein abgebrochenes Manöver ist ein souveränes. Eine "
        "Hand für das Schiff, die andere für dich. Und: ein gemeldeter Fehler ist ein gelöster Fehler.",
        0, None,
    ),
]


def seed(apps, schema_editor):
    BriefingBaustein = apps.get_model('briefing', 'BriefingBaustein')
    if BriefingBaustein.objects.exists():
        return  # nicht doppelt befüllen, falls die Migration erneut angewendet wird

    for titel, kategorie, text, reihenfolge, bilddatei in BAUSTEINE:
        baustein = BriefingBaustein(
            titel=titel, kategorie=kategorie, text=text,
            reihenfolge=reihenfolge, ist_standard=True,
            autor=None, zuletzt_bearbeitet_von=None,
        )
        if bilddatei:
            pfad = os.path.join(SEED_ASSETS, bilddatei)
            with open(pfad, 'rb') as f:
                from django.core.files.base import ContentFile
                baustein.bild.save(bilddatei, ContentFile(f.read()), save=False)
        baustein.save()


def unseed(apps, schema_editor):
    BriefingBaustein = apps.get_model('briefing', 'BriefingBaustein')
    BriefingBaustein.objects.filter(autor__isnull=True, ist_standard=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('briefing', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
