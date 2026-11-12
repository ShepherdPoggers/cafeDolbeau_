from uuid import uuid4

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from ..models import AffectationEmployeSuccursale, AnnulationTransaction, Client, Employe, Succursale, TransactionCafe
from ..services import ajouter_cafes, annuler_operation, fusionner_clients, supprimer_clients
from .test_annulations import creer_employe


class SuccursaleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.barista = creer_employe("barista-succursales")
        cls.gerant = creer_employe("gerant-succursales", "Gérant")
        cls.autre = Succursale.objects.create(nom="Autre succursale")
        for employe in (cls.barista, cls.gerant):
            AffectationEmployeSuccursale.objects.create(employe_id=employe.pk, succursale=cls.autre)
        cls.personne = Client.objects.create(nom_complet="Camille", telephone="418 555-1000")

    def test_nom_obligatoire_et_limite_a_200_caracteres(self):
        for nom in ("", "x" * 201):
            with self.subTest(nom=nom), self.assertRaises(ValidationError):
                Succursale(nom=nom).full_clean()
        self.assertEqual(str(self.autre), "Autre succursale")

    def test_creation_directe_et_service_utilisent_la_succursale_un_par_defaut(self):
        directe = TransactionCafe.objects.create(client=self.personne, quantite=1)
        self.assertEqual(directe.succursale_id, 1)
        Client.objects.filter(pk=self.personne.pk).update(nombre_cafes_fidelite=9, nombre_cafes_achetes=9)
        lignes = ajouter_cafes(self.personne, 1, employe=self.barista, succursale_id=1)
        self.assertEqual({ligne.type_transaction for ligne in lignes}, {"achat", "gratuit"})
        self.assertEqual({ligne.succursale_id for ligne in lignes}, {1})

    def test_toutes_les_lignes_dune_operation_utilisent_la_succursale_choisie(self):
        for type_transaction, nombre_lignes in (("achat", 2), ("prepaye", 1), ("utilise", 3)):
            with self.subTest(type_transaction=type_transaction):
                Client.objects.filter(pk=self.personne.pk).update(
                    nombre_cafes_fidelite=9, nombre_cafes_achetes=9, nombre_cafes_prepayes=2, nombre_cafes_gratuits=1,
                )
                lignes = ajouter_cafes(
                    self.personne, 13, type_transaction, employe=self.barista,
                    succursale_id=self.autre.pk,
                )
                self.assertEqual(len(lignes), nombre_lignes)
                self.assertEqual({ligne.succursale_id for ligne in lignes}, {self.autre.pk})
                self.assertEqual(len({ligne.operation_id for ligne in lignes}), 1)
                self.assertEqual(self.autre.transactions_cafe.filter(
                    operation_id=lignes[0].operation_id,
                ).count(), nombre_lignes)

    def test_fidelite_partagee_entre_les_succursales(self):
        ajouter_cafes(self.personne, 9, employe=self.barista, succursale_id=1)
        lignes = ajouter_cafes(self.personne, 1, employe=self.barista, succursale_id=self.autre.pk)
        self.assertEqual({ligne.type_transaction for ligne in lignes}, {"achat", "gratuit"})
        self.assertEqual({ligne.succursale_id for ligne in lignes}, {self.autre.pk})
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 10)
        self.assertEqual(self.personne.nombre_cafes_gratuits, 1)

    def test_succursale_invalide_ne_modifie_pas_lhistorique_ni_les_soldes(self):
        clients = list(Client.objects.values())
        for identifiant in (999999, None):
            for type_transaction in ("achat", "prepaye", "utilise"):
                with self.subTest(succursale=identifiant, type_transaction=type_transaction):
                    with self.assertRaises(ValidationError) as erreur:
                        ajouter_cafes(
                            self.personne, 10, type_transaction, employe=self.barista,
                            succursale_id=identifiant,
                        )
                    self.assertIn("succursale", erreur.exception.message_dict)
                    self.assertEqual(list(Client.objects.values()), clients)
                    self.assertFalse(TransactionCafe.objects.exists())

    def test_contraintes_de_base_et_protection_de_la_succursale_referencee(self):
        for identifiant in (None, 999999):
            with self.subTest(succursale=identifiant):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    TransactionCafe.objects.create(
                        client=self.personne, quantite=1, succursale_id=identifiant,
                    )
                    connection.check_constraints()
        ajouter_cafes(self.personne, 1, employe=self.barista, succursale_id=self.autre.pk)
        with self.assertRaises(ProtectedError):
            self.autre.delete()

    def test_annulation_fusion_et_suppression_conservent_la_succursale(self):
        ligne = ajouter_cafes(
            self.personne, 1, employe=self.barista, succursale_id=self.autre.pk,
        )[0]
        annuler_operation(ligne.pk, self.barista, succursale_id=self.autre.pk)
        destination = Client.objects.create(nom_complet="Alex", telephone="418 555-2000")
        fusionner_clients(self.personne.pk, destination.pk, employe=self.gerant)
        ajouter_cafes(destination, 1, employe=self.barista, succursale_id=1)
        supprimer_clients([destination.pk], employe=self.gerant)
        ligne.refresh_from_db()
        self.assertEqual(ligne.succursale_id, self.autre.pk)
        self.assertEqual(ligne.client_id, Client.ID_SUPPRIME)
        self.assertTrue(ligne.annulee)

    def test_formulaire_actuel_ignore_une_succursale_envoyee_et_utilise_un(self):
        self.client.force_login(self.barista)
        response = self.client.post(reverse("ajouter_cafes", args=[1, self.personne.pk]), {
            "quantite": 1, "type_transaction": "achat", "succursale_id": self.autre.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TransactionCafe.objects.get().succursale_id, 1)


class AdministrationSuccursalesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.administrateur = Employe.objects.create_superuser("admin-succursales")
        cls.gerant = creer_employe("gerant-admin-succursales", "Gérant")
        cls.barista = creer_employe("barista-admin-succursales")
        cls.autre = Succursale.objects.create(nom="Autre succursale")
        for employe in (cls.barista, cls.gerant):
            AffectationEmployeSuccursale.objects.create(employe_id=employe.pk, succursale=cls.autre)
        cls.personne = Client.objects.create(nom_complet="Camille", telephone="418 555-1000")

    def test_superutilisateur_peut_consulter_creer_et_renommer_sans_supprimer(self):
        self.client.force_login(self.administrateur)
        liste = reverse("admin:CafeDolbeau_succursale_changelist")
        self.assertContains(self.client.get(reverse("admin:index")), liste)
        self.assertContains(self.client.get(liste), "Succursale #1")
        response = self.client.post(reverse("admin:CafeDolbeau_succursale_add"), {"nom": "Nouvelle succursale"})
        self.assertRedirects(response, liste)
        nouvelle = Succursale.objects.get(nom="Nouvelle succursale")
        self.assertGreater(nouvelle.pk, 1)
        detail = reverse("admin:CafeDolbeau_succursale_change", args=[1])
        self.assertRedirects(self.client.post(detail, {"nom": "Dolbeau"}), liste)
        self.assertEqual(Succursale.objects.get(pk=1).nom, "Dolbeau")
        self.assertNotContains(self.client.get(detail), "deletelink")
        suppression = reverse("admin:CafeDolbeau_succursale_delete", args=[nouvelle.pk])
        self.assertEqual(self.client.post(suppression, {"post": "yes"}).status_code, 403)
        self.assertTrue(Succursale.objects.filter(pk=nouvelle.pk).exists())

    def test_autres_roles_refuses_meme_avec_permissions_django_explicites(self):
        self.gerant.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="CafeDolbeau", content_type__model="succursale",
        ))
        for employe in (self.gerant, self.barista):
            self.client.force_login(employe)
            with self.subTest(employe=employe):
                for url in (
                    reverse("admin:CafeDolbeau_succursale_changelist"),
                    reverse("admin:CafeDolbeau_succursale_add"),
                    reverse("admin:CafeDolbeau_succursale_change", args=[1]),
                ):
                    self.assertEqual(self.client.get(url, follow=True).status_code, 403)
                self.assertEqual(self.client.post(reverse("admin:CafeDolbeau_succursale_add"), {
                    "nom": "Interdite",
                }, follow=True).status_code, 403)
                self.assertEqual(self.client.post(reverse("admin:CafeDolbeau_succursale_change", args=[1]), {
                    "nom": "Interdit",
                }, follow=True).status_code, 403)
        self.assertEqual(Succursale.objects.get(pk=1).nom, "Succursale #1")
        self.assertFalse(Succursale.objects.filter(nom="Interdite").exists())
        self.client.force_login(self.gerant)
        self.assertNotContains(self.client.get(reverse("admin:index")), "Succursales")

    def test_transactions_affichent_filtrent_et_protegent_la_succursale(self):
        premiere = ajouter_cafes(self.personne, 1, employe=self.barista, succursale_id=1)[0]
        seconde = ajouter_cafes(
            self.personne, 1, employe=self.barista, succursale_id=self.autre.pk,
        )[0]
        self.client.force_login(self.gerant)
        liste = reverse("admin:CafeDolbeau_transactioncafe_changelist")
        response = self.client.get(liste)
        self.assertContains(response, "Succursale #1")
        self.assertContains(response, "Autre succursale")
        response = self.client.get(liste, {"succursale__id__exact": self.autre.pk})
        self.assertEqual(list(response.context["cl"].result_list), [seconde])
        detail = reverse("admin:CafeDolbeau_transactioncafe_change", args=[premiere.pk])
        response = self.client.get(detail)
        self.assertContains(response, "Succursale #1")
        self.assertNotContains(response, 'name="succursale"')
        self.assertEqual(self.client.post(detail, {"succursale": self.autre.pk}).status_code, 403)
        premiere.refresh_from_db()
        self.assertEqual(premiere.succursale_id, 1)


