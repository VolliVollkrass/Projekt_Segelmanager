"""Zahlungswege (PayPal, IBAN, Wero): Prüfen, Normalisieren, Anzeigen.

Gespeichert wird immer die normalisierte Form — die IBAN ohne Leerzeichen und
in Großbuchstaben, PayPal entweder als reiner PayPal.Me-Name oder als
E-Mail-Adresse. Die Anzeige (Vierergruppen, Link) wird erst beim Rendern gebaut.
"""
import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

# Länder-Präfix, zwei Prüfziffern, Kontokennung — die Länge variiert je Land
# (DE 22, NL 18, MT 31 …); die Prüfsumme fängt Tippfehler zuverlässig ab.
_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
_PAYPAL_URL_RE = re.compile(r"^(?:https?://)?(?:www\.)?paypal\.me/", re.IGNORECASE)
_PAYPAL_NAME_RE = re.compile(r"^[A-Za-z0-9]{1,50}$")
_TELEFON_RE = re.compile(r"^\+?[\d\s/()-]{6,}$")


def normalisiere_iban(wert):
    """Leerzeichen raus, Großbuchstaben. Leerer Wert bleibt leer."""
    iban = re.sub(r"\s+", "", wert or "").upper()
    if not iban:
        return ""
    if not _IBAN_RE.match(iban):
        raise ValidationError("Das sieht nicht nach einer IBAN aus (z. B. DE89 3704 0044 0532 0130 00).")
    # ISO 13616: die ersten vier Zeichen ans Ende, Buchstaben → Zahlen (A=10 …),
    # das Ganze modulo 97 muss 1 ergeben.
    umgestellt = iban[4:] + iban[:4]
    ziffern = "".join(str(int(z, 36)) for z in umgestellt)
    if int(ziffern) % 97 != 1:
        raise ValidationError("Die IBAN-Prüfziffer stimmt nicht — bitte auf Tippfehler prüfen.")
    return iban


def formatiere_iban(iban):
    """DE89370400440532013000 → DE89 3704 0044 0532 0130 00"""
    return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))


def _ist_email(wert):
    try:
        validate_email(wert)
    except ValidationError:
        return False
    return True


def normalisiere_paypal(wert):
    """Nimmt PayPal.Me-Link, @Name, Namen oder E-Mail entgegen.

    Rückgabe: E-Mail-Adresse unverändert, sonst der reine PayPal.Me-Name.
    """
    wert = (wert or "").strip()
    if not wert:
        return ""
    if _ist_email(wert):
        return wert
    name = _PAYPAL_URL_RE.sub("", wert).lstrip("@").strip("/")
    # Ein kopierter Link kann schon einen Betrag enthalten (…/meinname/20EUR)
    name = name.split("/")[0].split("?")[0]
    if not _PAYPAL_NAME_RE.match(name):
        raise ValidationError(
            "Bitte deinen PayPal.Me-Namen (z. B. paypal.me/meinname) oder deine PayPal-E-Mail angeben."
        )
    return name


def normalisiere_wero(wert):
    """Wero läuft über Handynummer oder E-Mail — beides wird akzeptiert."""
    wert = (wert or "").strip()
    if not wert:
        return ""
    if _ist_email(wert) or _TELEFON_RE.match(wert):
        return wert
    raise ValidationError("Bitte die Handynummer oder E-Mail-Adresse angeben, unter der du Wero nutzt.")


def paypal_link(paypal, betrag=None):
    """PayPal.Me-Link, auf Wunsch mit vorausgefülltem Betrag.

    Für eine reine E-Mail-Adresse gibt es keinen solchen Link → None.
    """
    if not paypal or _ist_email(paypal):
        return None
    link = f"https://paypal.me/{paypal}"
    if betrag is not None and Decimal(betrag) > 0:
        link += f"/{Decimal(betrag):.2f}EUR"
    return link


def zahlungswege(user, betrag=None):
    """Aufbereitete Zahlungswege eines Users für die Anzeige.

    Rückgabe: Liste von Dicts {art, label, wert, link}; leer, wenn nichts
    hinterlegt ist.
    """
    wege = []
    if user.zahlung_paypal:
        wege.append({
            "art": "paypal",
            "label": "PayPal",
            "wert": user.zahlung_paypal if _ist_email(user.zahlung_paypal)
                    else f"paypal.me/{user.zahlung_paypal}",
            "link": paypal_link(user.zahlung_paypal, betrag),
        })
    if user.zahlung_iban:
        wege.append({
            "art": "iban",
            "label": "IBAN",
            "wert": formatiere_iban(user.zahlung_iban),
            "inhaber": user.zahlung_kontoinhaber
                       or f"{user.first_name} {user.last_name}".strip(),
            "link": None,
        })
    if user.zahlung_wero:
        wege.append({
            "art": "wero",
            "label": "Wero",
            "wert": user.zahlung_wero,
            "link": None,
        })
    return wege
