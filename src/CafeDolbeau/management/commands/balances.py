import csv

from django.core.management.base import BaseCommand, CommandError

from ...models import Client, ParametresCafe, Succursale


class Command(BaseCommand):
    help = "Affiche les soldes des clients au format CSV, sans les modifier."

    def add_arguments(self, parser):
        parser.add_argument(
            "--succursale", type=int, action="append", dest="succursale_ids", metavar="ID",
            help="Limiter aux clients ayant des transactions dans cette succursale. Répétable ; les soldes restent globaux.",
        )

    def handle(self, *args, **options):
        clients = Client.objects.exclude(pk=Client.ID_SUPPRIME).order_by("pk")
        identifiants = options["succursale_ids"]
        if identifiants is not None:
            identifiants = set(identifiants)
            existants = set(Succursale.objects.filter(pk__in=identifiants).values_list("pk", flat=True))
            inconnus = identifiants - existants
            if inconnus:
                raise CommandError("Succursale(s) inexistante(s) : " + ", ".join(map(str, sorted(inconnus))))
            clients = clients.filter(transactions_cafe__succursale_id__in=identifiants).distinct()
        parametres = ParametresCafe.objects.get(pk=1)
        seuil = parametres.seuil_gratuite_actif
        writer = csv.writer(self.stdout, lineterminator="\n")
        writer.writerow((
            "id", "client", "cafes_achetes", "etampes",
            "recompenses_en_reserve", "cafes_prepayes",
        ))
        for identifiant, nom, achetes, gratuits, prepayes in clients.values_list(
            "pk", "nom_complet", "nombre_cafes_achetes",
            "nombre_cafes_gratuits", "nombre_cafes_prepayes",
        ).iterator():
            writer.writerow((identifiant, nom, achetes, achetes % seuil, gratuits, prepayes))
