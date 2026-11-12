import hashlib
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from runpy import run_path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest import skipUnless
from uuid import uuid4

from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import CommandError
from django.core.management import call_command
from django.db import connection, connections, DataError
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase
from django.utils import timezone

from ..models import AffectationEmployeSuccursale, Client, FusionClient, ParametresCafe, Succursale, TransactionCafe


RACINE = Path(__file__).resolve().parents[3]
script = run_path(str(RACINE / "scripts/migrer_sqlite_vers_postgres.py"))
transferer = script["transferer"]
ERREUR_DESTINATION = script["ERREUR_DESTINATION"]


@skipUnless(connection.vendor == "postgresql", "Nécessite PostgreSQL.")
class TransfertSQLiteTests(TransactionTestCase):
    @classmethod
    def _validate_databases(cls):
        # Le script crée et ferme cet alias SQLite pendant chaque transfert.
        return super()._validate_databases() | {"sqlite_transfert", "sqlite_reference_transfert"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dossier = TemporaryDirectory(prefix="cafe-test-transfert-")
        cls.addClassCleanup(cls.dossier.cleanup)
        cls.modele = Path(cls.dossier.name) / "modele.sqlite3"
        subprocess.run(
            [sys.executable, str(RACINE / "scripts/donnees_v2.py"), "--database", str(cls.modele)],
            cwd=RACINE, check=True, capture_output=True, text=True,
        )

        # Étendre uniquement le jeu de test, sans imposer ces comptes à la démonstration V2.
        subprocess.run(
            [sys.executable, str(RACINE / "src/manage.py"), "shell", "-c", """
from django.contrib.auth.models import Group
from CafeDolbeau.models import AffectationEmployeSuccursale, Employe, Succursale
compte = Employe.objects.create_user('proprietaire_test', password='CafeTest-2026!')
compte.groups.add(Group.objects.get(name='Propriétaire'))
seconde = Succursale.objects.create(nom='Succursale #2')
Succursale.objects.create(nom='Succursale #3')
for utilisateur in Employe.objects.filter(username__in=['gerant_test', 'barista2_test']):
    AffectationEmployeSuccursale.objects.create(employe_id=utilisateur.pk, succursale=seconde)
"""],
            env={**os.environ, "CAFE_DB_ENGINE": "sqlite", "CAFE_DB_PATH": str(cls.modele)},
            cwd=RACINE, check=True, capture_output=True, text=True,
        )

    def setUp(self):
        self.source = Path(self.dossier.name) / "source.sqlite3"
        shutil.copyfile(self.modele, self.source)
        self.schema = connection.ops.quote_name(f"transfert_test_{uuid4().hex}")
        with connection.cursor() as curseur:
            curseur.execute("SHOW search_path")
            self.ancien_chemin = curseur.fetchone()[0]
            curseur.execute(f"CREATE SCHEMA {self.schema}")
            curseur.execute(f"SET search_path TO {self.schema}")
        ContentType.objects.clear_cache()
        self.addCleanup(self.nettoyer_schema)

    def nettoyer_schema(self):
        ContentType.objects.clear_cache()
        with connection.cursor() as curseur:
            curseur.execute("SELECT set_config('search_path', %s, false)", [self.ancien_chemin])
            curseur.execute(f"DROP SCHEMA {self.schema} CASCADE")

    def ancien_schema_source(self):
        subprocess.run(
            [sys.executable, str(RACINE / "src/manage.py"), "migrate", "CafeDolbeau", "0016", "--noinput"],
            env={**os.environ, "CAFE_DB_ENGINE": "sqlite", "CAFE_DB_PATH": str(self.source)},
            cwd=RACINE, check=True, capture_output=True, text=True,
        )

    def instantane_destination(self):
        return script["normaliser"](script["exporter"]("default"))

    def test_transfere_soldes_historique_comptes_roles_json_et_sequences(self):
        with sqlite3.connect(self.source) as source:
            source.execute(
                'INSERT INTO "CafeDolbeau_succursale" (id, nom) VALUES (?, ?)',
                [701, "Autre succursale"],
            )
            source.execute(
                'UPDATE "CafeDolbeau_transactioncafe" SET succursale_id = 701 '
                'WHERE operation_id = (SELECT operation_id FROM "CafeDolbeau_transactioncafe" '
                'ORDER BY id LIMIT 1)'
            )
            source.execute("INSERT INTO auth_group (id, name) VALUES (801, 'Rôle personnalisé')")
            source.execute(
                "INSERT INTO auth_user_groups (user_id, group_id) "
                "SELECT id, 801 FROM auth_user WHERE username = 'gerant_test'"
            )
            effectifs = {
                modele: source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for modele, table in (
                    ("CafeDolbeau.client", "CafeDolbeau_client"),
                    ("CafeDolbeau.succursale", "CafeDolbeau_succursale"),
                    ("CafeDolbeau.affectationemployesuccursale", "CafeDolbeau_affectationemployesuccursale"),
                    ("CafeDolbeau.transactioncafe", "CafeDolbeau_transactioncafe"),
                    ("auth.user", "auth_user"),
                )
            }
            clients = source.execute(
                'SELECT id, nombre_cafes_achetes, nombre_cafes_prepayes, nombre_cafes_gratuits '
                'FROM "CafeDolbeau_client" ORDER BY id'
            ).fetchall()
            succursales_transactions = source.execute(
                'SELECT id, succursale_id FROM "CafeDolbeau_transactioncafe" ORDER BY id'
            ).fetchall()
        empreinte = hashlib.sha256(self.source.read_bytes()).hexdigest()

        resultat = transferer(self.source)

        for modele, nombre in effectifs.items():
            self.assertEqual(resultat[modele], nombre)
        self.assertEqual(list(Client.objects.order_by("pk").values_list(
            "pk", "nombre_cafes_achetes", "nombre_cafes_prepayes", "nombre_cafes_gratuits",
        )), clients)
        self.assertTrue(User.objects.get(username="admin_test").check_password("CafeTest-2026!"))
        self.assertTrue(User.objects.get(username="gerant_test").has_perm("CafeDolbeau.acces_gerant"))
        proprietaire = User.objects.get(username="proprietaire_test")
        self.assertTrue(proprietaire.has_perm("CafeDolbeau.acces_proprietaire"))
        self.assertFalse(proprietaire.is_superuser)
        self.assertEqual(set(AffectationEmployeSuccursale.objects.filter(
            employe__username="gerant_test",
        ).values_list("succursale_id", flat=True)), {1, 2})
        self.assertTrue(User.objects.get(username="gerant_test").groups.filter(pk=801).exists())
        self.assertFalse(User.objects.get(username="inactif_test").is_active)
        self.assertTrue(TransactionCafe.objects.filter(client_id=-1).exists())
        fusion = FusionClient.objects.get()
        self.assertIsInstance(fusion.soldes_source, dict)
        self.assertTrue(fusion.transactions_deplacees)
        self.assertTrue(TransactionCafe.objects.filter(annulation__isnull=False).exists())
        self.assertEqual(Succursale.objects.get(pk=1).nom, "Succursale #1")
        self.assertEqual(Succursale.objects.get(pk=701).nom, "Autre succursale")
        self.assertEqual(list(TransactionCafe.objects.order_by("pk").values_list(
            "pk", "succursale_id",
        )), succursales_transactions)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), empreinte)
        self.assertNotIn("sqlite_transfert", connections)

        dernier_client = Client.objects.order_by("-pk").first().pk
        self.assertGreater(Client.objects.create(nom_complet="Après transfert").pk, dernier_client)
        self.assertGreater(Group.objects.create(name="Après transfert").pk, 801)
        self.assertGreater(Succursale.objects.create(nom="Après transfert").pk, 701)
        self.assertGreater(User.objects.create_user("apres-transfert").pk, max(
            User.objects.exclude(username="apres-transfert").values_list("pk", flat=True),
        ))

    def test_client_fictif_seul_ne_produit_pas_de_sequence_negative(self):
        with sqlite3.connect(self.source) as source:
            for table in (
                "CafeDolbeau_annulationtransaction", "CafeDolbeau_fusionclient",
                "CafeDolbeau_transactioncafe",
            ):
                source.execute(f'DELETE FROM "{table}"')
            source.execute('DELETE FROM "CafeDolbeau_client" WHERE id != -1')

        transferer(self.source)

        self.assertEqual(list(Client.objects.values_list("pk", flat=True)), [-1])
        self.assertEqual(Client.objects.create(nom_complet="Premier nouveau client").pk, 1)

    def test_refuse_une_destination_existante_sans_la_modifier(self):
        with connection.cursor() as curseur:
            curseur.execute("CREATE TABLE a_conserver (id integer)")
            curseur.execute("INSERT INTO a_conserver VALUES (42)")

        with self.assertRaisesMessage(CommandError, ERREUR_DESTINATION):
            transferer(self.source)

        self.assertEqual(connection.introspection.table_names(), ["a_conserver"])
        with connection.cursor() as curseur:
            curseur.execute("SELECT id FROM a_conserver")
            self.assertEqual(curseur.fetchall(), [(42,)])

    def test_erreur_import_annule_aussi_la_creation_des_tables(self):
        with sqlite3.connect(self.source) as source:
            source.execute("UPDATE auth_user SET username = ? WHERE username = ?", ["x" * 151, "admin_test"])

        with self.assertRaises(DataError):
            transferer(self.source)

        self.assertEqual(connection.introspection.table_names(), [])
        self.assertNotIn("sqlite_transfert", connections)
        with sqlite3.connect(self.source) as source:
            source.execute("UPDATE auth_user SET username = ? WHERE username = ?", ["admin_test", "x" * 151])
        self.assertEqual(transferer(self.source)["auth.user"], 6)

    def test_migre_la_copie_v2_et_preserve_le_fichier_original_les_comptes_et_les_roles(self):
        self.ancien_schema_source()
        with sqlite3.connect(self.source) as source:
            clients = source.execute('SELECT * FROM "CafeDolbeau_client" ORDER BY id').fetchall()
            champs_comptes = [champ[1] for champ in source.execute('PRAGMA table_info(auth_user)')]
            comptes = [tuple(
                datetime.fromisoformat(valeur).replace(tzinfo=UTC)
                if nom in ("last_login", "date_joined") and valeur is not None else valeur
                for nom, valeur in zip(champs_comptes, ligne)
            ) for ligne in source.execute('SELECT * FROM auth_user ORDER BY id')]
            roles = source.execute('SELECT * FROM auth_user_groups ORDER BY id').fetchall()
            transactions = source.execute('SELECT id, client_id, quantite, type_transaction, date_creation FROM "CafeDolbeau_transactioncafe" ORDER BY id').fetchall()
        empreinte = hashlib.sha256(self.source.read_bytes()).hexdigest()

        transferer(self.source)

        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), empreinte)
        with sqlite3.connect(self.source) as source:
            self.assertEqual(source.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'CafeDolbeau_succursale'").fetchone()[0], 0)
            self.assertEqual(list(Client.objects.order_by("pk").values_list(
                *[champ[1] for champ in source.execute('PRAGMA table_info("CafeDolbeau_client")')],
            )), clients)
        self.assertEqual(list(User.objects.order_by("pk").values_list(*champs_comptes)), comptes)
        self.assertEqual(list(User.groups.through.objects.order_by("pk").values_list()), roles)
        self.assertEqual([(ligne.pk, ligne.client_id, ligne.quantite, ligne.type_transaction,
                           ligne.date_creation.isoformat(sep=" "))
                          for ligne in TransactionCafe.objects.order_by("pk")], [
                              (*ligne[:4], ligne[4] + "+00:00") for ligne in transactions
                          ])
        self.assertFalse(TransactionCafe.objects.exclude(succursale_id=1).exists())
        self.assertTrue(AffectationEmployeSuccursale.objects.filter(employe__username="gerant_test", succursale_id=1).exists())

    def test_transfere_directement_une_v1_sans_modifier_sqlite(self):
        source_v1 = self.source.with_name("source-v1.sqlite3")
        subprocess.run(
            [sys.executable, str(RACINE / "scripts/donnees_v1.py"), "--database", str(source_v1)],
            cwd=RACINE, check=True, capture_output=True, text=True,
        )
        empreinte = hashlib.sha256(source_v1.read_bytes()).hexdigest()
        resultat = transferer(source_v1)
        self.assertEqual(resultat["CafeDolbeau.client"], 6)
        self.assertEqual(resultat["CafeDolbeau.transactioncafe"], 12)
        self.assertEqual(hashlib.sha256(source_v1.read_bytes()).hexdigest(), empreinte)
        self.assertFalse(TransactionCafe.objects.exclude(succursale_id=1).exists())

    def test_accepte_une_destination_initialisee_par_migrate(self):
        call_command("migrate", interactive=False, verbosity=0)
        self.assertTrue(connection.introspection.table_names())
        self.assertFalse(User.objects.exists())

        resultat = transferer(self.source)

        self.assertEqual(User.objects.count(), resultat["auth.user"])
        self.assertTrue(User.objects.get(username="gerant_test").has_perm("CafeDolbeau.acces_gerant"))
        self.assertNotIn("sqlite_reference_transfert", connections)

    def test_accepte_une_destination_initialisee_un_autre_jour(self):
        call_command("migrate", interactive=False, verbosity=0)
        hier = timezone.now() - timedelta(days=1)
        MigrationRecorder(connection).migration_qs.filter(
            app="CafeDolbeau", name="0015_date_application_gratuite",
        ).update(applied=hier)
        ParametresCafe.objects.filter(pk=1).update(date_application=timezone.localdate(hier))
        resultat = transferer(self.source)
        self.assertEqual(User.objects.count(), resultat["auth.user"])

    def test_refuse_les_comptes_existants_meme_sans_clients(self):
        call_command("migrate", interactive=False, verbosity=0)
        User.objects.create_superuser("administrateur-a-conserver")
        avant = self.instantane_destination()
        with self.assertRaisesMessage(CommandError, ERREUR_DESTINATION):
            transferer(self.source)
        self.assertEqual(self.instantane_destination(), avant)

    def test_refuse_une_configuration_personnalisee_sans_la_modifier(self):
        call_command("migrate", interactive=False, verbosity=0)
        ParametresCafe.objects.filter(pk=1).update(cafes_pour_gratuite=7)
        avant = self.instantane_destination()
        with self.assertRaisesMessage(CommandError, ERREUR_DESTINATION):
            transferer(self.source)
        self.assertEqual(self.instantane_destination(), avant)
        self.assertNotIn("sqlite_reference_transfert", connections)

    def test_echec_import_restaure_une_destination_initialisee(self):
        call_command("migrate", interactive=False, verbosity=0)
        avant = self.instantane_destination()
        with sqlite3.connect(self.source) as source:
            source.execute("UPDATE auth_user SET username = ? WHERE username = ?", ["x" * 151, "admin_test"])
        with self.assertRaises(DataError):
            transferer(self.source)
        self.assertEqual(self.instantane_destination(), avant)

    def test_refuse_un_historique_incoherent_avant_de_toucher_postgresql(self):
        with sqlite3.connect(self.source) as source:
            source.execute(
                "DELETE FROM django_migrations WHERE app = 'CafeDolbeau' AND name = '0017_succursales'"
            )

        with self.assertRaisesMessage(CommandError, "historique des migrations est incohérent"):
            transferer(self.source)

        self.assertEqual(connection.introspection.table_names(), [])

    def test_ligne_de_commande_charge_la_connexion_et_refuse_une_seconde_execution(self):
        self.ancien_schema_source()
        call_command("migrate", interactive=False, verbosity=0)
        configuration = connection.settings_dict
        environnement = {
            **os.environ,
            "POSTGRES_DB": str(configuration["NAME"]),
            "POSTGRES_USER": configuration["USER"],
            "POSTGRES_PASSWORD": configuration["PASSWORD"],
            "POSTGRES_HOST": configuration["HOST"],
            "POSTGRES_PORT": str(configuration["PORT"]),
            "PGOPTIONS": f"-csearch_path={self.schema}",
            "CAFE_DB_ENGINE": "sqlite",
        }
        commande = [
            sys.executable, str(RACINE / "scripts/migrer_sqlite_vers_postgres.py"),
            "--source", str(self.source),
        ]
        resultat = subprocess.run(commande, env=environnement, capture_output=True, text=True)
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertIn("Transfert vérifié", resultat.stdout)
        self.assertEqual(User.objects.count(), 6)
        effectifs = (Client.objects.count(), TransactionCafe.objects.count())

        resultat = subprocess.run(commande, env=environnement, capture_output=True, text=True)
        self.assertEqual(resultat.returncode, 1)
        self.assertEqual(
            resultat.stderr,
            f"Erreur : {ERREUR_DESTINATION}\n",
        )
        self.assertEqual((Client.objects.count(), TransactionCafe.objects.count()), effectifs)

    def test_ligne_de_commande_source_absente_affiche_erreur_sans_traceback(self):
        resultat = subprocess.run(
            [sys.executable, str(RACINE / "scripts/migrer_sqlite_vers_postgres.py"),
             "--source", str(self.source.parent / "absent.sqlite3")],
            capture_output=True, text=True,
        )
        self.assertEqual(resultat.returncode, 1)
        self.assertIn("Erreur : Fichier SQLite introuvable", resultat.stderr)
        self.assertNotIn("Traceback", resultat.stderr)
