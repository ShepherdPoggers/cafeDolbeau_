# Café Dolbeau

Application Django pour gérer les clients, les achats de cafés, les cartes prépayées et les cafés gratuits.


## Auteurs

- DESA07010400, Desbiens, Anthony
- SHEE15060600, Shepherd, Elliot

## Documentation

- [Conception du projet](docs/conception.md)
- [Migration de la V1 à la V2 et comparaison des soldes](docs/migration.md)
- [Retrospéction V1](docs/retrospection-V1.md)
- [Retrospéction V2](docs/retrospection-V2.md)
- [Migration](docs/migration.md)
- [ADR](docs/adr)
- [Utilisation de l'IA](AI-USAGE.md)


## Prérequis

- Python 3.12 avec `pip` et `venv`.
- Une copie du dépôt sur votre ordinateur.

Les dépendances sont fixées dans `requirements.txt`, notamment Django 5.2.17. PostgreSQL est utilisé par défaut, selon la configuration `.env`. Les scripts historiques de démonstration peuvent produire une base SQLite pour l’import initial. Le développement V3 utilise aussi PostgreSQL, avec la configuration locale explicite décrite dans le [guide de déploiement](docs/deploiement.md#développement-local-séparé).


## Démarrage de production V3

```bash
cp .env.example .env
docker compose up --build
```

Sur une installation existante, conserver `.env` et compléter ses variables plutôt
que de l’écraser. Ajouter `COMPOSE_FILE=docker/compose.yaml` si cette variable
est absente. Les secrets vides sont générés automatiquement au démarrage et
conservés dans un volume dédié ; les valeurs renseignées dans `.env` sont prioritaires. L’application est accessible sur **http://localhost:8000** via nginx
et Gunicorn, avec `DEBUG=False` et PostgreSQL interne persistant.

Pour arrêter les conteneurs, depuis la racine du projet :

```bash
docker compose down
```

Les données PostgreSQL sont conservées dans les volumes. Ne pas ajouter `-v` :
cette option supprime les volumes et leurs données.

Pour une installation indépendante sur AWS, suivre la
[procédure complète d'hébergement depuis zéro](docs/deploiement.md) :
préparation Linux, Windows ou macOS, clés et secrets GitHub, runner local,
déploiement du site puis transfert de PostgreSQL. Le déploiement AWS prépare un
certificat Let’s Encrypt pour Nginx avec renouvellement automatique ; suivre la
[transition du tunnel vers HTTPS](docs/deploiement.md#41-certificat-lets-encrypt-sur-nginx)
après le premier déploiement.

Le [guide Docker local](docs/dockerDeploiement.md) précise les commandes Windows,
les migrations automatiques, la création du premier compte, l’import SQLite V2,
le changement de domaine et le développement séparé. Les procédures V1/V2 plus bas
concernent les versions historiques et leurs données de démonstration.

Pour transférer PostgreSQL local directement vers EC2 sans passer les données par
GitHub, suivre la [procédure de transfert PostgreSQL](docs/deploiement.md#9-préparer-puis-transférer-la-vraie-base-locale).

Pour suivre le dernier déploiement de `main` puis afficher son résumé dans le
terminal (DNS EC2, liens et commande de transfert), avec GitHub CLI connecté :

```bash
python3 infra/scripts/suivre-deploiement.py
```

Ajouter un identifiant pour consulter une exécution précise, par exemple
`python3 infra/scripts/suivre-deploiement.py 44809435792`.

Pour déclencher un nouveau déploiement, suivre cette exécution et afficher son
résumé dans la même console :

Renseigner d'abord `GH_REPO=PROPRIETAIRE/DEPOT` dans le `.env` local pour cibler
votre fork à chaque lancement. Une variable `GH_REPO` exportée est prioritaire
sur ce fichier ; `CAFE_REPO` exportée sert de repli si `GH_REPO` n'est pas défini.
Sans dépôt explicite, le script
utilise le dépôt par défaut de GitHub CLI (`gh repo set-default`).

```bash
python3 infra/scripts/suivre-deploiement.py --lancer
```

Ajouter `--ref NOM_BRANCHE_TAG_OU_SHA` pour déployer une autre version que `main`.
Le workflow est toujours chargé depuis `main` ; les modifications du workflow et
du script doivent donc être poussées avant la première utilisation de `--lancer`.
Le runner autohébergé doit être en ligne. Sans `--lancer`, le script consulte
uniquement une exécution existante. Un identifiant unique permet de suivre le
pipeline lancé par la commande, même si d'autres déploiements sont déclenchés
en parallèle. Les modifications locales non poussées ne sont pas déployées.

Tous les tests Django et JavaScript, avec un PostgreSQL isolé :

```bash
docker compose --profile test run --build --rm tests
```

Dans les rapports, la synthèse et le détail des totaux présentent chaque
succursale sélectionnée séparément, puis le global de la sélection. Les mêmes
sections sont disponibles dans l’export Excel, y compris pour les succursales
sans activité.

## Consulter les soldes V3

Depuis la racine, pour tout le réseau :

```bash
docker compose exec app python src/manage.py balances
```

Pour une succursale, ou plusieurs succursales sélectionnées :

```bash
docker compose exec app python src/manage.py balances --succursale 1
docker compose exec app python src/manage.py balances --succursale 1 --succursale 2
```

Le filtre retient les clients ayant des transactions dans au moins une des
succursales choisies, y compris des transactions annulées. Chaque client apparaît
une seule fois avec ses **soldes globaux**, puisque sa fidélité est commune au
réseau. Les clients sans transaction apparaissent seulement dans la sortie
globale. Une succursale inexistante provoque une erreur sans produire de CSV.
Le format CSV reste identique pour comparer les soldes avant et après migration.

## Données de démonstration V3

Après le démarrage de la V3 et l’application des migrations, charger les données
avec le script dédié (l’image est reconstruite pour inclure le script) :

```bash
docker compose run --build --rm app python scripts/donnees_v3.py
```

Le script utilise PostgreSQL configuré dans Compose. Il ajoute trois succursales
`[Démo V3] Centre`, `Nord` et `Sud`, six clients et les comptes suivants :

| Compte | Rôle | Succursales accessibles |
| --- | --- | --- |
| `demo_proprietaire` | Propriétaire | Tout le réseau, sans affectation requise |
| `demo_gerant_centre_nord` | Gérant | Centre et Nord |
| `demo_gerant_sud` | Gérant | Sud |
| `demo_barista_centre` | Barista | Centre |
| `demo_barista_nord` | Barista | Nord |
| `demo_barista_sud` | Barista | Sud |
| `demo_barista_mobile` | Barista | Centre et Sud |
| `demo_inactif` | Barista désactivé | Centre, connexion refusée |

Un mot de passe aléatoire commun est affiché à la fin, avec les adresses des
caisses et les numéros des promotions. Pour choisir ce mot de passe, ajouter
`--password 'VotreMotDePasseDeDemo!'`. Aucun superutilisateur technique n’est créé.

Les scénarios comprennent des achats dans les trois succursales, l’historique
partagé d’un client avec plus de dix opérations, des cartes prépayées et leur
consommation, une opération annulée, une promotion active partagée par Centre et
Nord, une promotion annulée au Sud et une future promotion d’une journée.
Des transactions des derniers jours permettent aussi de tester les rapports.

Le chargement est atomique, conserve les données existantes et ne change pas la
succursale nº 1 ni les paramètres de fidélité. Si un identifiant de démonstration
existe déjà, le script refuse de charger une seconde fois les données.
Il ne s’exécute jamais automatiquement au démarrage.

Pour une exécution locale avec un environnement Python et la connexion PostgreSQL
déjà configurés : `python scripts/donnees_v3.py`. La commande Django équivalente
est `python src/manage.py donnees_v3`.


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
| `proprietaire_test` | `CafeTest-2026!` | Propriétaire | Toutes les fonctions métier et toutes les succursales, gestion des employés et des affectations, rapports et export Excel. Ce compte n’est pas superutilisateur Django. |
| `gerant_test` | `CafeTest-2026!` | Gérant | Succursales nº 1 et nº 2 : opérations et annulations dans son périmètre, création de Baristas et gestion de leurs affectations dans ce périmètre. Gestion globale des clients, fusions, soldes et fidélité. Aucun accès aux rapports et exports pour cette étape. |
| `barista_test` | `CafeTest-2026!` | Barista | `acces_base` : recherche et création de clients, achats de cafés et de cartes, consommation de crédits et annulation de ses propres transactions récentes dans la succursale courante (nº 1). Aucun accès aux rapports ni à l’administration. |
| `barista2_test` | `CafeTest-2026!` | Barista | `acces_base` : mêmes permissions que `barista_test`, avec ses propres transactions. Affecté aux succursales nº 1 et nº 2; permet de vérifier qu’un barista ne peut pas annuler les transactions d’un autre ou d’une autre caisse. |
| `inactif_test` | `CafeTest-2026!` | Barista désactivé | Membre du groupe Barista, mais connexion refusée et aucun accès tant que le compte est désactivé. |

Le groupe Gérant possède aussi les permissions Django `add_client`, `view_client`, `change_client` et `delete_client` pour administrer les clients.

La connexion se fait sur [http://127.0.0.1:8000/connexion/](http://127.0.0.1:8000/connexion/). L’administration est accessible aux Gérants, Propriétaires et superutilisateurs sur [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/).

Les pages de caisse utilisent `/succursales/1/`, `/succursales/2/` et `/succursales/3/`. La page `/` présente les succursales autorisées. L’historique client affiche les dix dernières transactions de tout le réseau; les soldes et la fidélité sont communs. Le Propriétaire accède aussi à la nº 3 et à toute future succursale. Pour une base existante, consulter la [migration des rôles et affectations](docs/migration.md#7-mettre-la-v3-en-service).

### Données disponibles

Le jeu de test contient des clients, dont deux homonymes, des achats directs avec récompense, des cartes prépayées, une consommation de crédits, une annulation, une fusion réversible et l’historique d’un client supprimé.

Les transactions sont réparties sur les 45 derniers jours. Pour voir tous les exemples dans les rapports, se connecter comme `proprietaire_test` ou `admin_test`, choisir une période couvrant les **60 derniers jours** et sélectionner tous les types de transactions.

## Afficher les soldes

Depuis la racine du dépôt, avec l’environnement virtuel activé :

```bash
python src/manage.py balances
```

Sous Windows, utiliser `.\.venv\Scripts\python.exe src/manage.py balances`.

Cette commande affiche un CSV trié par identifiant avec, pour chaque client, les achats cumulés (`cafes_achetes`), les étampes vers la prochaine récompense (`etampes`), les cafés gratuits en réserve (`recompenses_en_reserve`) et les cafés restants sur les cartes (`cafes_prepayes`). Les étampes correspondent au reste du compteur de fidélité habituelle (`nombre_cafes_fidelite`) divisé par le seuil actuellement en vigueur, soit 10 lors de la migration V1. Les achats promotionnels restent inclus dans les achats cumulés, mais ne font pas avancer ce compteur habituel. Le client fictif « Client supprimé » est exclu. Les données ne sont pas modifiées.

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

Pour transférer une ancienne base SQLite vers PostgreSQL, le script s’occupe des migrations et de l’importation :

```bash
python scripts/migrer_sqlite_vers_postgres.py --source src/db.sqlite3
```

Il met à jour une copie temporaire de SQLite et conserve le fichier original. PostgreSQL peut être vide ou déjà initialisé par `manage.py migrate`, avec uniquement ses valeurs initiales. Tout écrasement de données existantes est refusé. Voir la [procédure de transfert](docs/migration.md#5-transférer-le-sqlite-v2-en-lecture-seule).

La base SQLite de démonstration se trouve dans **`src/db.sqlite3`**. La base PostgreSQL est configurée par les variables `POSTGRES_*` du fichier `.env`. La commande `migrate` crée la base et ses tables si elles n’existent pas, ou applique les migrations manquantes. Elle doit être exécutée avant la première utilisation.

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
