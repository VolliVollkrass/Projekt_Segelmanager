from PIL import Image, ImageOps
from io import BytesIO
from django.core.files.base import ContentFile

MAX_SIZE = (1200, 1200)
QUALITY = 85


def optimize_image(uploaded_image):
    """
    Optimiert Bilder für Web:
    - EXIF Rotation korrigieren
    - maximale Auflösung begrenzen
    - JPEG Kompression
    """

    img = Image.open(uploaded_image)

    # EXIF Rotation fix
    img = ImageOps.exif_transpose(img)

    # Farbmodus korrigieren
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Größe begrenzen
    img.thumbnail(MAX_SIZE, Image.Resampling.LANCZOS)

    buffer = BytesIO()

    img.save(
        buffer,
        format="JPEG",
        quality=QUALITY,
        optimize=True
    )

    return ContentFile(buffer.getvalue())