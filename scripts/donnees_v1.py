"""Créer une base au schéma V1, prête à migrer vers la V2."""
import csv
from datetime import UTC, datetime, timedelta
import sys


def creer_donnees(modeles_v1):
    ClientV1 = modeles_v1.get_model("CafeDolbeau", "Client")
    TransactionV1 = modeles_v1.get_model("CafeDolbeau", "TransactionCafe")
    for identifiant, (nom, achetes, gratuits, prepayes) in enumerate([
        ("Alice Tremblay", 9, 0, 0),
        ("Benoît Gagnon", 12, 1, 0),
        ("Camille Roy", 20, 0, 17),
        ("Dominique Fortin", 17, 0, 10),
        ("Élodie Simard", 33, 1, 10),
        ("Client sans solde", 0, 0, 0),
    ], 1):
        ClientV1.objects.create(
            pk=identifiant, nom_complet=nom, telephone=f"418-555-{identifiant:04d}",
            courriel=f"client{identifiant}@example.test", nombre_cafes_achetes=achetes,
            nombre_cafes_gratuits=gratuits, nombre_cafes_prepayes=prepayes,
        )

    for identifiant, (client_id, type_cafe, quantite) in enumerate([
        (1, "achat", 9),
        (2, "achat", 12),
        (2, "gratuit", 1),
        (3, "prepaye", 20),
        (3, "utilise", 5),
        (4, "achat", 7),
        (4, "prepaye", 10),
        (4, "utilise", 1),
        (5, "achat", 23),
        (5, "gratuit", 2),
        (5, "prepaye", 10),
        (5, "utilise", 2),
    ], 1):
        TransactionV1.objects.create(
            pk=identifiant, client_id=client_id, type_transaction=type_cafe, quantite=quantite,
        )
        TransactionV1.objects.filter(pk=identifiant).update(
            date_creation=datetime(2026, 9, 1, 14, tzinfo=UTC) + timedelta(days=identifiant - 1),
        )


def main():
    from _donnees_test import comptes, initialiser, terminer

    initialiser("V1")
    from django.core.management import call_command
    from django.db import connection, transaction
    from django.db.migrations.executor import MigrationExecutor

    for application in ("contenttypes", "auth", "admin", "sessions"):
        call_command("migrate", application, interactive=False, verbosity=0)
    migration_v1 = "0008_client_client_telephone_unique_non_vide_and_more"
    call_command("migrate", "CafeDolbeau", migration_v1, interactive=False, verbosity=0)
    modeles_v1 = MigrationExecutor(connection).loader.project_state([
        ("CafeDolbeau", migration_v1),
    ]).apps
    with transaction.atomic():
        comptes()
        creer_donnees(modeles_v1)

    print("V1 : 6 clients et 12 transactions. Soldes avant migration :")
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow((
        "id", "client", "cafes_achetes", "etampes",
        "recompenses_en_reserve", "cafes_prepayes",
    ))
    ClientV1 = modeles_v1.get_model("CafeDolbeau", "Client")
    for client in ClientV1.objects.order_by("pk"):
        writer.writerow((
            client.pk, client.nom_complet, client.nombre_cafes_achetes,
            client.nombre_cafes_achetes % 10, client.nombre_cafes_gratuits,
            client.nombre_cafes_prepayes,
        ))
    terminer()


if __name__ == "__main__":
    main()
