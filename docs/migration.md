# Migrer les données de la V1 vers la V2

## Conservation des données

Les migrations V1 `0001` à `0008` sont identiques à celles des tags existants, dont `v1.0.0.4`. La V2 applique ensuite les migrations `0009` à `0016` sans supprimer les clients ni recalculer leurs soldes.

Les trois compteurs de `Client` conservent leur forme et leurs valeurs :

| Donnée | Champ conservé |
| --- | --- |
| Achats cumulés servant au calcul des étampes | `nombre_cafes_achetes` |
| Récompenses en réserve | `nombre_cafes_gratuits` |
| Cafés restants sur les cartes prépayées | `nombre_cafes_prepayes` |

Les étampes vers la prochaine récompense correspondent à `nombre_cafes_achetes % seuil`. Le seuil est de 10 en V1 et reste à 10 après les migrations V2. La commande V2 `python src/manage.py balances` affiche ces étampes et les trois compteurs.

Aucune reconstitution des soldes n’est nécessaire. Les informations d’audit absentes de la V1 restent inconnues, comme expliqué dans l’[ADR-0008](adr/0008-MIGRATION_V1.md).

## Mettre à jour une base existante

1. Arrêter le serveur V1 et sauvegarder `src/db.sqlite3` ainsi que le code V1.
2. Avec le code V1 et l’environnement virtuel activé, enregistrer les clients avant la mise à jour :

   ```bash
   python src/manage.py dumpdata CafeDolbeau.Client --indent 2 --output clients-v1.json
   ```

3. Récupérer le code V2 en conservant **le même fichier `src/db.sqlite3`**. Si `CAFE_DB_PATH` est défini en V2, vérifier qu’il désigne cette base.
4. Depuis la racine du dépôt, mettre à jour les dépendances et appliquer les migrations :

   ```bash
   python -m pip install -r requirements.txt
   python src/manage.py migrate
   python src/manage.py check
   python src/manage.py showmigrations
   python src/manage.py balances
   ```

5. Comparer les soldes affichés avec les compteurs enregistrés dans `clients-v1.json`.
6. Avec un superutilisateur existant, attribuer les groupes Barista ou Gérant aux anciens employés. Leurs comptes et mots de passe sont conservés, mais les groupes ne leur sont pas attribués automatiquement.
7. Vérifier l’historique et les accès, puis relancer le serveur.

