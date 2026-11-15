"""Initialiser les secrets persistants avant le démarrage de PostgreSQL et Django."""
import os
from pathlib import Path
import secrets


def preparer(dossier):
    dossier = Path(dossier)
    for nom, longueur in (("SECRET_KEY", 64), ("POSTGRES_PASSWORD", 32)):
        chemin = dossier / nom
        valeur = os.environ.get(nom, "")
        if chemin.exists() and not valeur:
            if not chemin.read_text().strip():
                raise RuntimeError(f"Le secret {nom} est vide dans le volume.")
            continue
        if chemin.exists() and chemin.read_text() == valeur:
            continue
        temporaire = dossier / (nom + ".tmp")
        temporaire.write_text(valeur or secrets.token_urlsafe(longueur))
        # PostgreSQL et Django utilisent des UID distincts ; seuls ces services
        # montent ce volume, en lecture seule après son initialisation.
        temporaire.chmod(0o444)
        temporaire.replace(chemin)


if __name__ == "__main__":
    preparer("/app/secrets")
    print("Secrets prêts ; aucune valeur n’est affichée.")
