from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

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
        response = self.client.post(self.url, {"cafes_pour_gratuite": 5, "_save": "Enregistrer"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ParametresCafe.charger().cafes_pour_gratuite, 5)
        self.achat(5)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 1)
        self.client.post(self.url, {"cafes_pour_gratuite": 3, "_save": "Enregistrer"})
        self.achat(1)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 2)

    def test_admin_refuse_les_valeurs_invalides(self):
        for valeur in ("", "0", "-1", "1.5", "abc", "2147483648"):
            with self.subTest(valeur=valeur):
                response = self.client.post(self.url, {"cafes_pour_gratuite": valeur, "_save": "Enregistrer"})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["adminform"].form.errors)
                self.assertEqual(ParametresCafe.charger().cafes_pour_gratuite, 10)
        for valeur in (0, -1, 2147483648):
            with self.assertRaises(ValidationError):
                ParametresCafe(pk=1, cafes_pour_gratuite=valeur).full_clean()

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
        self.client.post(self.url, {"cafes_pour_gratuite": 3, "_save": "Enregistrer"})
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
