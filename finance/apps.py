from django.apps import AppConfig


class FinanceConfig(AppConfig):
    name = 'finance'

    def ready(self):
        # HEIC/HEIF-Unterstützung für iPhone-Fotos (Belege) registrieren.
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except Exception:
            pass
