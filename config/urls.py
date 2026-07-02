
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

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
    path('schema-viewer/', include('schema_viewer.urls')),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]