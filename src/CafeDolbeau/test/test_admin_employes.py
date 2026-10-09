from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client as Navigateur, TestCase, override_settings
from django.urls import reverse

from ..models import Employe
from ..permissions import PERMISSION_BASE, PERMISSION_GERANT


class AdministrationEmployesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.administrateur = get_user_model().objects.create_superuser("administrateur")

    def setUp(self):
        self.client.force_login(self.administrateur)
        self.url_ajout = reverse("admin:CafeDolbeau_employe_add")

    def donnees_creation(self, username="nouvel-employe", role="Barista"):
        return {
            "username": username,
            "role": Group.objects.get(name=role).pk,
            "password1": "123",
            "password2": "123",
        }

    def test_administration_affiche_employes_et_les_comptes_existants(self):
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Employés")
        self.assertContains(response, reverse("admin:CafeDolbeau_employe_changelist"))
        self.assertNotContains(response, "Utilisateurs")
        self.assertNotContains(response, "/admin/auth/user/")
        response = self.client.get(reverse("admin:CafeDolbeau_employe_changelist"))
        self.assertContains(response, "administrateur")
        self.assertContains(response, "Gérant")

    def test_formulaire_creation_demande_un_role_obligatoire(self):
        response = self.client.get(self.url_ajout)
        self.assertContains(response, "Ajouter employé")
        form = response.context["adminform"].form
        self.assertTrue(form.fields["role"].required)
        self.assertEqual(set(form.fields["role"].queryset.values_list("name", flat=True)), {"Barista", "Gérant"})
        self.assertFalse(form["role"].value())

    @override_settings(AUTH_PASSWORD_VALIDATORS=[])
    def test_creation_des_deux_roles_et_connexion_immediate(self):
        for role in ("Barista", "Gérant"):
            with self.subTest(role=role):
                username = "nouveau-barista" if role == "Barista" else "nouveau-gerant"
                response = self.client.post(self.url_ajout, self.donnees_creation(username, role))
                employe = Employe.objects.get(username=username)
                self.assertRedirects(response, reverse("admin:CafeDolbeau_employe_change", args=[employe.pk]))
                self.assertEqual(list(employe.groups.values_list("name", flat=True)), [role])
                self.assertTrue(employe.check_password("123"))
                self.assertNotEqual(employe.password, "123")
                self.assertTrue(employe.is_active)
                self.assertFalse(employe.is_superuser)
                self.assertTrue(employe.has_perm(PERMISSION_BASE))
                self.assertEqual(employe.has_perm(PERMISSION_GERANT), role == "Gérant")
                navigateur = Navigateur()
                response = navigateur.post(reverse("connexion"), {
                    "username": username, "password": "123",
                })
                self.assertRedirects(response, reverse("accueil"))
                response = navigateur.get(reverse("admin:index"), follow=True)
                self.assertEqual(response.status_code, 200 if role == "Gérant" else 403)

    def test_role_manquant_invalide_ou_autre_groupe_refuse_sans_creer_de_compte(self):
        autre_groupe = Group.objects.create(name="Autre groupe")
        for role in (None, "", "invalide", "999999", autre_groupe.pk):
            with self.subTest(role=role):
                donnees = self.donnees_creation()
                if role is None:
                    donnees.pop("role")
                else:
                    donnees["role"] = role
                response = self.client.post(self.url_ajout, donnees)
                self.assertEqual(response.status_code, 200)
                self.assertIn("role", response.context["adminform"].form.errors)
                self.assertFalse(Employe.objects.filter(username="nouvel-employe").exists())

    def test_mots_de_passe_vides_ou_differents_refuses(self):
        for first, second in (("", ""), ("123", "456")):
            with self.subTest(first=first, second=second):
                donnees = self.donnees_creation()
                donnees.update(password1=first, password2=second)
                response = self.client.post(self.url_ajout, donnees)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["adminform"].form.errors)
                self.assertFalse(Employe.objects.filter(username="nouvel-employe").exists())

    @override_settings(AUTH_PASSWORD_VALIDATORS=[])
    def test_champs_non_proposes_ne_donnent_pas_de_permissions_supplementaires(self):
        donnees = self.donnees_creation()
        donnees.update(
            is_superuser="on", is_staff="on",
            groups=[Group.objects.get(name="Gérant").pk],
        )
        self.client.post(self.url_ajout, donnees)
        employe = Employe.objects.get(username="nouvel-employe")
        self.assertFalse(employe.is_superuser)
        self.assertFalse(employe.is_staff)
        self.assertEqual(list(employe.groups.values_list("name", flat=True)), ["Barista"])
        self.assertFalse(employe.has_perm(PERMISSION_GERANT))

    def test_modification_du_role_preserve_le_mot_de_passe_et_les_autres_groupes(self):
        employe = Employe.objects.create_user("barista", password="123")
        ancien_mot_de_passe = employe.password
        autre_groupe = Group.objects.create(name="Équipe de soirée")
        employe.groups.add(Group.objects.get(name="Barista"), autre_groupe)
        url = reverse("admin:CafeDolbeau_employe_change", args=[employe.pk])
        response = self.client.get(url)
        self.assertEqual(
            response.context["adminform"].form["role"].value(),
            Group.objects.get(name="Barista").pk,
        )
        for role in ("Gérant", "Barista"):
            with self.subTest(role=role):
                response = self.client.post(url, {
                    "username": "barista", "role": Group.objects.get(name=role).pk,
                    "is_active": "on", "_save": "Enregistrer",
                })
                self.assertRedirects(response, reverse("admin:CafeDolbeau_employe_changelist"))
                employe = Employe.objects.get(pk=employe.pk)
                self.assertEqual(set(employe.groups.values_list("name", flat=True)), {role, "Équipe de soirée"})
                self.assertEqual(employe.password, ancien_mot_de_passe)
                self.assertEqual(employe.has_perm(PERMISSION_GERANT), role == "Gérant")

    def test_changement_de_mot_de_passe_reste_disponible(self):
        employe = Employe.objects.create_user("barista", password="123")
        employe.groups.add(Group.objects.get(name="Barista"))
        url = reverse("admin:auth_user_password_change", args=[employe.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {
            "password1": "456", "password2": "456", "usable_password": "true",
        })
        self.assertRedirects(response, reverse("admin:CafeDolbeau_employe_change", args=[employe.pk]))
        employe.refresh_from_db()
        self.assertTrue(employe.check_password("456"))

    def test_employes_ordinaires_ne_peuvent_pas_creer_de_comptes(self):
        for role in ("Barista", "Gérant"):
            with self.subTest(role=role):
                employe = Employe.objects.create_user("employe-" + role)
                employe.groups.add(Group.objects.get(name=role))
                navigateur = Navigateur()
                navigateur.force_login(employe)
                response = navigateur.post(self.url_ajout, self.donnees_creation(), follow=True)
                self.assertEqual(response.status_code, 403)
        self.assertFalse(Employe.objects.filter(username="nouvel-employe").exists())
