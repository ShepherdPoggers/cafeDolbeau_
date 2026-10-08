from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class CafedolbeauConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'CafeDolbeau'


class AdministrationCafeConfig(AdminConfig):
    default_site = 'CafeDolbeau.admin_site.AdministrationCafe'
