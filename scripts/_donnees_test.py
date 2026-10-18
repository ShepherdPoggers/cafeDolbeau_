"""Initialisation des données de test V2 sur une nouvelle base."""
import argparse
import os
from pathlib import Path
import sys


def initialiser():
    parser = argparse.ArgumentParser(description="Créer une base de démonstration V2.")
    parser.add_argument("--database", required=True, type=Path, help="Nouveau fichier SQLite à créer.")
    args = parser.parse_args()
    chemin = args.database.resolve()
    if chemin.exists():
        parser.error(f"La base existe déjà : {chemin}. Choisissez un nouveau fichier.")
    if not chemin.parent.is_dir():
        parser.error("Le dossier de destination doit exister.")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    os.environ["CAFE_DB_PATH"] = str(chemin)
    import django
    django.setup()
    return args


def comptes():
    from django.contrib.auth.models import User
    resultat = {}
    for nom in ("admin_test", "gerant_test", "barista_test", "barista2_test", "inactif_test"):
        resultat[nom] = User.objects.create_user(
            username=nom, password="CafeTest-2026!",
            is_active=nom != "inactif_test",
            is_superuser=nom == "admin_test", is_staff=nom == "admin_test",
        )
    return resultat


def attribuer_roles(utilisateurs):
    from django.contrib.auth.models import Group
    for nom, utilisateur in utilisateurs.items():
        role = "Gérant" if nom == "gerant_test" else "Barista"
        utilisateur.groups.add(Group.objects.get(name=role))


def terminer():
    from django.conf import settings
    print(f"Base créée : {settings.DATABASES['default']['NAME']}")
    print("Comptes : admin_test, gerant_test, barista_test, barista2_test, inactif_test")
    print("Mot de passe de démonstration : CafeTest-2026!")
