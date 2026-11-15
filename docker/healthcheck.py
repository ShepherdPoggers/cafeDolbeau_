"""Vérifie Django et PostgreSQL sans dépendance curl dans l’image Python."""
import os
from urllib.request import Request, urlopen

hote = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost").split(",")[0].strip().lstrip(".")
if hote == "*":
    hote = "localhost"
requete = Request("http://127.0.0.1:8000/healthz", headers={"Host": hote})
with urlopen(requete, timeout=3) as reponse:
    if reponse.status != 200:
        raise SystemExit(1)
