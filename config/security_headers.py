"""Content-Security-Policy (und ergänzende Header) für alle Responses.

Bewusst mit 'unsafe-inline' für script/style, weil die Templates viele
Inline-<script>-Blöcke und style="…"-Attribute nutzen (ein Umstieg auf
Nonces/Hashes wäre ein größerer Umbau). Der Gewinn liegt trotzdem in:
- object-src 'none' + base-uri 'self' + frame-ancestors 'none' (Clickjacking,
  base-tag-Injection, Plugin-Objekte)
- Einschränkung aller Skript-/Style-Quellen auf 'self' (keine CDNs).

Externe Ressourcen: keine. cropperjs (CSS+JS) wird lokal aus static/*/vendor/
ausgeliefert – DSGVO-konform, kein Drittanbieter-Request beim Seitenaufruf.
"""

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    # blob: für cropperjs (liest das hochgeladene Bild per XHR zur EXIF-Auswertung)
    "connect-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

PERMISSIONS_POLICY = "geolocation=(), microphone=(), camera=()"


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", CSP)
        response.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        return response
