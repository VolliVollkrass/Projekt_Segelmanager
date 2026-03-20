from django.contrib import admin
from .models import Einkaufspunkt, Gegenstand, Mitbringer, PersönlicherGegenstand

admin.site.register(Einkaufspunkt)
admin.site.register(Gegenstand)
admin.site.register(Mitbringer)
admin.site.register(PersönlicherGegenstand)