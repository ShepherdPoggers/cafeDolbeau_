import csv
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from ..models import Client, ParametresCafe


class BalancesTests(TestCase):
    def soldes(self):
        output = StringIO()
        call_command("balances", stdout=output)
        return list(csv.DictReader(StringIO(output.getvalue())))

    def test_affiche_les_compteurs_et_les_etampes_sans_modifier_les_clients(self):
        personne = Client.objects.create(
            nom_complet='Roy, "Camille"', telephone="418-555-0101",
            nombre_cafes_achetes=37, nombre_cafes_gratuits=4, nombre_cafes_prepayes=17,
        )
        avant = list(Client.objects.values())
        self.assertEqual(self.soldes(), [{
            "id": str(personne.pk), "client": 'Roy, "Camille"', "cafes_achetes": "37",
            "etampes": "7", "recompenses_en_reserve": "4", "cafes_prepayes": "17",
        }])
        self.assertEqual(list(Client.objects.values()), avant)

    def test_inclut_les_clients_inactifs_et_exclut_le_client_fictif(self):
        Client.objects.create(pk=-1, nom_complet="Client supprimé", est_actif=False)
        personne = Client.objects.create(nom_complet="Source", telephone="111", est_actif=False)
        self.assertEqual([ligne["id"] for ligne in self.soldes()], [str(personne.pk)])

    def test_utilise_le_seuil_en_vigueur_pour_les_etampes(self):
        Client.objects.create(nom_complet="Alice", telephone="111", nombre_cafes_achetes=37)
        parametres = ParametresCafe.objects.get(pk=1)
        parametres.cafes_pour_gratuite = 5
        parametres.cafes_pour_gratuite_precedent = 10
        parametres.date_application = timezone.localdate() + timedelta(days=1)
        parametres.save()
        self.assertEqual(self.soldes()[0]["etampes"], "7")
        parametres.date_application = timezone.localdate()
        parametres.save()
        self.assertEqual(self.soldes()[0]["etampes"], "2")

    def test_base_vide_affiche_uniquement_les_entetes(self):
        output = StringIO()
        call_command("balances", stdout=output)
        self.assertEqual(
            output.getvalue(),
            "id,client,cafes_achetes,etampes,recompenses_en_reserve,cafes_prepayes\n",
        )
