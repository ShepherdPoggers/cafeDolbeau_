from django.test import TestCase
from django.urls import reverse

from .models import Client, TransactionCafe
from .services import ajouter_cafes
from unittest.mock import patch


class TransactionCafeTests(TestCase):
    def test_achat_hors_carte_preserve_le_solde_et_accorde_la_gratuite(self):
        Client.objects.filter(pk=self.personne.pk).update(
            nombre_cafes_achetes=10, nombre_cafes_prepayes=11,
        )
        response = self.client.post(self.url, {
            "quantite": 3, "type_transaction": "achat",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["achetes"], 13)
        self.assertEqual(response.json()["prepayes"], 11)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_prepayes, 11)
        self.assertEqual(TransactionCafe.objects.get(type_transaction="achat").quantite, 2)
        self.assertEqual(TransactionCafe.objects.get(type_transaction="gratuit").quantite, 1)
        self.assertFalse(TransactionCafe.objects.filter(type_transaction="utilise").exists())

    def test_utilisation_invalide_affiche_les_erreurs_sur_son_formulaire(self):
        response = self.client.post(self.url, {"quantite": 0, "type_transaction": "utilise"})
        self.assertTrue(response.context["form_utilisation"].errors)
        self.assertFalse(response.context["form"].is_bound)
        self.assertFalse(response.context["form_prepaye"].is_bound)
        self.assertEqual(TransactionCafe.objects.count(), 0)

    def test_ajouts_asynchrones_actualisent_compteurs_et_historique(self):
        response = self.client.post(self.url, {
            "quantite": 1, "type_transaction": "prepaye",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["prepayes"], 11)
        self.assertEqual(response.json()["achetes"], 18)
        response = self.client.post(self.url, {
            "quantite": 15, "type_transaction": "utilise",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["achetes"], 22)
        self.assertEqual(data["prepayes"], 0)
        self.assertIn("Cafés gratuits", data["historique"])
        self.assertIn("Cafés prépayés consommés", data["historique"])
        self.assertTrue(any("felicitations" in message["tags"] for message in data["messages"]))
        self.assertEqual(TransactionCafe.objects.count(), 4)
        response = self.client.get(self.url)
        self.assertNotContains(response, "La transaction de cafés a été enregistrée.")

    def test_ajout_asynchrone_invalide_ne_modifie_pas_les_compteurs(self):
        for type_transaction in ("achat", "prepaye", "utilise"):
            response = self.client.post(self.url, {
                "quantite": 0, "type_transaction": type_transaction,
            }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
            self.assertEqual(response.status_code, 400)
            self.assertIn("quantite", response.json()["erreurs"])
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 7)
        self.assertEqual(self.personne.nombre_cafes_prepayes, 0)
        self.assertEqual(TransactionCafe.objects.count(), 0)

    def test_gratuite_et_separation_des_transactions(self):
        for total, quantite, gratuits in (
            (9, 1, 0), (10, 1, 1), (10, 3, 1), (11, 1, 0),
            (21, 1, 1), (0, 22, 2), (10, 23, 3),
        ):
            with self.subTest(total=total, quantite=quantite):
                Client.objects.filter(pk=self.personne.pk).update(
                    nombre_cafes_achetes=total, nombre_cafes_prepayes=0
                )
                transactions = ajouter_cafes(self.personne, quantite)
                self.personne.refresh_from_db()
                self.assertEqual(self.personne.nombre_cafes_achetes, total + quantite)
                self.assertEqual(self.personne.nombre_cafes_prepayes, 0)
                self.assertEqual(sum(t.quantite for t in transactions), quantite)
                self.assertEqual(sum(t.quantite for t in transactions
                                     if t.type_transaction == TransactionCafe.Type.GRATUIT), gratuits)
                self.assertTrue(all(t.quantite > 0 and t.pk for t in transactions))

    def test_message_gratuit_et_solde_insuffisant(self):
        Client.objects.filter(pk=self.personne.pk).update(
            nombre_cafes_achetes=10, nombre_cafes_prepayes=1
        )
        response = self.client.post(self.url, {"quantite": 4, "type_transaction": "utilise"}, follow=True)
        self.assertContains(response, "Fecilication un café gratuit est accordé")
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_prepayes, 0)
        self.assertEqual(self.personne.nombre_cafes_achetes, 13)
        self.assertEqual(TransactionCafe.objects.count(), 3)
        self.client.get(self.url)
        self.assertEqual(TransactionCafe.objects.count(), 3)

    def test_achat_cartes_inclut_la_gratuite_sans_ligne_supplementaire(self):
        Client.objects.filter(pk=self.personne.pk).update(nombre_cafes_achetes=10)
        transactions = ajouter_cafes(self.personne, 2, TransactionCafe.Type.PREPAYE)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 32)
        self.assertEqual(self.personne.nombre_cafes_prepayes, 22)
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].quantite, 22)
        self.assertEqual(transactions[0].type_transaction, TransactionCafe.Type.PREPAYE)

    def test_echec_ligne_gratuite_annule_toute_la_commande(self):
        Client.objects.filter(pk=self.personne.pk).update(
            nombre_cafes_achetes=10, nombre_cafes_prepayes=5
        )
        original_save = TransactionCafe.save

        def sauvegarder(instance, *args, **kwargs):
            if instance.type_transaction == TransactionCafe.Type.GRATUIT:
                raise RuntimeError("échec gratuit")
            return original_save(instance, *args, **kwargs)

        with patch.object(TransactionCafe, "save", sauvegarder):
            with self.assertRaises(RuntimeError):
                ajouter_cafes(self.personne, 8, TransactionCafe.Type.UTILISE)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 10)
        self.assertEqual(self.personne.nombre_cafes_prepayes, 5)
        self.assertEqual(TransactionCafe.objects.count(), 0)

    def test_ajout_prepaye_puis_utilisation(self):
        response = self.client.post(self.url, {
            "quantite": 1, "type_transaction": "prepaye",
        }, follow=True)
        self.assertRedirects(response, self.url)
        self.assertContains(response, "Total de cafés prépayés : 11")
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 18)
        self.assertEqual(self.personne.nombre_cafes_prepayes, 11)
        ajout = TransactionCafe.objects.get()
        self.assertEqual(ajout.type_transaction, TransactionCafe.Type.PREPAYE)
        self.assertEqual(ajout.quantite, 11)
        self.client.get(self.url)
        self.assertEqual(TransactionCafe.objects.count(), 1)
        self.client.post(self.url, {"quantite": 2, "type_transaction": "utilise"})
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 18)
        self.assertEqual(self.personne.nombre_cafes_prepayes, 9)
        self.assertEqual(TransactionCafe.objects.get(type_transaction="utilise").quantite, 2)

    def test_commande_utilise_les_prepayes_disponibles(self):
        for solde, reste, total in ((0, 0, 10), (2, 0, 8), (3, 0, 7), (5, 2, 7)):
            with self.subTest(solde=solde):
                Client.objects.filter(pk=self.personne.pk).update(
                    nombre_cafes_prepayes=solde, nombre_cafes_achetes=7
                )
                transactions = ajouter_cafes(self.personne, 3, TransactionCafe.Type.UTILISE)
                self.personne.refresh_from_db()
                self.assertEqual(self.personne.nombre_cafes_achetes, total)
                self.assertEqual(self.personne.nombre_cafes_prepayes, reste)
                self.assertEqual(sum(t.quantite for t in transactions), 3)
                self.assertEqual(sum(t.quantite for t in transactions
                                     if t.type_transaction == TransactionCafe.Type.UTILISE), min(solde, 3))

    def test_commandes_successives_epuisent_le_solde(self):
        ajouter_cafes(self.personne, 1, TransactionCafe.Type.PREPAYE)
        for _ in range(11):
            ajouter_cafes(self.personne, 1, TransactionCafe.Type.UTILISE)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 18)
        self.assertEqual(self.personne.nombre_cafes_prepayes, 0)
        self.assertEqual(TransactionCafe.objects.filter(type_transaction="utilise").count(), 11)
        self.assertFalse(TransactionCafe.objects.filter(type_transaction="gratuit").exists())
        ajouter_cafes(self.personne, 4)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 22)
        self.assertEqual(TransactionCafe.objects.get(type_transaction="gratuit").quantite, 1)

    def test_prepaye_invalide_et_erreurs_sur_le_bon_formulaire(self):
        for valeur in ("", "0", "-2", "1.5", "abc", str(2147483647 // 11 + 1)):
            response = self.client.post(self.url, {
                "quantite": valeur, "type_transaction": "prepaye",
            })
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form_prepaye"].errors)
            self.assertFalse(response.context["form"].is_bound)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_prepayes, 0)
        self.assertEqual(TransactionCafe.objects.count(), 0)

    def test_type_invalide_refuse(self):
        from django.core.exceptions import ValidationError

        response = self.client.post(self.url, {"quantite": 2, "type_transaction": "inconnu"})
        self.assertEqual(response.status_code, 400)
        with self.assertRaises(ValidationError):
            ajouter_cafes(self.personne, 2, "inconnu")
        self.assertEqual(TransactionCafe.objects.count(), 0)

    def test_echec_prepaye_annule_le_compteur(self):
        with patch.object(TransactionCafe, "save", side_effect=RuntimeError("échec")):
            with self.assertRaises(RuntimeError):
                ajouter_cafes(self.personne, 2, TransactionCafe.Type.PREPAYE)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_prepayes, 0)
        self.assertEqual(self.personne.nombre_cafes_achetes, 7)
        self.assertEqual(TransactionCafe.objects.count(), 0)

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
        Client.objects.filter(pk=self.personne.pk).update(nombre_cafes_prepayes=5)
        with patch.object(TransactionCafe, "save", side_effect=RuntimeError("échec")):
            with self.assertRaises(RuntimeError):
                ajouter_cafes(self.personne, 2)
        self.personne.refresh_from_db()
        self.assertEqual(self.personne.nombre_cafes_achetes, 7)
        self.assertEqual(self.personne.nombre_cafes_prepayes, 5)
        self.assertEqual(TransactionCafe.objects.count(), 0)

    def test_client_inexistant(self):
        url = reverse("ajouter_cafes", args=[self.autre.pk + 1])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"quantite": 1}).status_code, 404)


