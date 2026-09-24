# Café Dolbeau

Base de projet Django 5.2, avec Python 3.12 et SQLite pour le développement local.

## Cartes de cafés

- Le formulaire d’achat de cartes demande un nombre de cartes, chacune contenant 11 cafés, gratuité incluse.
- Chaque carte ajoute 11 au total de cafés achetés et 11 au solde prépayé.
- Le bouton « Utiliser les cafés prépayés » consomme d’abord le solde sans augmenter le total acheté. La portion dépassant le solde est comptée hors carte, avec la règle du 11e café gratuit.
- L’enregistrement dans « Ajouter des cafés achetés » compte tous les cafés hors carte et conserve le solde prépayé intact, avec la même règle de gratuité.
- L’historique distingue les prépaiements, leur consommation, les achats hors carte et les cafés gratuits.

Les anciens compteurs et transactions sont conservés : ce changement ne recalcule pas les opérations passées.

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

## Lancement dans VS Code

Avec les extensions **Python** et **Python Debugger** de Microsoft installées,
ouvrir `manage.py` et cliquer sur le bouton ▶ **Run Python File** en haut à droite.
Sans argument, `manage.py` démarre le serveur de développement.
Le site est accessible à http://127.0.0.1:8000/.

Pour déboguer, appuyer sur **F5** avec la configuration
**Café Dolbeau : démarrer Django**. Arrêter le serveur avec **Ctrl+C** dans le
terminal, ou **Shift+F5** pendant le débogage.

Le projet utilise l'environnement `.venv`. Si VS Code a déjà sélectionné un autre
interpréteur, exécuter **Python: Select Interpreter** dans la palette de commandes
et choisir `.venv/bin/python`.

## Structure du projet

- `manage.py` : commandes Django.
- `config/` : paramètres, routes et points d’entrée ASGI/WSGI.
- `.venv/` : environnement Python local, ignoré par Git.

Vérifier la configuration avec `python manage.py check`.
Les paramètres fournis sont destinés au développement local.
