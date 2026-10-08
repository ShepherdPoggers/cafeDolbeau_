from urllib.parse import urlencode

from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.models import Group, Permission
from django.http import HttpResponse
from django.test import Client as Navigateur, TestCase, override_settings
from django.urls import path, reverse

from config.urls import urlpatterns as application_urls

from .models import Client, Employe, TransactionCafe
from .permissions import PERMISSION_BASE, PERMISSION_GERANT, gerant_requis


def nouvelle_vue(request):
    return HttpResponse("Fonction de base")


@gerant_requis
def fonction_gerant(request):
    return HttpResponse("Fonction de gérant")


urlpatterns = [
    *application_urls,
    path("nouvelle-fonction/", nouvelle_vue, name="nouvelle_fonction"),
    path("gestion/", fonction_gerant, name="fonction_gerant"),
]


class AuthentificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mot_de_passe = "Cafe-Dolbeau-test-2026!"
        User = get_user_model()
        cls.barista = User.objects.create_user("barista", password=cls.mot_de_passe)
        cls.gerant = User.objects.create_user("gerant", password=cls.mot_de_passe)
        cls.sans_role = User.objects.create_user("sans-role", password=cls.mot_de_passe)
        cls.inactif = User.objects.create_user(
            "inactif", password=cls.mot_de_passe, is_active=False,
        )
        cls.superutilisateur = User.objects.create_superuser(
            "administrateur", password=cls.mot_de_passe,
        )
        baristas = Group.objects.get(name="Barista")
        cls.barista.groups.add(baristas)
        cls.inactif.groups.add(baristas)
        cls.gerant.groups.add(Group.objects.get(name="Gérant"))
        cls.personne = Client.objects.create(
            nom_complet="Client confidentiel", courriel="client@example.com",
        )

    def connexion_url(self, destination):
        return reverse("connexion") + "?" + urlencode({"next": destination}, safe="/")

    def test_roles_crees_avec_les_permissions_attendues(self):
        self.assertTrue(self.barista.has_perm(PERMISSION_BASE))
        self.assertFalse(self.barista.has_perm(PERMISSION_GERANT))
        self.assertFalse(self.barista.has_perm("CafeDolbeau.change_client"))
        self.assertTrue(self.gerant.has_perm(PERMISSION_BASE))
        self.assertTrue(self.gerant.has_perm(PERMISSION_GERANT))
        self.assertTrue(self.gerant.has_perm("CafeDolbeau.change_client"))
        self.assertFalse(self.gerant.has_perm("auth.change_user"))
        self.assertFalse(self.gerant.has_perm("auth.change_group"))

    def test_permissions_des_roles_rattachees_aux_employes(self):
        permissions = Permission.objects.filter(
            content_type__app_label="CafeDolbeau",
            codename__in=("acces_base", "acces_gerant"),
        )
        self.assertEqual(permissions.count(), 2)
        self.assertEqual(set(permissions.values_list("content_type__model", flat=True)), {"employe"})
        self.assertEqual(
            Permission.objects.get(
                content_type__app_label="CafeDolbeau", codename="change_client",
            ).content_type.model,
            "client",
        )
        employe = Employe.objects.get(pk=self.barista.pk)
        self.assertTrue(employe.has_perm(PERMISSION_BASE))
        self.assertFalse(employe.has_perm(PERMISSION_GERANT))

    def test_pages_et_recherche_exigent_une_connexion(self):
        for url in (
            reverse("accueil"),
            reverse("accueil") + "?q=confidentiel&partiel=recherche",
            reverse("ajouter_cafes", args=[self.personne.pk]),
            reverse("ajouter_cafes", args=[self.personne.pk + 1]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, self.connexion_url(url))
                self.assertNotIn(b"client@example.com", response.content)

    def test_posts_anonymes_ne_modifient_aucune_donnee(self):
        response = self.client.post(reverse("accueil"), {
            "nom_complet": "Intrus", "telephone": "418 555-1234",
        })
        self.assertRedirects(response, self.connexion_url(reverse("accueil")))
        for asynchrone in (False, True):
            url = reverse("ajouter_cafes", args=[self.personne.pk])
            response = self.client.post(url, {"quantite": 10}, **(
                {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"} if asynchrone else {}
            ))
            self.assertRedirects(response, self.connexion_url(url))
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 0)
        self.assertEqual(TransactionCafe.objects.count(), 0)
        self.assertEqual(Client.objects.count(), 1)

    def test_connexion_accessible_et_formulaire_protege(self):
        response = self.client.get(reverse("connexion"))
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertNotContains(response, "Client confidentiel")

    def test_connexion_des_deux_roles_sans_statut_equipe(self):
        for employe in (self.barista, self.gerant):
            with self.subTest(employe=employe.username):
                self.client.logout()
                self.assertFalse(employe.is_staff)
                response = self.client.post(reverse("connexion"), {
                    "username": employe.username, "password": self.mot_de_passe,
                })
                self.assertRedirects(response, reverse("accueil"))
                self.assertEqual(self.client.session[SESSION_KEY], str(employe.pk))

    def test_connexion_revient_a_la_page_demandee(self):
        destination = reverse("ajouter_cafes", args=[self.personne.pk])
        response = self.client.post(reverse("connexion"), {
            "username": "barista", "password": self.mot_de_passe,
            "next": destination,
        })
        self.assertRedirects(response, destination)

    def test_redirection_externe_refusee(self):
        for destination in ("https://example.com/", "//example.com/"):
            with self.subTest(destination=destination):
                self.client.logout()
                response = self.client.post(reverse("connexion"), {
                    "username": "barista", "password": self.mot_de_passe,
                    "next": destination,
                })
                self.assertRedirects(response, reverse("accueil"))

    def test_mauvais_mot_de_passe_compte_inactif_et_role_manquant_refuses(self):
        for username, password in (
            ("barista", "incorrect"), ("inactif", self.mot_de_passe),
            ("sans-role", self.mot_de_passe),
        ):
            with self.subTest(username=username):
                response = self.client.post(reverse("connexion"), {
                    "username": username, "password": password,
                })
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].non_field_errors())
                self.assertNotIn(SESSION_KEY, self.client.session)

    def test_compte_sans_role_deja_connecte_refuse_en_get_et_post(self):
        self.client.force_login(self.sans_role)
        for url in (reverse("accueil"), reverse("ajouter_cafes", args=[self.personne.pk])):
            for method in (self.client.get, self.client.post):
                with self.subTest(url=url, method=method.__name__):
                    response = method(url, {"quantite": 1})
                    self.assertContains(response, "Accès refusé", status_code=403)
                    self.assertNotContains(response, "Client confidentiel", status_code=403)
        self.assertEqual(TransactionCafe.objects.count(), 0)

    def test_barista_utilise_les_fonctions_de_base(self):
        self.client.force_login(self.barista)
        response = self.client.get(reverse("accueil"))
        self.assertContains(response, "Barista")
        self.assertContains(response, "Se déconnecter")
        self.assertNotContains(response, "Administration")
        self.assertContains(response, "Client confidentiel")
        response = self.client.post(reverse("accueil"), {
            "nom_complet": "Nouveau client", "telephone": "418 555-1234",
        })
        self.assertRedirects(response, reverse("accueil"))
        response = self.client.post(reverse("ajouter_cafes", args=[self.personne.pk]), {
            "quantite": 2, "type_transaction": "achat",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["achetes"], 2)

    def test_gerant_accede_aux_fonctions_de_base_et_a_l_administration(self):
        self.client.force_login(self.gerant)
        for url in (reverse("accueil"), reverse("ajouter_cafes", args=[self.personne.pk])):
            response = self.client.get(url)
            self.assertContains(response, "Gérant")
            self.assertContains(response, "Administration")
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:CafeDolbeau_client_changelist")).status_code, 200)

    def test_barista_meme_equipe_ne_peut_pas_acceder_a_l_administration(self):
        for equipe in (False, True):
            self.barista.is_staff = equipe
            self.barista.save(update_fields=["is_staff"])
            self.client.force_login(self.barista)
            for url in (
                reverse("admin:index"), reverse("admin:login"),
                reverse("admin:CafeDolbeau_client_changelist"),
            ):
                with self.subTest(equipe=equipe, url=url):
                    response = self.client.get(url, follow=True)
                    self.assertContains(response, "Accès refusé", status_code=403)
                    self.assertNotContains(response, "Client confidentiel", status_code=403)
            response = self.client.post(
                reverse("admin:CafeDolbeau_client_delete", args=[self.personne.pk]),
                {"post": "yes"}, follow=True,
            )
            self.assertEqual(response.status_code, 403)
        self.assertTrue(Client.objects.filter(pk=self.personne.pk).exists())

    def test_administration_anonyme_utilise_la_connexion_commune(self):
        response = self.client.get(reverse("admin:index"), follow=True)
        self.assertTemplateUsed(response, "registration/login.html")
        self.assertEqual(response.context["next"], reverse("admin:index"))
        response = self.client.post(reverse("connexion"), {
            "username": "gerant", "password": self.mot_de_passe,
            "next": reverse("admin:index"),
        })
        self.assertRedirects(response, reverse("admin:index"))

    def test_superutilisateur_existant_conserve_ses_acces(self):
        response = self.client.post(reverse("connexion"), {
            "username": "administrateur", "password": self.mot_de_passe,
        })
        self.assertRedirects(response, reverse("accueil"))
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:CafeDolbeau_employe_changelist")).status_code, 200)

    def test_gerant_ne_peut_pas_modifier_les_comptes_ou_les_permissions(self):
        self.client.force_login(self.gerant)
        for url in (
            reverse("admin:CafeDolbeau_employe_changelist"),
            reverse("admin:CafeDolbeau_employe_change", args=[self.barista.pk]),
            reverse("admin:auth_group_change", args=[Group.objects.get(name="Gérant").pk]),
        ):
            for method in (self.client.get, self.client.post):
                with self.subTest(url=url, method=method.__name__):
                    self.assertEqual(method(url, {"is_superuser": "on"}).status_code, 403)
        self.barista.refresh_from_db()
        self.assertFalse(self.barista.is_superuser)

    def test_deconnexion_post_et_protection_apres_deconnexion(self):
        self.client.force_login(self.barista)
        self.assertEqual(self.client.get(reverse("deconnexion")).status_code, 405)
        self.assertIn(SESSION_KEY, self.client.session)
        response = self.client.post(reverse("deconnexion"))
        self.assertRedirects(response, reverse("connexion"))
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertRedirects(
            self.client.get(reverse("accueil")), self.connexion_url(reverse("accueil")),
        )

    def test_connexion_et_deconnexion_exigent_un_jeton_csrf(self):
        navigateur = Navigateur(enforce_csrf_checks=True)
        response = navigateur.post(reverse("connexion"), {
            "username": "barista", "password": self.mot_de_passe,
        })
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(SESSION_KEY, navigateur.session)
        navigateur.force_login(self.barista)
        self.assertEqual(navigateur.post(reverse("deconnexion")).status_code, 403)
        self.assertIn(SESSION_KEY, navigateur.session)
        navigateur.get(reverse("accueil"))
        response = navigateur.post(reverse("deconnexion"), {
            "csrfmiddlewaretoken": navigateur.cookies["csrftoken"].value,
        })
        self.assertRedirects(response, reverse("connexion"))

    def test_retrait_du_role_bloque_la_session_existante(self):
        self.client.force_login(self.barista)
        self.barista.groups.clear()
        self.assertEqual(self.client.get(reverse("accueil")).status_code, 403)
        response = self.client.post(reverse("ajouter_cafes", args=[self.personne.pk]), {"quantite": 1})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(TransactionCafe.objects.count(), 0)

    def test_pages_privees_ne_sont_pas_mises_en_cache(self):
        self.client.force_login(self.barista)
        for url in (reverse("accueil"), reverse("ajouter_cafes", args=[self.personne.pk])):
            self.assertIn("no-store", self.client.get(url).headers["Cache-Control"])

    @override_settings(ROOT_URLCONF=__name__)
    def test_nouvelle_vue_est_privee_par_defaut(self):
        url = reverse("nouvelle_fonction")
        self.assertRedirects(self.client.get(url), self.connexion_url(url))

    @override_settings(ROOT_URLCONF=__name__)
    def test_futures_fonctions_gerant_protegees_en_get_et_post(self):
        url = reverse("fonction_gerant")
        self.assertRedirects(self.client.get(url), self.connexion_url(url))
        for employe, status in ((self.barista, 403), (self.gerant, 200)):
            self.client.force_login(employe)
            for method in (self.client.get, self.client.post):
                with self.subTest(employe=employe.username, method=method.__name__):
                    self.assertEqual(method(url).status_code, status)
