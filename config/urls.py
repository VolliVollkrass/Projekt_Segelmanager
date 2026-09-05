
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings

from utils.protected_media import protected_media_serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('home.urls')),
    path('accounts/', include('accounts.urls')),
    path('toern/', include('toern.urls')),
    path('boote/', include('boote.urls')),
    path('kochbuch/', include('rezepte.urls')),
    path('segelwissen/', include('segelwissen.urls')),
    path('andacht/', include('andacht.urls')),
    path('finance/', include('finance.urls')),
    # Sensible Uploads (Lizenzen, Belege, Logbücher, Schadensfotos) werden hier
    # autorisiert; öffentliche Medien wie bisher direkt ausgeliefert.
    re_path(r'^media/(?P<path>.*)$', protected_media_serve),
]

# schema_viewer zeigt die komplette DB-Struktur und hat KEINE Auth — nur lokal.
# Die App ist ohnehin nur bei DEBUG in INSTALLED_APPS; die Route muss ebenso
# hinter DEBUG liegen, sonst ist /schema-viewer/schema/ in Production offen.
if settings.DEBUG:
    urlpatterns += [path('schema-viewer/', include('schema_viewer.urls'))]