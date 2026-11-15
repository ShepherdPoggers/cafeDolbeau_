"""Ajouter le jeu de démonstration V3 à la base PostgreSQL configurée."""
import os
from pathlib import Path
import sys


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line([sys.argv[0], "donnees_v3", *sys.argv[1:]])


if __name__ == "__main__":
    main()
