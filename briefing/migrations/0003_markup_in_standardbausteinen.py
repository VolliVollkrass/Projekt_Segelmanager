# -*- coding: utf-8 -*-
"""Rüstet die Standard-Bausteine mit Auszeichnungen nach (siehe briefing/markup.py).

Der Startbestand wurde als reiner Fließtext angelegt, bevor es Warnungen,
Hinweise, Merksätze, Listen und Tabellen gab. Diese Migration ersetzt den Text
bei genau den Bausteinen, die seither niemand angefasst hat — bearbeitete
Bausteine bleiben unberührt, damit keine fremde Arbeit überschrieben wird."""
from django.db import migrations


# titel -> neuer Text
TEXTE = {
    "Die wichtigste Regel: jedes Kommando bekommt eine Antwort": (
        "Manche von euch waren schon mehrfach segeln, andere stehen heute zum ersten Mal an Deck. "
        "Unterschiedliche Menschen machen dieselben Dinge unterschiedlich — deshalb legen wir sehr "
        "großen Wert auf Kommunikation.\n\n"
        "Beim Ablegen und beim Anlegen passiert sehr viel gleichzeitig. Ich stehe in dieser Zeit am "
        "Steuer und kann nicht überall gleichzeitig hinschauen. Ich bin darauf angewiesen, dass ich "
        "höre, was an Deck passiert, statt es sehen zu müssen.\n\n"
        "* Auf jedes Kommando folgt eine Bestätigung — laut gesprochen, nicht genickt.\n\n"
        "Erst wenn ich die Bestätigung gehört habe, weiß ich, dass die Aufgabe angekommen und "
        "erledigt ist. Während eines Manövers habe ich das Kommando über alle Vorgänge an Bord; alle "
        "anderen konzentrieren sich in dieser Zeit auf mich und bleiben ansprechbar."
    ),
    "Wenn Rufen nicht mehr reicht: Handzeichen": (
        "Zwischen Vorschiff und Steuerstand liegen mehr als zehn Meter, dazwischen ein laufender Motor "
        "und der Wind. Gerufene Worte gehen dort regelmäßig unter, und zwar genau dann, wenn es eng "
        "wird. Wir benutzen deshalb ein paar wenige, unmissverständliche Handzeichen.\n\n"
        "| Zeichen | Bedeutung |\n"
        "| Daumen hoch | Verstanden, erledigt, alles in Ordnung |\n"
        "| Flache Hand, ruhig auf und ab | Langsamer — wir sind zu schnell |\n"
        "| Beide Hände gekreuzt über Kopf | Stopp. Sofort anhalten |\n"
        "| Arm ausgestreckt in eine Richtung | Dorthin sollen wir fahren |\n"
        "| Hände zeigen einen Abstand | So viel Platz ist noch |\n"
        "| Faust | Halt so, wie es jetzt ist |\n\n"
        "> Wer ein Zeichen gibt, schaut den anderen dabei an. Sonst kommt es nicht an."
    ),
    "Rettungsweste und Lifebelt": (
        "Jede und jeder bekommt eine eigene Rettungsweste, die auf die eigene Körpergröße eingestellt "
        "wird.\n\n"
        "Angelegt wird sie:\n"
        "- bei Dunkelheit\n"
        "- bei Welle oder mehr Wind\n"
        "- bei allen Manövern an Deck\n"
        "- immer dann, wenn du dich damit wohler fühlst\n\n"
        "> Für den letzten Punkt braucht niemand eine Begründung.\n\n"
        "Bei Nachtfahrten und bei rauer See leinen wir uns mit dem Lifebelt am Strecktau an, bevor wir "
        "das Cockpit verlassen.\n\n"
        "* Eine Hand für das Schiff, eine Hand für dich.\n\n"
        "Bewegt euch möglichst auf der Luv-Seite und haltet euch immer an etwas Festem fest, nie an "
        "einer Leine."
    ),
    "Mann über Bord": (
        "! Wer den Blickkontakt zur Person im Wasser verliert, findet sie bei Welle oft nicht wieder.\n\n"
        "Wenn jemand über Bord geht, läuft es immer in dieser Reihenfolge:\n\n"
        "- Laut rufen: „Mann über Bord!“ — so laut, dass es alle hören.\n"
        "- Eine Person zeigt ununterbrochen mit ausgestrecktem Arm auf die Person im Wasser und macht "
        "ab sofort nichts anderes mehr.\n"
        "- Rettungsring oder Rettungsboje sofort hinterherwerfen, auch als Positionsmarkierung.\n"
        "- MOB-Taste am Plotter drücken, damit die Position gespeichert ist.\n"
        "- Ich übernehme das Manöver. Alle anderen bleiben auf ihren Plätzen und warten auf Anweisungen."
    ),
    "Feuer, Gas und Notruf": (
        "! Der Gashahn wird nach jedem Kochen geschlossen. Gas ist schwerer als Luft und sammelt sich "
        "unten im Boot.\n\n"
        "Wir schauen uns gemeinsam an, wo Feuerlöscher, Löschdecke und Bordapotheke liegen; wichtig ist, "
        "sich die Orte zu merken, nicht nur die Namen. Am Funkgerät hängt eine Mayday-Karte mit dem "
        "Wortlaut des Notrufs und den Bootsdaten, die auch ohne Funkschein abzulesen ist.\n\n"
        "> Wer Medikamente nimmt, Allergien hat oder eine im Notfall wichtige Vorerkrankung, sagt das "
        "bitte unter vier Augen dem Skipper."
    ),
    "Der Sicherheits-Rundgang": (
        "Diese Liste gehen wir gemeinsam ab, bevor wir zum ersten Mal ablegen:\n\n"
        "- Feuerlöscher\n"
        "- Löschdecke\n"
        "- Bordapotheke\n"
        "- Rettungsinsel\n"
        "- Hauptgashahn\n"
        "- Seeventile und Lenzpumpe\n"
        "- Rettungsringe und Rettungsboje\n"
        "- Signalmittel\n"
        "- Werkzeug und Bolzenschneider\n"
        "- Notpinne\n\n"
        "> Jede und jeder fasst die Ausrüstung einmal selbst an — was man einmal in der Hand hatte, "
        "findet man auch im Dunkeln wieder."
    ),
    "Die drei Knoten, die wir brauchen": (
        "Drei Knoten decken praktisch alles ab, was wir in den nächsten Tagen brauchen, und die üben "
        "wir in Ruhe im Cockpit.\n\n"
        "- Palstek — feste Schlaufe, die sich unter Last nicht zuzieht und trotzdem wieder aufgeht. "
        "Für Leinen um Poller oder Ring an Land.\n"
        "- Webleinstek — schnell gelegt und gelöst, gut für Fender an der Reling.\n"
        "- Klampe belegen — ein Rundtörn um die Klampe, dann zwei bis drei Kreuzschläge.\n\n"
        "! Bei Leinen, die wir schnell lösen müssen, kommt kein Kopfschlag obendrauf — sonst geht sie "
        "unter Last nicht mehr auf."
    ),
    "Fünf Wörter, die wir nicht verwechseln dürfen": (
        "| Wort | Bedeutung |\n"
        "| Fieren | Kontrolliert nachgeben. Die Leine bleibt in der Hand. |\n"
        "| Losmachen | Die Leine ist frei. Danach hält sie gar nichts mehr. |\n"
        "| Dichtholen | Die Leine straff durchholen. |\n"
        "| Belegen | Auf einer Klampe festmachen, sodass sie ohne Hand hält. |\n"
        "| Aufschießen | Ordentlich zu Buchten aufnehmen. |\n\n"
        "! Wenn ich „fieren“ sage und du machst stattdessen los, verliert das Boot in diesem Moment "
        "seinen letzten Halt.\n\n"
        "> Im Zweifelsfall lieber einmal zu viel nachfragen als eine Leine zu früh freigeben."
    ),
    "Aufschießen ohne Dreher, und was an Deck wehtut": (
        "Eine Leine, die beim Aufschießen Drall bekommen hat, verhakt sich später genau dann, wenn es "
        "schnell gehen muss. Der Trick: Bei jedem Schlag, den du aufnimmst, gibst du der Leine mit den "
        "Fingern eine kleine halbe Drehung mit, dann legt sich jede Bucht flach auf die vorherige.\n\n"
        "! Nie mit Hand oder Fingern in eine Schlaufe greifen, die unter Last geraten kann.\n"
        "! Nie zwischen Leine und Klampe oder Poller stehen.\n"
        "! Nie eine Leine um die Hand wickeln, um besser ziehen zu können."
    ),
    "Zweimal anfassen, dann melden": (
        "Bevor du meldest, dass eine Leine los ist, fass sie ein zweites Mal an und verfolge sie mit "
        "der Hand bis zum Ende. Erst dann ist sicher, dass sie wirklich frei ist und sich nirgends mehr "
        "eingehakt hat.\n\n"
        "! Eine Leine, die noch irgendwo hängt, während wir schon Fahrt aufnehmen, ist eines der "
        "ärgerlichsten Probleme überhaupt."
    ),
    "Die Marineros meinen es gut — aber sie kennen unseren Plan nicht": (
        "In den meisten Häfen kommen Hafenmitarbeiter an den Steg und machen laute Ansagen, oft mit "
        "großen Gesten. Diese Ansagen gelten dem Schiffsführer, nicht der Crew — sie sehen den Steg, "
        "aber nicht, was das Boot gerade unter Wasser macht.\n\n"
        "* Der Marinero sagt es dem Skipper, der Skipper sagt es der Crew. Erst dann wird geworfen.\n\n"
        "Ein abgebrochenes Anlegemanöver ist kein misslungenes, sondern ein souveränes — wir haben Zeit, "
        "im Zweifelsfall drehen wir eine Runde und fahren neu an."
    ),
    "Die Leine gehört nicht ins Wasser": (
        "Unter dem Heck sitzt ein Propeller, der eine erhebliche Menge Wasser ansaugt — und alles, was "
        "darin schwimmt, wird mitgezogen. Eine Leine, die ins Wasser fällt, wickelt sich in Sekunden um "
        "die Welle, besonders kritisch beim Rückwärtsfahren am Dock.\n\n"
        "! Ein Boot ohne Antrieb ist im Hafen manövrierunfähig.\n\n"
        "Wenn es doch passiert:\n"
        "- Sofort und laut melden, nicht erst versuchen, sie unauffällig herauszuziehen.\n"
        "- Der Antrieb bleibt neutral, bis die Leine vollständig wieder an Deck ist.\n"
        "- Danach machen wir weiter, als wäre nichts gewesen.\n\n"
        "Eine Leine im Wasser ist erst einmal schlecht, aber harmlos, solange sie gemeldet wird — "
        "gefährlich wird sie nur durch Schweigen.\n\n"
        "* Ein gemeldeter Fehler ist ein gelöster Fehler."
    ),
    "Die Halse — Vorsicht beim Großbaum": (
        "Bei der Halse geht das Heck durch den Wind, und der Großbaum wandert mit Schwung von einer "
        "Seite zur anderen — genau auf Kopfhöhe.\n\n"
        "! Köpfe runter, Hände weg vom Baum, niemand steht in seiner Bahn.\n\n"
        "Die Halse wird immer laut angesagt, bevor sie beginnt, und wir fahren sie bewusst langsam und "
        "kontrolliert, mit vorher dichtgeholter Großschot, damit der Baum nicht durchschlagen kann."
    ),
    "Die Seetoilette": (
        "! In die Toilette darf ausschließlich das, was vorher durch den menschlichen Körper gegangen "
        "ist. Papier gehört in den Eimer daneben, ebenso Hygieneartikel und Feuchttücher.\n\n"
        "Die Pumpe und die Schläuche sind eng — eine verstopfte Bordtoilette ist der unbeliebteste Job "
        "an Bord.\n\n"
        "> Der Skipper zeigt jeder und jedem einmal persönlich, wie gepumpt wird. Lieber ein zweites "
        "Mal nachfragen als raten."
    ),
    "Die zehn Sätze für den Törn": (
        "- Kommunikation ist alles — auf jedes Kommando folgt eine laut gesprochene Bestätigung.\n"
        "- Kurz heißt nicht unfreundlich.\n"
        "- Nachfragen ist erwünscht — „Nochmal!“ ist ein vollwertiges Kommando.\n"
        "- Steuerbord ist grün, die langen Wörter gehören zusammen.\n"
        "- Fieren ist nicht losmachen.\n"
        "- Erst auf Kommando werfen, auch wenn der Marinero schon ruft.\n"
        "- Die Leine gehört nicht ins Wasser — und wenn doch, sofort melden.\n"
        "- Wir haben Zeit; ein abgebrochenes Manöver ist ein souveränes.\n"
        "- Eine Hand für das Schiff, die andere für dich.\n"
        "- Ein gemeldeter Fehler ist ein gelöster Fehler."
    ),
}


def markup_nachruesten(apps, schema_editor):
    BriefingBaustein = apps.get_model("briefing", "BriefingBaustein")
    for titel, text in TEXTE.items():
        # Nur unveränderte System-Bausteine anfassen — was ein Skipper schon
        # bearbeitet hat, bleibt seins.
        BriefingBaustein.objects.filter(
            titel=titel, ist_standard=True,
            autor__isnull=True, zuletzt_bearbeitet_von__isnull=True,
        ).update(text=text)


def rueckwaerts(apps, schema_editor):
    # Der ursprüngliche Fließtext steht in 0002; ein Rückbau würde ihn nur
    # erneut überschreiben. Bewusst ein No-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("briefing", "0002_seed_standardbausteine"),
    ]

    operations = [
        migrations.RunPython(markup_nachruesten, rueckwaerts),
    ]
