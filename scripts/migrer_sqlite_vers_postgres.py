"""Migrer une copie de SQLite et la transférer vers PostgreSQL sans modifier l'original."""

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, time
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
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connections, DatabaseError, models, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import InconsistentMigrationHistory
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone


ERREUR_DESTINATION = (
    "La destination contient des données, une configuration personnalisée ou des tables étrangères. "
    "Utilisez une base vide ou initialisée uniquement par migrate ; aucun écrasement n'est effectué."
)


class EncodeurDatesExactes(DjangoJSONEncoder):
    def default(self, valeur):
        # L'encodeur Django standard tronque les microsecondes en millisecondes.
        if isinstance(valeur, (datetime, time)):
            return valeur.isoformat()
        return super().default(valeur)


def exporter(alias, *, naturelles=False):
    def objets():
        for modele in apps.get_models():
            if modele._meta.managed and not modele._meta.proxy:
                yield from modele._base_manager.using(alias).order_by(modele._meta.pk.name).iterator()

    return serializers.serialize(
        "json", objets(), cls=EncodeurDatesExactes,
        use_natural_foreign_keys=naturelles, use_natural_primary_keys=naturelles,
    )


def normaliser(donnees):
    lignes = json.loads(donnees)
    for ligne in lignes:
        modele = apps.get_model(ligne["model"])
        for champ in modele._meta.many_to_many:
            ligne["fields"][champ.name].sort()
    return sorted(lignes, key=lambda ligne: (ligne["model"], str(ligne["pk"])))


def configuration_initiale(alias):
    """Compare les valeurs initiales indépendamment des identifiants des permissions."""
    lignes = json.loads(exporter(alias, naturelles=True))
    initialisation = MigrationRecorder(connections[alias]).migration_qs.get(
        app="CafeDolbeau", name="0015_date_application_gratuite",
    ).applied
    date_initiale = timezone.localdate(initialisation).isoformat()
    for ligne in lignes:
        modele = apps.get_model(ligne["model"])
        # Une base initialisée hier reste une base initiale. Une date modifiée
        # manuellement, en revanche, doit être conservée et bloque le transfert.
        if modele._meta.model_name == "parametrescafe" and ligne["fields"]["date_application"] == date_initiale:
            ligne["fields"]["date_application"] = "date de la migration initiale"
        for champ in modele._meta.many_to_many:
            ligne["fields"][champ.name].sort()
    return sorted(json.dumps(ligne, sort_keys=True) for ligne in lignes)


def migrer(alias):
    connexion = connections[alias]
    executor = MigrationExecutor(connexion)
    try:
        executor.loader.check_consistent_history(connexion)
    except InconsistentMigrationHistory as erreur:
        raise CommandError(f"L'historique des migrations est incohérent : {erreur}") from erreur
    if set(executor.loader.applied_migrations) - set(executor.loader.disk_migrations):
        raise CommandError("La base contient des migrations inconnues de cette version du code.")
    call_command("migrate", database=alias, interactive=False, verbosity=0, skip_checks=True)
    connexion.check_constraints()


def verrouiller_destination(cible):
    """N'accepte que les tables Django attendues, sans données ajoutées."""
    tables = cible.introspection.table_names()
    if not tables:
        return False
    attendues = {
        modele._meta.db_table for modele in apps.get_models(include_auto_created=True)
        if modele._meta.managed
    } | {"django_migrations"}
    if set(tables) - attendues:
        raise CommandError(ERREUR_DESTINATION)
    valeurs_initiales = {
        "django_migrations", "django_content_type", "auth_permission", "auth_group",
        "auth_group_permissions", "CafeDolbeau_parametrescafe", "CafeDolbeau_succursale",
    }
    with cible.cursor() as curseur:
        noms = ", ".join(cible.ops.quote_name(table) for table in tables)
        curseur.execute(f"LOCK TABLE {noms} IN ACCESS EXCLUSIVE MODE")
        for table in tables:
            if table not in valeurs_initiales:
                curseur.execute(f"SELECT EXISTS(SELECT 1 FROM {cible.ops.quote_name(table)})")
                if curseur.fetchone()[0]:
                    raise CommandError(ERREUR_DESTINATION)
    return True


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
    reference = "sqlite_reference_transfert"
    if alias in connections or reference in connections:
        raise CommandError("Une connexion SQLite de transfert existe déjà.")

    with TemporaryDirectory(prefix="cafe-transfert-") as dossier:
        copie = Path(dossier) / "source.sqlite3"
        # L'API de sauvegarde inclut aussi les données du journal WAL.
        with closing(sqlite3.connect(f"{chemin_source.as_uri()}?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(copie)) as instantane:
                source.backup(instantane)

        configuration = cible.settings_dict.copy()
        configuration.update(
            ENGINE="django.db.backends.sqlite3",
            NAME=str(copie),
            USER="", PASSWORD="", HOST="", PORT="",
            OPTIONS={}, CONN_MAX_AGE=0,
        )
        connections.databases[alias] = configuration
        try:
            connexion_source = connections[alias]
            with connexion_source.cursor() as curseur:
                curseur.execute("PRAGMA quick_check")
                if curseur.fetchall() != [("ok",)]:
                    raise CommandError("La vérification du fichier SQLite a échoué.")
            connexion_source.check_constraints()
            # Seule cette copie privée est mise à jour, jamais le fichier source.
            migrer(alias)
            donnees = exporter(alias)
            attendu = normaliser(donnees)

            with transaction.atomic(using=destination):
                with cible.cursor() as curseur:
                    curseur.execute("SELECT pg_try_advisory_xact_lock(%s)", [73758639])
                    if not curseur.fetchone()[0]:
                        raise CommandError("Un autre transfert est déjà en cours.")
                deja_initialisee = verrouiller_destination(cible)
                migrer(destination)
                if deja_initialisee:
                    configuration_reference = configuration.copy()
                    configuration_reference["NAME"] = str(Path(dossier) / "reference.sqlite3")
                    connections.databases[reference] = configuration_reference
                    migrer(reference)
                    if configuration_initiale(destination) != configuration_initiale(reference):
                        raise CommandError(ERREUR_DESTINATION)
                # Remplacer seulement les valeurs initiales des migrations,
                # après vérification qu'aucune donnée ajoutée ne sera écrasée.
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
            for temporaire in (alias, reference):
                if temporaire in connections:
                    connections[temporaire].close()
                    del connections[temporaire]
                    del connections.databases[temporaire]
            ContentType.objects.clear_cache()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Arrêtez Django avant le transfert. La destination est configurée par "
            "POSTGRES_* dans .env et doit être vide ou contenir uniquement les valeurs initiales de migrate. "
            "Le script met à jour une copie temporaire de SQLite, crée le schéma PostgreSQL et annule "
            "tout le transfert en cas d'erreur. Le fichier SQLite original reste inchangé."
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
