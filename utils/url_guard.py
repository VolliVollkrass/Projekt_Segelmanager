"""SSRF-Schutz für serverseitige HTTP-Requests auf nutzergelieferte URLs.

Verhindert, dass ein eingeloggter Nutzer den Server dazu bringt, interne
Adressen abzurufen (Cloud-Metadaten 169.254.169.254, localhost, interne
Docker-Services). Genutzt vom KI-Rezept-Import.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import requests


class UnsafeUrlError(ValueError):
    """URL zeigt auf ein nicht erlaubtes (internes/privates) Ziel."""


def _ip_ist_erlaubt(ip_str):
    ip = ipaddress.ip_address(ip_str)
    # Alles Nicht-Öffentliche blocken: privat, loopback, link-local
    # (inkl. 169.254.169.254 Metadaten), reserviert, multicast, unspecified.
    return ip.is_global and not ip.is_multicast


def _pruefe_host(hostname):
    """Löst den Host auf und stellt sicher, dass KEINE Adresse intern ist."""
    if not hostname:
        raise UnsafeUrlError("Kein Hostname in der URL.")
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Hostname nicht auflösbar: {hostname}") from exc
    for info in infos:
        ip_str = info[4][0]
        if not _ip_ist_erlaubt(ip_str):
            raise UnsafeUrlError(f"URL zeigt auf eine interne Adresse ({ip_str}).")


def _pruefe_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError("Nur http/https ist erlaubt.")
    _pruefe_host(parsed.hostname)


def safe_get(url, *, timeout=10, max_redirects=5, headers=None):
    """GET auf eine nutzergelieferte URL mit SSRF-Schutz.

    Prüft Schema und aufgelöste IPs vor jedem Request und folgt Redirects
    manuell, damit auch das Redirect-Ziel geprüft wird.

    Wirft UnsafeUrlError bei unerlaubtem Ziel, requests-Exceptions bei
    Netzwerkfehlern.
    """
    current = url
    for _ in range(max_redirects + 1):
        _pruefe_url(current)
        resp = requests.get(
            current,
            timeout=timeout,
            headers=headers,
            allow_redirects=False,
        )
        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("Location")
            if not location:
                return resp
            current = requests.compat.urljoin(current, location)
            continue
        return resp
    raise UnsafeUrlError("Zu viele Weiterleitungen.")
