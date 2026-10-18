from pathlib import Path
from runpy import run_path

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


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
                employe__isnull=True, operation_id__isnull=True, variation_achetes__isnull=True,
                variation_gratuits__isnull=True, variation_prepayes__isnull=True,
            ).exists())
        finally:
            MigrationExecutor(connection).migrate(dernier_schema)
