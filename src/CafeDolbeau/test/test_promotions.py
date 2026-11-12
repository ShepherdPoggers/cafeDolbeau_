from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from ..models import Client, CompteurPromotion, FusionClient, Promotion, PromotionSuccursale, Succursale, TransactionCafe
from ..promotions import annuler_promotion, contexte_promotion
from ..rapports import exporter_excel, generer_rapport
from ..services import ajouter_cafes, annuler_fusion, annuler_operation, fusionner_clients, supprimer_clients
from .test_annulations import creer_employe


class PromotionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.proprietaire = creer_employe("proprietaire-promotions", "Propriétaire")
        cls.gerant = creer_employe("gerant-promotions", "Gérant")
        cls.barista = creer_employe("barista-promotions")
        cls.s2 = Succursale.objects.create(nom="Deuxième")
        cls.s3 = Succursale.objects.create(nom="Troisième")

    def setUp(self):
        self.jour = timezone.localdate()
        self.personne = Client.objects.create(nom_complet="Camille", telephone="promo-1", nombre_cafes_achetes=9)
        self.promotion = self.creer_promotion()
        self.affecter(self.promotion, 1, self.s2.pk)

    def creer_promotion(self, debut=None, fin=None, seuil=3):
        return Promotion.objects.create(nom="Promotion test", cafes_pour_gratuite=seuil,
                                        date_debut=debut or self.jour, date_fin=fin or self.jour)

    def affecter(self, promotion, *succursales):
        for identifiant in succursales:
            PromotionSuccursale.objects.create(promotion=promotion, succursale_id=identifiant)

    def operation(self, quantite=1, type_cafe="achat", succursale=1, personne=None):
        return ajouter_cafes(personne or self.personne, quantite, type_cafe,
                             employe=self.proprietaire, succursale_id=succursale)

    def compteur(self):
        return CompteurPromotion.objects.get(client=self.personne, promotion=self.promotion)

    def test_remplace_fidelite_sans_alterer_total_et_partage_la_progression(self):
        self.operation(2)
        lignes = self.operation(2, succursale=self.s2.pk)
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_fidelite, self.personne.nombre_cafes_gratuits), (13, 9, 0))
        self.assertEqual((self.compteur().progression, self.compteur().cafes_gratuits), (1, 1))
        self.assertEqual({ligne.promotion_id for ligne in lignes}, {self.promotion.pk})
        self.operation(succursale=self.s3.pk)
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_fidelite, self.personne.nombre_cafes_gratuits), (10, 1))

    def test_plusieurs_seuils_et_annulation_exacte(self):
        self.operation(2)
        lignes = self.operation(8)
        self.assertEqual((self.compteur().progression, self.compteur().cafes_gratuits), (1, 3))
        self.assertEqual(len({ligne.operation_id for ligne in lignes}), 1)
        self.assertEqual(annuler_operation(lignes[0].pk, self.proprietaire), 2)
        self.assertEqual((self.compteur().progression, self.compteur().cafes_gratuits), (2, 0))
        self.assertEqual(annuler_operation(lignes[0].pk, self.proprietaire), 0)

    def test_priorite_consommation_et_plusieurs_lignes(self):
        self.operation(3)
        Client.objects.filter(pk=self.personne.pk).update(nombre_cafes_gratuits=2, nombre_cafes_prepayes=3)
        lignes = self.operation(8, "utilise")
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_gratuits, self.personne.nombre_cafes_prepayes), (14, 0, 0))
        self.assertEqual((self.compteur().progression, self.compteur().cafes_gratuits), (2, 0))
        self.assertEqual(len(lignes), 3)
        annuler_operation(lignes[0].pk, self.proprietaire)
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_gratuits, self.personne.nombre_cafes_prepayes), (2, 3))
        self.assertEqual((self.compteur().progression, self.compteur().cafes_gratuits), (0, 1))

    def test_gratuits_promotionnels_inutilisables_hors_succursales_participantes(self):
        self.operation(3)
        self.operation(1, "utilise", succursale=self.s3.pk)
        self.assertEqual(self.compteur().cafes_gratuits, 1)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 13)

    def test_cartes_conservent_leur_bonus_habituel(self):
        lignes = self.operation(2, "prepaye")
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_prepayes, self.personne.nombre_cafes_gratuits), (20, 2))
        self.assertEqual(self.personne.nombre_cafes_fidelite, 9)
        self.assertIsNone(lignes[0].promotion_id)
        self.assertFalse(CompteurPromotion.objects.exists())

    def test_expiration_masque_compteur_et_empeche_utilisation_sans_effacer_trace(self):
        lignes = self.operation(4)
        with patch("django.utils.timezone.localdate", return_value=self.jour + timedelta(days=1)):
            self.assertIsNone(contexte_promotion(self.personne, 1))
            self.operation(1, "utilise")
            self.assertEqual(self.compteur().cafes_gratuits, 1)
            annuler_operation(lignes[0].pk, self.proprietaire)
            self.assertEqual((self.compteur().progression, self.compteur().cafes_gratuits), (0, 0))
            self.assertIsNone(contexte_promotion(self.personne, 1))

    def test_annuler_consommation_apres_fin_ne_reactive_pas_solde(self):
        self.operation(3)
        consommation = self.operation(1, "utilise")[0]
        with patch("django.utils.timezone.localdate", return_value=self.jour + timedelta(days=1)):
            annuler_operation(consommation.pk, self.proprietaire)
            self.assertEqual(self.compteur().cafes_gratuits, 1)
            self.assertIsNone(contexte_promotion(self.personne, 1))

    def test_dates_inclusives_et_promotion_future(self):
        with patch("django.utils.timezone.localdate", return_value=self.jour - timedelta(days=1)):
            self.assertIsNone(contexte_promotion(self.personne, 1))
        self.assertIsNotNone(contexte_promotion(self.personne, 1))
        suivante = self.creer_promotion(debut=self.jour + timedelta(days=1), fin=self.jour + timedelta(days=2))
        self.affecter(suivante, 1)
        with patch("django.utils.timezone.localdate", return_value=self.jour + timedelta(days=2)):
            self.assertEqual(contexte_promotion(self.personne, 1)["id"], suivante.pk)

    def test_chevauchement_refuse_meme_sur_date_limite(self):
        autre = self.creer_promotion(fin=self.jour + timedelta(days=2))
        with self.assertRaises(ValidationError):
            self.affecter(autre, 1)
        self.affecter(autre, self.s3.pk)
        self.assertEqual(autre.succursales.count(), 1)

    def test_dates_et_seuil_invalides(self):
        for donnees in ({"date_fin": self.jour - timedelta(days=1)}, {"cafes_pour_gratuite": 0}):
            for champ, valeur in donnees.items():
                setattr(self.promotion, champ, valeur)
            with self.assertRaises(ValidationError):
                self.promotion.save()
            self.promotion.refresh_from_db()

    def test_promotion_utilisee_figee_sauf_nom_et_prolongation(self):
        self.operation()
        for champ, valeur in (("cafes_pour_gratuite", 2), ("date_debut", self.jour - timedelta(days=1))):
            setattr(self.promotion, champ, valeur)
            with self.assertRaises(ValidationError):
                self.promotion.save()
            self.promotion.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.affecter(self.promotion, self.s3.pk)
        with self.assertRaises(ValidationError), transaction.atomic():
            self.promotion.affectations.all().delete()
        self.promotion.nom = "Nom corrigé"
        self.promotion.date_fin += timedelta(days=1)
        self.promotion.save()
        self.assertEqual(self.promotion.date_fin, self.jour + timedelta(days=1))

    def test_prolongation_refusee_si_expiree_ou_chevauchement(self):
        self.operation()
        suivante = self.creer_promotion(debut=self.jour + timedelta(days=1), fin=self.jour + timedelta(days=2))
        self.affecter(suivante, 1)
        self.promotion.date_fin += timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.promotion.save()
        with patch("django.utils.timezone.localdate", return_value=self.jour + timedelta(days=1)):
            with self.assertRaises(ValidationError):
                self.promotion.save()

    def test_api_m2m_verifie_periodes_et_fige_les_succursales(self):
        autre = self.creer_promotion()
        with self.assertRaises(ValidationError), transaction.atomic():
            autre.succursales.add(1)
        self.operation()
        with self.assertRaises(ValidationError), transaction.atomic():
            self.promotion.succursales.add(self.s3)
        with self.assertRaises(ValidationError), transaction.atomic():
            self.promotion.succursales.clear()
        with self.assertRaises(ValidationError), transaction.atomic():
            self.s2.promotions.remove(self.promotion)

    def test_echec_credit_promotionnel_annule_tous_les_effets(self):
        sauvegarder = TransactionCafe.save
        def enregistrer(ligne, *args, **kwargs):
            if ligne.type_transaction == "gratuit":
                raise RuntimeError("échec simulé")
            return sauvegarder(ligne, *args, **kwargs)
        with patch.object(TransactionCafe, "save", enregistrer), self.assertRaises(RuntimeError):
            self.operation(3)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 9)
        self.assertFalse(TransactionCafe.objects.exists())
        self.assertFalse(CompteurPromotion.objects.exists())

    def test_depassement_solde_promotionnel_refuse_sans_effet(self):
        CompteurPromotion.objects.create(client=self.personne, promotion=self.promotion, cafes_gratuits=2147483647)
        with self.assertRaises(ValidationError):
            self.operation(3)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 9)
        self.assertEqual(self.compteur().cafes_gratuits, 2147483647)
        self.assertFalse(TransactionCafe.objects.exists())

    def test_compteurs_distincts_pour_promotions_successives(self):
        self.operation(4)
        lendemain = self.jour + timedelta(days=1)
        suivante = self.creer_promotion(debut=lendemain, fin=lendemain, seuil=2)
        self.affecter(suivante, 1)
        with patch("django.utils.timezone.localdate", return_value=lendemain):
            self.operation()
            compteur = CompteurPromotion.objects.get(client=self.personne, promotion=suivante)
            self.assertEqual((compteur.progression, compteur.cafes_gratuits), (1, 0))
        self.assertEqual((self.compteur().progression, self.compteur().cafes_gratuits), (1, 1))

    def test_promotion_referencee_protegee(self):
        self.operation()
        with self.assertRaises((ValidationError, ProtectedError)):
            self.promotion.delete()

    def test_fusion_sans_cadeau_et_retour_arriere(self):
        autre = Client.objects.create(nom_complet="Autre", telephone="promo-2")
        self.operation(5)
        self.operation(5, personne=autre)
        fusion = fusionner_clients(self.personne.pk, autre.pk, employe=self.proprietaire)
        compteur = CompteurPromotion.objects.get(client=autre, promotion=self.promotion)
        self.assertEqual((compteur.progression, compteur.cafes_gratuits), (1, 2))
        annuler_fusion(fusion.pk, employe=self.proprietaire)
        self.assertEqual((self.compteur().progression, self.compteur().cafes_gratuits), (2, 1))
        compteur.refresh_from_db()
        self.assertEqual((compteur.progression, compteur.cafes_gratuits), (2, 1))

    def test_fusion_finalisee_et_suppression_conservent_historique_promo(self):
        autre = Client.objects.create(nom_complet="Autre", telephone="promo-2")
        self.operation(3)
        fusion = fusionner_clients(self.personne.pk, autre.pk, employe=self.proprietaire)
        self.operation(personne=autre)
        fusion.refresh_from_db()
        self.assertEqual(fusion.statut, FusionClient.Statut.FINALISEE)
        supprimer_clients([autre.pk], employe=self.proprietaire)
        self.assertFalse(CompteurPromotion.objects.exists())
        self.assertTrue(TransactionCafe.objects.filter(client_id=-1, promotion=self.promotion).exists())

    def test_caisse_et_reponse_asynchrone_affichent_promotion(self):
        self.client.force_login(self.barista)
        url = reverse("ajouter_cafes", args=[1, self.personne.pk])
        self.assertContains(self.client.get(url), f"Promotion #{self.promotion.pk}")
        reponse = self.client.post(url, {"quantite": 3, "type_transaction": "achat", "promotion_id": 999}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(reponse.status_code, 200)
        self.assertIn("disponibles : 1", reponse.json()["promotion_html"])
        self.assertEqual(self.compteur().cafes_gratuits, 1)
        with patch("django.utils.timezone.localdate", return_value=self.jour + timedelta(days=1)):
            self.assertNotContains(self.client.get(url), "Promotion en cours")

    def test_actualisation_promotion_en_lecture_seule_et_sans_cache(self):
        self.client.force_login(self.barista)
        url = reverse("ajouter_cafes", args=[1, self.personne.pk])
        reponse = self.client.get(url, {"partiel": "promotion"})
        self.assertEqual(reponse.status_code, 200)
        self.assertIn(f"Promotion #{self.promotion.pk}", reponse.json()["promotion_html"])
        self.assertIn("no-store", reponse["Cache-Control"])
        self.assertFalse(TransactionCafe.objects.exists())
        self.assertFalse(CompteurPromotion.objects.exists())
        with patch("django.utils.timezone.localdate", return_value=self.jour + timedelta(days=1)):
            self.assertEqual(self.client.get(url, {"partiel": "promotion"}).json()["promotion_html"].strip(), "")
        self.barista.affectations_succursales.all().delete()
        self.assertEqual(self.client.get(url, {"partiel": "promotion"}).status_code, 403)

    def test_annulation_immediate_retablit_fidelite_et_conserve_historique(self):
        self.operation(4)
        avant = list(TransactionCafe.objects.order_by("pk").values())
        self.assertTrue(annuler_promotion(self.promotion.pk, employe=self.proprietaire, motif="Erreur de configuration"))
        self.promotion.refresh_from_db()
        self.assertEqual(self.promotion.annulee_par_id, self.proprietaire.pk)
        self.assertEqual(self.promotion.motif_annulation, "Erreur de configuration")
        self.assertIsNone(contexte_promotion(self.personne, 1))
        self.assertIsNone(contexte_promotion(self.personne, self.s2.pk))
        self.assertEqual(list(TransactionCafe.objects.order_by("pk").values()), avant)
        self.assertEqual(self.compteur().cafes_gratuits, 1)
        lignes = self.operation(1, "utilise")
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_gratuits, 1)
        self.assertEqual(self.personne.nombre_cafes_fidelite, 10)
        self.assertTrue(all(ligne.promotion_id is None for ligne in lignes))
        self.assertEqual(self.compteur().cafes_gratuits, 1)
        self.assertFalse(annuler_promotion(self.promotion.pk, employe=self.proprietaire))

    def test_annulation_reste_inactive_apres_annulation_transaction_et_autorise_remplacement(self):
        self.operation(3)
        utilisee = self.operation(1, "utilise")[0]
        annuler_promotion(self.promotion.pk, employe=self.proprietaire)
        annuler_operation(utilisee.pk, self.proprietaire)
        self.assertEqual(self.compteur().cafes_gratuits, 1)
        self.assertIsNone(contexte_promotion(self.personne, 1))
        autre = self.creer_promotion(seuil=2)
        self.affecter(autre, 1)
        self.assertEqual(contexte_promotion(self.personne, 1)["id"], autre.pk)
        self.assertEqual(contexte_promotion(self.personne, 1)["gratuits"], 0)

    def test_annulation_interdite_aux_autres_roles_et_hors_periode(self):
        for employe in (self.gerant, self.barista):
            with self.assertRaises(PermissionDenied):
                annuler_promotion(self.promotion.pk, employe=employe)
        for decalage in (-1, 1):
            with patch("django.utils.timezone.localdate", return_value=self.jour + timedelta(days=decalage)):
                with self.assertRaises(ValidationError):
                    annuler_promotion(self.promotion.pk, employe=self.proprietaire)

    def test_ancien_formulaire_ne_peut_pas_reactiver_promotion(self):
        self.operation()
        annuler_promotion(self.promotion.pk, employe=self.proprietaire)
        self.promotion.nom = "Ancien formulaire"
        with self.assertRaises(ValidationError):
            self.promotion.save()
        self.promotion.refresh_from_db()
        self.promotion.date_fin += timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.promotion.save()
        self.assertIsNone(contexte_promotion(self.personne, 1))

    def test_admin_confirmation_annulation_et_actualisation_caisse(self):
        self.operation(3)
        url = reverse("admin:CafeDolbeau_promotion_annuler", args=[self.promotion.pk])
        self.client.force_login(self.gerant)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.proprietaire)
        self.assertContains(self.client.get(url), "Confirmer l’annulation")
        self.promotion.refresh_from_db()
        self.assertIsNone(self.promotion.annulee_le)
        self.assertEqual(self.client.post(url, {"motif": "Arrêt anticipé"}).status_code, 302)
        self.promotion.refresh_from_db()
        self.assertIsNotNone(self.promotion.annulee_le)
        self.assertEqual(self.promotion.motif_annulation, "Arrêt anticipé")
        caisse = reverse("ajouter_cafes", args=[1, self.personne.pk])
        self.assertEqual(self.client.get(caisse, {"partiel": "promotion"}).json()["promotion_html"].strip(), "")
        self.assertEqual(self.client.post(url).status_code, 302)

    def test_admin_reserve_au_proprietaire_et_post_forge_refuse(self):
        url = reverse("admin:CafeDolbeau_promotion_add")
        for acteur in (self.barista, self.gerant):
            self.client.force_login(acteur)
            self.assertIn(self.client.get(url).status_code, (302, 403))
            self.assertIn(self.client.post(url, {"nom": "Forgée"}).status_code, (302, 403))
        self.client.force_login(self.proprietaire)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:CafeDolbeau_compteurpromotion_changelist")).status_code, 200)

    def test_admin_enregistre_promotion_et_refuse_affectation_forgee(self):
        self.client.force_login(self.proprietaire)
        demain = self.jour + timedelta(days=1)
        donnees = {"nom": "Demain", "cafes_pour_gratuite": 5, "date_debut": demain.isoformat(),
                   "date_fin": demain.isoformat(), "succursales": [1], "_save": "Enregistrer"}
        self.assertEqual(self.client.post(reverse("admin:CafeDolbeau_promotion_add"), donnees).status_code, 302)
        self.operation()
        donnees.update(nom=self.promotion.nom, cafes_pour_gratuite=3, date_debut=self.jour.isoformat(),
                       date_fin=self.jour.isoformat(), succursales=[self.s3.pk])
        reponse = self.client.post(reverse("admin:CafeDolbeau_promotion_change", args=[self.promotion.pk]), donnees)
        self.assertContains(reponse, "figées")
        self.assertEqual(set(self.promotion.succursales.values_list("pk", flat=True)), {1, self.s2.pk})

    def test_confirmation_ancienne_revalide_affectations(self):
        self.operation(3)
        lignes = ajouter_cafes(self.personne, 1, "utilise", employe=self.barista, succursale_id=1)
        self.client.force_login(self.barista)
        url = reverse("annuler_transaction", args=[1, self.personne.pk, lignes[0].pk])
        confirmation = self.client.get(url).context["confirmation"]
        self.barista.affectations_succursales.all().delete()
        self.assertEqual(self.client.post(url, {"action": "confirmer", "confirmation": confirmation}).status_code, 403)
        self.assertFalse(lignes[0].annulee)

    def test_rapport_et_excel_conservent_numero_apres_expiration_et_annulation(self):
        lignes = self.operation(3)
        annuler_operation(lignes[0].pk, self.proprietaire)
        rapport = generer_rapport(date_debut=self.jour, date_fin=self.jour,
                                 types=("achat", "gratuit"), precision="transaction")
        self.assertEqual(len(rapport.evenements), 4)
        self.assertEqual({e.promotion_id for e in rapport.evenements}, {self.promotion.pk})
        classeur = load_workbook(exporter_excel(rapport))
        self.assertEqual(classeur["Transactions"].cell(1, 10).value, "Promotion")
        self.assertEqual(classeur["Transactions"].cell(2, 10).value, self.promotion.pk)
        self.assertEqual(rapport.total, 0)


class ConcurrencePromotionsTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Exploitation PostgreSQL uniquement.")
        self.proprietaire = creer_employe("proprietaire-concurrence-promo", "Propriétaire")
        self.personne = Client.objects.create(nom_complet="Concurrent", telephone="concurrent")
        self.promotion = Promotion.objects.create(nom="Concurrente", cafes_pour_gratuite=2,
                                                date_debut=timezone.localdate(), date_fin=timezone.localdate())
        PromotionSuccursale.objects.create(promotion=self.promotion, succursale_id=1)

    def test_deux_achats_concurrents_un_seul_cadeau(self):
        barriere = Barrier(2)
        def acheter():
            close_old_connections()
            try:
                barriere.wait(timeout=10)
                ajouter_cafes(self.personne, 1, employe=self.proprietaire, succursale_id=1)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as equipe:
            list(equipe.map(lambda _: acheter(), range(2)))
        compteur = CompteurPromotion.objects.get(client=self.personne, promotion=self.promotion)
        self.assertEqual((compteur.progression, compteur.cafes_gratuits), (0, 1))

    def test_achat_et_annulation_simultanes_respectent_arret(self):
        barriere = Barrier(2)
        def effectuer(annulation):
            close_old_connections()
            try:
                barriere.wait(timeout=10)
                if annulation:
                    return annuler_promotion(self.promotion.pk, employe=self.proprietaire)
                return ajouter_cafes(self.personne, 2, employe=self.proprietaire, succursale_id=1)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as equipe:
            list(equipe.map(effectuer, [True, False]))
        self.promotion.refresh_from_db()
        self.personne.refresh_from_db()
        self.assertIsNotNone(self.promotion.annulee_le)
        self.assertIsNone(contexte_promotion(self.personne, 1))
        for ligne in TransactionCafe.objects.filter(promotion=self.promotion):
            self.assertLessEqual(ligne.date_creation, self.promotion.annulee_le)
        self.assertEqual(self.personne.nombre_cafes_achetes, 2)
        lignes = ajouter_cafes(self.personne, 1, employe=self.proprietaire, succursale_id=1)
        self.assertTrue(all(ligne.promotion_id is None for ligne in lignes))

    def test_affectations_concurrentes_refusent_chevauchement(self):
        autre = Promotion.objects.create(nom="Concurrente 2", cafes_pour_gratuite=3,
                                         date_debut=timezone.localdate(), date_fin=timezone.localdate())
        succursale = Succursale.objects.create(nom="Disponible")
        barriere = Barrier(2)
        def affecter(promotion):
            close_old_connections()
            try:
                barriere.wait(timeout=10)
                try:
                    PromotionSuccursale.objects.create(promotion=promotion, succursale=succursale)
                    return True
                except ValidationError:
                    return False
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as equipe:
            resultats = list(equipe.map(affecter, [self.promotion, autre]))
        self.assertEqual(sorted(resultats), [False, True])
