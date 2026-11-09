"""Transférer une base SQLite à jour vers une base PostgreSQL sans tables."""

import argparse
from collections import Counter
from contextlib import closing
from io import StringIO
import json
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

from django.apps import apps
from django.core import serializers
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.serializers.base import DeserializationError
from django.db import connections, DatabaseError, models, transaction
from django.db.migrations.executor import MigrationExecutor


def exporter(alias):
    sortie = StringIO()
    call_command(
        "dumpdata", database=alias, use_base_manager=True,
        stdout=sortie, verbosity=0, skip_checks=True,
    )
    return sortie.getvalue()


def normaliser(donnees):
    lignes = json.loads(donnees)
    for ligne in lignes:
        modele = apps.get_model(ligne["model"])
        for champ in modele._meta.many_to_many:
            ligne["fields"][champ.name].sort()
    return sorted(lignes, key=lambda ligne: (ligne["model"], str(ligne["pk"])))


def ajuster_sequences(connexion):
    # Le client fictif peut être le seul client, avec un identifiant de -1.
    # Dans ce cas, le prochain identifiant PostgreSQL doit commencer à 1.
    with connexion.cursor() as curseur:
        for modele in apps.get_models(include_auto_created=True):
            if not modele._meta.managed or modele._meta.proxy:
                continue
            cle = modele._meta.pk
            if not isinstance(cle, models.AutoField):
                continue
            table = connexion.ops.quote_name(modele._meta.db_table)
            colonne = connexion.ops.quote_name(cle.column)
            curseur.execute(
                f"SELECT setval(pg_get_serial_sequence(%s, %s), "
                f"GREATEST(COALESCE(MAX({colonne}), 1), 1), "
                f"COALESCE(MAX({colonne}), 0) >= 1) FROM {table}",
                [table, cle.column],
            )


def transferer(chemin_source, *, destination="default"):
    from django.contrib.contenttypes.models import ContentType

    chemin_source = Path(chemin_source).resolve()
    if not chemin_source.is_file():
        raise CommandError(f"Fichier SQLite introuvable : {chemin_source}")

    cible = connections[destination]
    if cible.vendor != "postgresql":
        raise CommandError("La destination doit utiliser PostgreSQL.")

    alias = "sqlite_transfert"
    if alias in connections:
        raise CommandError("Une connexion sqlite_transfert existe déjà.")

    with TemporaryDirectory(prefix="cafe-transfert-") as dossier:
        copie = Path(dossier) / "source.sqlite3"
        # L'API de sauvegarde inclut aussi les données du journal WAL.
        with closing(sqlite3.connect(f"{chemin_source.as_uri()}?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(copie)) as instantane:
                source.backup(instantane)

        configuration = cible.settings_dict.copy()
        configuration.update(
            ENGINE="django.db.backends.sqlite3",
            NAME=f"{copie.as_uri()}?mode=ro",
            USER="", PASSWORD="", HOST="", PORT="",
            OPTIONS={"uri": True}, CONN_MAX_AGE=0,
        )
        connections.databases[alias] = configuration
        try:
            connexion_source = connections[alias]
            with connexion_source.cursor() as curseur:
                curseur.execute("PRAGMA quick_check")
                if curseur.fetchall() != [("ok",)]:
                    raise CommandError("La vérification du fichier SQLite a échoué.")
            connexion_source.check_constraints()
            executor = MigrationExecutor(connexion_source)
            executor.loader.check_consistent_history(connexion_source)
            if executor.migration_plan(executor.loader.graph.leaf_nodes()):
                raise CommandError(
                    "La source SQLite n'est pas à jour. Appliquez ses migrations avant le transfert."
                )
            donnees = exporter(alias)
            attendu = normaliser(donnees)

            with transaction.atomic(using=destination):
                with cible.cursor() as curseur:
                    curseur.execute("SELECT pg_try_advisory_xact_lock(%s)", [73758639])
                    if not curseur.fetchone()[0]:
                        raise CommandError("Un autre transfert est déjà en cours.")
                    if cible.introspection.table_names():
                        raise CommandError(
                            "La destination contient déjà des tables. "
                            "Choisissez une base PostgreSQL vide ; aucun écrasement n'est effectué."
                        )

                call_command(
                    "migrate", database=destination, interactive=False,
                    verbosity=0, skip_checks=True,
                )
                cible.check_constraints()
                # Remplacer seulement les valeurs initiales des migrations,
                # dans cette base qui était vide avant notre transaction.
                tables = [
                    cible.ops.quote_name(table)
                    for table in cible.introspection.table_names()
                    if table != "django_migrations"
                ]
                with cible.cursor() as curseur:
                    curseur.execute(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY")
                ContentType.objects.clear_cache()
                for objet in serializers.deserialize("json", donnees, using=destination):
                    objet.save(using=destination)
                cible.check_constraints()
                ajuster_sequences(cible)
                if normaliser(exporter(destination)) != attendu:
                    raise CommandError("Les données diffèrent après import : transfert annulé.")

            return Counter(ligne["model"] for ligne in attendu)
        finally:
            connections[alias].close()
            del connections[alias]
            del connections.databases[alias]
            ContentType.objects.clear_cache()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Arrêtez Django avant le transfert. La destination est configurée par "
            "POSTGRES_* dans .env et ne doit contenir aucune table. "
            "Le script crée le schéma et annule tout le transfert en cas d'erreur."
        ),
    )
    parser.add_argument("--source", required=True, type=Path, help="Fichier SQLite à transférer.")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    os.environ["CAFE_DB_ENGINE"] = "postgresql"
    try:
        import django
        django.setup()
        effectifs = transferer(args.source)
    except (CommandError, DatabaseError, ImproperlyConfigured, OSError,
            sqlite3.Error, DeserializationError) as erreur:
        parser.exit(1, f"Erreur : {erreur}\n")
    print(
        f"Transfert vérifié : {effectifs['CafeDolbeau.client']} clients, "
        f"{effectifs['CafeDolbeau.transactioncafe']} transactions, "
        f"{effectifs['auth.user']} comptes. SQLite conservé."
    )


if __name__ == "__main__":
    main()
