import requests
from datetime import date


def hole_tageslosung(datum=None):
    """Holt die Tageslosung für das gegebene Datum (default: heute).
    Gibt dict mit losungstext, losungsvers, lehrtext, lehrvers zurück oder None bei Fehler."""
    if datum is None:
        datum = date.today()

    datum_str = datum.strftime('%Y-%m-%d')

    try:
        resp = requests.get(
            f'https://losungen.de/api/{datum_str}/',
            timeout=5,
            headers={'Accept': 'application/json'},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            'losungsvers': data.get('Losungsvers', ''),
            'losungstext': data.get('Losungstext', ''),
            'lehrvers': data.get('Lehrvers', ''),
            'lehrtext': data.get('Lehrtext', ''),
            'datum': datum_str,
        }
    except Exception:
        return None
