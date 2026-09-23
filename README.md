# Café Dolbeau

Base de projet Django 5.2, avec Python 3.12 et SQLite pour le développement local.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Si la création du venv échoue sur Ubuntu/Debian faute de `ensurepip`, installer
le paquet `python3-venv`, puis relancer la commande.

Le site est accessible à l’adresse http://127.0.0.1:8000/.
Pour accéder à l’administration `/admin/`, créer un compte avec :

```bash
python manage.py createsuperuser
```

## Structure

- `manage.py` : commandes Django.
- `config/` : paramètres, routes et points d’entrée ASGI/WSGI.
- `.venv/` : environnement Python local, ignoré par Git.

Vérifier la configuration avec `python manage.py check`.
Les paramètres fournis sont destinés au développement local.