class SuccursaleMigrationTests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        self.dernier_schema = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(self.dernier_schema))
        avant = [("CafeDolbeau", "0016_fusions_sans_noms")]
        executor.migrate(avant)
        self.anciens_modeles = executor.loader.project_state(avant).apps

    def test_base_vide_initialise_un_et_permet_une_deuxieme_succursale(self):
        MigrationExecutor(connection).migrate(self.dernier_schema)
        self.assertEqual(list(Succursale.objects.values_list("pk", "nom")), [(1, "Succursale #1")])
        self.assertEqual(Succursale.objects.create(nom="Deuxième succursale").pk, 2)
        MigrationExecutor(connection).migrate(self.dernier_schema)
        self.assertEqual(Succursale.objects.count(), 2)
        self.assertFalse(TransactionCafe.objects.exists())

    def test_historique_soldes_et_annulations_conserves_et_associes_a_un(self):
        AncienClient = self.anciens_modeles.get_model("CafeDolbeau", "Client")
        AncienneTransaction = self.anciens_modeles.get_model("CafeDolbeau", "TransactionCafe")
        AncienneAnnulation = self.anciens_modeles.get_model("CafeDolbeau", "AnnulationTransaction")
        User = self.anciens_modeles.get_model("auth", "User")
        employe = User.objects.create(username="migration-succursales")
        personne = AncienClient.objects.create(
            nom_complet="Camille", telephone="418 555-1000", nombre_cafes_achetes=19,
            nombre_cafes_prepayes=8, nombre_cafes_gratuits=2,
        )
        fictif = AncienClient.objects.create(pk=-1, nom_complet="Client supprimé", est_actif=False)
        for type_transaction in ("achat", "prepaye", "utilise", "gratuit"):
            ligne = AncienneTransaction.objects.create(
                client=personne, quantite=1, type_transaction=type_transaction,
                employe_id=employe.pk, operation_id=uuid4(),
                variation_achetes=1 if type_transaction == "achat" else 0,
                variation_prepayes=0, variation_gratuits=0,
            )
        AncienneAnnulation.objects.create(transaction=ligne, employe_id=employe.pk)
        AncienneTransaction.objects.create(client=fictif, quantite=2, client_origine_id=123)
        clients = list(AncienClient.objects.order_by("pk").values())
        lignes = list(AncienneTransaction.objects.order_by("pk").values())
        annulations = list(AncienneAnnulation.objects.values())

        MigrationExecutor(connection).migrate(self.dernier_schema)

        self.assertEqual(list(Client.objects.order_by("pk").values(*clients[0])), clients)
        self.assertEqual(Client.objects.get(pk=personne.pk).nombre_cafes_fidelite, 19)
        self.assertEqual(list(TransactionCafe.objects.order_by("pk").values(*lignes[0], "succursale_id")), [
            {**ligne, "succursale_id": 1} for ligne in lignes
        ])
        self.assertEqual(list(AnnulationTransaction.objects.values()), annulations)
        self.assertEqual(Succursale.objects.get(pk=1).transactions_cafe.count(), len(lignes))
        connection.check_constraints()
