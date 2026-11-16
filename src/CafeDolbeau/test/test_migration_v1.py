from pathlib import Path
from runpy import run_path
import hashlib

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import SimpleTestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from ..models import Client


class MigrationHistoriqueV2Tests(SimpleTestCase):
    def test_0016_est_identique_au_fichier_livre_dans_v2_0_0(self):
        chemin = Path(__file__).resolve().parents[1] / "migrations/0016_fusions_sans_noms.py"
        contenu = chemin.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(hashlib.sha256(contenu).hexdigest(), "953df3b12a9c18b934eba4d762a526769ab48f1b65a7afc4bbc505cc64d97f4b")


class MigrationRemplacementV2Tests(TransactionTestCase):
    def test_installation_avec_0016_deja_appliquee_ne_rejoue_pas_les_operations(self):
        personne = Client.objects.create(nom_complet="Solde à conserver", nombre_cafes_prepayes=17)
        original = ("CafeDolbeau", "0016_fusions_sans_noms")
        remplacement = ("CafeDolbeau", "0016_fusions_sans_noms_compat_postgresql")
        registre = MigrationRecorder(connection)
        self.assertIn(original, registre.applied_migrations())
        # Simuler l’arrivée du nouveau fichier sur une base déjà migrée en V2/V3.
        registre.record_unapplied(*remplacement)
        try:
            executor = MigrationExecutor(connection)
            dernier_schema = executor.loader.graph.leaf_nodes()
            executor.loader.check_consistent_history(connection)
            self.assertEqual(executor.migration_plan(dernier_schema), [])
            with CaptureQueriesContext(connection) as requetes:
                executor.migrate(dernier_schema)
            self.assertFalse(any("ALTER TABLE" in requete["sql"] for requete in requetes))
            personne.refresh_from_db()
            self.assertEqual(personne.nombre_cafes_prepayes, 17)
            self.assertIn(original, registre.applied_migrations())
            self.assertIn(remplacement, registre.applied_migrations())
        finally:
            if remplacement not in registre.applied_migrations():
                registre.record_applied(*remplacement)


class MigrationV1Tests(TransactionTestCase):
    def test_conserve_les_soldes_et_lhistorique_du_jeu_de_demonstration_v1(self):
        executor = MigrationExecutor(connection)
        dernier_schema = executor.loader.graph.leaf_nodes()
        schema_v1 = [("CafeDolbeau", "0008_client_client_telephone_unique_non_vide_and_more")]
        try:
            executor.migrate(schema_v1)
            anciens_modeles = executor.loader.project_state(schema_v1).apps
            script = Path(__file__).resolve().parents[3] / "scripts/donnees_v1.py"
            run_path(str(script))["creer_donnees"](anciens_modeles)

            AncienClient = anciens_modeles.get_model("CafeDolbeau", "Client")
            AncienneTransaction = anciens_modeles.get_model("CafeDolbeau", "TransactionCafe")
            champs_clients = (
                "pk", "nom_complet", "telephone", "courriel", "nombre_cafes_achetes",
                "nombre_cafes_gratuits", "nombre_cafes_prepayes",
            )
            champs_transactions = ("pk", "client_id", "type_transaction", "quantite", "date_creation")
            clients_avant = list(AncienClient.objects.order_by("pk").values_list(*champs_clients))
            transactions_avant = list(
                AncienneTransaction.objects.order_by("pk").values_list(*champs_transactions)
            )
            self.assertEqual(len(clients_avant), 6)
            self.assertEqual(len(transactions_avant), 12)

            executor = MigrationExecutor(connection)
            executor.migrate(dernier_schema)
            nouveaux_modeles = executor.loader.project_state(dernier_schema).apps
            NouveauClient = nouveaux_modeles.get_model("CafeDolbeau", "Client")
            NouvelleTransaction = nouveaux_modeles.get_model("CafeDolbeau", "TransactionCafe")
            self.assertEqual(
                list(NouveauClient.objects.order_by("pk").values_list(*champs_clients)), clients_avant,
            )
            self.assertEqual(
                list(NouvelleTransaction.objects.order_by("pk").values_list(*champs_transactions)),
                transactions_avant,
            )
            self.assertFalse(NouvelleTransaction.objects.exclude(
                succursale_id=1,
                employe__isnull=True, operation_id__isnull=True, variation_achetes__isnull=True,
                variation_gratuits__isnull=True, variation_prepayes__isnull=True,
            ).exists())
        finally:
            MigrationExecutor(connection).migrate(dernier_schema)
