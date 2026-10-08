from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client as Navigateur, TestCase, TransactionTestCase
from django.urls import reverse

from .models import AnnulationTransaction, Client, Employe, TransactionCafe
from .permissions import PERMISSION_BASE, PERMISSION_GERANT
from .services import ajouter_cafes, annuler_operation, preparer_annulation


def creer_employe(username, role="Barista"):
    employe = Employe.objects.create_user(username)
    groupe, _ = Group.objects.get_or_create(name=role)
    codes = ["acces_base", "acces_gerant"] if role == "Gérant" else ["acces_base"]
    groupe.permissions.add(*Permission.objects.filter(content_type__app_label="CafeDolbeau", codename__in=codes))
    employe.groups.add(groupe)
    return employe


class AnnulationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.barista = creer_employe("barista")
        cls.autre = creer_employe("autre")
        cls.gerant = creer_employe("gerant", "Gérant")
        cls.personne = Client.objects.create(nom_complet="Camille", telephone="418 555-1111")
        cls.autre_client = Client.objects.create(nom_complet="Alex", telephone="418 555-2222")

    def setUp(self):
        self.client.force_login(self.barista)

    def soldes(self):
        self.personne.refresh_from_db()
        return (self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_prepayes, self.personne.nombre_cafes_gratuits)

    def initialiser(self, achetes=0, prepayes=0, gratuits=0):
        Client.objects.filter(pk=self.personne.pk).update(
            nombre_cafes_achetes=achetes, nombre_cafes_prepayes=prepayes,
            nombre_cafes_gratuits=gratuits,
        )

    def operation(self, quantite=1, type_transaction="achat", employe=None):
        return ajouter_cafes(self.personne, quantite, type_transaction, employe=employe or self.barista)

    def url(self, ligne, admin=False):
        url = reverse("annuler_transaction", args=[ligne.client_id, ligne.pk])
        return url + "?origine=admin" if admin else url

    def confirmer(self, ligne, admin=False):
        url = self.url(ligne, admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return self.client.post(url, {"action": "confirmer", "confirmation": response.context["confirmation"]})

    def ancienne(self, type_transaction="achat", quantite=1, client=None):
        return TransactionCafe.objects.create(client=client or self.personne, type_transaction=type_transaction, quantite=quantite)

    def donnees_effets(self, lignes, valeurs):
        donnees = {
            "action": "previsualiser", "lignes": [ligne.pk for ligne in lignes],
            "form-TOTAL_FORMS": len(lignes), "form-INITIAL_FORMS": len(lignes),
            "form-MIN_NUM_FORMS": 0, "form-MAX_NUM_FORMS": 2000,
        }
        for index, (ligne, effets) in enumerate(zip(lignes, valeurs)):
            donnees[f"form-{index}-transaction_id"] = ligne.pk
            for champ, valeur in zip(("variation_achetes", "variation_prepayes", "variation_gratuits"), effets):
                donnees[f"form-{index}-{champ}"] = valeur
        return donnees

    def test_achat_et_recompense_auteur_effets_et_annulation_complete(self):
        self.initialiser(achetes=9)
        lignes = self.operation()
        self.assertEqual(len(lignes), 2)
        self.assertEqual(len({ligne.operation_id for ligne in lignes}), 1)
        self.assertEqual({ligne.employe_id for ligne in lignes}, {self.barista.pk})
        self.assertEqual(self.soldes(), (10, 0, 1))
        self.assertEqual(annuler_operation(lignes[0].pk, self.barista), 2)
        self.assertEqual(self.soldes(), (9, 0, 0))
        self.assertEqual(TransactionCafe.objects.count(), 2)
        audits = list(AnnulationTransaction.objects.all())
        self.assertEqual({audit.employe_id for audit in audits}, {self.barista.pk})
        self.assertEqual(len({audit.date_annulation for audit in audits}), 1)
        self.assertEqual({audit.transaction_id for audit in audits}, {ligne.pk for ligne in lignes})

    def test_carte_retire_achats_prepayes_et_gratuits(self):
        self.initialiser(7, 4, 3)
        ligne = self.operation(2, "prepaye")[0]
        self.assertEqual(self.soldes(), (27, 24, 5))
        annuler_operation(ligne.pk, self.barista)
        self.assertEqual(self.soldes(), (7, 4, 3))

    def test_consommation_mixte_restitue_exactement_les_soldes(self):
        self.initialiser(9, 2, 1)
        lignes = self.operation(5, "utilise")
        self.assertEqual(self.soldes(), (11, 0, 1))
        consommation = next(ligne for ligne in lignes if ligne.type_transaction == "utilise")
        self.assertEqual((consommation.variation_prepayes, consommation.variation_gratuits), (-2, -1))
        annuler_operation(consommation.pk, self.barista)
        self.assertEqual(self.soldes(), (9, 2, 1))
        self.assertEqual(AnnulationTransaction.objects.count(), 3)

    def test_plancher_zero_et_pas_de_recalcul_des_operations_suivantes(self):
        ligne = self.operation(2, "prepaye")[0]
        suivantes = self.operation(25, "utilise")
        annuler_operation(ligne.pk, self.barista)
        self.assertEqual(self.soldes(), (3, 0, 0))
        self.assertTrue(all(not TransactionCafe.objects.get(pk=source.pk).annulee for source in suivantes))

    def test_plancher_apres_agregation_et_non_ligne_par_ligne(self):
        self.initialiser(9, 0, 1)
        lignes = self.operation(2, "utilise")
        self.initialiser(10, 0, 0)
        annuler_operation(lignes[0].pk, self.barista)
        self.assertEqual(self.soldes(), (9, 0, 0))

    def test_gerant_peut_annuler_un_autre_auteur_barista_non(self):
        ligne = self.operation()[0]
        with self.assertRaises(PermissionDenied):
            annuler_operation(ligne.pk, self.autre)
        self.assertEqual(self.soldes(), (1, 0, 0))
        annuler_operation(ligne.pk, self.gerant)
        self.assertEqual(AnnulationTransaction.objects.get().employe_id, self.gerant.pk)

    def test_double_annulation_ne_modifie_pas_les_soldes_ni_audits(self):
        ligne = self.operation()[0]
        self.assertEqual(annuler_operation(ligne.pk, self.barista), 1)
        self.assertEqual(annuler_operation(ligne.pk, self.barista), 0)
        self.assertEqual(self.soldes(), (0, 0, 0))
        self.assertEqual(AnnulationTransaction.objects.count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AnnulationTransaction.objects.create(transaction=ligne, employe=self.gerant)

    def test_permissions_reverifiees_meme_avec_un_employe_mis_en_cache(self):
        ligne = self.operation()[0]
        self.assertTrue(self.barista.has_perm(PERMISSION_BASE))
        self.barista.groups.clear()
        with self.assertRaises(PermissionDenied):
            annuler_operation(ligne.pk, self.barista)
        self.assertEqual(self.soldes(), (1, 0, 0))

    def test_echec_audit_annule_toutes_les_ecritures(self):
        self.initialiser(9)
        lignes = self.operation()
        sauvegarder = AnnulationTransaction.save
        compteur = 0

        def echouer(instance, *args, **kwargs):
            nonlocal compteur
            compteur += 1
            if compteur == 2:
                raise RuntimeError("échec audit")
            return sauvegarder(instance, *args, **kwargs)

        with patch.object(AnnulationTransaction, "save", echouer):
            with self.assertRaises(RuntimeError):
                annuler_operation(lignes[0].pk, self.barista)
        self.assertEqual(self.soldes(), (10, 0, 1))
        self.assertFalse(AnnulationTransaction.objects.exists())

    def test_protection_des_transactions_et_des_employes_references(self):
        ligne = self.operation()[0]
        annuler_operation(ligne.pk, self.gerant)
        for objet in (ligne, self.barista, self.gerant):
            with self.subTest(objet=objet):
                with self.assertRaises(ProtectedError):
                    objet.delete()

    def test_historique_dix_lignes_boutons_et_statut(self):
        for _ in range(12):
            self.operation()
        response = self.client.get(reverse("ajouter_cafes", args=[self.personne.pk]))
        self.assertEqual(len(response.context["transactions"]), 10)
        lignes = response.context["transactions"]
        self.assertEqual([ligne.pk for ligne in lignes], sorted((ligne.pk for ligne in lignes), reverse=True))
        self.assertTrue(all(ligne.annulation_disponible for ligne in lignes))
        self.assertContains(response, "Employé : barista")
        self.assertContains(response, "<small>Active</small>", count=10, html=True)
        annuler_operation(lignes[0].pk, self.barista)
        response = self.client.get(reverse("ajouter_cafes", args=[self.personne.pk]))
        self.assertContains(response, "Annulée le")
        self.assertFalse(response.context["transactions"][0].annulation_disponible)
        self.client.force_login(self.autre)
        response = self.client.get(reverse("ajouter_cafes", args=[self.personne.pk]))
        self.assertFalse(any(ligne.annulation_disponible for ligne in response.context["transactions"]))
        self.assertContains(response, " disabled title=")
        self.client.force_login(self.gerant)
        response = self.client.get(reverse("ajouter_cafes", args=[self.personne.pk]))
        self.assertTrue(all(ligne.annulation_disponible for ligne in response.context["transactions"][1:]))

    def test_operation_annulee_meme_si_une_ligne_est_hors_des_dix(self):
        self.initialiser(9)
        lignes = self.operation()
        for _ in range(9):
            self.operation(1, "prepaye")
        response = self.client.get(reverse("ajouter_cafes", args=[self.personne.pk]))
        visibles = {ligne.pk for ligne in response.context["transactions"]}
        self.assertEqual(len(visibles & {ligne.pk for ligne in lignes}), 1)
        annuler_operation(next(pk for pk in visibles if pk in {ligne.pk for ligne in lignes}), self.barista)
        self.assertTrue(all(TransactionCafe.objects.get(pk=ligne.pk).annulee for ligne in lignes))

    def test_ajax_auteur_fourni_par_session_et_historique_dix_lignes(self):
        for _ in range(11):
            self.operation(1, "prepaye")
        response = self.client.post(reverse("ajouter_cafes", args=[self.personne.pk]), {
            "quantite": 1, "type_transaction": "achat", "employe": self.autre.pk,
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TransactionCafe.objects.first().employe_id, self.barista.pk)
        self.assertEqual(response.json()["historique"].count('class="transaction-ligne'), 10)
        self.assertIn('class="bouton-annuler"', response.json()["historique"])
        self.assertNotIn(" disabled", response.json()["historique"])

    def test_confirmation_recapitulatif_get_sans_ecriture_et_post_seul(self):
        ligne = self.operation()[0]
        response = self.client.get(self.url(ligne))
        self.assertContains(response, "Après annulation")
        self.assertEqual(self.soldes(), (1, 0, 0))
        self.assertFalse(AnnulationTransaction.objects.exists())
        self.assertEqual(self.client.post(self.url(ligne), {"action": "confirmer"}).status_code, 400)
        self.assertFalse(AnnulationTransaction.objects.exists())
        self.assertRedirects(self.confirmer(ligne), reverse("ajouter_cafes", args=[self.personne.pk]))
        self.assertEqual(self.soldes(), (0, 0, 0))

    def test_confirmation_non_transferable_et_retrait_permissions(self):
        ligne = self.operation()[0]
        response = self.client.get(self.url(ligne))
        jeton = response.context["confirmation"]
        self.client.force_login(self.gerant)
        self.assertEqual(self.client.post(self.url(ligne), {"action": "confirmer", "confirmation": jeton}).status_code, 400)
        self.client.force_login(self.barista)
        self.barista.groups.clear()
        self.assertEqual(self.client.post(self.url(ligne), {"action": "confirmer", "confirmation": jeton}).status_code, 403)
        self.assertFalse(AnnulationTransaction.objects.exists())

    def test_double_confirmation_http_sans_double_effet(self):
        ligne = self.operation()[0]
        jeton = self.client.get(self.url(ligne)).context["confirmation"]
        for _ in range(2):
            response = self.client.post(self.url(ligne), {"action": "confirmer", "confirmation": jeton})
            self.assertEqual(response.status_code, 302)
        self.assertEqual(AnnulationTransaction.objects.count(), 1)
        self.assertEqual(self.soldes(), (0, 0, 0))

    def test_anonyme_autre_barista_client_incorrect_et_csrf(self):
        ligne = self.operation()[0]
        navigateur = Navigateur()
        self.assertEqual(navigateur.get(self.url(ligne)).status_code, 302)
        self.assertEqual(navigateur.post(self.url(ligne), {"action": "confirmer"}).status_code, 302)
        navigateur.force_login(self.autre)
        self.assertEqual(navigateur.get(self.url(ligne)).status_code, 403)
        navigateur.force_login(self.barista)
        self.assertEqual(navigateur.get(reverse("annuler_transaction", args=[self.autre_client.pk, ligne.pk])).status_code, 404)
        navigateur = Navigateur(enforce_csrf_checks=True)
        navigateur.force_login(self.barista)
        jeton = navigateur.get(self.url(ligne)).context["confirmation"]
        self.assertEqual(navigateur.post(self.url(ligne), {"action": "confirmer", "confirmation": jeton}).status_code, 403)
        response = navigateur.post(self.url(ligne), {
            "action": "confirmer", "confirmation": jeton,
            "csrfmiddlewaretoken": navigateur.cookies["csrftoken"].value,
        })
        self.assertEqual(response.status_code, 302)

    def test_anciennes_completion_recapitulatif_et_confirmation(self):
        self.initialiser(15, 4, 2)
        achat = self.ancienne("achat", 2)
        utilisation = self.ancienne("utilise", 3)
        self.assertEqual(self.client.get(self.url(achat)).status_code, 403)
        self.client.force_login(self.gerant)
        response = self.client.get(self.url(achat))
        self.assertContains(response, "Compléter")
        response = self.client.post(self.url(achat), {"action": "completer", "lignes": [achat.pk, utilisation.pk]})
        self.assertContains(response, "Variation des cafés gratuits")
        response = self.client.post(self.url(achat), self.donnees_effets([achat, utilisation], [(2, 0, 0), (0, -1, -2)]))
        self.assertEqual(response.status_code, 200)
        jeton = response.context["confirmation"]
        self.assertEqual(self.soldes(), (15, 4, 2))
        achat.refresh_from_db()
        self.assertIsNone(achat.operation_id)
        self.assertIsNone(achat.variation_achetes)
        self.assertFalse(AnnulationTransaction.objects.exists())
        self.client.post(self.url(achat), {"action": "confirmer", "confirmation": jeton})
        self.assertEqual(self.soldes(), (13, 5, 4))
        achat.refresh_from_db()
        utilisation.refresh_from_db()
        self.assertEqual(achat.operation_id, utilisation.operation_id)
        self.assertIsNone(achat.employe_id)
        self.assertIsNone(utilisation.employe_id)
        self.assertEqual(AnnulationTransaction.objects.count(), 2)
        self.assertEqual(self.client.post(self.url(achat), {"action": "confirmer", "confirmation": jeton}).status_code, 302)
        self.assertEqual(self.soldes(), (13, 5, 4))

    def test_anciennes_obligatoires_selection_limitee_et_signes_valides(self):
        source = self.ancienne()
        autre_client = self.ancienne(client=self.autre_client)
        nouvelle = self.operation()[0]
        annulee = self.ancienne()
        annuler_operation(annulee.pk, self.gerant, {annulee.pk: (1, 0, 0)})
        self.client.force_login(self.gerant)
        for ids in ([autre_client.pk], [source.pk, autre_client.pk], [source.pk, nouvelle.pk], [source.pk, annulee.pk]):
            response = self.client.post(self.url(source), {"action": "completer", "lignes": ids})
            self.assertTrue(response.context["selection"].errors)
        with self.assertRaises(ValidationError):
            annuler_operation(source.pk, self.gerant)
        with self.assertRaises(ValidationError):
            annuler_operation(source.pk, self.gerant, {source.pk: (-1, 0, 0)})
        consommation = self.ancienne("utilise")
        response = self.client.post(self.url(consommation), self.donnees_effets([consommation], [(0, 1, 0)]))
        self.assertTrue(response.context["effets"].errors[0])
        self.assertNotIn("confirmation", response.context)
        self.assertFalse(AnnulationTransaction.objects.filter(transaction=source).exists())

    def test_anciennes_echec_conserve_metadonnees_inconnues(self):
        source = self.ancienne()
        with patch.object(AnnulationTransaction, "save", side_effect=RuntimeError("échec")):
            with self.assertRaises(RuntimeError):
                annuler_operation(source.pk, self.gerant, {source.pk: (1, 0, 0)})
        source.refresh_from_db()
        self.assertIsNone(source.operation_id)
        self.assertIsNone(source.variation_achetes)
        self.assertFalse(source.annulee)

    def test_anciennes_formulaire_incomplet_ou_identifiants_modifies(self):
        source = self.ancienne()
        autre = self.ancienne()
        self.client.force_login(self.gerant)
        cas = []
        vide = self.donnees_effets([source], [(1, 0, 0)])
        vide["form-INITIAL_FORMS"] = 0
        for champ in list(vide):
            if champ.startswith("form-0-"):
                del vide[champ]
        cas.append(vide)
        duplique = self.donnees_effets([source, autre], [(1, 0, 0), (1, 0, 0)])
        duplique["form-1-transaction_id"] = source.pk
        cas.append(duplique)
        remplace = self.donnees_effets([source], [(1, 0, 0)])
        remplace["form-0-transaction_id"] = autre.pk
        cas.append(remplace)
        cas.append(self.donnees_effets([source], [(0, 0, 0)]))
        cas.append(self.donnees_effets([source], [(2147483648, 0, 0)]))
        for donnees in cas:
            with self.subTest(donnees=donnees):
                response = self.client.post(self.url(source), donnees)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("confirmation", response.context)
                self.assertFalse(AnnulationTransaction.objects.exists())
        source.refresh_from_db()
        self.assertIsNone(source.operation_id)

    def test_anciennes_selection_reverifiee_a_la_confirmation(self):
        self.initialiser(10)
        source = self.ancienne()
        autre = self.ancienne()
        self.client.force_login(self.gerant)
        response = self.client.post(self.url(source), self.donnees_effets([source, autre], [(1, 0, 0), (1, 0, 0)]))
        jeton = response.context["confirmation"]
        annuler_operation(autre.pk, self.gerant, {autre.pk: (1, 0, 0)})
        response = self.client.post(self.url(source), {"action": "confirmer", "confirmation": jeton})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.soldes(), (9, 0, 0))
        self.assertEqual(AnnulationTransaction.objects.count(), 1)
        source.refresh_from_db()
        self.assertIsNone(source.operation_id)
        self.assertIsNone(source.variation_achetes)

    def test_confirmation_utilise_les_soldes_actuels(self):
        ligne = self.operation()[0]
        jeton = self.client.get(self.url(ligne)).context["confirmation"]
        self.operation(2, "prepaye")
        self.client.post(self.url(ligne), {"action": "confirmer", "confirmation": jeton})
        self.assertEqual(self.soldes(), (20, 20, 2))

    def test_administration_vue_filtres_annulation_et_audit_sans_modification(self):
        ligne = self.operation()[0]
        url = reverse("admin:CafeDolbeau_transactioncafe_changelist")
        self.client.force_login(self.gerant)
        self.assertContains(self.client.get(reverse("admin:index")), "Transactions de cafés")
        self.assertContains(self.client.get(url), "Annuler l’opération")
        detail = reverse("admin:CafeDolbeau_transactioncafe_change", args=[ligne.pk])
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.post(detail, {"quantite": 50}).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:CafeDolbeau_transactioncafe_delete", args=[ligne.pk]), {"post": "yes"}).status_code, 403)
        self.assertRedirects(self.confirmer(ligne, admin=True), url)
        response = self.client.get(detail)
        self.assertContains(response, "gerant")
        self.assertContains(response, "Déjà annulée")
        self.assertEqual(self.client.get(url, {"annulee": "oui"}).context["cl"].result_count, 1)
        self.assertEqual(self.client.get(url, {"annulee": "non"}).context["cl"].result_count, 0)
        self.client.force_login(self.barista)
        self.assertEqual(self.client.get(url, follow=True).status_code, 403)


class AnnulationConcurrenceTests(TransactionTestCase):
    def setUp(self):
        self.barista = creer_employe("barista-concurrent")
        self.personne = Client.objects.create(nom_complet="Camille", telephone="418 555-1111", nombre_cafes_achetes=9)

    def simultanement(self, fonctions):
        barriere = Barrier(len(fonctions))

        def executer(fonction):
            close_old_connections()
            try:
                barriere.wait(timeout=10)
                return fonction()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(fonctions)) as pool:
            resultats = list(pool.map(executer, fonctions))
        return resultats

    def test_deux_annulations_simultanees_une_seule_inversion(self):
        lignes = ajouter_cafes(self.personne, 1, employe=self.barista)
        resultat = self.simultanement([
            lambda: annuler_operation(lignes[0].pk, self.barista),
            lambda: annuler_operation(lignes[1].pk, self.barista),
        ])
        self.assertEqual(sorted(resultat), [0, 2])
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 9)
        self.assertEqual(self.personne.nombre_cafes_gratuits, 0)
        self.assertEqual(AnnulationTransaction.objects.count(), 2)

    def test_ajout_et_annulation_simultanes_preservent_les_deux_operations(self):
        ligne = ajouter_cafes(self.personne, 1, employe=self.barista)[0]
        self.simultanement([
            lambda: annuler_operation(ligne.pk, self.barista),
            lambda: ajouter_cafes(self.personne, 1, "prepaye", employe=self.barista),
        ])
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_prepayes, self.personne.nombre_cafes_gratuits), (19, 10, 1))
        self.assertEqual(AnnulationTransaction.objects.count(), 2)

    def test_ancienne_operation_completee_et_annulee_une_seule_fois(self):
        gerant = creer_employe("gerant-concurrent", "Gérant")
        Client.objects.filter(pk=self.personne.pk).update(nombre_cafes_achetes=10, nombre_cafes_gratuits=1)
        achat = TransactionCafe.objects.create(client=self.personne, quantite=1, type_transaction="achat")
        gratuit = TransactionCafe.objects.create(client=self.personne, quantite=1, type_transaction="gratuit")
        effets = {achat.pk: (1, 0, 0), gratuit.pk: (0, 0, 1)}
        resultat = self.simultanement([
            lambda: annuler_operation(achat.pk, gerant, effets),
            lambda: annuler_operation(gratuit.pk, gerant, effets),
        ])
        self.assertEqual(sorted(resultat), [0, 2])
        achat.refresh_from_db()
        gratuit.refresh_from_db()
        self.assertEqual(achat.operation_id, gratuit.operation_id)
        self.assertIsNone(achat.employe_id)
        self.assertIsNone(gratuit.employe_id)
        self.assertEqual(AnnulationTransaction.objects.count(), 2)
        self.personne.refresh_from_db()
        self.assertEqual((self.personne.nombre_cafes_achetes, self.personne.nombre_cafes_gratuits), (9, 0))
