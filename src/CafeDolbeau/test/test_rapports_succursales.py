from io import BytesIO
from datetime import date, datetime
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from ..forms.forms_rapports import RapportForm
from ..models import AffectationEmployeSuccursale, AnnulationTransaction, Client, Employe, Promotion, Succursale, TransactionCafe
from ..rapports import FUSEAU_RAPPORT, exporter_excel, generer_rapport
from ..views import views_rapports
from .test_annulations import creer_employe


class RapportsSuccursalesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.proprietaire = creer_employe("proprietaire-rapport-filtre", "Propriétaire")
        cls.gerant = creer_employe("gerant-rapport-filtre", "Gérant")
        cls.autre_gerant = creer_employe("autre-gerant-rapport-filtre", "Gérant")
        cls.barista = creer_employe("barista-rapport-filtre")
        cls.s1 = Succursale.objects.get(pk=1)
        cls.s2 = Succursale.objects.create(nom="Deuxième succursale")
        cls.s3 = Succursale.objects.create(nom="Succursale hors périmètre")
        AffectationEmployeSuccursale.objects.create(employe=cls.gerant, succursale=cls.s2)
        cls.autre_gerant.affectations_succursales.all().delete()
        AffectationEmployeSuccursale.objects.create(employe=cls.autre_gerant, succursale=cls.s3)
        cls.personne = Client.objects.create(nom_complet="Client réseau", telephone="rapports-filtre")
        cls.admin = Employe.objects.create_superuser("super-rapports-filtre")

    def setUp(self):
        self.jour = timezone.localdate()
        self.client.force_login(self.gerant)

    def filtres(self, **changements):
        return {"date_debut": self.jour.isoformat(), "date_fin": self.jour.isoformat(),
                "precision": "transaction", "types": ["achat", "gratuit"],
                "succursales": [self.s1.pk, self.s2.pk], **changements}

    def ligne(self, succursale, quantite=1, **champs):
        return TransactionCafe.objects.create(client=self.personne, succursale=succursale,
                                               quantite=quantite, employe=self.barista, **champs)

    def generer(self, employe=None, succursales=None):
        return generer_rapport(date_debut=self.jour, date_fin=self.jour, types=("achat", "gratuit"),
                              precision="transaction", employe=employe or self.gerant,
                              succursale_ids=succursales if succursales is not None else [1, self.s2.pk])

    def test_selection_initiale_et_choix_limites_au_perimetre(self):
        for acteur, attendues in ((self.gerant, {1, self.s2.pk}), (self.autre_gerant, {self.s3.pk}),
                                  (self.proprietaire, {1, self.s2.pk, self.s3.pk}), (self.admin, {1, self.s2.pk, self.s3.pk})):
            self.client.force_login(acteur)
            reponse = self.client.get(reverse("rapports"))
            self.assertEqual(reponse.status_code, 200)
            form = reponse.context["form"]
            self.assertEqual(set(form.fields["succursales"].queryset.values_list("pk", flat=True)), attendues)
            self.assertEqual(set(form.cleaned_data["succursales"].values_list("pk", flat=True)), attendues)
        self.client.force_login(self.gerant)
        self.assertNotContains(self.client.get(reverse("rapports")), self.s3.nom)

    def test_totaux_combines_et_filtre_par_succursale(self):
        self.ligne(self.s1, 2)
        self.ligne(self.s2, 5)
        self.ligne(self.s3, 100)
        reponse = self.client.get(reverse("rapports"), self.filtres())
        self.assertEqual(reponse.context["rapport"].total, 7)
        self.assertEqual({e.succursale_id for e in reponse.context["rapport"].evenements}, {1, self.s2.pk})
        self.assertContains(reponse, "Succursales incluses")
        self.assertContains(reponse, self.s2.nom)
        reponse = self.client.get(reverse("rapports"), self.filtres(succursales=[self.s2.pk]))
        self.assertEqual(reponse.context["rapport"].total, 5)
        self.client.force_login(self.proprietaire)
        reponse = self.client.get(reverse("rapports"), self.filtres(succursales=[self.s3.pk]))
        self.assertEqual(reponse.context["rapport"].total, 100)

    def test_syntheses_par_succursale_puis_global_html_et_excel(self):
        self.ligne(self.s1, 3)
        annulee = self.ligne(self.s2, 5)
        AnnulationTransaction.objects.create(transaction=annulee, employe=self.proprietaire)
        self.ligne(self.s2, 2, type_transaction="gratuit")
        self.ligne(self.s3, 999)
        rapport = self.generer()
        self.assertEqual([b.succursale_id for b in rapport.par_succursale], [self.s1.pk, self.s2.pk])
        self.assertEqual([b.total for b in rapport.syntheses], [3, 2, 5])
        self.assertEqual([(c.enregistrees, c.annulees, c.net) for c in rapport.par_succursale[1].totaux], [(5, 5, 0), (2, 0, 2)])
        for i, total in enumerate(rapport.totaux):
            self.assertEqual(sum(b.totaux[i].enregistrees for b in rapport.par_succursale), total.enregistrees)
            self.assertEqual(sum(b.totaux[i].annulees for b in rapport.par_succursale), total.annulees)
        reponse = self.client.get(reverse("rapports"), self.filtres())
        html = reponse.content.decode()
        for bloc in rapport.syntheses:
            self.assertContains(reponse, f"<h3>{bloc.libelle}</h3>", count=2, html=True)
        self.assertLess(html.index(f"<h3>{rapport.par_succursale[0].libelle}</h3>"), html.index("<h3>Global"))
        self.assertNotContains(reponse, self.s3.nom)
        classeur = load_workbook(exporter_excel(rapport))
        for nom in ("Synthèse", "Détail des totaux"):
            feuille = classeur[nom]
            titres = [row[0] for row in feuille.iter_rows(values_only=True) if row[0] in [b.libelle for b in rapport.syntheses]]
            self.assertEqual(titres, [b.libelle for b in rapport.syntheses])
        nets = [row for row in classeur["Synthèse"].iter_rows(values_only=True) if row[0] == "TOTAL"]
        self.assertEqual(nets, [("TOTAL", 3, 0, 3), ("TOTAL", 0, 2, 2), ("TOTAL", 3, 2, 5)])

    def test_synthese_succursale_vide_presente_et_categories_limitees(self):
        self.ligne(self.s1, 4)
        reponse = self.client.get(reverse("rapports"), self.filtres(types=["achat"], precision="jour"))
        rapport = reponse.context["rapport"]
        self.assertEqual([b.total for b in rapport.syntheses], [4, 0, 4])
        self.assertEqual([c.code for c in rapport.par_succursale[1].totaux], ["achat"])
        self.assertTrue(all(g.total == 0 for g in rapport.par_succursale[1].groupes))

    def test_groupes_par_succursale_et_annulation_source_hors_periode(self):
        ancienne = self.ligne(self.s2, 5)
        TransactionCafe.objects.filter(pk=ancienne.pk).update(date_creation=datetime(2026, 9, 30, 12, tzinfo=FUSEAU_RAPPORT))
        trace = AnnulationTransaction.objects.create(transaction=ancienne, employe=self.proprietaire)
        AnnulationTransaction.objects.filter(pk=trace.pk).update(date_annulation=datetime(2026, 10, 2, 12, tzinfo=FUSEAU_RAPPORT))
        achat = self.ligne(self.s1, 3)
        TransactionCafe.objects.filter(pk=achat.pk).update(date_creation=datetime(2026, 10, 1, 12, tzinfo=FUSEAU_RAPPORT))
        for precision in ("periode", "jour", "semaine", "mois", "transaction"):
            with self.subTest(precision=precision):
                rapport = generer_rapport(
                    date_debut=date(2026, 9, 28) if precision == "semaine" else date(2026, 10, 1),
                    date_fin=date(2026, 10, 31) if precision == "mois" else date(2026, 10, 4),
                    types=("achat",), precision=precision, employe=self.gerant,
                    succursale_ids=[self.s1.pk, self.s2.pk],
                )
                # La semaine inclut la vente du 30/09 ; les autres sélections ne comptent que son annulation.
                self.assertEqual(rapport.par_succursale[1].total, 0 if precision == "semaine" else -5)
                for i, groupe in enumerate(rapport.groupes):
                    self.assertEqual(sum(b.groupes[i].categories[0].enregistrees for b in rapport.par_succursale), groupe.categories[0].enregistrees)
                    self.assertEqual(sum(b.groupes[i].categories[0].annulees for b in rapport.par_succursale), groupe.categories[0].annulees)

    def test_annulation_liee_a_succursale_origine_et_promotion_conservee(self):
        promo = Promotion.objects.create(nom="Promotion du réseau", cafes_pour_gratuite=3,
                                         date_debut=self.jour, date_fin=self.jour)
        ligne = self.ligne(self.s1, 3, promotion=promo)
        AnnulationTransaction.objects.create(transaction=ligne, employe=self.autre_gerant)
        self.ligne(self.s3, 99)
        rapport = self.generer(succursales=[1])
        self.assertEqual(rapport.total, 0)
        self.assertEqual(len(rapport.evenements), 2)
        self.assertEqual({e.succursale_id for e in rapport.evenements}, {1})
        self.assertEqual({e.promotion_id for e in rapport.evenements}, {promo.pk})
        self.assertEqual({e.employe for e in rapport.evenements}, {self.barista.username, self.autre_gerant.username})

    def test_selection_invalide_refuse_page_et_export_sans_generer(self):
        self.ligne(self.s3, 99)
        for selection in ([], [self.s3.pk], [1, self.s3.pk], [999999], ["forgé"]):
            with self.subTest(selection=selection), patch("CafeDolbeau.views.views_rapports.generer_rapport") as calcul:
                filtres = self.filtres(succursales=selection)
                reponse = self.client.get(reverse("rapports"), filtres)
                self.assertEqual(reponse.status_code, 200)
                self.assertIn("succursales", reponse.context["form"].errors)
                self.assertNotIn("rapport", reponse.context)
                self.assertEqual(self.client.get(reverse("rapport_excel"), filtres).status_code, 400)
                calcul.assert_not_called()

    def test_ancienne_url_sans_selection_demande_un_choix(self):
        filtres = self.filtres()
        filtres.pop("succursales")
        reponse = self.client.get(reverse("rapports"), filtres)
        self.assertContains(reponse, "Choisissez au moins une succursale")
        self.assertNotIn("rapport", reponse.context)
        self.assertEqual(self.client.get(reverse("rapport_excel"), filtres).status_code, 400)

    def test_gerant_sans_affectation_ne_genere_rien(self):
        self.gerant.affectations_succursales.all().delete()
        reponse = self.client.get(reverse("rapports"))
        self.assertContains(reponse, "Aucune succursale accessible")
        self.assertNotIn("rapport", reponse.context)
        self.assertEqual(self.client.get(reverse("rapport_excel")).status_code, 400)

    def test_retrait_affectation_entre_validation_et_generation_refuse_tout(self):
        vrai_calcul = generer_rapport
        def retirer(**options):
            self.gerant.affectations_succursales.filter(succursale=self.s2).delete()
            return vrai_calcul(**options)
        for nom in ("rapports", "rapport_excel"):
            AffectationEmployeSuccursale.objects.get_or_create(employe=self.gerant, succursale=self.s2)
            with patch("CafeDolbeau.views.views_rapports.generer_rapport", side_effect=retirer):
                self.assertEqual(self.client.get(reverse(nom), self.filtres()).status_code, 403)

    def test_retrait_apres_validation_ne_reduit_pas_silencieusement_selection(self):
        generation = views_rapports._generer
        def retirer(request, form):
            self.gerant.affectations_succursales.filter(succursale=self.s2).delete()
            return generation(request, form)
        for nom in ("rapports", "rapport_excel"):
            AffectationEmployeSuccursale.objects.get_or_create(employe=self.gerant, succursale=self.s2)
            with patch("CafeDolbeau.views.views_rapports._generer", side_effect=retirer):
                self.assertEqual(self.client.get(reverse(nom), self.filtres()).status_code, 403)

    def test_service_revalide_roles_affectations_et_identifiants(self):
        # Un formulaire déjà validé ne constitue pas une autorisation durable.
        form = RapportForm(self.filtres(), employe=self.gerant)
        self.assertTrue(form.is_valid())
        self.gerant.affectations_succursales.filter(succursale=self.s2).delete()
        with self.assertRaises(PermissionDenied):
            self.generer()
        for ids in ([self.s3.pk], [1, self.s3.pk], [999999]):
            with self.assertRaises(PermissionDenied):
                self.generer(succursales=ids)
        with self.assertRaises(ValidationError):
            self.generer(succursales=[])
        with self.assertRaises(PermissionDenied):
            self.generer(employe=self.barista, succursales=[1])
        self.gerant.has_perm("CafeDolbeau.acces_gerant")
        Employe.objects.filter(pk=self.gerant.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.generer(succursales=[1])

    def test_pagination_et_excel_conservent_selection_et_totaux(self):
        for _ in range(51):
            self.ligne(self.s2)
        self.ligne(self.s1, 50)
        self.ligne(self.s3, 100)
        filtres = self.filtres(succursales=[self.s2.pk])
        reponse = self.client.get(reverse("rapports"), filtres)
        conserves = QueryDict(reponse.context["filtres_pagination"])
        self.assertEqual(conserves.getlist("succursales"), [str(self.s2.pk)])
        self.assertEqual(reponse.context["rapport"].total, 51)
        self.assertEqual(len(reponse.context["page_evenements"]), 50)
        reponse = self.client.get(reverse("rapports"), {**filtres, "page": 2})
        self.assertEqual(len(reponse.context["page_evenements"]), 1)
        export = self.client.get(reverse("rapport_excel"), {**filtres, "page": 2})
        classeur = load_workbook(BytesIO(b"".join(export.streaming_content)))
        self.assertEqual(classeur["Transactions"].max_row, 52)
        self.assertEqual(classeur["Transactions"].cell(1, 11).value, "Succursale")
        self.assertEqual({ligne[10] for ligne in classeur["Transactions"].iter_rows(min_row=2, values_only=True)},
                         {f"#{self.s2.pk} — {self.s2.nom}"})
        parametres = dict(classeur["Paramètres"].iter_rows(min_row=2, values_only=True))
        self.assertEqual(parametres["Succursales"], f"#{self.s2.pk} — {self.s2.nom}")
        self.assertEqual(classeur["Synthèse"].cell(3, 4).value, 51)

    def test_barista_refuse_et_navigation_visible_aux_gerants(self):
        self.assertContains(self.client.get(reverse("accueil_succursale", args=[1])), 'action="/rapports/"')
        self.client.force_login(self.barista)
        for nom in ("rapports", "rapport_excel"):
            self.assertEqual(self.client.get(reverse(nom), self.filtres()).status_code, 403)
        self.assertNotContains(self.client.get(reverse("accueil_succursale", args=[1])), 'action="/rapports/"')

    def test_succursale_sans_activite_et_nouvelle_succursale_du_proprietaire(self):
        nouvelle = Succursale.objects.create(nom="Nouvelle succursale")
        rapport = self.generer(employe=self.proprietaire, succursales=[nouvelle.pk])
        self.assertEqual(rapport.total, 0)
        self.assertEqual(rapport.evenements, [])
        self.assertEqual([s.pk for s in rapport.succursales], [nouvelle.pk])
