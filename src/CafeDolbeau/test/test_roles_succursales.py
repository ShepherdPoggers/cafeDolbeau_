from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from ..models import AffectationEmployeSuccursale, AnnulationTransaction, Client, Employe, Succursale, TransactionCafe
from ..permissions import PERMISSION_PROPRIETAIRE, peut_annuler
from ..services import ajouter_cafes, annuler_operation, preparer_annulation
from .test_annulations import creer_employe


class PerimetresTransactionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s2 = Succursale.objects.create(nom="Deuxième café")
        cls.s3 = Succursale.objects.create(nom="Troisième café")
        cls.proprietaire = creer_employe("proprietaire-perimetres", "Propriétaire")
        cls.gerant = creer_employe("gerant-perimetres", "Gérant")
        cls.barista = creer_employe("barista-perimetres")
        cls.autre = creer_employe("autre-perimetres")
        for employe in (cls.gerant, cls.barista):
            AffectationEmployeSuccursale.objects.create(employe_id=employe.pk, succursale=cls.s2)
        cls.personne = Client.objects.create(nom_complet="Client du réseau", telephone="418-555-1000")

    def operation(self, auteur=None, succursale_id=1, quantite=1):
        return ajouter_cafes(self.personne, quantite, employe=auteur or self.proprietaire, succursale_id=succursale_id)

    def annulation_url(self, ligne, courante=1):
        return reverse("annuler_transaction", args=[courante, self.personne.pk, ligne.pk])

    def test_entree_sans_caisse_et_anciennes_routes_sans_mutation(self):
        self.client.force_login(self.barista)
        response = self.client.get(reverse("accueil"))
        self.assertContains(response, "Deuxième café")
        self.assertNotContains(response, "Troisième café")
        self.assertNotContains(response, 'name="quantite"')
        self.assertEqual(self.client.post(reverse("accueil"), {"quantite": 1}).status_code, 405)
        self.assertEqual(self.client.post(f"/clients/{self.personne.pk}/cafes/", {"quantite": 1}).status_code, 404)
        self.assertFalse(TransactionCafe.objects.exists())

    def test_caisse_url_persistante_et_post_forge_ignore(self):
        self.client.force_login(self.barista)
        url = reverse("ajouter_cafes", args=[self.s2.pk, self.personne.pk])
        response = self.client.post(url, {"quantite": 1, "succursale_id": self.s3.pk}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        ligne = TransactionCafe.objects.get()
        self.assertEqual(ligne.succursale_id, self.s2.pk)
        self.assertIn(self.annulation_url(ligne, self.s2.pk), response.json()["historique"])
        self.assertContains(self.client.get(url), "Succursale : Deuxième café")
        accueil = reverse("accueil_succursale", args=[self.s2.pk])
        recherche = self.client.get(accueil, {"q": "Client du réseau", "partiel": "recherche"})
        self.assertContains(recherche, url)
        self.assertRedirects(self.client.post(url, {"quantite": 1}), url)

    def test_caisse_interdite_et_service_sans_affectation_refusent(self):
        self.client.force_login(self.barista)
        url = reverse("ajouter_cafes", args=[self.s3.pk, self.personne.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"quantite": 1}).status_code, 403)
        with self.assertRaises(PermissionDenied):
            self.operation(self.barista, self.s3.pk)
        self.assertFalse(TransactionCafe.objects.exists())
        with self.assertRaises(TypeError):
            ajouter_cafes(self.personne, 1, employe=self.barista)

    def test_proprietaire_sans_affectation_accede_a_toute_nouvelle_succursale(self):
        self.proprietaire.affectations_succursales.all().delete()
        nouvelle = Succursale.objects.create(nom="Nouveau café")
        self.assertFalse(self.proprietaire.is_superuser)
        self.assertTrue(self.proprietaire.has_perm(PERMISSION_PROPRIETAIRE))
        ligne = self.operation(self.proprietaire, nouvelle.pk)[0]
        self.assertEqual(annuler_operation(ligne.pk, self.proprietaire), 1)
        self.client.force_login(self.proprietaire)
        self.assertEqual(self.client.get(reverse("accueil_succursale", args=[nouvelle.pk])).status_code, 200)

    def test_historique_global_dix_lignes_et_droits_selon_caisse_et_auteur(self):
        premiere = self.operation(self.barista)[0]
        seconde = self.operation(self.barista, self.s2.pk)[0]
        autre = self.operation(self.autre)[0]
        distante = self.operation(self.proprietaire, self.s3.pk)[0]
        self.client.force_login(self.barista)
        response = self.client.get(reverse("ajouter_cafes", args=[1, self.personne.pk]))
        historique = {ligne.pk: ligne for ligne in response.context["transactions"]}
        self.assertEqual(set(historique), {premiere.pk, seconde.pk, autre.pk, distante.pk})
        self.assertTrue(historique[premiere.pk].annulation_disponible)
        for ligne in (seconde, autre, distante):
            self.assertFalse(historique[ligne.pk].annulation_disponible)
            self.assertEqual(self.client.get(self.annulation_url(ligne)).status_code, 403)
        self.assertEqual(self.client.get(self.annulation_url(seconde, self.s2.pk)).status_code, 200)
        for _ in range(11):
            self.operation(self.barista)
        response = self.client.get(reverse("ajouter_cafes", args=[1, self.personne.pk]))
        self.assertEqual(len(response.context["transactions"]), 10)
        with self.assertRaises(PermissionDenied):
            annuler_operation(premiere.pk, self.barista, succursale_id=1)
        self.assertFalse(AnnulationTransaction.objects.exists())

    def test_gerant_annule_tout_son_perimetre_et_pas_les_autres_succursales(self):
        locale = self.operation(self.barista, self.s2.pk)[0]
        distante = self.operation(self.proprietaire, self.s3.pk)[0]
        self.client.force_login(self.gerant)
        url = self.annulation_url(locale)
        confirmation = self.client.get(url).context["confirmation"]
        self.assertEqual(self.client.post(url, {"action": "confirmer", "confirmation": confirmation}).status_code, 302)
        self.assertTrue(TransactionCafe.objects.get(pk=locale.pk).annulee)
        self.assertEqual(self.client.get(self.annulation_url(distante)).status_code, 403)
        with self.assertRaises(PermissionDenied):
            annuler_operation(distante.pk, self.gerant)
        liste = self.client.get(reverse("admin:CafeDolbeau_transactioncafe_changelist"))
        self.assertEqual(list(liste.context["cl"].result_list), [locale])
        self.assertEqual(self.client.get(reverse("admin:CafeDolbeau_transactioncafe_change", args=[distante.pk])).status_code, 302)

    def test_confirmation_liee_a_la_caisse_et_retrait_affectation_verifie(self):
        ligne = self.operation(self.barista)[0]
        self.client.force_login(self.barista)
        url = self.annulation_url(ligne)
        jeton = self.client.get(url).context["confirmation"]
        self.assertEqual(self.client.post(self.annulation_url(ligne, self.s2.pk), {
            "action": "confirmer", "confirmation": jeton,
        }).status_code, 403)
        self.barista.affectations_succursales.filter(succursale_id=1).delete()
        self.assertEqual(self.client.post(url, {"action": "confirmer", "confirmation": jeton}).status_code, 403)
        with self.assertRaises(PermissionDenied):
            annuler_operation(ligne.pk, self.barista, succursale_id=1)
        self.assertFalse(AnnulationTransaction.objects.exists())

    def test_toutes_les_lignes_sont_verifiees_avant_annulation(self):
        lignes = self.operation(self.barista, quantite=10)
        self.assertEqual(len(lignes), 2)
        TransactionCafe.objects.filter(pk=lignes[1].pk).update(succursale_id=self.s3.pk)
        avant = list(Client.objects.values())
        for acteur in (self.barista, self.gerant):
            with self.subTest(acteur=acteur), self.assertRaises(PermissionDenied):
                annuler_operation(lignes[0].pk, acteur, succursale_id=1)
        self.assertEqual(list(Client.objects.values()), avant)
        self.assertFalse(AnnulationTransaction.objects.exists())

    def test_selection_ancienne_hors_perimetre_refusee(self):
        locale = TransactionCafe.objects.create(client=self.personne, quantite=1)
        distante = TransactionCafe.objects.create(client=self.personne, quantite=1, succursale=self.s3)
        with self.assertRaises(PermissionDenied):
            preparer_annulation(locale, self.gerant, {locale.pk: (1, 0, 0), distante.pk: (1, 0, 0)})
        self.assertFalse(AnnulationTransaction.objects.exists())

    def test_rapports_et_exports_reserves_provisoirement_au_proprietaire(self):
        for acteur, statut in ((self.proprietaire, 200), (self.gerant, 403), (self.barista, 403)):
            self.client.force_login(acteur)
            for nom in ("rapports", "rapport_excel"):
                with self.subTest(acteur=acteur, nom=nom):
                    self.assertEqual(self.client.get(reverse(nom)).status_code, statut)


