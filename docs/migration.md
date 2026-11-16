# Migrer les données de la V1 vers la V2

Exécuter les commandes à la racine du projet, avec l’environnement virtuel activé.
Conserver le même fichier SQLite pendant le passage à la V2.

## 1. Sauvegarder la V1

Arrêter le serveur et conserver une copie du code V1. Sauvegarder la base :

```bash
python -c "import sqlite3; source = sqlite3.connect('file:src/db.sqlite3?mode=ro', uri=True); copie = sqlite3.connect('db-v1-sauvegarde.sqlite3'); source.backup(copie); copie.close(); source.close()"
python src/manage.py dumpdata CafeDolbeau.Client --indent 2 --output clients-v1.json
```

Choisir un autre nom de sauvegarde si le fichier existe déjà.

## 2. Installer la V2

Récupérer le code V2 en conservant `src/db.sqlite3`, puis exécuter :

```bash
python -m pip install -r requirements.txt
python src/manage.py migrate
python src/manage.py check
python src/manage.py balances
```

Si `CAFE_DB_PATH` est défini, vérifier qu’il désigne bien la base conservée.

## 3. Vérifier et remettre en service

Comparer les soldes avec les valeurs de `clients-v1.json`. Avec un
superutilisateur existant, attribuer les groupes Barista ou Gérant aux anciens
employés dans l’administration. Vérifier les accès et l’historique, puis relancer :

```bash
python src/manage.py runserver
```

Sous PowerShell, remplacer `python` par `.\.venv\Scripts\python.exe`.
En cas d’échec, arrêter la V2 et reprendre le code V1 avec la sauvegarde SQLite.
Ne pas charger de données de démonstration dans la base existante.

## Reproduire la vérification avec les données de démonstration V1

Dans une copie du code V2, avec les dépendances installées et sans fichier
`src/db.sqlite3` existant :

```bash
python scripts/donnees_v1.py --database src/db.sqlite3
python src/manage.py migrate
python src/manage.py check
python src/manage.py balances
```

Comparer les soldes avec ceux affichés par le script avant la mise à jour.

## Résultat de notre vérification V1 → V2

Essai effectué le **18 octobre 2026** : les soldes des six clients et les
12 transactions sont conservés, ainsi que les cinq comptes de démonstration.
Chaque cellule indique **avant / après** :

| Client | Achats cumulés | Étampes | Récompenses en réserve | Cafés prépayés restants |
| --- | --- | --- | --- | --- |
| Alice Tremblay | 9 / 9 | 9 / 9 | 0 / 0 | 0 / 0 |
| Benoît Gagnon | 12 / 12 | 2 / 2 | 1 / 1 | 0 / 0 |
| Camille Roy | 20 / 20 | 0 / 0 | 0 / 0 | 17 / 17 |
| Dominique Fortin | 17 / 17 | 7 / 7 | 0 / 0 | 10 / 10 |
| Élodie Simard | 33 / 33 | 3 / 3 | 1 / 1 | 10 / 10 |
| Client sans solde | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

# Migrer les données de la V2 vers la V3

Toutes les commandes partent de la racine du projet. La base SQLite V2 sera
transférée dans PostgreSQL ; conserver son fichier original et sa sauvegarde.

## 1. Sauvegarder la V2 et noter les soldes

Avec le code et la configuration V2, arrêter le serveur et toute application
qui écrit dans SQLite. Conserver une copie du code V2, puis exécuter :

```bash
python -c "import sqlite3; source = sqlite3.connect('file:src/db.sqlite3?mode=ro', uri=True); copie = sqlite3.connect('db-v2-sauvegarde.sqlite3'); source.backup(copie); copie.close(); source.close()"
python src/manage.py balances > balances-v2.csv
```

Choisir un autre nom de sauvegarde si le fichier existe déjà. Conserver aussi
`balances-v2.csv` pour la comparaison finale.

## 2. Installer le code V3

