# Café Dolbeau

Application Django pour gérer les clients, les achats de cafés, les cartes prépayées et les cafés gratuits.

## Documentation

- [Conception du projet](docs/conception.md)
- [Utilisation de l'IA](AI-USAGE.md)

## Prérequis

- Python 3.12 avec `pip` et `venv`.
- Une copie du dépôt sur votre ordinateur.

Les dépendances sont fixées dans `requirements.txt`, notamment Django 5.2.17. SQLite est utilisé localement : aucun serveur de base de données supplémentaire n’est nécessaire.

## Première installation — Linux ou macOS

Ouvrir un terminal **à la racine du dépôt**, dans le dossier contenant `requirements.txt`, `README.md` et `src/`. Exécuter ces commandes dans ce même terminal :

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python src/manage.py check
python src/manage.py migrate
python src/manage.py runserver
```

Utiliser `python3.12` à la place de `python3` pour créer l’environnement si plusieurs versions sont installées.

Ouvrir [http://127.0.0.1:8000/](http://127.0.0.1:8000/) dans le navigateur. Garder le terminal ouvert pendant l’utilisation. **Ctrl+C** arrête le serveur.

## Première installation — Windows PowerShell

Depuis la racine du dépôt :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src/manage.py check
.\.venv\Scripts\python.exe src/manage.py migrate
.\.venv\Scripts\python.exe src/manage.py runserver
```

Ces commandes utilisent directement Python dans l’environnement virtuel, sans nécessiter l’activation d’un script PowerShell. Ouvrir ensuite [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

## Relancer le projet

Sous Linux ou macOS, depuis la racine du dépôt :

```bash
source .venv/bin/activate
python src/manage.py runserver
```

Sous Windows PowerShell :

```powershell
.\.venv\Scripts\python.exe src/manage.py runserver
```

Après une mise à jour du code, arrêter le serveur puis, avec l’environnement activé :

```bash
python -m pip install -r requirements.txt
python src/manage.py migrate
python src/manage.py check
python src/manage.py runserver
```

Sous Windows, remplacer `python` par `.\.venv\Scripts\python.exe` dans ce bloc.

## Base de données et administration

La base locale se trouve dans **`src/db.sqlite3`**. La commande `migrate` crée la base et ses tables si elles n’existent pas, ou applique les migrations manquantes. Elle doit être exécutée avant la première utilisation.

Les clients et transactions sont conservés dans ce fichier. Il est ignoré par Git : une nouvelle copie du dépôt démarre sans ces données. Pour conserver les données d’une installation précédente, arrêter le serveur et sauvegarder sa base avant tout déplacement ou remplacement de `src/db.sqlite3`.

Pour créer un compte administrateur, depuis la racine du dépôt avec l’environnement activé :

```bash
python src/manage.py createsuperuser
```

Sous Windows :

```powershell
.\.venv\Scripts\python.exe src/manage.py createsuperuser
```

Suivre les indications du terminal, puis se connecter à [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) lorsque le serveur est démarré. Le compte administrateur est facultatif pour utiliser la page d’accueil.


## Vérifications et dépannage

Ces commandes s’exécutent à la racine avec l’environnement virtuel activé. Sous Windows, utiliser `.\.venv\Scripts\python.exe` à la place de `python`.

```bash
python -m pip check
python src/manage.py check
python src/manage.py showmigrations
```

`check` vérifie la configuration Django. Dans `showmigrations`, `[X]` indique une migration appliquée. Ces vérifications ne remplacent pas les tests fonctionnels, disponibles avec :

```bash
python src/manage.py test CafeDolbeau
```

| Problème | Solution |
| --- | --- |
| `can't open file 'manage.py'` | Depuis la racine, utiliser `python src/manage.py …` : le fichier est dans `src/`. |
| `No module named 'django'` | Utiliser Python de `.venv` et exécuter `python -m pip install -r requirements.txt`. |
| `ensurepip` ou `venv` indisponible sous Ubuntu/Debian | Installer le paquet `python3-venv` correspondant à Python, puis recréer l’environnement. |
| `no such table` ou `no such column` | Arrêter le serveur, lancer `python src/manage.py migrate`, puis redémarrer. |
| Le port 8000 est déjà utilisé | Lancer `python src/manage.py runserver 8001`, puis ouvrir `http://127.0.0.1:8001/`. |
| Les anciens clients ne s’affichent plus après un déplacement du code | Vérifier que la base attendue se trouve dans `src/db.sqlite3`. |
| Le navigateur conserve un ancien script ou style | Effectuer un rechargement forcé de la page, par exemple **Ctrl+F5**. |


