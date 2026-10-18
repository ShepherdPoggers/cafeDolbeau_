import csv

from django.core.management.base import BaseCommand

from ...models import Client, ParametresCafe


class Command(BaseCommand):
    help = "Affiche les soldes des clients au format CSV, sans les modifier."

    def handle(self, *args, **options):
        parametres = ParametresCafe.objects.get(pk=1)
        seuil = parametres.seuil_gratuite_actif
        writer = csv.writer(self.stdout, lineterminator="\n")
        writer.writerow((
            "id", "client", "cafes_achetes", "etampes",
            "recompenses_en_reserve", "cafes_prepayes",
        ))
        clients = Client.objects.exclude(pk=Client.ID_SUPPRIME).order_by("pk")
        for identifiant, nom, achetes, gratuits, prepayes in clients.values_list(
            "pk", "nom_complet", "nombre_cafes_achetes",
            "nombre_cafes_gratuits", "nombre_cafes_prepayes",
        ).iterator():
            writer.writerow((identifiant, nom, achetes, achetes % seuil, gratuits, prepayes))
