from io import StringIO
from unittest import skipUnless
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.db import connection
from django.test import TestCase

from ..models import (
    AffectationEmployeSuccursale, AnnulationTransaction, Client, CompteurPromotion,
    Employe, Promotion, Succursale, TransactionCafe,
)
from ..permissions import PERMISSION_PROPRIETAIRE, succursales_autorisees


@skipUnless(connection.vendor == "postgresql", "Le jeu V3 cible PostgreSQL.")
class DonneesV3Tests(TestCase):
    def charger(self):
        sortie = StringIO()
        call_command("donnees_v3", password="DemoV3-Tests-2026!", stdout=sortie)
        return sortie.getvalue()

    def test_scenarios_roles_affectations_et_soldes_sans_modifier_existant(self):
        existant = Employe.objects.create_user("compte_a_conserver", password="ancien", is_active=False)
        client_existant = Client.objects.create(nom_complet="Client existant", nombre_cafes_prepayes=7)
        empreinte = existant.password
        noms = list(Succursale.objects.values_list("pk", "nom"))
        sortie = self.charger()
        proprietaire = Employe.objects.get(username="demo_proprietaire")
        self.assertTrue(proprietaire.has_perm(PERMISSION_PROPRIETAIRE))
        self.assertFalse(proprietaire.is_superuser)
        self.assertTrue(proprietaire.check_password("DemoV3-Tests-2026!"))
        self.assertFalse(AffectationEmployeSuccursale.objects.filter(employe=proprietaire).exists())
        self.assertEqual(succursales_autorisees(proprietaire).count(), len(noms) + 3)
        gerant = Employe.objects.get(username="demo_gerant_centre_nord")
        self.assertSetEqual(set(succursales_autorisees(gerant).values_list("nom", flat=True)), {"[Démo V3] Centre", "[Démo V3] Nord"})
        self.assertFalse(Employe.objects.get(username="demo_inactif").is_active)
        self.assertEqual(Employe.objects.filter(username__startswith="demo_").count(), 8)
        self.assertEqual(Promotion.objects.filter(nom__startswith="[Démo V3]").count(), 3)
        self.assertEqual(Promotion.objects.exclude(annulee_le=None).count(), 1)
        self.assertGreaterEqual(AnnulationTransaction.objects.count(), 2)
        self.assertTrue(CompteurPromotion.objects.filter(cafes_gratuits__gt=0).exists())
        camille = Client.objects.get(courriel="demo-v3-3@example.test")
        self.assertEqual((camille.nombre_cafes_prepayes, camille.nombre_cafes_gratuits), (18, 0))
        self.assertEqual(TransactionCafe.objects.filter(client__courriel="demo-v3-5@example.test", annulation__isnull=True).count(), 0)
        for ligne in TransactionCafe.objects.select_related("employe"):
            self.assertTrue(succursales_autorisees(ligne.employe).filter(pk=ligne.succursale_id).exists())
        existant.refresh_from_db()
        client_existant.refresh_from_db()
        self.assertEqual(existant.password, empreinte)
        self.assertFalse(existant.is_active)
        self.assertEqual(client_existant.nombre_cafes_prepayes, 7)
        for pk, nom in noms:
            self.assertEqual(Succursale.objects.get(pk=pk).nom, nom)
        self.assertIn("DemoV3-Tests-2026!", sortie)
        self.assertIn("/succursales/", sortie)

    def test_seconde_execution_refusee_sans_doublon_ni_changement_de_mot_de_passe(self):
        self.charger()
        compte = Employe.objects.get(username="demo_proprietaire")
        empreinte = compte.password
        nombres = (Employe.objects.count(), Client.objects.count(), TransactionCafe.objects.count())
        with self.assertRaisesMessage(CommandError, "existent déjà"):
            self.charger()
        self.assertEqual((Employe.objects.count(), Client.objects.count(), TransactionCafe.objects.count()), nombres)
        compte.refresh_from_db()
        self.assertEqual(compte.password, empreinte)

    def test_collision_avec_compte_existant_refusee_avant_ecriture(self):
        employe = Employe.objects.create_user("demo_barista_sud", password="conserver")
        nombres = (Succursale.objects.count(), Client.objects.count(), Employe.objects.count())
        with self.assertRaisesMessage(CommandError, "existent déjà"):
            self.charger()
        self.assertEqual((Succursale.objects.count(), Client.objects.count(), Employe.objects.count()), nombres)
        employe.refresh_from_db()
        self.assertTrue(employe.check_password("conserver"))

    def test_erreur_de_service_annule_tout_le_chargement(self):
        nombres = (Succursale.objects.count(), Client.objects.count(), Employe.objects.count())
        with patch("CafeDolbeau.management.commands.donnees_v3.ajouter_cafes", side_effect=RuntimeError("échec simulé")):
            with self.assertRaisesMessage(RuntimeError, "échec simulé"):
                self.charger()
        self.assertEqual((Succursale.objects.count(), Client.objects.count(), Employe.objects.count()), nombres)
