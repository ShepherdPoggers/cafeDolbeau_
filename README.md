# Café Dolbeau

Application Django pour gérer les clients, les achats de cafés, les cartes prépayées et les cafés gratuits.

## Auteurs

- DESA07010400, Desbiens, Anthony
- SHEE15060600, Shepherd, Elliot

## Documentation

- [Conception du projet](docs/conception.md)
- [Migration de la V1 à la V2 et comparaison des soldes](docs/migration.md)
- [Retrospéction V1](docs/retrospection-V1.md)
- [ADR](docs/adr)
- [Utilisation de l'IA](AI-USAGE.md)


## Prérequis

- Python 3.12 avec `pip` et `venv`.
- Une copie du dépôt sur votre ordinateur.

Les dépendances sont fixées dans `requirements.txt`, notamment Django 5.2.17. SQLite est utilisé localement : aucun serveur de base de données supplémentaire n’est nécessaire.

## Démarrer une V2 neuve avec les données de test

Pour conserver les données d’une installation V1, suivre plutôt la [procédure de migration vers la V2](docs/migration.md).

Télécharger ou cloner le dépôt, puis ouvrir un terminal **à sa racine**, dans le dossier contenant `requirements.txt`, `README.md`, `scripts/` et `src/`.

Cette procédure crée une nouvelle base **`src/db.sqlite3`**. Ce fichier doit être absent : si une base existe déjà, arrêter le serveur et la déplacer ou la renommer pour la conserver avant de recommencer. Le script refuse d’écraser une base existante.

Le script `scripts/donnees_v2.py` applique toutes les migrations de la V2, crée les comptes et charge les données de test.

### Linux ou macOS

Exécuter ces commandes dans le même terminal :

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/donnees_v2.py --database src/db.sqlite3
python src/manage.py check
python src/manage.py runserver
```

Utiliser `python3.12` à la place de `python3` pour créer l’environnement si plusieurs versions sont installées.

Ouvrir [http://127.0.0.1:8000/](http://127.0.0.1:8000/) dans le navigateur. Garder le terminal ouvert pendant l’utilisation. **Ctrl+C** arrête le serveur.

### Windows PowerShell

Depuis la racine du dépôt :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/donnees_v2.py --database src/db.sqlite3
.\.venv\Scripts\python.exe src/manage.py check
.\.venv\Scripts\python.exe src/manage.py runserver
```

Ces commandes utilisent directement Python dans l’environnement virtuel, sans nécessiter l’activation d’un script PowerShell. Ouvrir ensuite [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

### Se connecter

Le script crée automatiquement les employés suivants :

| Nom d’utilisateur | Mot de passe | Rôle / état | Permissions et accès |
| --- | --- | --- | --- |
| `admin_test` | `CafeTest-2026!` | Superutilisateur | Toutes les permissions, y compris la gestion des employés et des groupes dans l’administration. |
| `gerant_test` | `CafeTest-2026!` | Gérant | `acces_base` et `acces_gerant` : opérations courantes, annulation des transactions des employés, rapports et export Excel, gestion des clients, fusions et modification de la règle du café gratuit. |
| `barista_test` | `CafeTest-2026!` | Barista | `acces_base` : recherche et création de clients, achats de cafés et de cartes, consommation de crédits et annulation de ses propres transactions. Aucun accès aux rapports ni à l’administration. |
| `barista2_test` | `CafeTest-2026!` | Barista | `acces_base` : mêmes permissions que `barista_test`, avec ses propres transactions. Permet de vérifier qu’un barista ne peut pas annuler les transactions d’un autre. |
| `inactif_test` | `CafeTest-2026!` | Barista désactivé | Membre du groupe Barista, mais connexion refusée et aucun accès tant que le compte est désactivé. |

Le groupe Gérant possède aussi les permissions Django `add_client`, `view_client`, `change_client` et `delete_client` pour administrer les clients.

La connexion se fait sur [http://127.0.0.1:8000/connexion/](http://127.0.0.1:8000/connexion/). L’administration est accessible aux gérants et superutilisateurs sur [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/).

### Données disponibles

Le jeu de test contient des clients, dont deux homonymes, des achats directs avec récompense, des cartes prépayées, une consommation de crédits, une annulation, une fusion réversible et l’historique d’un client supprimé.

Les transactions sont réparties sur les 45 derniers jours. Pour voir tous les exemples dans les rapports, choisir une période couvrant les **60 derniers jours** et sélectionner tous les types de transactions.

## Afficher les soldes

Depuis la racine du dépôt, avec l’environnement virtuel activé :

```bash
python src/manage.py balances
```

Sous Windows, utiliser `.\.venv\Scripts\python.exe src/manage.py balances`.

Cette commande affiche un CSV trié par identifiant avec, pour chaque client, les achats cumulés (`cafes_achetes`), les étampes vers la prochaine récompense (`etampes`), les cafés gratuits en réserve (`recompenses_en_reserve`) et les cafés restants sur les cartes (`cafes_prepayes`). Les étampes correspondent au reste des achats cumulés divisé par le seuil actuellement en vigueur, soit 10 lors de la migration V1. Le client fictif « Client supprimé » est exclu. Les données ne sont pas modifiées.

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

La procédure V2 ci-dessus exécute déjà les migrations. Pour démarrer plutôt avec une base vide, remplacer la commande de chargement des données de test par `python src/manage.py migrate`, puis créer un premier compte avec `python src/manage.py createsuperuser` avant de lancer le serveur. Sous Windows, utiliser `.\.venv\Scripts\python.exe` à la place de `python`.

Les clients et transactions sont conservés dans ce fichier. Il est ignoré par Git : une nouvelle copie du dépôt démarre sans ces données. Pour conserver les données d’une installation précédente, arrêter le serveur et sauvegarder sa base avant tout déplacement ou remplacement de `src/db.sqlite3`.

Le jeu de test fournit déjà les comptes `admin_test` et `gerant_test`. Pour créer un autre compte administrateur, depuis la racine du dépôt avec l’environnement activé :

```bash
python src/manage.py createsuperuser
```

Sous Windows :

```powershell
.\.venv\Scripts\python.exe src/manage.py createsuperuser
```

Suivre les indications du terminal, puis se connecter à [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) lorsque le serveur est démarré. L’accès à la page d’accueil nécessite un compte actif disposant des permissions du café.

### Planifier la règle du café gratuit

Dans l’administration, les gérants et superutilisateurs peuvent ouvrir « Paramètres du café », saisir le nombre de cafés achetés pour un café gratuit et choisir la date d’entrée en vigueur. Le seuil actuellement en vigueur est affiché à titre de référence. L’ancienne règle reste active jusqu’à minuit à la date choisie, heure du Québec ; la nouvelle règle s’applique ensuite automatiquement aux prochains achats. Choisir aujourd’hui pour un changement immédiat.

Une modification remplace toute planification précédente. Les cafés accumulés servent au calcul avec le nouveau seuil, sans recalculer les transactions ni les soldes existants.

### Supprimer un client

Les gérants et superutilisateurs peuvent supprimer un client depuis sa fiche dans l’administration, ou plusieurs clients avec l’action « Supprimer les clients sélectionnés ». La confirmation affiche les cafés prépayés et gratuits qui seront perdus. Si les soldes changent entre l’affichage et la validation, une nouvelle confirmation est nécessaire.

La suppression est définitive, mais les transactions et leurs annulations sont conservées sous « Client supprimé ». Ce client fictif est masqué dans la gestion courante des clients. Les gérants peuvent encore annuler ses transactions depuis l’administration des transactions ; ces annulations alimentent les rapports sans rétablir de crédits utilisables.


## Lancer tous les tests

Installer les dépendances Python selon la section d’installation. Node.js doit aussi être installé pour les tests JavaScript ; aucun paquet npm supplémentaire n’est requis.

Depuis la racine du dépôt, sous Linux ou macOS :

```bash
source .venv/bin/activate
python src/manage.py test CafeDolbeau
node --test src/CafeDolbeau/tests_js/rapports.test.cjs
```

Sous Windows PowerShell :

```powershell
.\.venv\Scripts\python.exe src/manage.py test CafeDolbeau
node --test src/CafeDolbeau/tests_js/rapports.test.cjs
```

La première commande de test lance tous les tests Django, notamment ceux des permissions, transactions, annulations, rapports, paramètres, suppressions, fusions et migrations V1. La commande Node.js lance les tests JavaScript des rapports.

Django crée automatiquement une base de test temporaire et les tests préparent leurs propres données. Les résultats des deux suites sont affichés dans le terminal.

## Vérifications et dépannage

Ces commandes s’exécutent à la racine avec l’environnement virtuel activé. Sous Windows, utiliser `.\.venv\Scripts\python.exe` à la place de `python`.

```bash
python -m pip check
python src/manage.py check
python src/manage.py showmigrations
```

`check` vérifie la configuration Django. Dans `showmigrations`, `[X]` indique une migration appliquée. Pour les tests, suivre la section [Lancer tous les tests](#lancer-tous-les-tests).

| Problème | Solution |
| --- | --- |
| `can't open file 'manage.py'` | Depuis la racine, utiliser `python src/manage.py …` : le fichier est dans `src/`. |
| `No module named 'django'` | Utiliser Python de `.venv` et exécuter `python -m pip install -r requirements.txt`. |
| `ensurepip` ou `venv` indisponible sous Ubuntu/Debian | Installer le paquet `python3-venv` correspondant à Python, puis recréer l’environnement. |
| `no such table` ou `no such column` | Arrêter le serveur, lancer `python src/manage.py migrate`, puis redémarrer. |
| Le port 8000 est déjà utilisé | Lancer `python src/manage.py runserver 8001`, puis ouvrir `http://127.0.0.1:8001/`. |
| Les anciens clients ne s’affichent plus après un déplacement du code | Vérifier que la base attendue se trouve dans `src/db.sqlite3`. |
| Le navigateur conserve un ancien script ou style | Effectuer un rechargement forcé de la page, par exemple **Ctrl+F5**. |

