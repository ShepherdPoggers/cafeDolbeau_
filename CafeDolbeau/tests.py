from django.test import TestCase
from django.urls import reverse

from .models import Client, TransactionCafe
from .services import ajouter_cafes
from unittest.mock import patch


class TransactionCafeTests(TestCase):
    def setUp(self):
        self.personne = Client.objects.create(
            nom_complet="Camille", telephone="418 555-1234", nombre_cafes_achetes=7
        )
        self.autre = Client.objects.create(nom_complet="Alex", courriel="alex@example.com")
        self.url = reverse("ajouter_cafes", args=[self.personne.pk])

    def test_page_et_bouton_recherche(self):
        response = self.client.get(reverse("accueil"), {"q": "Camille"})
        self.assertContains(response, f'action="{self.url}"')
        response = self.client.get(self.url)
        self.assertContains(response, "Aucune transaction enregistrée.")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertEqual(TransactionCafe.objects.count(), 0)

    def test_ajout_et_actualisation(self):
        response = self.client.post(self.url, {"quantite": 3}, follow=True)
        self.assertRedirects(response, self.url)
        self.assertContains(response, "Total de cafés achetés : 10")
        ajout = TransactionCafe.objects.get()
        self.assertEqual(ajout.client, self.personne)
        self.assertEqual(ajout.quantite, 3)
        self.assertIsNotNone(ajout.date_creation)
        self.client.get(self.url)
        self.assertEqual(TransactionCafe.objects.count(), 1)
        self.autre.refresh_from_db()
        self.assertEqual(self.autre.nombre_cafes_achetes, 0)
        response = self.client.get(reverse("ajouter_cafes", args=[self.autre.pk]))
        self.assertContains(response, "Aucune transaction enregistrée.")

    def test_quantite_invalide(self):
        for quantite in ("", "0", "-1", "1.5", "abc", "2147483648"):
            with self.subTest(quantite=quantite):
                response = self.client.post(self.url, {"quantite": quantite})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 7)
        self.assertEqual(TransactionCafe.objects.count(), 0)

    def test_echec_transaction_annule_le_compteur(self):
        with patch.object(TransactionCafe, "save", side_effect=RuntimeError("échec")):
            with self.assertRaises(RuntimeError):
                ajouter_cafes(self.personne, 2)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 7)
        self.assertEqual(TransactionCafe.objects.count(), 0)

    def test_client_inexistant(self):
        url = reverse("ajouter_cafes", args=[self.autre.pk + 1])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"quantite": 1}).status_code, 404)


class RechercheClientTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.camille = Client.objects.create(
            nom_complet="Camille Tremblay", courriel="camille@example.com",
            telephone="418 555-1234", nombre_cafes_achetes=7,
        )
        Client.objects.create(nom_complet="Alex Roy", telephone="514 555-9876")

    def test_recherche_partielle_sur_les_trois_champs(self):
        for terme in ("TREMB", "555-1234", "CAMILLE@", "  Camille  "):
            with self.subTest(terme=terme):
                response = self.client.get(reverse("accueil"), {"q": terme})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(list(response.context["resultats"]), [self.camille])
                self.assertContains(response, "camille@example.com")
                self.assertContains(response, "418 555-1234")
                self.assertContains(response, "Ajouter le client")
        self.assertEqual(Client.objects.count(), 2)

    def test_recherche_sans_resultat(self):
        response = self.client.get(reverse("accueil"), {"q": "introuvable"})
        self.assertContains(response, "Aucun client trouvé.")

    def test_recherche_vide_ne_liste_pas_les_clients(self):
        for params in ({}, {"q": ""}, {"q": "   "}):
            with self.subTest(params=params):
                response = self.client.get(reverse("accueil"), params)
                self.assertEqual(list(response.context["resultats"]), [])
                self.assertNotContains(response, "Camille Tremblay")


