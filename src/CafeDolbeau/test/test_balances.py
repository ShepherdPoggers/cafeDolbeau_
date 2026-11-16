import csv
from datetime import timedelta
from io import StringIO

from django.core.management import call_command, CommandError
from django.test import TestCase
from django.utils import timezone

from ..models import AnnulationTransaction, Client, Employe, ParametresCafe, Promotion, PromotionSuccursale, Succursale, TransactionCafe
from ..services import ajouter_cafes
from .test_annulations import creer_employe


class BalancesTests(TestCase):
    def soldes(self, *arguments):
        output = StringIO()
        call_command("balances", *arguments, stdout=output)
        return list(csv.DictReader(StringIO(output.getvalue())))

    def test_affiche_les_compteurs_et_les_etampes_sans_modifier_les_clients(self):
        personne = Client.objects.create(
            nom_complet='Roy, "Camille"', telephone="418-555-0101",
            nombre_cafes_achetes=37, nombre_cafes_gratuits=4, nombre_cafes_prepayes=17,
        )
        avant = list(Client.objects.values())
        self.assertEqual(self.soldes(), [{
            "id": str(personne.pk), "client": 'Roy, "Camille"', "cafes_achetes": "37",
            "etampes": "7", "recompenses_en_reserve": "4", "cafes_prepayes": "17",
        }])
        self.assertEqual(list(Client.objects.values()), avant)

    def test_inclut_les_clients_inactifs_et_exclut_le_client_fictif(self):
        Client.objects.create(pk=-1, nom_complet="Client supprimé", est_actif=False)
        personne = Client.objects.create(nom_complet="Source", telephone="111", est_actif=False)
        self.assertEqual([ligne["id"] for ligne in self.soldes()], [str(personne.pk)])

    def test_achats_promotionnels_conservent_les_etampes_habituelles(self):
        proprietaire = creer_employe("proprietaire-balances", "Propriétaire")
        promotion = Promotion.objects.create(
            nom="Ouverture", cafes_pour_gratuite=3,
            date_debut=timezone.localdate(), date_fin=timezone.localdate(),
        )
        PromotionSuccursale.objects.create(promotion=promotion, succursale_id=1)
        for achats_initiaux in (0, 9):
            personne = Client.objects.create(
                nom_complet=f"Client {achats_initiaux}", telephone=f"promo-{achats_initiaux}",
                nombre_cafes_achetes=achats_initiaux,
            )
            ajouter_cafes(personne, 4, employe=proprietaire, succursale_id=1)
            avant = list(Client.objects.values())
            for arguments in ((), ("--succursale", "1")):
                with self.subTest(achats_initiaux=achats_initiaux, arguments=arguments):
                    ligne = next(ligne for ligne in self.soldes(*arguments) if ligne["id"] == str(personne.pk))
                    self.assertEqual(ligne["cafes_achetes"], str(achats_initiaux + 4))
                    self.assertEqual(ligne["etampes"], str(achats_initiaux))
            self.assertEqual(list(Client.objects.values()), avant)

    def test_utilise_le_seuil_en_vigueur_pour_les_etampes(self):
        Client.objects.create(nom_complet="Alice", telephone="111", nombre_cafes_achetes=37)
        parametres = ParametresCafe.objects.get(pk=1)
        parametres.cafes_pour_gratuite = 5
        parametres.cafes_pour_gratuite_precedent = 10
        parametres.date_application = timezone.localdate() + timedelta(days=1)
        parametres.save()
        self.assertEqual(self.soldes()[0]["etampes"], "7")
        parametres.date_application = timezone.localdate()
        parametres.save()
        self.assertEqual(self.soldes()[0]["etampes"], "2")

    def test_base_vide_affiche_uniquement_les_entetes(self):
        output = StringIO()
        call_command("balances", stdout=output)
        self.assertEqual(
            output.getvalue(),
            "id,client,cafes_achetes,etampes,recompenses_en_reserve,cafes_prepayes\n",
        )

    def test_filtre_succursales_et_conserve_soldes_globaux_sans_doublons(self):
        s1 = Succursale.objects.get(pk=1)
        s2 = Succursale.objects.create(nom="Deuxième")
        s3 = Succursale.objects.create(nom="Troisième")
        partage = Client.objects.create(nom_complet="Partagé", nombre_cafes_achetes=37, nombre_cafes_prepayes=17, nombre_cafes_gratuits=4)
        autre = Client.objects.create(nom_complet="Autre", nombre_cafes_achetes=2)
        Client.objects.create(nom_complet="Sans transaction")
        for succursale in (s1, s1, s2):
            TransactionCafe.objects.create(client=partage, succursale=succursale, quantite=1)
        TransactionCafe.objects.create(client=autre, succursale=s3, quantite=2)
        avant = list(Client.objects.values())
        globales = self.soldes()
        attendues = [ligne for ligne in globales if ligne["id"] == str(partage.pk)]
        for arguments in (
            ("--succursale", str(s1.pk)),
            ("--succursale", str(s2.pk)),
            ("--succursale", str(s1.pk), "--succursale", str(s2.pk)),
            ("--succursale", str(s1.pk), "--succursale", str(s1.pk)),
        ):
            with self.subTest(arguments=arguments):
                self.assertEqual(self.soldes(*arguments), attendues)
        self.assertEqual(len(globales), 3)
        self.assertEqual(len(self.soldes("--succursale", str(s1.pk), "--succursale", str(s3.pk))), 2)
        self.assertEqual(list(Client.objects.values()), avant)

    def test_succursale_sans_transaction_ne_retourne_que_entetes(self):
        vide = Succursale.objects.create(nom="Vide")
        Client.objects.create(nom_complet="Client du réseau")
        self.assertEqual(self.soldes("--succursale", str(vide.pk)), [])

    def test_identifiants_inexistants_refuses_sans_csv_partiel(self):
        for identifiant in (0, -1, 999999):
            for arguments in (("--succursale", str(identifiant)), ("--succursale", "1", "--succursale", str(identifiant))):
                with self.subTest(arguments=arguments):
                    sortie = StringIO()
                    with self.assertRaisesMessage(CommandError, "inexistante"):
                        call_command("balances", *arguments, stdout=sortie)
                    self.assertEqual(sortie.getvalue(), "")

    def test_inclut_clients_inactifs_et_transactions_annulees_dans_filtre(self):
        employe = Employe.objects.create_user("annulation-balances")
        source = Client.objects.create(nom_complet="Source fusionnée", est_actif=False)
        fictif = Client.objects.create(pk=-1, nom_complet="Client supprimé", est_actif=False)
        ligne = TransactionCafe.objects.create(client=source, succursale_id=1, quantite=1)
        AnnulationTransaction.objects.create(transaction=ligne, employe=employe)
        TransactionCafe.objects.create(client=fictif, succursale_id=1, quantite=1)
        self.assertEqual([ligne["id"] for ligne in self.soldes("--succursale", "1")], [str(source.pk)])