Installer Docker et Docker Compose avec Buildx, puis récupérer le code V3 en
conservant le SQLite V2 à l’emplacement `src/db.sqlite3`.

Si aucun `.env` n’existe, le créer :

```bash
cp .env.example .env
```

Sous PowerShell, utiliser `Copy-Item .env.example .env`. Si `.env` existe déjà,
le conserver et compléter les variables manquantes à partir de `.env.example`,
notamment `COMPOSE_FILE=docker/compose.yaml`. Conserver les secrets d’une
installation PostgreSQL existante.

## 3. Préparer la destination PostgreSQL

Vérifier dans `.env` le nom de la base et du compte PostgreSQL :

```dotenv
POSTGRES_DB=cafe_dolbeau
POSTGRES_USER=cafe_dolbeau
```

Pour une installation neuve, `SECRET_KEY` et `POSTGRES_PASSWORD` peuvent rester
vides : ils sont générés au démarrage. Les autres valeurs par défaut conviennent
pour une utilisation sur `http://localhost:8000`.

Utiliser une destination vide ou initialisée uniquement par le démarrage V3.
**Ne pas créer de compte ni charger les données de démonstration V3 avant
l’import.** Si une base PostgreSQL contient déjà des données, choisir une autre
destination ; l’import refuse de les écraser. Changer `POSTGRES_DB` ne crée pas
une nouvelle base dans un volume PostgreSQL déjà initialisé.

## 4. Démarrer les conteneurs

```bash
docker compose up --build --detach --wait
docker compose ps -a
```

Attendre que `db`, `app` et `proxy` soient sains. Les services `init` et `secrets`
doivent être terminés avec le code `0`. En cas d’échec, consulter
`docker compose logs` et corriger l’erreur avant de continuer.

Arrêter les accès à l’application pendant le transfert, en laissant la base active :

```bash
docker compose stop proxy app
```

## 5. Transférer le SQLite V2 en lecture seule

Sous Linux ou macOS :

```bash
docker compose run --rm --no-deps -v "$PWD/src:/import:ro" app python scripts/migrer_sqlite_vers_postgres.py --source /import/db.sqlite3
```

Sous Windows PowerShell :

```powershell
docker compose run --rm --no-deps -v "${PWD}/src:/import:ro" app python scripts/migrer_sqlite_vers_postgres.py --source /import/db.sqlite3
```

Adapter le répertoire monté si le SQLite V2 se trouve ailleurs. Le dossier entier
est monté pour inclure les éventuels fichiers SQLite `-wal` et `-shm`.
Sous Linux, si le fichier n’est lisible que par son propriétaire, ajouter
`--user "$(id -u):$(id -g)"` à la commande `run`.

Attendre le message **`Transfert vérifié`**, suivi des nombres de clients,
transactions et comptes, puis de **`SQLite conservé`**. Le fichier source reste
inchangé. Une seconde importation dans la même destination est refusée.

Ne pas appliquer manuellement de mise à jour au SQLite V2. Aucun `migrate`
supplémentaire n’est nécessaire pour terminer ce transfert.

## 6. Comparer les données

```bash
docker compose run --rm --no-deps app python src/manage.py check
docker compose run --rm --no-deps app python src/manage.py balances > balances-v3.csv
```

Comparer `balances-v2.csv` et `balances-v3.csv` : tous les soldes doivent être
identiques. Utiliser `balances` **sans filtre par succursale** pour inclure aussi
les clients sans transaction. Vérifier également les comptes, les rôles et les
historiques, notamment les annulations et les transactions des clients supprimés.

Les comptes et mots de passe V2 restent utilisables. Si aucun superutilisateur
n’existait, en créer un après l’import :

```bash
docker compose run --rm --no-deps app python src/manage.py createsuperuser
```

## 7. Mettre la V3 en service

```bash
docker compose up --detach --wait
```

