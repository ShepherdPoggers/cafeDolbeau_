from django.contrib import admin

from .models import Client


admin.site.site_header = "Administration Café Dolbeau"
admin.site.site_title = "Administration Café Dolbeau"


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("nom_complet", "telephone", "courriel", "nombre_cafes_achetes", "nombre_cafes_prepayes")
    search_fields = ("nom_complet", "telephone", "courriel")