Sous Windows PowerShell, remplacer `python` par `.\.venv\Scripts\python.exe`. Pour préparer l’environnement virtuel, voir le [README](../README.md#prérequis).

En cas d’échec, restaurer la sauvegarde de la base avec le code V1. Le chargement de données de démonstration ne fait pas partie de la mise à jour d’une base existante.

## Reproduire la vérification avec les données de démonstration V1

Depuis le code V2, préparer l’environnement virtuel et les dépendances selon le README. Exécuter les commandes à la racine du dépôt, dans le même terminal. Le fichier `src/db.sqlite3` doit être absent : le script refuse d’écraser une base existante.

### 1. Créer la base de démonstration V1

```bash
python scripts/donnees_v1.py --database src/db.sqlite3
```

Le script applique uniquement les migrations V1 `0001` à `0008`, charge 6 clients et 12 transactions, puis affiche leurs soldes avant migration. Il crée aussi les comptes de démonstration avec le mot de passe `CafeTest-2026!`, dont le superutilisateur `admin_test`.

Les clients, leurs soldes et leurs transactions sont définis directement dans le script. Ils reprennent le jeu de démonstration validé avec les services du tag V1 `v1.0.0.4`. Le script utilise les modèles historiques V1 pour les créer ; il ne crée pas les colonnes ni les tables V2.

### 2. Migrer normalement vers la V2

```bash
python src/manage.py migrate
python src/manage.py check
python src/manage.py balances
```

Comparer les soldes affichés avec ceux du script : ils doivent être identiques au tableau ci-dessous. Le même fichier `src/db.sqlite3` est conservé et aucune donnée n’est rechargée. Après la migration, utiliser `admin_test` pour attribuer les rôles Barista ou Gérant aux autres comptes.

## Charger les données avec uniquement le code V1

Le correcteur qui a téléchargé directement la V1 peut charger le jeu de données de `donnees_v1.py` **sans installer ni exécuter la V2**. Le fichier doit lui être fourni séparément ou être joint à l'archive V1 ; un ancien tag ne contient pas automatiquement ce script ajouté ultérieurement.

Copier uniquement `donnees_v1.py` dans un dossier `scripts` à la racine du projet V1, au même niveau que `src`. La fonction `creer_donnees` est autonome : son import ne lance pas le script et ne nécessite pas `_donnees_test.py`. Elle utilise les modèles V1 de l'application déjà chargée par Django.

Arrêter le serveur, préparer l'environnement et installer les dépendances de la V1 selon son README. Utiliser une copie de travail V1 avec une base neuve : sauvegarder et déplacer tout fichier `src/db.sqlite3` existant avant de continuer. Le chargement ci-dessous utilise des identifiants fixes et doit être effectué une seule fois sur une base sans clients ni transactions.

Depuis la racine de cette copie V1, dans PowerShell :

```powershell
# Créer les tables avec les migrations disponibles dans la V1.
.\.venv\Scripts\python.exe src/manage.py migrate

# Charger les 6 clients et les 12 transactions dans une transaction atomique.
.\.venv\Scripts\python.exe src/manage.py shell -c "import sys; sys.path.insert(0, 'scripts'); from donnees_v1 import creer_donnees; from django.apps import apps; from django.db import transaction; transaction.atomic()(creer_donnees)(apps)"

# Facultatif : créer un compte pour consulter l'administration V1.
.\.venv\Scripts\python.exe src/manage.py createsuperuser

.\.venv\Scripts\python.exe src/manage.py runserver
```

Cette méthode charge uniquement les clients et les transactions ; elle ne crée pas les comptes de démonstration. Le compte d'administration et son mot de passe sont ceux choisis avec `createsuperuser`. Sous un autre système, remplacer `.\.venv\Scripts\python.exe` par l'interpréteur de l'environnement virtuel activé.

Ne pas lancer directement `python scripts/donnees_v1.py --database ...` dans cette procédure : ce point d'entrée dépend du fichier auxiliaire et du réglage `CAFE_DB_PATH` de la V2. Le passage par `manage.py shell` utilise la configuration de base de données propre à la V1.

Les soldes attendus figurent dans le tableau ci-dessous. Pour tester ensuite la mise à jour, arrêter le serveur et suivre la section « Mettre à jour une base existante » en conservant cette base.

## Résultat de notre vérification

Essai effectué le 18 octobre 2026 : base créée au schéma V1 avec `scripts/donnees_v1.py`, puis migrations V2 appliquées sur ce même fichier SQLite. Les migrations `0009` à `0016` et `check` ont réussi. Les achats cumulés, récompenses et prépayés sont identiques pour les 6 clients ; les étampes calculées le sont également.

Chaque cellule indique **avant / après** :

| Client | Achats cumulés | Étampes | Récompenses en réserve | Cafés prépayés restants |
| --- | --- | --- | --- | --- |
| Alice Tremblay | 9 / 9 | 9 / 9 | 0 / 0 | 0 / 0 |
| Benoît Gagnon | 12 / 12 | 2 / 2 | 1 / 1 | 0 / 0 |
| Camille Roy | 20 / 20 | 0 / 0 | 0 / 0 | 17 / 17 |
| Dominique Fortin | 17 / 17 | 7 / 7 | 0 / 0 | 10 / 10 |
| Élodie Simard | 33 / 33 | 3 / 3 | 1 / 1 | 10 / 10 |
| Client sans solde | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

Sortie de `balances` après la migration, identique à l’export CSV des mêmes valeurs avant la migration :

```csv
id,client,cafes_achetes,etampes,recompenses_en_reserve,cafes_prepayes
1,Alice Tremblay,9,9,0,0
2,Benoît Gagnon,12,2,1,0
3,Camille Roy,20,0,0,17
4,Dominique Fortin,17,7,0,10
5,Élodie Simard,33,3,1,10
6,Client sans solde,0,0,0,0
```

Les 12 transactions existantes conservent leurs identifiants, clients, types, quantités et dates. Les 5 comptes de démonstration conservent aussi leurs identifiants, mots de passe et états. Le script refuse une seconde exécution sur la même base sans la modifier.

La conservation des soldes et de l’historique a également été vérifiée avec une base créée par le code du tag `v1.0.0.4`. Les fichiers des migrations V1 ont été comparés à ceux des cinq tags V1 : aucune différence.

# Migrer les données de la V2 vers la V3

La V2 utilise le fichier SQLite `src/db.sqlite3`. La V3 utilise PostgreSQL pour
l’exploitation. Le transfert s’effectue une seule fois avec
`scripts/migrer_sqlite_vers_postgres.py` : ce script crée le schéma PostgreSQL,
applique les migrations nécessaires et transfère les données. Il n’est pas
nécessaire de migrer manuellement le fichier SQLite avant l’importation.

Toutes les commandes ci-dessous s’exécutent **à la racine du dépôt**, dans le
dossier contenant `src/`, `scripts/`, `docker/compose.yaml` et `requirements.txt`.

## 1. Arrêter la V2 et sauvegarder les données

1. Arrêter le serveur Django V2 et toute autre application qui écrit dans SQLite.
2. Conserver une copie du code et de la configuration V2 pour pouvoir revenir à
   cette version si nécessaire.
3. Avec Python disponible, sauvegarder la base V2 existante. Choisir un autre nom
   si `db-v2-sauvegarde.sqlite3` existe déjà :

   ```bash
   python -c "import sqlite3; source = sqlite3.connect('file:src/db.sqlite3?mode=ro', uri=True); copie = sqlite3.connect('db-v2-sauvegarde.sqlite3'); source.backup(copie); copie.close(); source.close()"
   ```

   Cette sauvegarde inclut les données du journal WAL, s’il existe. Le fichier
   source est ouvert en lecture seule.

4. Avant de remplacer le code V2, enregistrer les soldes avec sa configuration
   SQLite habituelle pour pouvoir les comparer après le transfert :

   ```bash
   python src/manage.py balances > balances-v2.csv
   ```

## 2. Installer le code V3 et préparer les secrets

Installer Docker et Docker Compose avec Buildx, puis récupérer le code V3 en
conservant le fichier SQLite V2. Dans cette procédure, son chemin reste
`src/db.sqlite3`. Toutes les commandes suivantes partent de la racine du dépôt.

Pour une nouvelle configuration :

```bash
cp .env.example .env
```

Sous PowerShell, utiliser `Copy-Item .env.example .env`. Si `.env` existe déjà,
le conserver et compléter les variables manquantes, dont
`COMPOSE_FILE=docker/compose.yaml`, à partir de `.env.example`. Les secrets vides
sont générés automatiquement dans un volume persistant au démarrage de Compose,
comme décrit dans le
[guide de déploiement](deploiement.md#installation-neuve).

## 3. Configurer la destination PostgreSQL

Vérifier les valeurs suivantes dans `.env` :

```dotenv
POSTGRES_DB=cafe_dolbeau
POSTGRES_USER=cafe_dolbeau
POSTGRES_HOST=db
POSTGRES_PORT=5432
CAFE_DB_ENGINE=postgresql
HTTP_PORT=8000
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1]
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
```

`SECRET_KEY` et `POSTGRES_PASSWORD` peuvent rester vides pour une installation
neuve : Compose les génère dans le volume `runtime_secrets`. Pour une base
existante, conserver les valeurs déjà configurées.
La destination doit être vide ou contenir uniquement les valeurs initiales des
migrations. Ne pas y créer de compte ni y charger de données avant l’import.

Compose utilise le nom interne `db` pour PostgreSQL. Son port n’est pas publié sur
l’ordinateur : le transfert s’exécute dans un conteneur du réseau interne.
Le fichier source est choisi par `--source`, indépendamment de `CAFE_DB_PATH`.
Les variables exportées dans le terminal sont prioritaires sur `.env` ; vérifier
qu’elles ne pointent pas vers une autre base. Le mot de passe d’un volume déjà
initialisé ne change pas simplement en modifiant `.env`.

## 4. Construire et démarrer la pile V3

```bash
docker compose up --build -d
docker compose ps -a
```

La pile démarre PostgreSQL, applique les migrations dans le service `init`,
collecte les fichiers statiques, puis démarre Gunicorn et nginx. Le service `init`
doit se terminer avec le code `0` ; les services permanents deviennent `healthy`.

Il est normal que le schéma PostgreSQL existe déjà avant le transfert : le script
accepte cet état initial. Ne pas créer de superutilisateur maintenant. Arrêter
les accès applicatifs avant l’import, en laissant PostgreSQL actif :

```bash
docker compose stop proxy app
```

En cas de problème, consulter `docker compose logs`. Une erreur de construction
mentionnant un plugin `docker-buildx` absent demande de réparer l’installation
Docker de l’ordinateur.

## 5. Transférer le SQLite V2 en lecture seule

Sous Linux ou macOS :

```bash
docker compose run --rm --no-deps -v "$PWD/src:/import:ro" app python scripts/migrer_sqlite_vers_postgres.py --source /import/db.sqlite3
```

Sous Windows PowerShell :

```powershell
docker compose run --rm --no-deps -v "${PWD}/src:/import:ro" app python scripts/migrer_sqlite_vers_postgres.py --source /import/db.sqlite3
```

Adapter le répertoire monté si le SQLite V2 est ailleurs. Monter le répertoire
permet d’inclure les éventuels fichiers `db.sqlite3-wal` et `db.sqlite3-shm`.
Le montage est en lecture seule. Sous Linux, si le fichier n’est lisible que par
son propriétaire, ajouter `--user "$(id -u):$(id -g)"` à la commande `run`.

**Cette commande réalise le transfert et les migrations nécessaires.** Le script
prend un instantané cohérent de SQLite et applique les migrations manquantes
uniquement sur cette copie temporaire. Le SQLite original reste inchangé.

Il conserve les identifiants, mots de passe, états d’activation et rôles : un
Barista reste Barista, un Gérant reste Gérant et un compte sans rôle reste sans
rôle. Les clients, leurs soldes, les dates et quantités des transactions, les
annulations et les fusions sont conservés. L’historique V2 est rattaché à la
succursale nº 1 ; les Baristas et Gérants existants y sont affectés. Aucun compte
n’est automatiquement promu Propriétaire.

L’import est transactionnel, vérifie les données et ajuste les séquences
PostgreSQL. En cas d’erreur, la destination retrouve son état précédent. Une
réussite affiche `Transfert vérifié`, les nombres de clients, transactions et
comptes, puis `SQLite conservé`.

Si la destination contient déjà des comptes, clients, transactions, paramètres
personnalisés ou tables étrangères, le script refuse le transfert sans les
effacer. Choisir alors une base vide. Une seconde exécution après un transfert
réussi est aussi refusée. Changer `POSTGRES_DB` dans `.env` ne crée pas à lui seul
une nouvelle base dans un volume PostgreSQL déjà initialisé.

## 6. Vérifier les données et les accès

```bash
docker compose run --rm --no-deps app python src/manage.py check
docker compose run --rm --no-deps app python src/manage.py showmigrations
docker compose run --rm --no-deps app python src/manage.py balances > balances-v3.csv
```

Les migrations doivent être marquées `[X]`. Comparer `balances-v3.csv` avec
`balances-v2.csv`. Aucun `migrate` supplémentaire n’est nécessaire après un
transfert réussi.

Un superutilisateur V2 conserve son compte et son mot de passe. Si la V2 n’en
possédait aucun, créer le premier superutilisateur **après l’import** :

```bash
docker compose run --rm --no-deps app python src/manage.py createsuperuser
```

## 7. Mettre la V3 en service

```bash
docker compose up -d
```

Ouvrir <http://localhost:8000/connexion/>, puis vérifier les rôles, les soldes et
les historiques, y compris les transactions annulées et les clients supprimés.
Avec un superutilisateur, attribuer le premier rôle Propriétaire dans `/admin/`,
puis configurer les succursales et affectations. La caisse initiale est
`/succursales/1/`. Les comptes sans rôle demandent une attribution explicite :
leur nom d’utilisateur ne détermine pas leur rôle.

La V3 fonctionne désormais uniquement sur PostgreSQL. Conserver le SQLite V2 et
sa sauvegarde comme archives. `docker compose down` conserve les données, tandis
que `docker compose down -v` supprime les volumes : ne pas utiliser cette dernière
commande pour un simple arrêt.

En cas d’échec avant la mise en service, garder la V3 arrêtée, corriger la cause
et relancer l’import sur une destination admissible. Le code et la configuration
V2 peuvent reprendre le SQLite conservé. Après de nouvelles opérations dans
PostgreSQL, cette archive ne contient plus les données récentes : un retour
arrière doit en tenir compte.

## Ajouter les succursales à une installation existante

Après avoir arrêté le serveur et sauvegardé la base utilisée par l’application, appliquer la mise à jour depuis la racine du dépôt, avec l’environnement virtuel activé :

```bash
python src/manage.py migrate
python src/manage.py check
```

La migration `0017_succursales` crée la succursale d’identifiant `1`, nommée « Succursale #1 », et lui associe toutes les transactions existantes, y compris les transactions annulées et celles des clients supprimés. Les dates, les quantités et les soldes des clients sont conservés. Cette migration fonctionne avec PostgreSQL et SQLite; elle s’applique aussi automatiquement aux installations neuves.

La fidélité reste commune à toutes les succursales. Les opérations saisies dans les formulaires utilisent maintenant la succursale de l’URL. Le service `ajouter_cafes` exige le paramètre `succursale_id` et vérifie les droits de l’employé; aucune opération de caisse ne choisit implicitement la succursale nº 1.

Les Propriétaires et superutilisateurs peuvent créer et renommer les succursales dans l’administration Django; leur suppression est désactivée. La succursale apparaît en lecture seule sur les transactions et permet de filtrer leur liste. Les gérants consultent et annulent les transactions des succursales auxquelles ils sont affectés, sans accès à la gestion des succursales.

Pour un transfert de SQLite vers PostgreSQL, le script applique cette migration sur sa copie temporaire et conserve les succursales et leurs liens avec les transactions.

## Ajouter le Propriétaire et les affectations

La même commande `python src/manage.py migrate` applique `0018_proprietaire_affectations`. Elle crée le groupe Propriétaire et les affectations des Baristas et Gérants existants à la succursale nº 1, y compris les comptes désactivés. Elle conserve les rôles existants, les identifiants, les mots de passe, les soldes et l’historique. Aucun compte n’est automatiquement promu Propriétaire.

Après la migration :

1. Se connecter avec un superutilisateur sur `/admin/`.
2. Créer ou modifier un compte employé, choisir le rôle **Propriétaire**, puis enregistrer. Ce compte obtient tous les droits métier et toutes les succursales sans devenir superutilisateur Django.
3. Le Propriétaire peut ensuite créer des Gérants et configurer les succursales de chaque employé. Un gérant peut créer uniquement des Baristas et gérer leurs affectations dans ses propres succursales. Les affectations hors de son périmètre sont conservées.
4. Remplacer les adresses des caisses par `/succursales/1/`, `/succursales/2/`, etc. Le nom de la succursale est affiché dans l’en-tête. `/` affiche les succursales accessibles, sans permettre d’opération de caisse; les anciennes adresses `/clients/.../cafes/` ne sont plus utilisées.

Les dix dernières transactions de chaque client restent visibles pour tous les employés autorisés à accéder à une caisse, toutes succursales confondues. Le barista peut annuler ses propres transactions récentes uniquement dans sa succursale courante. Le gérant peut annuler les transactions de toutes ses succursales; le Propriétaire peut annuler dans tout le réseau. Ces corrections restent des annulations tracées, sans suppression physique de transactions.

Les Gérants conservent les fonctions globales de gestion des clients, de fusion, de correction des soldes et de paramétrage de la fidélité. Les rapports et exports Excel sont accessibles aux Gérants pour leurs succursales et aux Propriétaires et superutilisateurs pour tout le réseau. Les succursales choisies sont obligatoires et les droits sont revérifiés avant chaque génération. Un retrait d’affectation interdit les nouvelles opérations de caisse et annulations concernées, sans modifier l’historique.

Lors d’un transfert SQLite vers PostgreSQL, le script applique également `0018` sur sa copie temporaire; aucune mise à jour manuelle du fichier SQLite source n’est nécessaire. Les affectations et le groupe Propriétaire sont transférés avec les autres données.

## Promotions temporaires (migration 0019)

L’application fonctionne sur PostgreSQL. Pour une installation déjà transférée :

```bash
python src/manage.py migrate
```

La migration initialise la progression habituelle avec le total existant des achats,
préserve les soldes, les transactions, les annulations et les rôles, et adapte les
instantanés des fusions réversibles. Aucune promotion n’est créée automatiquement.

Pour l’import initial d’un fichier SQLite V2, utiliser uniquement :

```bash
python scripts/migrer_sqlite_vers_postgres.py --source src/db.sqlite3
```