1. Ouvrir <http://localhost:8000/connexion/> avec un superutilisateur.
2. Dans `/admin/`, attribuer le rôle **Propriétaire** à un compte employé.
3. Créer les autres succursales et affecter les Gérants et Baristas concernés.
4. Utiliser `/succursales/1/` pour le premier café et les adresses indiquant
   l’identifiant des autres succursales pour leurs caisses.

Les transactions V2 et les affectations des Baristas et Gérants existants sont
rattachées à la succursale nº 1. Les anciens rôles sont conservés ; les comptes
sans rôle nécessitent une attribution explicite.

Conserver le SQLite V2, sa sauvegarde et les exports de soldes. Pour arrêter la
V3 en conservant PostgreSQL, utiliser `docker compose down`, **sans `-v`**.

## En cas d’échec

Garder l’application arrêtée et consulter `docker compose logs`. Si le transfert
a échoué, corriger la cause puis relancer la commande sur une destination
admissible. Ne pas effacer une base contenant des données à conserver.

Pour reprendre la V2 avant la mise en service, utiliser le code et la
configuration V2 avec le SQLite conservé ou sa sauvegarde. Après de nouvelles
opérations en V3, cette sauvegarde ne contient plus les données récentes : ne
pas l’utiliser comme remplacement de PostgreSQL.

## Résultat de notre vérification V2 → V3

Vérification effectuée le **15 novembre 2026**, avec une base SQLite créée par
`scripts/donnees_v2.py` provenant du **tag `v2.0.0`**, et non par le script du
code V3. Les soldes ont été exportés avec la commande `balances` de cette V2,
puis la base a été transférée avec le script V3 vers une instance PostgreSQL
isolée dans Docker Compose. Une nouvelle exécution de `balances` dans le
conteneur V3 a produit un CSV **strictement identique** à celui de la V2.

Chaque cellule indique **avant / après** :

| ID | Client | Achats cumulés | Étampes | Récompenses en réserve | Cafés prépayés restants |
| --- | --- | --- | --- | --- | --- |
| 1 | Alice Tremblay | 9 / 9 | 9 / 9 | 0 / 0 | 0 / 0 |
| 2 | Benoît Gagnon | 10 / 10 | 0 / 0 | 1 / 1 | 0 / 0 |
| 3 | Camille Roy | 0 / 0 | 0 / 0 | 15 / 15 | 200 / 200 |
| 4 | Dominique Fortin | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 5 | Fusion source | 3 / 3 | 3 / 3 | 0 / 0 | 0 / 0 |
| 6 | Fusion destination | 7 / 7 | 7 / 7 | 0 / 0 | 0 / 0 |
| 8 | Alice Tremblay | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

Les deux clients nommés Alice Tremblay sont distincts, d’où la présence de leurs
identifiants. Le client source de la fusion est inactif, mais reste inclus dans
`balances`. Les 200 cafés prépayés de Camille correspondent aux 20 cartes de
10 cafés achetées par le script V2 ; cette valeur n’a pas été recalculée.

Le script de transfert a affiché :

```text
Transfert vérifié : 8 clients, 9 transactions, 5 comptes. SQLite conservé.
```

Les contrôles supplémentaires ont confirmé :

- **8 clients conservés**, dont le client fictif d’identifiant `-1`, exclu de
  `balances`, et **9 transactions toutes rattachées à la succursale nº 1**.
- **1 annulation et 1 fusion conservées**, ainsi que les identifiants, dates,
  quantités et liens des transactions.
- **5 comptes conservés**, avec les mêmes mots de passe hachés, rôles et états
  d’activation ; les cinq employés sont affectés à la succursale nº 1.
- **Fichier SQLite original inchangé**, vérifié par comparaison de son empreinte
  SHA-256 avant et après le transfert.

La pile PostgreSQL de vérification a été supprimée après l’essai. La base de
l’application et ses données n’ont pas été utilisées pour cette vérification.
