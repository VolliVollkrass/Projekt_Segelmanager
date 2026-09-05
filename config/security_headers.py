"""Content-Security-Policy (und ergänzende Header) für alle Responses.

Bewusst mit 'unsafe-inline' für script/style, weil die Templates viele
Inline-<script>-Blöcke und style="…"-Attribute nutzen (ein Umstieg auf
Nonces/Hashes wäre ein größerer Umbau). Der Gewinn liegt trotzdem in:
- object-src 'none' + base-uri 'self' + frame-ancestors 'none' (Clickjacking,
  base-tag-Injection, Plugin-Objekte)
- Einschränkung externer Skript-/Style-Quellen auf self + unpkg (cropperjs).

Externe Ressourcen aktuell: cropperjs (CSS+JS) von https://unpkg.com.
"""

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://unpkg.com",
    "style-src 'self' 'unsafe-inline' https://unpkg.com",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
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