@override_settings(AUTH_PASSWORD_VALIDATORS=[])
class GestionAffectationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.proprietaire = creer_employe("proprietaire-affectations", "Propriétaire")
        cls.gerant = creer_employe("gerant-affectations", "Gérant")
        cls.barista = creer_employe("barista-affectations")
        cls.externe = Succursale.objects.create(nom="Succursale hors périmètre")
        AffectationEmployeSuccursale.objects.create(employe_id=cls.barista.pk, succursale=cls.externe)
        cls.admin = Employe.objects.create_superuser("superuser-protege")

    def creation(self, nom="nouveau", role="Barista", succursales=(1,)):
        return {"username": nom, "role": Group.objects.get(name=role).pk,
                "password1": "123", "password2": "123", "succursales": list(succursales)}

    def test_proprietaire_cree_gerant_et_gere_ses_affectations(self):
        self.client.force_login(self.proprietaire)
        url = reverse("admin:CafeDolbeau_employe_add")
        response = self.client.post(url, self.creation(role="Gérant", succursales=(1, self.externe.pk)))
        self.assertEqual(response.status_code, 302)
        compte = Employe.objects.get(username="nouveau")
        self.assertFalse(compte.is_superuser)
        self.assertEqual(set(compte.affectations_succursales.values_list("succursale_id", flat=True)), {1, self.externe.pk})
        detail = reverse("admin:CafeDolbeau_employe_change", args=[compte.pk])
        self.assertEqual(self.client.post(detail, {
            "username": compte.username, "role": Group.objects.get(name="Propriétaire").pk,
            "is_active": "on", "succursales": [], "is_superuser": "on", "is_staff": "on",
        }).status_code, 302)
        compte.refresh_from_db()
        self.assertTrue(compte.has_perm(PERMISSION_PROPRIETAIRE))
        self.assertFalse(compte.is_superuser)
        self.assertFalse(compte.is_staff)
        self.assertEqual(list(compte.groups.values_list("name", flat=True)), ["Propriétaire"])

    def test_gerant_ne_peut_pas_affecter_hors_perimetre_meme_en_post_forge(self):
        self.client.force_login(self.gerant)
        url = reverse("admin:CafeDolbeau_employe_add")
        response = self.client.post(url, self.creation(succursales=(self.externe.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertIn("succursales", response.context["adminform"].form.errors)
        self.assertFalse(Employe.objects.filter(username="nouveau").exists())
        for role in ("Gérant", "Propriétaire"):
            response = self.client.post(url, self.creation(role=role))
            self.assertIn("role", response.context["adminform"].form.errors)
        self.assertFalse(Employe.objects.filter(username="nouveau").exists())

    def test_gerant_preserve_autres_affectations_role_et_identifiants(self):
        self.client.force_login(self.gerant)
        self.barista.set_password("ancien-secret")
        self.barista.save()
        url = reverse("admin:CafeDolbeau_employe_change", args=[self.barista.pk])
        response = self.client.post(url, {
            "username": "pirate", "role": Group.objects.get(name="Propriétaire").pk,
            "is_superuser": "on", "is_active": "", "succursales": [], "password": "faux",
        })
        self.assertEqual(response.status_code, 302)
        self.barista.refresh_from_db()
        self.assertEqual(self.barista.username, "barista-affectations")
        self.assertTrue(self.barista.check_password("ancien-secret"))
        self.assertTrue(self.barista.is_active)
        self.assertFalse(self.barista.is_superuser)
        self.assertEqual(list(self.barista.groups.values_list("name", flat=True)), ["Barista"])
        self.assertEqual(list(self.barista.affectations_succursales.values_list("succursale_id", flat=True)), [self.externe.pk])
        self.assertEqual(self.client.post(url, {"succursales": [1]}).status_code, 302)
        self.assertEqual(set(self.barista.affectations_succursales.values_list("succursale_id", flat=True)), {1, self.externe.pk})
        self.assertEqual(self.client.get(reverse("admin:auth_user_password_change", args=[self.barista.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:CafeDolbeau_employe_change", args=[self.proprietaire.pk]), follow=True).status_code, 200)
        self.assertTrue(Employe.objects.filter(pk=self.proprietaire.pk, groups__name="Propriétaire").exists())

    def test_proprietaire_ne_peut_pas_modifier_les_comptes_techniques(self):
        self.client.force_login(self.proprietaire)
        url = reverse("admin:CafeDolbeau_employe_change", args=[self.admin.pk])
        self.assertEqual(self.client.post(url, self.creation(nom="superuser-modifie")).status_code, 302)
        self.assertEqual(self.client.get(reverse("admin:auth_user_password_change", args=[self.admin.pk])).status_code, 404)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.username, "superuser-protege")
        self.assertTrue(self.admin.is_superuser)

    def test_unicite_affectation_et_retrait_sans_perte_historique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AffectationEmployeSuccursale.objects.create(employe_id=self.barista.pk, succursale_id=1)
        client = Client.objects.create(nom_complet="Camille", telephone="111")
        ligne = ajouter_cafes(client, 1, employe=self.barista, succursale_id=1)[0]
        self.barista.affectations_succursales.filter(succursale_id=1).delete()
        self.assertTrue(TransactionCafe.objects.filter(pk=ligne.pk, employe_id=self.barista.pk, succursale_id=1).exists())


class MigrationAffectationsTests(TransactionTestCase):
    def test_preserve_comptes_historique_et_roles_et_affecte_les_employes_existants_a_un(self):
        executor = MigrationExecutor(connection)
        dernier = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(dernier))
        avant = [("CafeDolbeau", "0017_succursales")]
        executor.migrate(avant)
        apps = executor.loader.project_state(avant).apps
        # TransactionTestCase vide les données des migrations entre les tests.
        apps.get_model("CafeDolbeau", "Succursale").objects.get_or_create(
            pk=1, defaults={"nom": "Succursale #1"},
        )
        User = apps.get_model("auth", "User")
        Groupe = apps.get_model("auth", "Group")
        AncienClient = apps.get_model("CafeDolbeau", "Client")
        AncienneTransaction = apps.get_model("CafeDolbeau", "TransactionCafe")
        employes = []
        for role, actif in (("Barista", True), ("Gérant", False)):
            groupe, _ = Groupe.objects.get_or_create(name=role)
            compte = User.objects.create(username="ancien-" + role, password="hash-conserve", is_active=actif)
            compte.groups.add(groupe)
            employes.append(compte.pk)
        sans_role = User.objects.create(username="sans-role-migration")
        client = AncienClient.objects.create(nom_complet="Migration", telephone="111", nombre_cafes_achetes=5)
        AncienneTransaction.objects.create(client=client, quantite=5, employe_id=employes[0])
        comptes = list(User.objects.order_by("pk").values())
        lignes = list(AncienneTransaction.objects.values())
        clients = list(AncienClient.objects.values())
        MigrationExecutor(connection).migrate(dernier)
        self.assertEqual(list(Employe.objects.order_by("pk").values()), comptes)
        self.assertEqual(list(Client.objects.values()), clients)
        self.assertEqual(list(TransactionCafe.objects.values()), lignes)
        self.assertEqual(set(AffectationEmployeSuccursale.objects.values_list("employe_id", "succursale_id")), {(pk, 1) for pk in employes})
        self.assertFalse(AffectationEmployeSuccursale.objects.filter(employe_id=sans_role.pk).exists())
        self.assertFalse(Employe.objects.filter(groups__name="Propriétaire").exists())
        self.assertEqual(set(Group.objects.get(name="Propriétaire").permissions.filter(
            content_type__model="employe",
        ).values_list("codename", flat=True)), {"acces_base", "acces_gerant", "acces_proprietaire"})
