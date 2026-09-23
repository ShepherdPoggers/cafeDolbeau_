from django.contrib import admin

from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("nom_complet", "telephone", "courriel", "nombre_cafes_achetes")
    search_fields = ("nom_complet", "telephone", "courriel")