class ModificationClientTests(TestCase):
    def setUp(self):
        self.personne = Client.objects.create(
            nom_complet="Camille Tremblay", courriel="camille@example.com",
            telephone="418 555-1234", nombre_cafes_achetes=7,
        )
        self.url = reverse("modifier_client", args=[self.personne.pk])

    def test_bouton_recherche_et_formulaire_prerempli(self):
        response = self.client.get(reverse("accueil"), {"q": "Camille"})
        self.assertContains(response, f'action="{self.url}"')
        response = self.client.get(self.url)
        for valeur in ("Camille Tremblay", "camille@example.com", "418 555-1234"):
            self.assertContains(response, f'value="{valeur}"')
        self.assertNotContains(response, 'name="nombre_cafes_achetes"')

    def test_modification_sans_creer_de_client_ni_modifier_les_cafes(self):
        for contact in (
            {"courriel": "nouveau@example.com", "telephone": ""},
            {"courriel": "", "telephone": "514 555-9876"},
            {"courriel": "nouveau@example.com", "telephone": "514 555-9876"},
        ):
            with self.subTest(contact=contact):
                response = self.client.post(self.url, {
                    "nom_complet": "Camille Roy", "nombre_cafes_achetes": "999",
                    **contact,
                }, follow=True)
                self.assertRedirects(response, reverse("accueil"))
                self.assertContains(response, "Le client a été modifié avec succès.")
                self.personne.refresh_from_db()
                self.assertEqual(self.personne.nom_complet, "Camille Roy")
                self.assertEqual(self.personne.courriel, contact["courriel"])
                self.assertEqual(self.personne.telephone, contact["telephone"])
                self.assertEqual(self.personne.nombre_cafes_achetes, 7)
                self.assertEqual(Client.objects.count(), 1)

    def test_modification_invalide_conserve_les_donnees_en_base(self):
        for champs in (
            {"nom_complet": "Camille Roy", "courriel": "", "telephone": ""},
            {"nom_complet": "Camille Roy", "courriel": "invalide"},
            {"nom_complet": "", "telephone": "418 555-1234"},
        ):
            with self.subTest(champs=champs):
                response = self.client.post(self.url, champs)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.personne.refresh_from_db()
                self.assertEqual(self.personne.nom_complet, "Camille Tremblay")
                self.assertEqual(self.personne.courriel, "camille@example.com")
                self.assertEqual(self.personne.telephone, "418 555-1234")

    def test_client_inexistant(self):
        url = reverse("modifier_client", args=[self.personne.pk + 1])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {}).status_code, 404)


class AccueilTests(TestCase):
    def test_accueil_affiche_le_formulaire(self):
        response = self.client.get(reverse("accueil"))
        self.assertEqual(response.status_code, 200)
        for name in ("nom_complet", "courriel", "telephone", "csrfmiddlewaretoken"):
            self.assertContains(response, f'name="{name}"')

    def test_ajout_client_et_actualisation(self):
        response = self.client.post(reverse("accueil"), {
            "nom_complet": "Camille Tremblay",
            "courriel": "camille@example.com",
            "telephone": "418 555-1234",
            "nombre_cafes_achetes": "100",
        }, follow=True)
        self.assertRedirects(response, reverse("accueil"))
        self.assertContains(response, "Le client a été ajouté avec succès.")
        client = Client.objects.get()
        self.assertEqual(client.nom_complet, "Camille Tremblay")
        self.assertEqual(client.courriel, "camille@example.com")
        self.assertEqual(client.telephone, "418 555-1234")
        self.assertEqual(client.nombre_cafes_achetes, 0)
        self.client.get(reverse("accueil"))
        self.assertEqual(Client.objects.count(), 1)

    def test_champs_obligatoires_et_courriel_invalide(self):
        for data in ({}, {
            "nom_complet": "Camille Tremblay",
            "courriel": "invalide",
            "telephone": "418 555-1234",
        }):
            with self.subTest(data=data):
                response = self.client.post(reverse("accueil"), data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertEqual(Client.objects.count(), 0)
        self.assertContains(response, 'value="Camille Tremblay"')

    def test_inscription_avec_un_seul_moyen_de_contact(self):
        for contact in (
            {"courriel": "camille@example.com"},
            {"telephone": "418 555-1234"},
        ):
            with self.subTest(contact=contact):
                response = self.client.post(reverse("accueil"), {
                    "nom_complet": "Camille Tremblay", **contact,
                })
                self.assertRedirects(response, reverse("accueil"))
                self.assertTrue(Client.objects.filter(**contact).exists())
        self.assertEqual(Client.objects.count(), 2)

    def test_inscription_sans_contact_refusee(self):
        for contact in ({}, {"courriel": "", "telephone": ""},
                        {"courriel": "   ", "telephone": "   "}):
            with self.subTest(contact=contact):
                response = self.client.post(reverse("accueil"), {
                    "nom_complet": "Camille Tremblay", **contact,
                })
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response, "Veuillez renseigner un courriel ou un téléphone."
                )
                self.assertEqual(Client.objects.count(), 0)
