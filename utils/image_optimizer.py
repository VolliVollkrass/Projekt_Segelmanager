import logging

from PIL import Image, ImageOps
from io import BytesIO
from django.core.files.base import ContentFile
from pillow_heif import register_heif_opener

logger = logging.getLogger(__name__)

# 👉 HEIC Support aktivieren (NEU)
register_heif_opener()

MAX_SIZE = (1200, 1200)
QUALITY = 85


def optimize_image(uploaded_image):
    """
    Optimiert Bilder für Web:
    - HEIC Support (iPhone)
    - EXIF Rotation korrigieren
    - maximale Auflösung begrenzen
    - JPEG Kompression
    """

    try:
        img = Image.open(uploaded_image)

        # 👉 EXIF Rotation fix (dein Code bleibt)
        img = ImageOps.exif_transpose(img)

        # 👉 Farbmodus korrigieren (leicht erweitert)
        if img.mode not in ("RGB",):
            img = img.convert("RGB")

        # 👉 Größe begrenzen (dein Code bleibt)
        img.thumbnail(MAX_SIZE, Image.Resampling.LANCZOS)

        buffer = BytesIO()

        # 👉 IMMER als JPG speichern (dein Verhalten bleibt)
        img.save(
            buffer,
            format="JPEG",
            quality=QUALITY,
            optimize=True
        )

        return ContentFile(buffer.getvalue())

    except Exception as e:
        logger.exception("Image Optimizer Fehler: %s", e)
        return uploaded_image