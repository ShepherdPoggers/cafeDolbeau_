"""Préparer les secrets locaux sans les inclure dans le dépôt ou dans une image."""
import argparse
from pathlib import Path
import re
import secrets


RACINE = Path(__file__).resolve().parents[1]


def configurer(chemin):
    chemin = Path(chemin)
    contenu = chemin.read_text() if chemin.exists() else (RACINE / ".env.example").read_text()
    for nom in ("SECRET_KEY", "POSTGRES_PASSWORD"):
        expression = re.compile(r"^" + nom + r"=(.*)$", re.M)
        valeur = expression.search(contenu)
        if valeur is not None and valeur.group(1).strip().strip("\"'"):
            continue
        ligne = nom + "=" + secrets.token_urlsafe(64 if nom == "SECRET_KEY" else 32)
        if valeur:
            contenu = expression.sub(lambda _: ligne, contenu)
        else:
            contenu = contenu.rstrip() + "\n" + ligne + "\n"
    # O_EXCL n’est pas utilisé : le script doit aussi compléter un .env existant.
    # Ne pas changer un mot de passe déjà configuré sur un volume PostgreSQL.
    chemin.touch(mode=0o600, exist_ok=True)
    chemin.chmod(0o600)
    chemin.write_text(contenu)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=RACINE / ".env", help="Fichier .env à préparer.")
    options = parser.parse_args()
    configurer(options.file)
    print("Configuration prête. Les secrets existants ont été conservés ; aucune valeur n’est affichée.")
