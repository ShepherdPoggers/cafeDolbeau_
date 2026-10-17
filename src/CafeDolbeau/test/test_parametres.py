from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from ..models import AnnulationTransaction, Client, Employe, ParametresCafe, TransactionCafe
from ..services import ajouter_cafes, annuler_operation


class ParametresCafeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gerant = Employe.objects.create_user("gerant-parametres")
        cls.gerant.groups.add(Group.objects.get(name="Gérant"))
        cls.barista = Employe.objects.create_user("barista-parametres")
        cls.barista.groups.add(Group.objects.get(name="Barista"))
        cls.personne = Client.objects.create(nom_complet="Camille", telephone="418 555-1111")

    def setUp(self):
        self.client.force_login(self.gerant)
        self.url = reverse("admin:CafeDolbeau_parametrescafe_change", args=[1])

    def regler(self, seuil):
        ParametresCafe.objects.filter(pk=1).update(cafes_pour_gratuite=seuil)

    def modifier_regle(self, seuil, date_application=None):
        return self.client.post(self.url, {
            "cafes_pour_gratuite": seuil,
            "date_application": date_application if date_application is not None else timezone.localdate().isoformat(),
            "_save": "Enregistrer",
        })

    def achat(self, quantite, type_cafe="achat"):
        return ajouter_cafes(self.personne, quantite, type_cafe, employe=self.barista)

    def test_configuration_initialisee_a_dix_et_unique(self):
        self.assertEqual(ParametresCafe.objects.count(), 1)
        self.assertEqual(ParametresCafe.objects.get(pk=1).cafes_pour_gratuite, 10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ParametresCafe.objects.create(pk=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ParametresCafe.objects.filter(pk=1).update(cafes_pour_gratuite=0)

    def test_chargement_recree_le_reglage_manquant(self):
        ParametresCafe.objects.all().delete()
        self.assertEqual(ParametresCafe.charger().cafes_pour_gratuite, 10)
        self.assertEqual(ParametresCafe.objects.count(), 1)

    def test_admin_gerant_peut_modifier_et_valeur_prend_effet_immediatement(self):
        self.assertFalse(self.gerant.is_staff)
        self.assertContains(self.client.get(reverse("admin:index")), "Paramètres du café")
        self.assertContains(self.client.get(self.url), "Nombre de cafés achetés pour un café gratuit")
        response = self.modifier_regle(5)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ParametresCafe.charger().cafes_pour_gratuite, 5)
        self.achat(5)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 1)
        self.modifier_regle(3)
        self.achat(1)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 2)

    def test_admin_refuse_les_valeurs_invalides(self):
        for valeur in ("", "0", "-1", "1.5", "abc", "2147483648"):
            with self.subTest(valeur=valeur):
                response = self.modifier_regle(valeur)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["adminform"].form.errors)
                self.assertEqual(ParametresCafe.charger().cafes_pour_gratuite, 10)
        for valeur in (0, -1, 2147483648):
            with self.assertRaises(ValidationError):
                ParametresCafe(pk=1, cafes_pour_gratuite=valeur).full_clean()

    def test_admin_exige_une_date_valide(self):
        for valeur in ("", "invalide", "2026-02-30"):
            with self.subTest(date=valeur):
                response = self.modifier_regle(5, valeur)
                self.assertEqual(response.status_code, 200)
                self.assertIn("date_application", response.context["adminform"].form.errors)
                self.assertEqual(ParametresCafe.charger().cafes_pour_gratuite, 10)
        response = self.client.post(self.url, {"cafes_pour_gratuite": 5, "_save": "Enregistrer"})
        self.assertIn("date_application", response.context["adminform"].form.errors)

    def test_regle_future_utilise_ancien_seuil_avant_et_nouveau_des_la_date(self):
        date_application = timezone.localdate() + timedelta(days=1)
        response = self.modifier_regle(5, date_application.isoformat())
        self.assertEqual(response.status_code, 302)
        parametres = ParametresCafe.charger()
        self.assertEqual(parametres.date_application, date_application)
        self.assertEqual(parametres.seuil_gratuite_actif, 10)
        response = self.client.get(self.url)
        self.assertContains(response, "Seuil actuellement en vigueur")
        self.assertContains(response, 'type="date"')
        self.assertContains(response, f'value="{date_application.isoformat()}"')
        self.achat(4)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 0)
        with patch("django.utils.timezone.localdate", return_value=date_application):
            self.assertEqual(parametres.seuil_gratuite_actif, 5)
            self.achat(1)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 1)

    def test_bascule_a_minuit_heure_du_quebec(self):
        avant = datetime(2026, 10, 18, 3, 59, 59, tzinfo=UTC)
        apres = datetime(2026, 10, 18, 4, 0, tzinfo=UTC)
        with timezone.override("America/Toronto"), patch("django.utils.timezone.now", return_value=avant):
            self.assertEqual(self.modifier_regle(5, "2026-10-18").status_code, 302)
            self.achat(9)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 0)
        with timezone.override("America/Toronto"), patch("django.utils.timezone.now", return_value=apres):
            self.achat(1)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 1)

    def test_remplacer_une_planification_conserve_la_regle_en_vigueur(self):
        demain = timezone.localdate() + timedelta(days=1)
        plus_tard = demain + timedelta(days=1)
        self.assertEqual(self.modifier_regle(7).status_code, 302)
        self.assertEqual(self.modifier_regle(5, demain.isoformat()).status_code, 302)
        self.assertEqual(self.modifier_regle(3, plus_tard.isoformat()).status_code, 302)
        parametres = ParametresCafe.charger()
        self.assertEqual(parametres.seuil_gratuite_actif, 7)
        with patch("django.utils.timezone.localdate", return_value=demain):
            self.assertEqual(parametres.seuil_gratuite_actif, 7)
            self.achat(6)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 0)
        with patch("django.utils.timezone.localdate", return_value=plus_tard):
            self.achat(3)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 1)

    def test_nouvelle_planification_apres_activation_conserve_le_seuil_active(self):
        demain = timezone.localdate() + timedelta(days=1)
        plus_tard = demain + timedelta(days=1)
        self.assertEqual(self.modifier_regle(5, demain.isoformat()).status_code, 302)
        with patch("django.utils.timezone.localdate", return_value=demain):
            self.assertEqual(self.modifier_regle(3, plus_tard.isoformat()).status_code, 302)
            self.assertEqual(ParametresCafe.charger().seuil_gratuite_actif, 5)
            self.achat(5)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 1)
        with patch("django.utils.timezone.localdate", return_value=plus_tard):
            self.achat(1)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 2)

    def test_date_passee_applique_la_regle_aux_prochains_achats(self):
        hier = timezone.localdate() - timedelta(days=1)
        self.assertEqual(self.modifier_regle(5, hier.isoformat()).status_code, 302)
        self.assertEqual(ParametresCafe.charger().seuil_gratuite_actif, 5)
        self.achat(5)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 1)

    def test_admin_barista_anonyme_ajout_et_suppression_interdits(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.barista)
        self.assertEqual(self.client.get(self.url, follow=True).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"cafes_pour_gratuite": 1}, follow=True).status_code, 403)
        self.client.force_login(self.gerant)
        self.assertEqual(self.client.get(reverse("admin:CafeDolbeau_parametrescafe_add")).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:CafeDolbeau_parametrescafe_delete", args=[1]), {"post": "yes"}).status_code, 403)
        self.assertEqual(ParametresCafe.charger().cafes_pour_gratuite, 10)

    def test_franchissement_de_plusieurs_seuils_et_effets_enregistres(self):
        self.regler(5)
        Client.objects.filter(pk=self.personne.pk).update(nombre_cafes_achetes=4)
        lignes = self.achat(12)
        gratuite = next(ligne for ligne in lignes if ligne.type_transaction == "gratuit")
        self.assertEqual(gratuite.quantite, 3)
        self.assertEqual(gratuite.variation_gratuits, 3)
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_gratuits), (16, 3))

    def test_seuil_un_et_achat_sans_franchissement(self):
        self.regler(5)
        lignes = self.achat(4)
        self.assertEqual([ligne.type_transaction for ligne in lignes], ["achat"])
        self.regler(1)
        self.achat(3)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 3)

    def test_consommation_ne_recompense_que_les_cafes_payes(self):
        self.regler(5)
        Client.objects.filter(pk=self.personne.pk).update(nombre_cafes_achetes=4, nombre_cafes_prepayes=2, nombre_cafes_gratuits=1)
        lignes = self.achat(6, "utilise")
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_prepayes, self.personne.nombre_cafes_gratuits), (7, 0, 1))
        self.regler(8)
        annuler_operation(lignes[0].pk, self.barista)
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_prepayes, self.personne.nombre_cafes_gratuits), (4, 2, 1))

    def test_modifier_le_seuil_ne_recalcule_pas_les_anciennes_operations(self):
        lignes = self.achat(20)
        avant = list(TransactionCafe.objects.values())
        self.assertEqual(self.modifier_regle(3).status_code, 302)
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_gratuits), (20, 2))
        self.assertEqual(list(TransactionCafe.objects.values()), avant)
        self.assertFalse(AnnulationTransaction.objects.exists())
        annuler_operation(lignes[0].pk, self.barista)
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_gratuits), (0, 0))

    def test_contenu_des_cartes_prepayees_conserve(self):
        self.regler(7)
        ligne = self.achat(2, "prepaye")[0]
        self.personne.refresh_from_db()
        self.assertEqual(ligne.quantite, 20)
        self.assertEqual((self.personne.nombre_cafes_prepayes, self.personne.nombre_cafes_gratuits), (20, 2))

    def test_activation_ne_recalcule_pas_les_operations_et_preserve_annulation(self):
        lignes = self.achat(20)
        avant = list(TransactionCafe.objects.values())
        demain = timezone.localdate() + timedelta(days=1)
        self.assertEqual(self.modifier_regle(3, demain.isoformat()).status_code, 302)
        self.assertEqual(ParametresCafe.charger().seuil_gratuite_actif, 10)
        with patch("django.utils.timezone.localdate", return_value=demain):
            self.assertEqual(ParametresCafe.charger().seuil_gratuite_actif, 3)
            self.personne.refresh_from_db()
            self.assertEqual((self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_gratuits), (20, 2))
            self.assertEqual(list(TransactionCafe.objects.values()), avant)
            annuler_operation(lignes[0].pk, self.barista)
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_gratuits), (0, 0))

    def test_consommation_utilise_le_seuil_actif_pour_les_cafes_payes(self):
        demain = timezone.localdate() + timedelta(days=1)
        self.assertEqual(self.modifier_regle(3, demain.isoformat()).status_code, 302)
        Client.objects.filter(pk=self.personne.pk).update(
            nombre_cafes_achetes=2, nombre_cafes_prepayes=2, nombre_cafes_gratuits=1,
        )
        self.achat(4, "utilise")
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_gratuits), (3, 0))
        with patch("django.utils.timezone.localdate", return_value=demain):
            self.achat(3, "utilise")
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_gratuits), (6, 1))


class ParametresCafeMigrationTests(TransactionTestCase):
    def test_migration_conserve_le_seuil_existant(self):
        avant = [("CafeDolbeau", "0014_fusions_clients")]
        executor = MigrationExecutor(connection)
        dernier_schema = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate(avant)
            apps = executor.loader.project_state(avant).apps
            AnciensParametres = apps.get_model("CafeDolbeau", "ParametresCafe")
            AnciensParametres.objects.update_or_create(pk=1, defaults={"cafes_pour_gratuite": 7})
            MigrationExecutor(connection).migrate(dernier_schema)
            parametres = ParametresCafe.charger()
            self.assertEqual(parametres.cafes_pour_gratuite, 7)
            self.assertEqual(parametres.cafes_pour_gratuite_precedent, 7)
            self.assertEqual(parametres.date_application, timezone.localdate())
            self.assertEqual(parametres.seuil_gratuite_actif, 7)
        finally:
            MigrationExecutor(connection).migrate(dernier_schema)