class RechercheClientTests(TestCase):
    def test_recherche_partielle_retourne_seulement_les_resultats(self):
        response = self.client.get(reverse("accueil"), {
            "q": "Camille", "partiel": "recherche",
        })
        self.assertTemplateUsed(response, "resultats_recherche.html")
        self.assertContains(response, "Camille Tremblay")
        self.assertContains(response, reverse("ajouter_cafes", args=[self.camille.pk]))
        self.assertNotContains(response, "Ajouter le client")
        self.assertNotContains(response, "<!DOCTYPE html>")

    def test_recherche_partielle_vide_ou_sans_resultat(self):
        response = self.client.get(reverse("accueil"), {
            "q": "   ", "partiel": "recherche",
        })
        self.assertContains(response, "Camille Tremblay")
        self.assertContains(response, "Alex Roy")
        response = self.client.get(reverse("accueil"), {
            "q": "introuvable", "partiel": "recherche",
        })
        self.assertContains(response, "Aucun client trouvé.")

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

    def test_recherche_vide_liste_tous_les_clients(self):
        for params in ({}, {"q": ""}, {"q": "   "}):
            with self.subTest(params=params):
                response = self.client.get(reverse("accueil"), params)
                self.assertEqual(list(response.context["resultats"]), list(Client.objects.all()))
                self.assertContains(response, "Camille Tremblay")
                self.assertContains(response, "Alex Roy")

    def test_liste_vide_conserve_le_tableau(self):
        Client.objects.all().delete()
        response = self.client.get(reverse("accueil"))
        self.assertContains(response, 'id="resultats-recherche"')
        self.assertContains(response, "<table>")
        self.assertContains(response, "Aucun client enregistré.")


class ModificationClientTests(TestCase):
    def setUp(self):
        self.personne = Client.objects.create(
            nom_complet="Camille Tremblay", courriel="camille@example.com",
            telephone="418 555-1234", nombre_cafes_achetes=7,
        )
        self.url = reverse("modifier_client", args=[self.personne.pk])

    def test_accueil_sans_bouton_modifier_et_formulaire_prerempli(self):
        response = self.client.get(reverse("accueil"), {"q": "Camille"})
        self.assertNotContains(response, f'action="{self.url}"')
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
