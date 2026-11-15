# Déployer la V3 avec Docker Compose

## Installation neuve

Prérequis : Docker et Docker Compose avec Buildx (inclus dans Docker Desktop).
Ouvrir un terminal à la racine du dépôt.

Les fichiers Compose, Dockerfile, exclusions de construction, configurations
nginx et Gunicorn et scripts de conteneurs sont regroupés dans `docker/`.
Le fichier `.env` reste à la racine, car il configure aussi les commandes Django
locales. Sa variable `COMPOSE_FILE=docker/compose.yaml` permet d’utiliser
simplement `docker compose` depuis la racine, conformément à la commande de correction.
Ce mécanisme est décrit dans la [documentation Compose](https://docs.docker.com/compose/how-tos/environment-variables/envvars/#compose_file).

Le nom de projet par défaut reste `cafedolbeau_` pour réutiliser les volumes
existants après ce déplacement. Si votre installation utilisait un autre nom de
projet, conserver ce nom avec `-p` ou `COMPOSE_PROJECT_NAME`.

```bash
cp .env.example .env
docker compose up --build
```

Sous Windows PowerShell, utiliser `Copy-Item .env.example .env`.
Aucune installation locale de Python ni préparation de clé n’est nécessaire.

Le service ponctuel `secrets` génère aléatoirement `SECRET_KEY` et
`POSTGRES_PASSWORD` lorsqu’ils sont vides. Les valeurs sont conservées dans le
volume nommé `runtime_secrets`, réutilisées aux démarrages suivants et ne sont
jamais affichées dans les journaux. PostgreSQL et Django y accèdent en lecture
seule par les variables `SECRET_KEY_FILE` et `POSTGRES_PASSWORD_FILE`.
Ce volume doit être conservé et sauvegardé avec celui de PostgreSQL.
Il n’est monté ni dans nginx ni sur l’ordinateur hôte.

Les valeurs explicitement définies dans `.env` sont prioritaires. Pour une
installation existante, conserver le `.env` et ses secrets ; ajouter
`COMPOSE_FILE=docker/compose.yaml` si nécessaire. Ne pas remplacer ce fichier par
l’exemple sur une base existante : le mot de passe doit correspondre à celui de
PostgreSQL. Une modification dans `.env` ne change pas le mot de passe enregistré
dans PostgreSQL.

Le script `python scripts/configurer_env.py` reste facultatif pour préparer les
secrets dans `.env` avant la première initialisation, notamment pour exécuter
Django localement en développement. Il ne change pas les valeurs déjà renseignées.
Après une génération automatique en volume, ne pas générer un autre mot de passe
dans `.env` : conserver les secrets déjà utilisés par cette installation.

Ouvrir <http://localhost:8000>. Aucun compte avec un mot de passe prédéfini n’est
créé. Pour une base neuve, ouvrir un second terminal et créer le premier compte :

```bash
docker compose exec app python src/manage.py createsuperuser
```

L’administration se trouve sur <http://localhost:8000/admin/>. Un superutilisateur
peut attribuer le premier rôle applicatif Propriétaire.

Pour tester les rôles et les succursales avec des données de démonstration V3 :

```bash
docker compose run --build --rm app python scripts/donnees_v3.py
```

Ce chargement est facultatif et manuel. Le mot de passe des comptes de
démonstration et les adresses des caisses sont affichés à la fin. Le script
conserve les données existantes et refuse une seconde exécution avec les mêmes
identifiants. Les comptes et les scénarios sont détaillés dans le
[README](../README.md#données-de-démonstration-v3).

## Démarrage et migrations

Compose initialise les secrets, attend le healthcheck PostgreSQL, puis lance
le service ponctuel `init` :

1. `python src/manage.py migrate --noinput` ;
2. `python src/manage.py collectstatic --noinput`.

Gunicorn ne démarre qu’après leur réussite. nginx attend ensuite que l’application
soit saine. Le service `init` doit apparaître terminé avec le code `0`, les trois
services permanents doivent être `healthy`. Une migration en échec bloque le
démarrage applicatif et son erreur apparaît dans les journaux.

Le service `secrets` se termine aussi avec le code `0`.

Les migrations sont appliquées automatiquement lors du démarrage de la pile.
Pour une mise à jour avec des utilisateurs actifs, arrêter d’abord l’application,
sauvegarder la base et reconstruire la pile :

```bash
docker compose stop proxy app
docker compose up --build
```

Ne pas lancer plusieurs mises à jour de la même base en parallèle. La commande
manuelle reste disponible pour le diagnostic :

```bash
docker compose run --rm --no-deps app python src/manage.py migrate --noinput
```

Cette commande suppose que PostgreSQL est déjà démarré et prêt.

## Erreur « password authentication failed » sur une base existante

PostgreSQL enregistre son mot de passe lors de la première initialisation du
volume. Copier de nouveau `.env.example` sur `.env` efface les secrets configurés
et peut provoquer la génération d’un mot de passe différent. Le service
`secrets` ne change pas le mot de passe enregistré dans PostgreSQL.

Si l’ancien mot de passe est connu, le remettre dans `POSTGRES_PASSWORD` du
`.env`, puis relancer `docker compose up --build`.

S’il est perdu, l’administrateur local peut aligner le compte PostgreSQL sur le
secret du volume actuel. Cette opération change uniquement le mot de passe du
compte utilisé, sans supprimer de données. Depuis la racine, ouvrir PostgreSQL :

```bash
docker compose exec db sh -c 'exec psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --no-psqlrc'
```

Puis exécuter dans `psql` :

```sql
DO $$
DECLARE
    mot_de_passe text := pg_read_file('/app/secrets/POSTGRES_PASSWORD');
BEGIN
    IF length(mot_de_passe) < 1 THEN
        RAISE EXCEPTION 'Le secret PostgreSQL est vide';
    END IF;
    EXECUTE format('ALTER ROLE %I PASSWORD %L', current_user, mot_de_passe);
END
$$;
\q
```

Cette commande utilise l’accès local du compte administrateur de l’image
PostgreSQL fournie, sans afficher le secret. Relancer ensuite
`docker compose up --build`. Conserver les fichiers `.env` et les volumes de
cette installation lors des démarrages suivants.

## Configuration et changement de domaine

Toutes les variables sont documentées dans `.env.example`. Les variables du
terminal sont prioritaires sur ce fichier. Dans Compose, les noms internes sont
`db` et `app` : aucun port PostgreSQL ou Gunicorn n’est publié.

- `SECRET_KEY`, `POSTGRES_PASSWORD` : secrets générés localement, requis.
- `POSTGRES_DB`, `POSTGRES_USER` : base et compte PostgreSQL.
- `HTTP_BIND_ADDRESS`, `HTTP_PORT` : adresse et port publiés par nginx ; valeurs
  initiales `127.0.0.1` et `8000`.
- `DJANGO_ALLOWED_HOSTS` : hôtes autorisés séparés par des virgules, sans schéma.
  Le premier est utilisé dans les requêtes internes de santé.
- `DJANGO_CSRF_TRUSTED_ORIGINS` : origines complètes, avec schéma et port éventuel.
- `PUBLIC_SCHEME` : `http` pour l’accès local, `https` derrière une terminaison TLS.
- `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SESSION_COOKIE_SECURE`,
  `DJANGO_CSRF_COOKIE_SECURE`, `DJANGO_SECURE_HSTS_*` : options HTTPS.
- `GUNICORN_WORKERS`, `GUNICORN_TIMEOUT`, `DJANGO_LOG_LEVEL` : exécution et journaux.

Pour un domaine public en HTTPS, terminer TLS devant nginx, puis adapter les
variables, par exemple :

```dotenv
HTTP_BIND_ADDRESS=0.0.0.0
DJANGO_ALLOWED_HOSTS=cafe.exemple.ca
DJANGO_CSRF_TRUSTED_ORIGINS=https://cafe.exemple.ca
PUBLIC_SCHEME=https
DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_SESSION_COOKIE_SECURE=true
DJANGO_CSRF_COOKIE_SECURE=true
DJANGO_SECURE_HSTS_SECONDS=3600
```

Aucune modification du code n’est nécessaire. Les certificats et la terminaison
TLS sont à fournir par l’hébergeur ou le proxy HTTPS frontal. L’accès HTTP local
demandé pour la correction garde les options HTTPS désactivées ; Django reste
avec `DEBUG=False`. `check --deploy` signale donc les options HTTPS non activées
sur cette configuration locale.

## Contrôles, journaux et persistance

```bash
docker compose ps -a
docker compose logs -f
docker compose exec app python src/manage.py check
docker compose exec app python src/manage.py showmigrations
```

`/healthz` retourne `200` si Django peut interroger PostgreSQL, sinon `503`, sans
authentification ni détail d’erreur interne. Les contrôles de santé utilisent cet
endpoint. nginx sert `/static/` depuis les fichiers collectés, notamment les styles
de l’administration ; le volume est monté en lecture seule dans le proxy.

Pour vérifier la persistance, créer une donnée, exécuter `docker compose down`,
puis `docker compose up` : la donnée doit rester présente. **Ne pas ajouter `-v`**
à `down` : cette option supprime les volumes, dont la base. Les journaux vont sur
stdout/stderr et sont accessibles avec `docker compose logs`.

## Tests PostgreSQL en une commande

```bash
docker compose --profile test run --build --rm tests
```

Le profil construit une image de tests avec Node.js et les jeux de données. Il
lance toute la suite Django contre **un PostgreSQL de test distinct**, puis les
tests JavaScript. Django crée et détruit sa base de test. Les données de
l’application ne sont pas utilisées. L’image de production ne contient ni les
tests ni les comptes de démonstration.

## Importer une base SQLite V2

Suivre la [procédure V2 vers V3](migration.md#migrer-les-données-de-la-v2-vers-la-v3).
Le fichier SQLite n’est pas inclus dans l’image. Le monter en lecture seule dans
un conteneur ponctuel qui accède au PostgreSQL interne, sans publier son port :

```bash
docker compose stop proxy app
docker compose run --rm --no-deps -v "$PWD/src:/import:ro" app python scripts/migrer_sqlite_vers_postgres.py --source /import/db.sqlite3
docker compose up -d
```

Sous PowerShell, remplacer `$PWD/src` par `${PWD}/src`. Le répertoire est monté pour inclure aussi
les éventuels fichiers SQLite `-wal` et `-shm`.
Si le fichier n’est lisible que par son propriétaire sous Linux, ajouter
`--user "$(id -u):$(id -g)"` à la commande `run`. PostgreSQL doit être démarré. Ne pas créer de compte ni saisir de données avant
l’import : le script accepte uniquement une destination vide ou initialisée par
les migrations, conserve le SQLite original et refuse tout écrasement de données.

## Développement local séparé

Le fichier `docker/compose.dev.yaml` n’est jamais chargé implicitement. Il permet de
publier PostgreSQL uniquement pour Python exécuté sur l’ordinateur :

Pour une nouvelle installation de développement, exécuter d’abord
`python scripts/configurer_env.py` afin que le processus Python local et les
conteneurs partagent les secrets renseignés dans `.env`. Si la base existe déjà,
utiliser ses secrets actuels ; ne pas en générer d’autres.

```bash
docker compose -f docker/compose.yaml -f docker/compose.dev.yaml up -d db
```

Avec l’environnement virtuel activé et les dépendances installées :

```bash
export DJANGO_SETTINGS_MODULE=config.settings_development
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432
python src/manage.py migrate
python src/manage.py runserver
```

Sous PowerShell, définir les variables avec `$env:DJANGO_SETTINGS_MODULE =
"config.settings_development"`, `$env:POSTGRES_HOST = "127.0.0.1"` et
`$env:POSTGRES_PORT = "5432"`. Adapter le port si `POSTGRES_DEV_PORT` change.
Cette configuration permet `DEBUG=True` et le rechargement automatique ; elle
n’est pas celle démarrée par `docker compose up --build`.

Si une commande de construction échoue avec `docker-buildx: no such file or
directory`, installer ou réparer le plugin Docker Buildx. Cela concerne
l’installation Docker de l’ordinateur, pas les services de l’application.

## Vérification réalisée

Le 15 novembre 2026, la commande Compose standard a été vérifiée sur une pile
isolée : initialisation terminée avec le code `0`, PostgreSQL, Gunicorn et nginx
sains, seul le proxy publié. Les trois services permanents s’exécutent sans root.
Les pages de connexion, les styles de l’administration et les fichiers statiques
répondent correctement ; une URL absente retourne une 404 sans débogage et un
hôte non autorisé est refusé.

La commande de tests conteneurisés a réussi : **327 tests Django sur PostgreSQL**
et **11 tests JavaScript**. Le parcours `cp .env.example .env` puis
`docker compose up --build` a été vérifié sur une copie neuve, sans génération
manuelle de secrets. Les secrets générés restent identiques après redémarrage.
La persistance après `down` puis `up` et le changement
de domaine uniquement par environnement ont été vérifiés, y compris la connexion,
le contrôle CSRF, l’administration et la déconnexion. La coupure de PostgreSQL
produit une santé `503` ; son redémarrage rétablit une santé `200`.
