# Héberger Café Dolbeau depuis zéro, puis transférer PostgreSQL

Ce guide s'adresse à une personne qui installe **sa propre copie du projet**, dans
son compte AWS, avec son dépôt GitHub et son domaine. Suivre les sections dans
l'ordre. Les commandes communes sont en **Bash**, jamais dans PowerShell sauf
mention explicite. Un environnement Python `.venv` n'est pas nécessaire pour les
scripts d'infrastructure et de transfert : ils utilisent la bibliothèque standard.

## Table des matières

- [1. Comprendre les machines et préparer les comptes](#1-comprendre-les-machines-et-préparer-les-comptes)
  - [1.1. Où exécuter les commandes](#11-où-exécuter-les-commandes)
  - [1.2. Comptes et droits](#12-comptes-et-droits)
  - [1.3. Fiche de configuration](#13-fiche-de-configuration)
- [2. Installer les outils](#2-installer-les-outils)
  - [2.1. Ubuntu 24.04 x64](#21-ubuntu-2404-x64)
  - [2.2. Windows x64 avec WSL2](#22-windows-x64-avec-wsl2)
  - [2.3. macOS : CLIENT natif et RUNNER Ubuntu x64](#23-macos--client-natif-et-runner-ubuntu-x64)
  - [2.4. Vérifications avant de continuer](#24-vérifications-avant-de-continuer)
- [3. Créer le dépôt personnel et la clé SSH](#3-créer-le-dépôt-personnel-et-la-clé-ssh)
  - [3.1. Copier le projet dans GitHub](#31-copier-le-projet-dans-github)
  - [3.2. Cloner et définir les valeurs non secrètes](#32-cloner-et-définir-les-valeurs-non-secrètes)
  - [3.3. Générer la clé qui servira au transfert](#33-générer-la-clé-qui-servira-au-transfert)
- [4. Préparer le domaine et Cloudflare Tunnel](#4-préparer-le-domaine-et-cloudflare-tunnel)
- [5. Amorcer AWS et la fédération GitHub](#5-amorcer-aws-et-la-fédération-github)
  - [5.1. Ouvrir une session AWS temporaire](#51-ouvrir-une-session-aws-temporaire)
  - [5.2. Aligner le sujet OIDC sur le code Terraform](#52-aligner-le-sujet-oidc-sur-le-code-terraform)
  - [5.3. Créer l'état Terraform et le rôle du pipeline](#53-créer-létat-terraform-et-le-rôle-du-pipeline)
- [6. Enregistrer variables, clés et secrets dans GitHub](#6-enregistrer-variables-clés-et-secrets-dans-github)
  - [6.1. Créer l'environnement](#61-créer-lenvironnement)
  - [6.2. Ajouter les variables d'environnement](#62-ajouter-les-variables-denvironnement)
  - [6.3. Ajouter les secrets d'environnement](#63-ajouter-les-secrets-denvironnement)
- [7. Installer et démarrer le runner Linux x64](#7-installer-et-démarrer-le-runner-linux-x64)
- [8. Déployer le site par le pipeline](#8-déployer-le-site-par-le-pipeline)
  - [8.1. Vérifier le code à déployer](#81-vérifier-le-code-à-déployer)
  - [8.2. Lancer et suivre](#82-lancer-et-suivre)
  - [8.3. Vérifier avant de transférer](#83-vérifier-avant-de-transférer)
- [9. Préparer puis transférer la vraie base locale](#9-préparer-puis-transférer-la-vraie-base-locale)
  - [9.1. Identifier la source avant de la démarrer](#91-identifier-la-source-avant-de-la-démarrer)
  - [9.2. Arrêter les écritures et vérifier le schéma](#92-arrêter-les-écritures-et-vérifier-le-schéma)
  - [9.3. Vérifier SSH et lancer le transfert](#93-vérifier-ssh-et-lancer-le-transfert)
  - [9.4. Contrôler les données et basculer les utilisateurs](#94-contrôler-les-données-et-basculer-les-utilisateurs)
- [10. Diagnostic, reprise et restauration](#10-diagnostic-reprise-et-restauration)
  - [10.1. Erreurs fréquentes](#101-erreurs-fréquentes)
  - [10.2. Logs du pipeline et du serveur](#102-logs-du-pipeline-et-du-serveur)
  - [10.3. Clé d'hôte SSH modifiée](#103-clé-dhôte-ssh-modifiée)
  - [10.4. Restaurer la sauvegarde distante d'avant import](#104-restaurer-la-sauvegarde-distante-davant-import)
  - [10.5. Sauvegarder la production et télécharger une copie](#105-sauvegarder-la-production-et-télécharger-une-copie)
  - [10.6. Restaurer la copie dans une base locale de test](#106-restaurer-la-copie-dans-une-base-locale-de-test)
  - [10.7. Vérification A8 : preuves à conserver](#107-vérification-a8--preuves-à-conserver)
  - [10.8. Ouvrir l’application locale avec la base restaurée](#108-ouvrir-lapplication-locale-avec-la-base-restaurée)
- [11. Exploitation après la première installation](#11-exploitation-après-la-première-installation)
- [12. Liste de contrôle finale](#12-liste-de-contrôle-finale)

Procédure vérifiée contre les fichiers du dépôt et les documentations officielles
le **22 novembre 2026**. Les commandes ont été relues et vérifiées statiquement ;
ce document ne constitue pas un essai réel de déploiement sur les trois systèmes.

## 1. Comprendre les machines et préparer les comptes

### 1.1. Où exécuter les commandes

| Repère utilisé dans ce guide | Fonction | Emplacement |
| --- | --- | --- |
| **CLIENT** | Cloner, configurer AWS/GitHub, lancer le pipeline et transférer les données | Ubuntu local, Ubuntu WSL2, ou Terminal macOS |
| **RUNNER** | Exécuter les jobs GitHub Actions et construire les images | Ubuntu **x64**, directement, dans WSL2 ou dans une VM locale |
| **EC2** | Héberger le site et sa base PostgreSQL de production | Instance Ubuntu créée par le pipeline dans AWS |
| **NAVIGATEUR** | Configurer les comptes, le domaine, les secrets et le runner | Navigateur habituel |

Sous Linux x64 et Windows x64, CLIENT et RUNNER peuvent partager le même Ubuntu,
dans deux terminaux. Sous macOS, CLIENT reste sur le Mac et RUNNER tourne dans
une VM Ubuntu x64 distincte. **Le transfert doit partir de CLIENT, là où Docker
voit la base contenant réellement vos données, pas d'une VM de runner vide.**

La base locale n'est jamais intégrée au dépôt ou aux images de déploiement.
Le pipeline envoie les images et la configuration privée par S3/SSM ; le script
de transfert envoie ensuite PostgreSQL **directement par SSH**, sans GitHub ni S3.

### 1.2. Comptes et droits

Préparer les éléments suivants dans NAVIGATEUR :

1. Un compte GitHub ayant les droits **Admin** sur le nouveau dépôt.
2. Un compte AWS actif avec facturation configurée et accès à **US East (Ohio),
   `us-east-2`**. Cette région est imposée par le projet. Pour partir de zéro,
   choisir [Sign up for AWS (advanced)](https://docs.aws.amazon.com/accounts/latest/reference/getting-started.html)
   dans le navigateur : renseigner courriel, nom du compte, mot de passe, coordonnées,
   facturation et vérification téléphonique, puis attendre le courriel d'activation.
   Choisir le support Basic si aucun accompagnement payant n'est souhaité.
3. Une identité AWS d'administration pour l'amorçage : elle créera un bucket S3,
   le fournisseur OIDC et le rôle IAM du pipeline. Les jobs utiliseront ensuite
   ce rôle, pas les identifiants personnels de l'administrateur.
4. Un compte Cloudflare et un nom de domaine dont vous pouvez modifier les
   serveurs DNS chez le registraire.
5. Un gestionnaire de mots de passe pour conserver les secrets de production.

Si le compte AWS vient d'être créé : activer le MFA du compte racine, puis créer
une identité d'administration pour le travail courant. Pour un compte individuel
dans la console AWS classique sans IAM Identity Center : **IAM → Users → Create user**, nommer l'utilisateur
`cafedolbeau-bootstrap`, activer l'accès console et choisir la création d'un
utilisateur IAM. Lui attribuer `AdministratorAccess` pour cet amorçage ainsi que
`SignInLocalDevelopmentAccess` pour la connexion CLI décrite en section 5. Conserver
l'URL de connexion et le mot de passe initial, ouvrir une session avec cet utilisateur
et configurer son MFA. Ne pas créer de clé d'accès permanente pour le pipeline.
Les droits administrateur servent à créer l'infrastructure et les rôles décrits
dans `infra/bootstrap/` ; le rôle des jobs est défini séparément dans Terraform.
Voir la [création d'un utilisateur IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_users_create.html).

Ce parcours utilise un compte AWS classique/advanced pour pouvoir choisir la
région et gérer IAM et le réseau. La **nouvelle expérience AWS avec projets** a
des restrictions différentes, notamment sur le choix de région et la connexion
console des utilisateurs IAM. Si vous utilisez déjà cette expérience, ne pas
supposer que les étapes IAM ci-dessus s'appliquent : partir d'un compte advanced
pour suivre exactement ce parcours. Voir la
[comparaison officielle des inscriptions AWS](https://docs.aws.amazon.com/accounts/latest/reference/sign-up-for-aws.html).

**Prévoir des frais AWS** : le pipeline crée notamment une EC2 `t3.small`, un
disque EBS de 30 Gio et un bucket d'artefacts. Le bucket d'état est créé avant.
L'arrêt du runner local n'arrête pas EC2. Cette procédure suppose qu'aucune autre
installation Café Dolbeau n'existe dans ce compte : plusieurs noms IAM/S3 sont
fixes, et un second déploiement indépendant pourrait entrer en conflit.

### 1.3. Fiche de configuration

Remplir cette fiche dans une note privée. Les exemples sont fictifs.

| Valeur | Exemple / règle | Obtenue à l'étape |
| --- | --- | --- |
| Dépôt `PROPRIETAIRE/DEPOT` | `mon-compte/cafeDolbeau_` | 3 |
| ID numérique du propriétaire | Nombre, différent du nom GitHub | 3 |
| ID numérique du dépôt | Nombre propre à votre copie | 3 |
| Compte AWS | 12 chiffres | 5 |
| Région AWS | `us-east-2` | Fixe |
| Bucket d'état Terraform | `cafedolbeau-state-COMPTE-SUFFIXE` en minuscules | 5 |
| ARN du rôle GitHub | `arn:aws:iam::COMPTE:role/cafedolbeau-github-production` | 5 |
| Domaine public | `cafe.votre-domaine.ca`, sans `https://` ni `/` | 4 |
| IPv4 publique de CLIENT | Adresse courante de votre connexion, sans port | 6 |
| Clé SSH privée | `~/.ssh/cafedolbeau`, uniquement sur CLIENT | 3 |
| Clé SSH publique | Contenu de `~/.ssh/cafedolbeau.pub` | 3 |
| Secrets applicatifs et jeton du tunnel | Gestionnaire de mots de passe | 4 et 6 |
| Projet Docker source | Nom du projet qui possède vos données locales | 9 |

## 2. Installer les outils

Lire uniquement le parcours de votre système, puis effectuer les vérifications
de la section 2.4. Pour un ordinateur Linux ARM ou Windows ARM, le runner doit
également disposer d'un Ubuntu **x64 émulé** : un runner ARM64 ne correspond pas
aux labels du workflow actuel. Le parcours direct Linux/Windows ci-dessous vise x64.

### 2.1. Ubuntu 24.04 x64

**CLIENT et RUNNER — terminal Ubuntu.** Vérifier que `uname -m` affiche `x86_64`.
Installer les outils de base :

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates unzip gnupg openssh-client python3 python3-venv gh
```

Installer Docker Engine depuis son dépôt officiel **sur une nouvelle installation
Ubuntu sans moteur Docker existant** :

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Se déconnecter complètement de la session Ubuntu puis se reconnecter pour appliquer
le groupe `docker`. Le compte du runner doit pouvoir lancer Docker sans `sudo`.
L'appartenance à ce groupe donne des privilèges élevés sur la machine ; utiliser
un runner pour un dépôt que vous administrez. Si Docker est déjà installé,
conserver son installation et ses volumes ; ne pas le désinstaller pour ce guide.
Sources : [installation Docker Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
et [gestion du groupe Docker](https://docs.docker.com/engine/install/linux-postinstall/).

Installer la version actuelle de **AWS CLI v2**, au minimum 2.32.0 pour `aws login` :

```bash
CAFE_AWS_INSTALL=$(mktemp -d)
curl -fsSL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o "$CAFE_AWS_INSTALL/awscliv2.zip"
unzip -q "$CAFE_AWS_INSTALL/awscliv2.zip" -d "$CAFE_AWS_INSTALL"
sudo "$CAFE_AWS_INSTALL/aws/install" --update
```

Le dossier temporaire ne contient que l'installateur ; il peut être supprimé
manuellement après installation. Pour vérifier sa signature avant installation,
suivre la [procédure officielle AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).

Installer **Terraform 1.11.4**, identique à la version du workflow :

```bash
CAFE_TF_INSTALL=$(mktemp -d)
curl -fsSL https://releases.hashicorp.com/terraform/1.11.4/terraform_1.11.4_linux_amd64.zip -o "$CAFE_TF_INSTALL/terraform.zip"
curl -fsSL https://releases.hashicorp.com/terraform/1.11.4/terraform_1.11.4_SHA256SUMS -o "$CAFE_TF_INSTALL/SHA256SUMS"
python3 - "$CAFE_TF_INSTALL" <<'PY'
import hashlib, pathlib, sys
folder = pathlib.Path(sys.argv[1])
name = 'terraform_1.11.4_linux_amd64.zip'
expected = next(line.split()[0] for line in (folder / 'SHA256SUMS').read_text().splitlines() if line.endswith(name))
assert hashlib.sha256((folder / 'terraform.zip').read_bytes()).hexdigest() == expected, 'Archive Terraform corrompue'
PY
unzip -q "$CAFE_TF_INSTALL/terraform.zip" -d "$CAFE_TF_INSTALL"
sudo install -m 0755 "$CAFE_TF_INSTALL/terraform" /usr/local/bin/terraform
```

Le SHA256 détecte un téléchargement corrompu ; pour l'authentification de la
signature, consulter la [documentation d'installation Terraform](https://developer.hashicorp.com/terraform/install).

### 2.2. Windows x64 avec WSL2

**CLIENT — PowerShell ouvert en administrateur**, installer Ubuntu :

```powershell
wsl --install -d Ubuntu-24.04
```

Redémarrer Windows si demandé. Ouvrir **Ubuntu 24.04** depuis le menu Démarrer,
créer le compte Linux et son mot de passe. Dans PowerShell, vérifier :

```powershell
wsl --update
wsl --list --verbose
```

La distribution doit être en version `2`. Si elle est en version `1` :

```powershell
wsl --set-version Ubuntu-24.04 2
```

Installer [Docker Desktop pour Windows](https://docs.docker.com/desktop/setup/install/windows-install/),
le démarrer, sélectionner **Settings → General → Use the WSL 2 based engine**,
puis **Settings → Resources → WSL Integration** et activer `Ubuntu-24.04`.
Cliquer **Apply & restart**. Utiliser les conteneurs Linux.

Dans le terminal **Ubuntu WSL**, exécuter les commandes d'installation des outils
de base, AWS CLI et Terraform de la section 2.1, **mais pas le bloc d'installation
Docker Engine ni `systemctl`/`usermod`** : Docker est fourni par Docker Desktop.
Ne pas installer un second moteur dans cette distribution.

Toutes les commandes restantes seront dans Ubuntu WSL, y compris GitHub CLI,
SSH et Python. Garder le dépôt dans `~/Documents/Prog/`, pas dans `/mnt/c/`, pour
éviter les problèmes de permissions et de performance. Une clé créée dans WSL
est distincte d'une clé dans le dossier `.ssh` Windows.

Sources : [installation WSL](https://learn.microsoft.com/en-us/windows/wsl/install)
et [intégration Docker WSL2](https://docs.docker.com/desktop/features/wsl/).

### 2.3. macOS : CLIENT natif et RUNNER Ubuntu x64

**CLIENT — Terminal macOS.** Installer les outils de ligne de commande Apple :

```bash
xcode-select --install
```

Si macOS indique qu'ils existent déjà, continuer. Installer Homebrew à partir des
instructions affichées sur [brew.sh](https://brew.sh/), puis exécuter les commandes
`brew shellenv` indiquées à la fin de son installation. Ensuite :

```bash
brew install python@3.12 gh awscli
export PATH="$(brew --prefix python@3.12)/libexec/bin:$PATH"
```

Ajouter cette dernière ligne au fichier `~/.zprofile` avec un éditeur pour les
prochaines sessions. Vérifier que `python3 --version` affiche au moins 3.11.
Installer et démarrer [Docker Desktop pour Mac](https://docs.docker.com/desktop/setup/install/mac-install/),
en choisissant **Apple silicon** ou **Intel** selon **Apple → À propos de ce Mac**.
Les commandes Git et SSH sont fournies par macOS et les outils Apple.

Installer Terraform natif en choisissant automatiquement l'architecture :

```bash
CAFE_TF_ARCH=amd64
if [ "$(uname -m)" = arm64 ]; then CAFE_TF_ARCH=arm64; fi
CAFE_TF_INSTALL=$(mktemp -d)
curl -fsSL "https://releases.hashicorp.com/terraform/1.11.4/terraform_1.11.4_darwin_${CAFE_TF_ARCH}.zip" -o "$CAFE_TF_INSTALL/terraform.zip"
curl -fsSL https://releases.hashicorp.com/terraform/1.11.4/terraform_1.11.4_SHA256SUMS -o "$CAFE_TF_INSTALL/SHA256SUMS"
python3 - "$CAFE_TF_INSTALL" "$CAFE_TF_ARCH" <<'PY'
import hashlib, pathlib, sys
folder = pathlib.Path(sys.argv[1])
name = f'terraform_1.11.4_darwin_{sys.argv[2]}.zip'
expected = next(line.split()[0] for line in (folder / 'SHA256SUMS').read_text().splitlines() if line.endswith(name))
assert hashlib.sha256((folder / 'terraform.zip').read_bytes()).hexdigest() == expected, 'Archive Terraform corrompue'
PY
unzip -q "$CAFE_TF_INSTALL/terraform.zip" -d "$CAFE_TF_INSTALL"
sudo mkdir -p /usr/local/bin
sudo install -m 0755 "$CAFE_TF_INSTALL/terraform" /usr/local/bin/terraform
```

**RUNNER — créer une VM locale séparée.** Le workflow exige `self-hosted, linux,
x64`. Installer un runner directement sur macOS, ou sur Ubuntu ARM64, ne convient
pas, même si Docker sait construire des images amd64.

1. Installer [UTM pour macOS](https://mac.getutm.app/).
2. Télécharger l'ISO **Ubuntu Server 24.04 LTS amd64**, depuis les
   [images officielles Ubuntu 24.04](https://releases.ubuntu.com/24.04/).
3. Dans UTM, créer une nouvelle VM : sur Intel, choisir **Virtualize → Linux** ;
   sur Apple Silicon, choisir **Emulate**, architecture **x86_64**, puis Linux.
4. Attacher l'ISO, prévoir par exemple 4 processeurs, 8 Gio de mémoire si le Mac
   le permet et un disque de 60 Gio. Ce sont des valeurs de départ, pas un minimum
   garanti pour toutes les versions du projet. Utiliser le réseau partagé/NAT.
5. Installer Ubuntu avec un utilisateur ordinaire et son mot de passe. Accepter
   l'installation standard ; aucun Kubernetes ni Docker supplémentaire pendant
   l'assistant. Retirer l'ISO à la fin et redémarrer sur le disque installé.
6. Dans le terminal de la VM, vérifier `uname -m` : le résultat doit être
   **`x86_64`**. Appliquer la section 2.1 dans cette VM et y vérifier Docker.

**Sur Apple Silicon, l'émulation x64 peut être très lente** : elle n'est pas la
virtualisation ARM native. Le workflow expire après 90 minutes et peut ne pas
terminer sur une machine trop lente. Ne pas contourner cela en étiquetant un
runner ARM64 comme x64 ; utiliser alors un ordinateur Ubuntu x64 local plus adapté.
Cette limite n'est pas validée par un essai matériel dans ce guide.
Sources : [guide Ubuntu UTM](https://docs.getutm.app/guides/ubuntu/)
et [architecture des VM UTM](https://docs.getutm.app/settings-qemu/system/).

La VM ne contient pas vos données Docker Desktop macOS. Garder le Mac comme
CLIENT pour l'amorçage et le transfert ; seule la section 7 se fait dans la VM.

### 2.4. Vérifications avant de continuer

**CLIENT**, puis **RUNNER si distinct**, exécuter :

```bash
git --version
python3 --version
ssh -V
gh --version
aws --version
terraform version
docker version
docker compose version
docker buildx version
docker info > /dev/null
```

Attendu : Python ≥ 3.11, AWS CLI ≥ 2.32.0, Terraform 1.11.4, un serveur Docker
joignable **sans `sudo`**, Compose et Buildx disponibles. Sur RUNNER, ajouter
`uname -s` et `uname -m` : résultats `Linux` et `x86_64`. Corriger toute erreur
avant de continuer. Après une modification de PATH ou de groupe Docker,
redémarrer le terminal et le processus du runner s'il tournait déjà.

Si `aws --version` est inférieur à 2.32.0, mettre à jour avec l'installateur AWS
Linux ci-dessus ou `brew upgrade awscli` sur macOS, puis refaire la vérification.
Ne pas poursuivre l'amorçage avec une commande `aws login` indisponible.

## 3. Créer le dépôt personnel et la clé SSH

### 3.1. Copier le projet dans GitHub

**NAVIGATEUR**, ouvrir le dépôt source `ShepherdPoggers/cafeDolbeau_`, cliquer
**Fork → Create a new fork**, choisir votre compte et le nom `cafeDolbeau_`, puis
créer la copie. Dans la copie, vérifier que la branche par défaut est `main` et
contient `.github/workflows/deploy.yml` et les trois scripts `bootstrap.py`,
`suivre-deploiement.py`, `transferer-postgres.py` sous `infra/scripts/`.

Ouvrir **Actions** dans votre copie et autoriser les workflows si GitHub affiche
le bouton d'activation pour un fork. Dans **Settings → Actions → General**,
autoriser les actions nécessaires au workflow. Si une politique d'organisation
les bloque, l'administrateur doit autoriser celles listées dans `deploy.yml`.
Les modifications du dépôt original ne mettent pas votre fork à jour automatiquement.

### 3.2. Cloner et définir les valeurs non secrètes

**CLIENT**, se connecter à GitHub ; sélectionner GitHub.com, HTTPS et la connexion
par navigateur. Le compte doit administrer le fork :

```bash
gh auth login
gh auth status
```

Définir les valeurs suivantes en remplaçant les exemples. Conserver ces lignes
dans la fiche de configuration : il faudra les réexécuter dans tout nouveau
terminal CLIENT. Ne pas utiliser le nom du propriétaire original.

```bash
export CAFE_REPO='mon-compte/cafeDolbeau_'
export CAFE_DOMAIN='cafe.votre-domaine.ca'
export AWS_REGION='us-east-2'
export AWS_DEFAULT_REGION='us-east-2'
mkdir -p ~/Documents/Prog
cd ~/Documents/Prog
gh repo clone "$CAFE_REPO"
cd cafeDolbeau_
export CAFE_ROOT="$PWD"
export CAFE_OWNER_ID=$(gh api "repos/$CAFE_REPO" --jq '.owner.id')
export CAFE_REPO_ID=$(gh api "repos/$CAFE_REPO" --jq '.id')
gh api "repos/$CAFE_REPO" --jq '{depot: .full_name, proprietaire_id: .owner.id, depot_id: .id, branche: .default_branch}'
git remote -v
```

Attendu : votre dépôt, ses identifiants numériques et `main`. Noter les deux ID.
Si le dossier existe déjà parce qu'il contient la base locale et son `.env`,
**ne pas recloner ni remplacer `.env`** : entrer dans ce dossier, vérifier
`git remote -v`, puis définir `CAFE_ROOT` et récupérer les ID comme ci-dessus.
Si `origin` vise encore le dépôt original, le remplacer explicitement par votre
fork avec `git remote set-url origin "https://github.com/$CAFE_REPO.git"`.
Vérifier `git status` avant tout changement de branche ; conserver les modifications
locales et pousser le code voulu sur votre `main` avant le déploiement.

**Fixer votre fork comme dépôt GitHub CLI par défaut**, depuis ce dossier :

```bash
gh repo set-default "$CAFE_REPO"
gh repo set-default --view
```

Attendu : votre dépôt, jamais celui du propriétaire original. Ce choix persiste
pour cette copie Git, y compris dans un nouveau terminal, et s'applique aux
commandes `gh run`, `gh workflow`, etc. Une variable `GH_REPO` déjà exportée dans
le terminal reste prioritaire : vérifier qu'elle ne pointe pas vers un autre dépôt.

Pour configurer explicitement le script de déploiement de façon persistante,
ajouter ou modifier **cette seule ligne** dans le `.env` à la racine du projet,
avec votre véritable dépôt :

```dotenv
GH_REPO=mon-compte/cafeDolbeau_
```

Si `.env` existe déjà, conserver toutes ses autres valeurs. S'il n'existe pas,
copier `.env.example` dans `.env` puis renseigner `GH_REPO`. Ne pas ajouter `.env`
à Git. Le script utilise, dans cet ordre : `GH_REPO` du terminal, `GH_REPO`
du `.env`, `CAFE_REPO` du terminal, puis le dépôt par défaut de GitHub CLI. Aligner
ces valeurs sur le même fork. Seule cette option du `.env` est lue par le script,
sans importer les secrets applicatifs dans les commandes GitHub.

Après cette configuration, la commande reste simplement
`python3 infra/scripts/suivre-deploiement.py --lancer` : inutile de la préfixer
par `GH_REPO=...`. Le script affiche le dépôt explicite sélectionné, puis
l'utilise pour le lancement, la recherche d'exécution, le suivi et les logs.

### 3.3. Générer la clé qui servira au transfert

**CLIENT**, vérifier si la clé existe déjà :

```bash
ls -l ~/.ssh/cafedolbeau ~/.ssh/cafedolbeau.pub
```

Si les deux fichiers existent, conserver la clé et passer à `ssh-add`. Si aucun
n'existe, les créer ; ne pas accepter l'écrasement d'une clé existante :

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/cafedolbeau -C 'cafedolbeau-production'
```

Choisir une phrase secrète et la conserver dans le gestionnaire. Si seule la clé
privée existe, recréer sa partie publique avec
`ssh-keygen -y -f ~/.ssh/cafedolbeau > ~/.ssh/cafedolbeau.pub`.

Charger la clé dans le terminal qui effectuera le transfert :

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/cafedolbeau
ssh-add -l
cat ~/.ssh/cafedolbeau.pub
```

Copier **la ligne publique entière** commençant par `ssh-ed25519`, sans retour
à la ligne interne. Elle ira dans `SSH_PUBLIC_KEY`, section 6. Le fichier sans
`.pub` est privé : il ne va ni dans GitHub, ni sur le runner séparé, ni sur EC2.
Le transfert utilise `BatchMode=yes` : sans agent chargé, une clé chiffrée ne
pourra pas demander sa phrase secrète et la connexion échouera.

## 4. Préparer le domaine et Cloudflare Tunnel

**NAVIGATEUR — Cloudflare.**

1. Ajouter votre domaine dans Cloudflare, choisir le plan adapté, puis chez le
   registraire remplacer les serveurs DNS par ceux attribués par Cloudflare.
   Attendre que la zone soit **Active**. Ne pas poursuivre avec une délégation
   encore en attente.
2. Dans Cloudflare, ouvrir **Networking → Tunnels**. Selon l'interface du compte,
   cette fonction peut aussi être accessible depuis Cloudflare One, dans les
   connecteurs réseau. Créer un tunnel de type **Cloudflared**, nommé par exemple
   `cafedolbeau-production`.
3. À l'étape de connexion du tunnel, Cloudflare affiche une commande contenant
   `--token`. Copier **uniquement la valeur du jeton**, sans `--token`, guillemets
   ni commande autour. L'enregistrer dans le gestionnaire comme
   `CLOUDFLARE_TUNNEL_TOKEN`. Ne pas lancer cette commande sur CLIENT : le
   connecteur sera démarré par le conteneur sur EC2.
4. Ajouter une **Published application route** avec le sous-domaine `cafe`, votre
   domaine, aucun chemin, type de service **HTTP** et URL **`proxy:8080`**. La
   destination complète doit être **`http://proxy:8080`**. Le nom `proxy` est
   résolu dans Docker sur EC2, pas par le DNS public.
5. Enregistrer la route et vérifier le CNAME créé par Cloudflare pour ce nom.
   Si un ancien enregistrement du même nom existe, le retirer seulement après
   avoir vérifié qu'il ne sert plus. Ne pas créer un enregistrement A vers EC2
   pour ce même nom : le domaine passe par le tunnel.

`CAFE_DOMAIN` doit être exactement le nom publié. Ne pas choisir `localhost` :
dans `cloudflared`, il désignerait le conteneur du tunnel. Ne pas placer une règle
Cloudflare Access exigeant une connexion devant `/healthz`, que le pipeline doit
pouvoir consulter publiquement. Le tunnel peut rester **Inactive/Down** à ce stade,
ce qui est normal avant le démarrage du connecteur sur EC2.
Source : [création d'un tunnel géré à distance](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/).

### 4.1. Certificat Let’s Encrypt sur Nginx

Le tunnel utilise d’abord `http://proxy:8080` pour permettre une transition sans
changer simultanément l’infrastructure et la route Cloudflare. Le déploiement
prépare aussi `https://proxy:8443`, disponible uniquement dans le réseau Docker.
L'entrée publique HTTPS sur EC2:443 utilise une autre écoute Nginx, `8444`, qui
redirige vers le domaine du tunnel (section 4.2). Aucun mécanisme de bascule DNS
n'est ajouté.

Dans Cloudflare, créer un **API Token** avec le droit **Zone → DNS → Edit**,
limité à la zone contenant `PUBLIC_DOMAIN`. Ce jeton est distinct du jeton de
connexion du tunnel. Le conserver dans le secret GitHub
`CLOUDFLARE_DNS_API_TOKEN`. Ajouter aussi la variable GitHub `LETSENCRYPT_EMAIL`
avec l’adresse de contact pour le compte ACME. Si la zone contient des règles
CAA, elles doivent autoriser Let’s Encrypt (`letsencrypt.org`).

Certbot utilise la validation DNS-01 : il crée puis retire un enregistrement TXT
`_acme-challenge`, sans modifier le CNAME du site. Au premier déploiement de chaque
domaine, le script teste une émission et un renouvellement à blanc dans staging,
puis obtient un certificat de production. Les certificats staging restent séparés
et ne sont jamais servis par Nginx. Un échec de préparation interrompt le
déploiement avant l’arrêt des services existants.

Après un déploiement réussi, dans **Networking → Tunnels → votre tunnel →
Published application routes**, modifier la route existante :

- Type : **HTTPS** ; URL : **`proxy:8443`**.
- Dans les paramètres TLS, **Origin Server Name** : le nom exact de `PUBLIC_DOMAIN`
  (par exemple `cafe.votre-domaine.ca`, sans protocole ni port).
- **No TLS Verify** : désactivé. Ne pas contourner la vérification du certificat.

Ouvrir ensuite `https://VOTRE_DOMAINE/healthz` et l’application. Le chemin devient
**navigateur → Cloudflare → tunnel → Nginx HTTPS → Django**. En cas de problème de
transition, remettre temporairement la route sur `http://proxy:8080` et examiner
les journaux ; les deux écoutes internes restent disponibles.

Sur EC2, les fichiers persistants se trouvent sous `/opt/cafedolbeau/tls` : compte
ACME, paramètres de renouvellement, jeton privé et journaux Certbot. Nginx reçoit
uniquement `served/` en lecture seule, avec une paire certificat/clé lisible par
son groupe. Ne pas supprimer ce dossier lors du nettoyage des versions et ne pas
copier ses clés dans le dépôt ou une image Docker.

Le timer systemd vérifie le renouvellement deux fois par jour, avec un délai
aléatoire d’au plus une heure. Il partage le verrou du déploiement. Une nouvelle
paire est vérifiée (autorité, domaine, validité et correspondance de clé), puis
publiée avant `nginx -t` et le rechargement. En cas d’échec, le lien vers la paire
précédente est restauré ; aucun rechargement n’a lieu si la validation échoue.
Une paire inchangée ne provoque pas de rechargement.

**EC2 — diagnostic et renouvellement manuel :**

```bash
sudo systemctl list-timers cafedolbeau-tls.timer
sudo journalctl -u cafedolbeau-tls.service --since '2 days ago'
sudo python3 /opt/cafedolbeau/tls/tls.py dry-run
sudo systemctl start cafedolbeau-tls.service
```

`dry-run` teste le renouvellement auprès de staging sans publier son certificat.
Les détails Certbot restent dans les dossiers privés
`/opt/cafedolbeau/tls/production/logs` et `staging/logs`. Un échec du service est
visible dans systemd ; aucune notification externe n’est configurée. Pour tourner
le jeton DNS, modifier le secret GitHub puis redéployer : sa copie privée sur EC2
sera mise à jour. En cas d’échec, corriger le jeton et redéployer avant expiration
du certificat existant.

Sources : [validation DNS Cloudflare dans Certbot](https://certbot-dns-cloudflare.readthedocs.io/en/stable/),
[paramètres TLS du tunnel](https://developers.cloudflare.com/tunnel/reference/origin-parameters/).

### 4.2. Redirections des accès publics EC2 vers le tunnel

Le domaine `PUBLIC_DOMAIN` reste publié par le tunnel Cloudflare : son CNAME
pointe vers la destination du tunnel (`UUID.cfargotunnel.com`), avec le proxy
Cloudflare activé. Aucun enregistrement A supplémentaire ni Elastic IP n'est
créé par cette configuration. Utiliser l'IP actuelle du résumé du déploiement
pour les accès directs à EC2 ; elle peut changer après un arrêt/démarrage.

Les deux chemins sont distincts :

```text
IP EC2:80  → Nginx:8081 → redirection HTTPS vers PUBLIC_DOMAIN
IP EC2:443 → Nginx:8444 → redirection HTTPS vers PUBLIC_DOMAIN
PUBLIC_DOMAIN → Cloudflare → tunnel → Nginx HTTPS:8443 → Django
```

| Entrée | Publication Docker | Comportement |
| --- | --- | --- |
| HTTP public | `80:8081` | Réponse 308 vers `https://PUBLIC_DOMAIN`, sauf `/healthz` qui répond directement pour les contrôles de déploiement |
| HTTPS public | `443:8444` | Réponse 308 vers `https://PUBLIC_DOMAIN` pour toutes les URL, y compris `/healthz` |
| HTTPS du tunnel | Aucune publication ; `proxy:8443` interne | Sert l'application et `/healthz` |
| HTTP de transition | Aucune publication ; `proxy:8080` interne | Sert l'application et les contrôles internes |

Les redirections conservent le chemin et les paramètres, par exemple
`/connexion/?next=/`. Leur destination est fixée par `PUBLIC_DOMAIN`, quel que
soit l'en-tête `Host` reçu. Nginx ne relaie pas la requête vers Cloudflare : il
demande au navigateur de visiter le domaine public, qui emprunte alors le tunnel.
La séparation des écoutes empêche de rediriger à nouveau les requêtes du tunnel.

Le security group ouvre uniquement les ports applicatifs TCP 80 et 443 à
Internet. SSH reste limité aux adresses configurées ; PostgreSQL, Gunicorn et
les ports internes 8080, 8081, 8443 et 8444 ne sont pas ouverts dans ce groupe.
Le même certificat Let’s Encrypt et le même renouvellement systemd couvrent les
deux écoutes HTTPS de Nginx.

Avec `http://IP_EC2`, le navigateur peut suivre la redirection sans avertissement.
Avec `https://IP_EC2`, il signalera un nom de certificat incorrect **avant** de
recevoir la redirection : le certificat couvre le domaine, pas l'adresse IP.
Cette configuration reste dépendante de Cloudflare et ne donne pas d'accès de
secours à l'application si Cloudflare est indisponible.

Le pipeline vérifie la redirection publique HTTPS en joignant directement l'IP
EC2 avec `curl --resolve`, tout en vérifiant le certificat avec le nom du domaine.
Pour reproduire ce contrôle depuis CLIENT, remplacer `VOTRE_DOMAINE` et `IP_EC2`
par les valeurs du dernier déploiement :

```bash
curl --noproxy '*' --resolve 'VOTRE_DOMAINE:443:IP_EC2' \
  --max-time 10 --dump-header - --output /dev/null \
  'https://VOTRE_DOMAINE/connexion/?next=/'
```

Le résultat attendu est un statut **308** avec l'en-tête
`Location: https://VOTRE_DOMAINE/connexion/?next=/`. Ne pas ajouter `--location` :
ce contrôle doit examiner la redirection, sans la suivre vers Cloudflare.
L'URL publique du domaine doit ensuite continuer à afficher l'application via
le tunnel. L'ouverture de 443 est appliquée par Terraform ; le déploiement
protège toujours l'instance et ses disques contre leur remplacement.

**Bonus DNS/HTTPS :** les redirections 80/443 et le certificat sont présents,
mais le critère exigeant un enregistrement **A vers EC2** n'est pas rempli par ce
mode utilisant un CNAME de tunnel. Ne pas présenter cette configuration seule
comme satisfaisant l'intégralité du bonus.


## 5. Amorcer AWS et la fédération GitHub

### 5.1. Ouvrir une session AWS temporaire

**CLIENT, à la racine du dépôt.** Utiliser l'identité d'administration préparée
en section 1. La connexion ci-dessous ouvre le navigateur ; choisir `us-east-2`
si la CLI demande la région :

```bash
aws login --profile cafedolbeau-console
```

Si le navigateur n'est pas accessible depuis CLIENT, utiliser
`aws login --profile cafedolbeau-console --remote` et suivre le lien/code affiché.
Si votre organisation utilise déjà IAM Identity Center, garder ce mécanisme :
configurer le profil avec `aws configure sso --profile cafedolbeau-console`, puis
`aws sso login --profile cafedolbeau-console` au lieu d'`aws login`.
Source : [authentification locale AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html).

Créer un profil de compatibilité qui transmet à Terraform les identifiants
temporaires, même si son SDK ne sait pas lire directement la session de connexion :

```bash
aws configure set credential_process 'aws configure export-credentials --profile cafedolbeau-console --format process' --profile cafedolbeau-bootstrap
aws configure set region us-east-2 --profile cafedolbeau-bootstrap
export AWS_PROFILE=cafedolbeau-bootstrap
aws sts get-caller-identity
export CAFE_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
```

Vérifier le compte et l'ARN affichés avant toute création. Ne pas continuer sur
le mauvais compte. Ne pas afficher le résultat d'`export-credentials` directement
dans le terminal ni l'enregistrer dans GitHub : le profil l'utilise en interne.
Voir le [paramètre `credential_process`](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html).

### 5.2. Aligner le sujet OIDC sur le code Terraform

**CLIENT.** Terraform attend ce format exact :
`repo:PROPRIETAIRE@OWNER_ID/DEPOT@REPO_ID:environment:production`.
Pour éviter qu'un dépôt ancien ou une configuration héritée utilise un autre
format, fixer explicitement les claims `repo` et `context` et activer les ID
immuables **sur votre nouveau dépôt** :

```bash
gh api --method PUT "repos/$CAFE_REPO/actions/oidc/customization/sub" \
  -H 'X-GitHub-Api-Version: 2026-03-10' \
  --input - <<'JSON'
{"use_default":false,"include_claim_keys":["repo","context"],"use_immutable_subject":true}
JSON
gh api "repos/$CAFE_REPO/actions/oidc/customization/sub"
```

Attendu : requête réussie, configuration avec `use_default: false` et les claims
`repo`, `context`. Si la réponse restitue `use_immutable_subject`, il doit être
`true`. Le GET peut ne pas renvoyer tous les champs ; ne pas déduire de leur
absence que le PUT a échoué. En cas de 403, vérifier les droits Actions/Admin du
compte ; ne pas élargir la confiance IAM avec un joker pour contourner l'erreur.
Sources : [API OIDC GitHub](https://docs.github.com/en/rest/actions/oidc)
et [format des sujets immuables](https://docs.github.com/en/actions/reference/security/oidc).

### 5.3. Créer l'état Terraform et le rôle du pipeline

**CLIENT.** Choisir une fois un nom de bucket globalement unique. La commande
ci-dessous génère un suffixe ; noter le résultat et **réutiliser ce même nom pour
toutes les reprises**, sans régénérer un état pour une installation existante :

```bash
export CAFE_STATE_BUCKET="cafedolbeau-state-${CAFE_ACCOUNT_ID}-$(python3 -c 'import secrets; print(secrets.token_hex(4))')"
printf '%s\n' "$CAFE_STATE_BUCKET"
python3 infra/scripts/bootstrap.py \
  --state-bucket "$CAFE_STATE_BUCKET" \
  --region us-east-2 \
  --repository "$CAFE_REPO" \
  --owner-id "$CAFE_OWNER_ID" \
  --repository-id "$CAFE_REPO_ID"
```

Le script crée/configure le bucket privé, versionné et chiffré, initialise l'état
`bootstrap/terraform.tfstate`, puis présente un plan Terraform. Vérifier le compte,
le dépôt et les créations proposées ; saisir **`yes`** à la demande d'approbation.
Ne pas créer manuellement l'instance du site : ce sera le rôle du pipeline.

Récupérer l'ARN du rôle et le conserver dans la fiche :

```bash
export CAFE_ROLE_ARN=$(terraform -chdir=infra/bootstrap output -raw github_role_arn)
printf '%s\n' "$CAFE_ROLE_ARN"
```

Attendu : `arn:aws:iam::VOTRE_COMPTE:role/cafedolbeau-github-production`.
Un 403 sur un bucket n'autorise pas à le remplacer : choisir un autre nom uniquement
pour une toute première installation. Lors d'une reprise, retrouver le bucket
original. Le bucket et ses états constituent le suivi de l'infrastructure ; ne
pas les supprimer pour résoudre une erreur Terraform.

## 6. Enregistrer variables, clés et secrets dans GitHub

### 6.1. Créer l'environnement

**NAVIGATEUR — votre dépôt → Settings → Environments → New environment.**
Créer exactement **`production`**, en minuscules. Pour ce premier parcours,
autoriser le déploiement depuis `main`. Si vous imposez des reviewers, noter qui
devra approuver le job : il restera en attente jusque-là. Un compte personnel
privé doit disposer d'une offre GitHub prenant en charge les environnements ;
si les paramètres sont indisponibles, régler ce point avant de poursuivre.
Voir les [offres compatibles avec les environnements GitHub](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

### 6.2. Ajouter les variables d'environnement

Dans **Settings → Environments → production → Environment variables**, cliquer
**Add environment variable** pour chaque ligne :

| Nom exact | Valeur à coller | Origine |
| --- | --- | --- |
| `AWS_REGION` | `us-east-2` | Région imposée |
| `AWS_ROLE_ARN` | ARN complet, sans guillemets | `CAFE_ROLE_ARN`, section 5 |
| `TF_STATE_BUCKET` | Nom du bucket, sans `s3://` | `CAFE_STATE_BUCKET`, section 5 |
| `PUBLIC_DOMAIN` | `cafe.votre-domaine.ca`, sans protocole ni chemin | Route Cloudflare |
| `LETSENCRYPT_EMAIL` | Adresse courriel de contact ACME | Responsable du domaine |
| `SSH_ALLOWED_CIDRS` | Tableau JSON, par exemple `["203.0.113.42/32"]` | IPv4 publique réelle de CLIENT |
| `SSH_PUBLIC_KEY` | Ligne complète `ssh-ed25519 AAAA… commentaire` | `~/.ssh/cafedolbeau.pub` sur CLIENT |

Pour connaître l'IPv4 publique de **CLIENT**, dans le même réseau/VPN que celui
qui servira au transfert :

```bash
curl -4 --fail --silent --show-error https://checkip.amazonaws.com
```

Remplacer l'adresse d'exemple par le résultat et ajouter `/32`. Le JSON doit
utiliser des guillemets doubles. `0.0.0.0/0` est refusé par Terraform. Si plusieurs
ordinateurs sont autorisés, utiliser par exemple `["IP_CLIENT_1/32","IP_CLIENT_2/32"]`
avec des adresses réelles. L'IP du runner n'est pas nécessaire pour le déploiement
SSM, sauf si ce même ordinateur fera le transfert.

Ne pas créer `SSH_PUBLIC_KEYS` pour une seule clé. Si plusieurs personnes doivent
se connecter, cette variable facultative accepte un tableau JSON de lignes de
clés publiques complètes. Le pipeline combine les deux variables et synchronise
les clés sur EC2 ; conserver toutes celles qui doivent rester autorisées.

### 6.3. Ajouter les secrets d'environnement

Dans **Settings → Environments → production → Environment secrets**, cliquer
**Add environment secret** :

| Nom exact | Valeur | Création et conservation |
| --- | --- | --- |
| `SECRET_KEY` | Secret Django sur une ligne, au moins 32 caractères | Générer avec la commande Python ci-dessous, puis conserver dans le gestionnaire de mots de passe |
| `POSTGRES_PASSWORD` | Secret distinct, une ligne, au moins 32 caractères | Générer une deuxième valeur de 64 caractères ; ne pas réutiliser la précédente |
| `CLOUDFLARE_TUNNEL_TOKEN` | Jeton seul, sans commande autour | Tunnel de la section 4 |
| `CLOUDFLARE_DNS_API_TOKEN` | Jeton API limité à DNS Edit sur la zone | Section 4.1 |

**CLIENT — terminal Ubuntu, WSL ou macOS.** Pour la première installation,
exécuter cette commande afin de générer `SECRET_KEY` :

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
```

La commande affiche une clé d'environ **86 caractères**, issue de 64 octets
aléatoires. Copier uniquement la ligne générée, sans espaces ni retour à la ligne,
dans une entrée `SECRET_KEY` du gestionnaire de mots de passe. Dans GitHub, ouvrir
**Settings → Environments → production → Environment secrets → Add environment
secret**, saisir **`SECRET_KEY`** dans **Name**, coller la même valeur dans
**Secret**, puis enregistrer. Ne pas réexécuter cette commande pour remplacer la
clé lors des déploiements suivants : réutiliser la valeur conservée.

Pour `POSTGRES_PASSWORD`, créer une entrée distincte avec le générateur du
gestionnaire : longueur **64**, lettres majuscules/minuscules et chiffres, puis
copier cette valeur dans le secret GitHub `POSTGRES_PASSWORD`. Enregistrer aussi
le jeton Cloudflare dans le gestionnaire et le secret GitHub correspondant.
Ne pas copier les secrets dans un fichier du dépôt ni dans une commande conservée
dans l'historique. Les secrets de production peuvent différer de ceux de la base
locale : l'export ne transfère pas le mot de passe du rôle PostgreSQL.

Contrôler les **noms**, sans lire les valeurs secrètes :

```bash
gh variable list --env production --repo "$CAFE_REPO"
gh secret list --env production --repo "$CAFE_REPO"
```

On doit retrouver les six variables et les trois secrets. Ne pas ajouter
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` ou la clé SSH privée aux secrets :
GitHub utilisera OIDC pour AWS. Le jeton du runner ne va pas non plus ici.
**Conserver `SECRET_KEY` et `POSTGRES_PASSWORD` lors des mises à jour** : le script
de déploiement refuse leur modification implicite sur une base existante.

## 7. Installer et démarrer le runner Linux x64

**NAVIGATEUR — votre dépôt → Settings → Actions → Runners → New self-hosted runner.**
Sélectionner **Linux**, architecture **x64**. GitHub affiche les commandes exactes
de téléchargement, de vérification SHA256 et d'extraction correspondant à la
version actuelle, ainsi qu'un jeton d'enregistrement temporaire.

**RUNNER — terminal Ubuntu ordinaire, pas root**, créer un dossier séparé du dépôt :

```bash
mkdir -p ~/actions-runner
cd ~/actions-runner
```

Exécuter les commandes **Download** affichées par GitHub dans ce dossier. Si elles
commencent par créer `actions-runner`, ne pas recréer ce sous-dossier : reprendre
à la commande de téléchargement. Respecter le test SHA256 affiché. Puis exécuter
`sudo ./bin/installdependencies.sh` pour installer les bibliothèques système
nécessaires au runner sur cet Ubuntu neuf. Ensuite, exécuter
la commande **Configure** fournie, de la forme :

```bash
./config.sh --url https://github.com/PROPRIETAIRE/DEPOT --token JETON_TEMPORAIRE
```

Copier la vraie commande de votre écran, et non les valeurs fictives ci-dessus.
Si le jeton expire, recharger l'écran GitHub et en obtenir un nouveau.
Répondre **Entrée** pour le groupe par défaut, nommer le runner
`cafedolbeau-local`, garder les labels automatiques et le dossier de travail
`_work`. Les labels doivent inclure `self-hosted`, `Linux` et `X64` ; la casse
n'empêche pas la correspondance avec le workflow. Ne pas remplacer un runner
existant sans l'avoir identifié.

Vérifier `docker info`, `aws --version` et `python3 --version` dans ce terminal.
Avant de lancer le runner, retirer de **ce terminal seulement** d'éventuels
identifiants AWS exportés pour l'amorçage, afin que le job utilise son rôle OIDC :

```bash
unset AWS_PROFILE AWS_DEFAULT_PROFILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_SECURITY_TOKEN AWS_CONFIG_FILE AWS_SHARED_CREDENTIALS_FILE
./run.sh
```

Attendu : **Connected to GitHub**, puis **Listening for Jobs** ; dans GitHub,
le runner est **Idle**. Laisser ce terminal et la machine/VM allumés, sans veille.
Ne pas utiliser `sudo ./run.sh`. Les mises à jour de PATH et de groupe Docker ne
seront prises en compte qu'au redémarrage du runner. Sur Mac, ni les secrets AWS
personnels ni la base locale ni la clé privée de transfert ne sont requis dans
la VM du runner.

Ouvrir un **second terminal CLIENT** pour les commandes suivantes. `./run.sh`
affiche le début et la fin des jobs ; les sorties détaillées sont dans Actions.
Source : [ajouter un runner autohébergé](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners).

## 8. Déployer le site par le pipeline

### 8.1. Vérifier le code à déployer

**CLIENT, racine de votre copie**, rétablir les variables de la fiche si le
terminal est nouveau, puis :

```bash
cd ~/Documents/Prog/cafeDolbeau_
git status --short
git branch --show-current
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

Pour déployer cette copie, la branche doit être `main` et le SHA local doit
correspondre au SHA distant. S'il y a des changements de code voulus à publier,
les examiner, les committer et les pousser sur **votre** `main` avant de lancer.
Le pipeline récupère GitHub ; il ne déploie jamais automatiquement des fichiers
locaux non poussés. Ne pas ajouter `.env`, les sauvegardes ou les clés privées.

### 8.2. Lancer et suivre

```bash
python3 infra/scripts/suivre-deploiement.py --lancer
```

Le script lance `deploy.yml` depuis `main` et suit l'exécution qu'il vient de
créer. Si une approbation est demandée, aller dans **Actions → exécution en
attente → Review deployments** et faire approuver `production` par la personne
autorisée. Un job en attente de runner nécessite le terminal RUNNER de la section 7.

Le pipeline valide la configuration, construit les images sur RUNNER, obtient
un accès AWS temporaire, applique Terraform, déploie par SSM et vérifie les accès.
La première installation peut prendre plusieurs minutes, notamment pendant
l'initialisation Ubuntu sur EC2. Ne pas lancer un second déploiement pour
« débloquer » le premier sans avoir consulté son état.

Attendu : toutes les étapes réussissent puis le résumé apparaît avec :

```text
Version : SHA_GIT_DEPLOYE
EC2 : i-IDENTIFIANT
DNS public EC2 : ec2-ADRESSE.us-east-2.compute.amazonaws.com
Application : https://cafe.votre-domaine.ca
Santé HTTP : http://IP_PUBLIQUE/healthz
Transfert PostgreSQL depuis votre ordinateur (remplace les données du site) :
python3 infra/scripts/transferer-postgres.py --host ubuntu@DNS_EC2 --confirm-host ubuntu@DNS_EC2 --identity ~/.ssh/cafedolbeau
```

Conserver le SHA, l'ID EC2, le DNS et la commande complète. Le **domaine Cloudflare**
sert au navigateur ; le **DNS EC2** sert au transfert SSH. Ils sont différents.

### 8.3. Vérifier avant de transférer

Dans CLIENT, remettre votre domaine réel dans la variable si nécessaire :

```bash
export CAFE_DOMAIN='cafe.votre-domaine.ca'
curl --fail --silent --show-error "https://$CAFE_DOMAIN/healthz"
```

Attendu : réponse HTTP réussie, code de sortie zéro. Ouvrir le domaine en HTTPS
dans NAVIGATEUR et vérifier l'écran de connexion. Une base neuve n'a pas de compte
applicatif prédéfini ; les comptes viendront de l'import. **Ne pas charger la démo
sur EC2 avant l'import**. Le contrôle `/healthz` teste le service, pas la présence
de vos clients ni la connexion d'un utilisateur.

Pour reprendre le suivi sans relancer le pipeline :

```bash
gh run list --workflow deploy.yml --limit 5
python3 infra/scripts/suivre-deploiement.py ID_EXECUTION
gh run view ID_EXECUTION --log-failed
```

Remplacer `ID_EXECUTION` par le nombre de la colonne ID. `gh run watch` seul
affiche les étapes, mais pas le résumé personnalisé final du script.

## 9. Préparer puis transférer la vraie base locale

**Si vous n'avez aucune donnée à transférer**, ne créer aucune base locale pour
faire un export vide. Passer directement à la section 9.4, ouvrir la session EC2,
définir `compose` comme indiqué, puis exécuter
`"${compose[@]}" exec app python src/manage.py createsuperuser`. Répondre aux
questions de création du compte technique, puis se connecter à `/admin/` en HTTPS
pour préparer les employés, rôles et succursales. Les contrôles de comparaison
avec une source locale ne concernent que le parcours avec import.

### 9.1. Identifier la source avant de la démarrer

**CLIENT, dossier du projet contenant le `.env` et la base existants.** Ne pas
écraser `.env` avec l'exemple et ne pas recréer les volumes. Sous Windows, vérifier
que l'intégration WSL utilise le même Docker Desktop que celui de la base.

```bash
docker context show
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Label "com.docker.compose.project"}}\t{{.Label "com.docker.compose.service"}}'
docker compose --env-file .env -f docker/compose.yaml ps -a
```

Identifier le conteneur PostgreSQL attendu, son label de projet et le service `db`.
**Ne pas continuer si vous ne retrouvez pas la base connue** : un nouveau clone
dans un autre Docker ou un autre projet peut démarrer une base vide.

Le projet par défaut est `cafedolbeau_`. Si la base utilise un autre nom, définir
ci-dessous ce nom **observé**. Utiliser le même nom pour tous les contrôles et le
transfert. Le tableau Docker peut aussi montrer `db-test` : ne pas choisir la
base de tests.

```bash
export CAFE_SOURCE_PROJECT='cafedolbeau_'
```

**Seulement après identification**, si `db` est arrêté :

```bash
docker compose --env-file .env -f docker/compose.yaml -p "$CAFE_SOURCE_PROJECT" up -d db
```

Attendre que la base soit prête. Vérifier le serveur et les volumes :

```bash
docker compose --env-file .env -f docker/compose.yaml -p "$CAFE_SOURCE_PROJECT" ps
docker compose --env-file .env -f docker/compose.yaml -p "$CAFE_SOURCE_PROJECT" exec -T db sh -ec 'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT current_database(), version();"'
```

Attendu : PostgreSQL **17** et le nom de votre base. Si la source utilise une
autre version ou n'est pas dans Docker, ne pas appliquer ce parcours par défaut.
Le script accepte une source native via `--pg-service NOM_SERVICE_LIBPQ`, avec
`pg_dump` local et les fichiers de configuration libpq, mais sa configuration
doit être préparée séparément avant le transfert.

### 9.2. Arrêter les écritures et vérifier le schéma

Planifier une interruption. Prévenir les utilisateurs des deux installations.
Arrêter les caisses/processus Python qui écrivent localement, puis les services
web Docker **sans arrêter `db`** :

```bash
docker compose --env-file .env -f docker/compose.yaml -p "$CAFE_SOURCE_PROJECT" stop cloudflared proxy app
```

Vérifier que le code local correspond au **SHA Version** du résumé du pipeline.
Si ce n'est pas le cas, aligner et valider le code avant de migrer la base ; ne
pas faire un changement forcé de branche sur des modifications non sauvegardées.
Avant les migrations, créer une sauvegarde locale du schéma actuel. Les commandes
suivantes ne suppriment rien ; le dossier `backups/` est ignoré par Git :

```bash
mkdir -p backups
chmod 700 backups
export CAFE_LOCAL_BACKUP="$PWD/backups/avant-migration-$(date +%Y%m%d-%H%M%S).dump"
(
set -e
umask 077
docker compose --env-file .env -f docker/compose.yaml -p "$CAFE_SOURCE_PROJECT" exec -T db sh -ec 'exec pg_dump --no-password --format=custom --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$CAFE_LOCAL_BACKUP"
docker compose --env-file .env -f docker/compose.yaml -p "$CAFE_SOURCE_PROJECT" exec -T db pg_restore --list < "$CAFE_LOCAL_BACKUP" > /dev/null
)
```

Attendu : export et vérification terminés sans erreur ; conserver le chemin et
le fichier. Sinon, ne pas poursuivre les migrations. Appliquer ensuite celles
du code qui vient d'être déployé :

```bash
docker compose --env-file .env -f docker/compose.yaml -p "$CAFE_SOURCE_PROJECT" run --build --rm --no-deps app python src/manage.py migrate --noinput
docker compose --env-file .env -f docker/compose.yaml -p "$CAFE_SOURCE_PROJECT" run --rm --no-deps app python src/manage.py migrate --check --noinput
```

Ne pas utiliser un jeu de démonstration pour
réparer une erreur de migration.

Relever des comptages non nominatifs, qui serviront à comparer après import :

```bash
docker compose --env-file .env -f docker/compose.yaml -p "$CAFE_SOURCE_PROJECT" run --rm --no-deps app python src/manage.py shell -c 'from CafeDolbeau.models import Client, Employe, Succursale, TransactionCafe; print({m.__name__: m.objects.count() for m in (Client, Employe, Succursale, TransactionCafe)})'
```

Si les nombres ne correspondent pas à la base que vous pensiez transférer,
**arrêter ici** et retrouver le bon projet Docker. Si vous n'avez pas encore de
données locales, aucune importation n'est nécessaire pour héberger un site neuf.
Créer alors le premier compte sur le serveur via `createsuperuser`, puis configurer
les employés et rôles dans l'application ; ne pas importer une base vide par défaut.

### 9.3. Vérifier SSH et lancer le transfert

**CLIENT**, reprendre le DNS exact du dernier déploiement réussi, sans protocole :

```bash
export CAFE_EC2_DNS='ec2-ADRESSE.us-east-2.compute.amazonaws.com'
ssh-add -l
ssh -T -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i ~/.ssh/cafedolbeau "ubuntu@$CAFE_EC2_DNS" 'sudo -n test -f /opt/cafedolbeau/current/compose.yaml'
```

Remplacer `ec2-ADRESSE...` par le vrai nom. Attendu : aucune erreur et code de
sortie zéro. Le script accepte et enregistre automatiquement une clé d'hôte pour
un **nouveau** DNS (`accept-new`). Un avertissement de clé modifiée pour un nom
déjà connu reste bloquant ; voir section 10. Cela ne remplace pas la clé privée
de l'utilisateur, qui doit correspondre à la clé publique publiée dans GitHub.

Copier la commande donnée par le pipeline ; pour rendre explicite le projet
source identifié plus haut, utiliser cette forme équivalente :

```bash
python3 infra/scripts/transferer-postgres.py \
  --host "ubuntu@$CAFE_EC2_DNS" \
  --confirm-host "ubuntu@$CAFE_EC2_DNS" \
  --identity ~/.ssh/cafedolbeau \
  --project-name "$CAFE_SOURCE_PROJECT"
```

Pour sélectionner directement un conteneur PostgreSQL source, par exemple `BLA`
créé avec `restaurer-postgres.py --container BLA`, remplacer les options Compose
par `--container` :

```bash
python3 infra/scripts/transferer-postgres.py \
  --host "ubuntu@$CAFE_EC2_DNS" \
  --confirm-host "ubuntu@$CAFE_EC2_DNS" \
  --identity ~/.ssh/cafedolbeau \
  --container BLA
```

Le conteneur source doit être démarré. Le script lit `POSTGRES_DB` et
`POSTGRES_USER` dans ce conteneur (avec `postgres` comme valeur par défaut).
Cette option ne lit pas le `.env` local et ne se combine pas avec `--pg-service`,
`--project-name`, `-f` ou un autre `--env-file`. Si `lancer-restauration.py` utilise
déjà ce volume, `BLA` est arrêté : sélectionner plutôt le nom du conteneur `db`
de cette pile, visible avec `docker ps`. Ne pas démarrer deux PostgreSQL sur le
même volume.

**Cette commande remplace les objets présents dans l'export et leurs données sur
le site. Elle ne fusionne pas deux historiques.** Les éventuelles tables distantes
absentes de l'export ne sont pas supprimées. Garder les écritures locales arrêtées
jusqu'à la bascule définitive : un export cohérent n'inclut pas les opérations
faites après son cliché.

Le script effectue les opérations suivantes :

1. Vérifie l'accès SSH et la configuration de production.
2. Produit un export `pg_dump` dans un dossier temporaire privé hors du dépôt.
3. Envoie l'archive directement par SSH et contrôle son SHA256.
4. Prend le même verrou que les déploiements, vérifie la lisibilité de l'archive,
   puis arrête le tunnel, le proxy et l'application de production.
5. Sauvegarde PostgreSQL distant dans
   `/opt/cafedolbeau/backups/import-XXXXXXXX/avant-import.dump` ; noter le chemin
   exact affiché.
6. Restaure avec `pg_restore --single-transaction`. Une erreur SQL annule cette
   transaction ; une erreur applicative ultérieure ne restaure pas automatiquement
   l'ancienne base.
7. Vérifie les migrations, démarre l'application et le proxy, contrôle la santé
   HTTP interne, puis redémarre le tunnel.
8. Supprime l'archive reçue et, à la sortie normale ou sur erreur gérée, le dossier
   temporaire local. Une interruption brutale de la machine peut laisser des fichiers.

Attendu : **« Import terminé ; application saine et tunnel redémarré. »**, puis
**« Transfert terminé ; le fichier temporaire local a été supprimé. »**. Si une
erreur survient après l'arrêt, le script tente de maintenir le site arrêté ;
examiner la situation avant de le rouvrir. Les détails de la transaction sont
décrits dans la [documentation PostgreSQL](https://www.postgresql.org/docs/17/app-pgrestore.html).

### 9.4. Contrôler les données et basculer les utilisateurs

**CLIENT**, vérifier à nouveau l'accès public :

```bash
curl --fail --silent --show-error "https://$CAFE_DOMAIN/healthz"
ssh -i ~/.ssh/cafedolbeau "ubuntu@$CAFE_EC2_DNS"
```

**EC2 — session SSH ouverte**, comparer les comptages avec la source :

```bash
sudo -i
cd /opt/cafedolbeau/current
compose=(docker compose --project-name cafedolbeau_ --env-file "$PWD/.env" -f "$PWD/compose.yaml")
"${compose[@]}" ps
"${compose[@]}" exec -T app python src/manage.py shell -c 'from CafeDolbeau.models import Client, Employe, Succursale, TransactionCafe; print({m.__name__: m.objects.count() for m in (Client, Employe, Succursale, TransactionCafe)})'
exit
exit
```

Les deux `exit` ferment le shell root puis la session SSH. Dans NAVIGATEUR,
ouvrir le domaine HTTPS, se connecter avec un compte importé connu et vérifier
ses succursales, ses permissions, les clients et un historique connu. Les mots
de passe des comptes sont importés avec leurs empreintes ; les anciennes sessions
peuvent nécessiter une nouvelle connexion, notamment si la clé Django diffère.

Si les comptages et contrôles fonctionnels concordent, diriger les utilisateurs
vers le site. Garder l'ancienne installation locale arrêtée et sauvegardée.
**Ne pas relancer un import ultérieur pour une simple mise à jour du code** : il
pourrait remplacer les transactions saisies depuis la mise en ligne.

## 10. Diagnostic, reprise et restauration

### 10.1. Erreurs fréquentes

| Symptôme | Vérification et action |
| --- | --- |
| Job « Queued » / en attente | Vérifier **Settings → Actions → Runners**, état Idle/Active et labels Linux x64 ; garder `./run.sh` ouvert. Vérifier aussi les approbations de `production` et un déploiement précédent encore actif. |
| `gh` refuse l'accès | Exécuter `gh auth status`, vérifier le compte, le dépôt `origin` et les droits. Le suivi utilise GitHub CLI ; il ne nécessite pas de session AWS personnelle. |
| `suivi_id` inconnu au lancement | Le workflow sur `main` est trop ancien ; pousser/synchroniser la version contenant ce champ avant `--lancer`. |
| Erreur OIDC / `AssumeRoleWithWebIdentity` | Vérifier `AWS_ROLE_ARN`, `production`, les deux ID GitHub et la configuration OIDC de la section 5.2. Le rôle doit faire confiance au sujet exact du dépôt avec ses ID ; ne pas ajouter de joker. |
| Secret ou variable manquant | Vérifier l'orthographe et l'environnement `production`, les trois secrets et les six variables. Éviter les valeurs vides, retours à la ligne et noms écrits dans le mauvais dépôt. |
| Docker « permission denied » sur RUNNER | Reconnexion au groupe Docker, vérifier `docker info` sans sudo, puis redémarrer le runner. Sous WSL2, vérifier Docker Desktop et son intégration Ubuntu. |
| Tunnel Inactive / erreur 502 | Vérifier jeton, domaine et service `https://proxy:8443` après la transition (ou `http://proxy:8080` avant). Vérifier aussi Origin Server Name et le certificat Nginx. Consulter les logs `cloudflared`, `proxy`, `app` sur EC2. Ne pas lancer le même connecteur sur un autre ordinateur sans intention explicite. |
| `service "db" is not running` | Retrouver le projet/contexte source avec la section 9.1 ; démarrer son `db` existant et vérifier les comptages. Ne pas créer une base neuve au hasard. |
| Avertissement local `CLOUDFLARE_TUNNEL_TOKEN` non défini | Ce seul avertissement n'empêche pas l'export de `db`. Le jeton de production reste dans les secrets GitHub ; ne pas le copier localement juste pour supprimer l'avertissement. |
| SSH expire / connexion refusée | Vérifier le DNS du dernier résumé, l'état EC2 et `SSH_ALLOWED_CIDRS`. Une IP publique modifiée exige de mettre à jour la variable GitHub et de redéployer pour appliquer la règle réseau. |
| `Permission denied (publickey)` | Vérifier `ubuntu`, `ssh-add -l`, la clé privée utilisée et `SSH_PUBLIC_KEY`/`SSH_PUBLIC_KEYS`. Après changement des clés publiques GitHub, redéployer pour les synchroniser sur EC2. |
| Mot de passe PostgreSQL local incorrect | Conserver le `.env` et le volume de secrets d'origine. Modifier `.env` ne change pas le mot de passe enregistré par PostgreSQL. Voir le guide Docker local. |
| Identifiants de démonstration déjà présents | La démo a déjà été chargée ou certains identifiants existent. Ne pas la recharger pour préparer le transfert ; ne pas vider la base. |
| Clé Django ou mot de passe persistants modifiés | Remettre les secrets de production précédents. Une rotation demande une intervention coordonnée, pas un changement aveugle dans GitHub. |
| Remplacement/destruction EC2 refusé par Terraform | Protection volontaire des données. Examiner le plan ; ne pas retirer les protections ni supprimer l'état pour forcer le déploiement. |

### 10.2. Logs du pipeline et du serveur

**CLIENT**, remplacer les identifiants fictifs :

```bash
gh run list --workflow deploy.yml --limit 5
gh run view ID_EXECUTION --log-failed
gh run view ID_EXECUTION --log
```

Les logs techniques du runner sont dans `~/actions-runner/_diag/` ; la console
de `run.sh` n'affiche pas toutes les sorties du job. Un avertissement de version
Node des actions n'est pas à lui seul un échec du pipeline : regarder sa conclusion.

Si le déploiement SSM échoue, relever l'ID **« Commande SSM »** dans les logs.
Dans AWS **Systems Manager → Run Command → Command history**, région `us-east-2`,
ouvrir cette commande et les sorties de son invocation. Si l'instance n'est pas
encore accessible, contrôler également **EC2 → Instances → instance → Actions →
Monitor and troubleshoot → Get system log**, puis les status checks.

Si SSH fonctionne, ouvrir EC2 et examiner les services :

```bash
ssh -i ~/.ssh/cafedolbeau "ubuntu@$CAFE_EC2_DNS"
sudo -i
cd /opt/cafedolbeau/current
compose=(docker compose --project-name cafedolbeau_ --env-file "$PWD/.env" -f "$PWD/compose.yaml")
"${compose[@]}" ps -a
"${compose[@]}" logs --tail 100 app proxy cloudflared
exit
exit
```

Lors d'un tout premier déploiement raté, `current` peut ne pas exister : la promotion
se fait seulement après les contrôles. Consulter alors la sortie SSM et le dossier
de la release indiqué dans la commande sous `/opt/cafedolbeau/releases/`. Ne pas
publier le contenu du `.env` dans une issue ou un message de diagnostic.

### 10.3. Clé d'hôte SSH modifiée

`accept-new` accepte un nouveau nom, mais refuse une clé différente pour un nom
déjà enregistré. Vérifier d'abord le compte AWS, l'ID de l'instance et son DNS.
Depuis **EC2 → instance → Connect → Session Manager**, si votre identité y a accès,
exécuter sur l'instance :

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Comparer cette empreinte à celle présentée lors d'une connexion SSH manuelle.
Seulement si le remplacement de serveur est confirmé et légitime, sur CLIENT :

```bash
ssh-keygen -R "$CAFE_EC2_DNS"
ssh -o StrictHostKeyChecking=accept-new -i ~/.ssh/cafedolbeau "ubuntu@$CAFE_EC2_DNS"
```

Comparer à nouveau l'empreinte si SSH demande une confirmation. Ne pas effacer
tout `known_hosts`. Le DNS public EC2 peut changer après un arrêt/redémarrage de
l'instance : reprendre alors le DNS actuel, sans supprimer les données ni l'état.

### 10.4. Restaurer la sauvegarde distante d'avant import

Cette opération remplace les données actuelles par la sauvegarde choisie et
nécessite une interruption. Utiliser le **chemin exact affiché par le transfert**.
Ne pas choisir une archive vide issue d'une sauvegarde échouée. Si SSH a été
coupé pendant un transfert, vérifier qu'aucun import n'est encore en cours avant
d'entreprendre une restauration ; le verrou ci-dessous empêche le chevauchement.

**CLIENT**, se connecter :

```bash
ssh -i ~/.ssh/cafedolbeau "ubuntu@$CAFE_EC2_DNS"
```

**EC2**, ouvrir root et lister les sauvegardes :

```bash
sudo -i
ls -lh /opt/cafedolbeau/backups/import-*/avant-import.dump
```

Remplacer `import-XXXXXXXX` dans le bloc suivant par le vrai dossier. Exécuter
le bloc comme un sous-shell unique : une erreur interrompt la séquence et libère
le verrou à sa sortie. Ne pas rouvrir le site si les contrôles échouent.

```bash
(
set -euo pipefail
CAFE_BACKUP='/opt/cafedolbeau/backups/import-XXXXXXXX/avant-import.dump'
test -s "$CAFE_BACKUP"
exec 9>/opt/cafedolbeau/deploy.lock
flock -n 9
cd /opt/cafedolbeau/current
compose=(docker compose --project-name cafedolbeau_ --env-file "$PWD/.env" -f "$PWD/compose.yaml")
CAFE_RESTORE_OK=false
trap 'if [ "$CAFE_RESTORE_OK" != true ]; then "${compose[@]}" stop cloudflared proxy app || true; fi' EXIT
"${compose[@]}" exec -T db pg_restore --list < "$CAFE_BACKUP" > /dev/null
"${compose[@]}" stop cloudflared proxy app
"${compose[@]}" exec -T db sh -ec 'exec pg_restore --no-password --clean --if-exists --single-transaction --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$CAFE_BACKUP"
"${compose[@]}" run --rm --no-deps app python src/manage.py migrate --check --noinput
"${compose[@]}" up -d --no-deps --wait --wait-timeout 240 app
"${compose[@]}" up -d --no-deps --wait --wait-timeout 120 proxy
curl --fail --silent --show-error --max-time 15 http://127.0.0.1/healthz
"${compose[@]}" up -d --no-deps cloudflared
CAFE_RESTORE_OK=true
)
```

Attendu : restauration et contrôles réussis. Le bloc tente de maintenir le site
arrêté en cas d'erreur, y compris pendant le redémarrage. Examiner les logs avant
de reprendre. Fermer ensuite les deux shells avec `exit`, puis `exit`, et refaire
les contrôles publics et fonctionnels de la section 9.4.

Le dossier `backups` distant est privé et conservé par les déploiements, mais il
reste sur le disque EC2 : ce n'est pas une sauvegarde indépendante contre la perte
de ce disque. Définir une rétention et une copie externe selon vos besoins.
Ne pas supprimer cette sauvegarde pendant le diagnostic.

### 10.5. Sauvegarder la production et télécharger une copie

**CLIENT — Python 3.12 et SSH**, depuis la racine du dépôt :

```bash
export CAFE_EC2_DNS='DNS_PUBLIC_ACTUEL_EC2'

python3 infra/scripts/sauvegarder-postgres.py \
  --host "ubuntu@$CAFE_EC2_DNS" \
  --identity ~/.ssh/cafedolbeau
```

Remplacer `$CAFE_EC2_DNS` par le DNS ou l’IP actuels si cette variable n’est pas
définie. L’accès SSH doit être autorisé depuis votre adresse IP et le compte
`ubuntu` doit disposer de `sudo` sans mot de passe, comme pour le transfert.
La production doit être déployée dans `/opt/cafedolbeau/current` et son service
`db` doit être démarré. Le script utilise la configuration du serveur ; il ne
nécessite ni PostgreSQL local en cours d’exécution, ni session AWS CLI active.
Omettre `--identity` pour utiliser l’agent ou la configuration SSH. Le script
accepte aussi `--port 22` et `--output-dir /chemin/vers/sauvegardes`.

Le script exécute `pg_dump` au format personnalisé dans le conteneur PostgreSQL
de production, sans arrêter le site. Il valide la table des matières de l’archive
avec `pg_restore --list`, conserve l’archive distante dans
`/opt/cafedolbeau/backups/export-XXXXXXXX/production.dump`, puis la télécharge par
SSH. Il vérifie la taille et le SHA-256 avant de publier la copie locale sous un
nom unique dans `backups/postgres/`. Les sauvegardes sont privées (mode `0600`)
et le dossier local par défaut est exclu de Git. Aucun mot de passe PostgreSQL
n’est transmis en argument ou affiché.

Un verrou empêche le chevauchement avec un déploiement ou un import. Si le
téléchargement échoue ou si l’empreinte diffère, le fichier local partiel est
supprimé ; la sauvegarde distante terminée reste disponible. Les sauvegardes
réussies ne sont pas supprimées automatiquement : surveiller l’espace disque.

Conserver la sortie indiquant les chemins, la taille et le SHA-256 comme preuve
de sauvegarde. **Pour satisfaire A8, il faut ensuite restaurer la copie dans une
base de test séparée et vérifier les données.** La validation de l’archive seule
ne démontre pas une restauration réussie.

### 10.6. Restaurer la copie dans une base locale de test

**CLIENT — Python 3.12 et Docker**, depuis la racine du dépôt. Le script restaure
le fichier téléchargé et affiche les tables ainsi que les comptages des clients
et des transactions :

```bash
python3 infra/scripts/restaurer-postgres.py \
  backups/postgres/NOM_DU_FICHIER.dump
```

Remplacer le chemin par celui affiché par `sauvegarder-postgres.py`. Le script
crée `cafe-restauration-a8`, attend PostgreSQL, restaure dans `cafe_restore` et
vérifie les données. Il refuse une archive absente, vide ou sans en-tête de dump
personnalisé, ainsi qu’un nom de conteneur déjà utilisé. Pour conserver un essai
précédent, choisir un autre nom avec `--container cafe-restauration-a8-2`.

Le conteneur est conservé pour l’inspection et les preuves, même après une erreur
de restauration. Le script affiche les commandes de consultation des journaux et
de nettoyage. Comparer les comptages affichés aux relevés faits en production au
moment de la sauvegarde. La production et la base de développement ne sont pas
modifiées.

**Alternative manuelle — Bash et Docker.** Choisir le script ci-dessus ou les
commandes suivantes pour un même essai. Cette procédure restaure
la sauvegarde dans un nouveau PostgreSQL local, indépendant de la production et
de la base de développement. Utiliser PostgreSQL 17, comme sur EC2.

Définir le chemin exact affiché par le script de sauvegarde ; remplacer
`NOM_DU_FICHIER.dump` par le nom réel, sans sélectionner plusieurs archives :

```bash
CAFE_DUMP='backups/postgres/NOM_DU_FICHIER.dump'
test -s "$CAFE_DUMP"
```

Continuer seulement si la commande réussit. Créer un conteneur dédié au test :

```bash
docker run -d \
  --name cafe-restauration-a8 \
  --network none \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  -e POSTGRES_DB=cafe_restore \
  postgres:17.9-bookworm
```

Le conteneur ne publie aucun port et n’a pas d’accès réseau. L’authentification
`trust` est réservée à ce conteneur de test isolé. Si ce nom est déjà utilisé,
vérifier le test précédent avant de le supprimer ou de choisir un autre nom.

Attendre que PostgreSQL accepte les connexions, avec un délai maximal d’environ
une minute. En cas d’échec, consulter `docker logs cafe-restauration-a8` avant de
continuer :

```bash
(
  for tentative in {1..30}; do
    docker exec cafe-restauration-a8 \
      pg_isready -U postgres -d cafe_restore && exit 0
    sleep 2
  done
  echo 'PostgreSQL de test ne devient pas prêt.' >&2
  exit 1
)
```

Restaurer l’archive dans la base de test vide :

```bash
docker exec -i cafe-restauration-a8 \
  pg_restore \
  --exit-on-error \
  --single-transaction \
  --no-owner \
  --no-acl \
  -U postgres \
  -d cafe_restore \
  < "$CAFE_DUMP" \
  && echo 'Restauration réussie'
```

Attendu : code de sortie `0` et message `Restauration réussie`. Les options
`--no-owner` et `--no-acl` permettent la restauration avec le compte local de
test sans recréer les comptes PostgreSQL de production. En cas d’échec, ne pas
considérer A8 comme validé ; lire l’erreur avant de recommencer dans une base vide.

Vérifier les tables et les données restaurées :

```bash
docker exec cafe-restauration-a8 \
  psql -v ON_ERROR_STOP=1 -U postgres -d cafe_restore \
  -c '\dt' \
  -c 'SELECT COUNT(*) AS clients FROM "CafeDolbeau_client";' \
  -c 'SELECT COUNT(*) AS transactions FROM "CafeDolbeau_transactioncafe";'
```

Comparer les comptages avec ceux relevés en production au moment de la
sauvegarde. Une base sans clients n’est pas nécessairement un échec de
restauration : les résultats doivent correspondre aux données réellement
sauvegardées. Si des opérations ont été ajoutées depuis la sauvegarde, les
comptages actuels de production peuvent avoir changé.

Après avoir conservé les preuves, supprimer uniquement le conteneur de test et
son volume anonyme :

```bash
docker rm -fv cafe-restauration-a8
```

Conserver le `.dump` dans un emplacement privé hors de Git. Il contient les
données de production, notamment les informations des clients et les empreintes
des mots de passe des comptes applicatifs.

### 10.7. Vérification A8 : preuves à conserver

La procédure ci-dessus décrit les actions à effectuer ; elle ne constitue pas
une preuve qu’une sauvegarde a effectivement été restaurée. Après l’essai réel,
ajouter ici la date, les résultats et le lien vers la vidéo ou les captures :

- la commande `sauvegarder-postgres.py` et sa sortie indiquant les chemins,
  la taille et le SHA-256 vérifié ;
- le nom du conteneur local et de la base `cafe_restore`, montrant que la cible
  est distincte de la production ;
- la commande `pg_restore` et le message de réussite ;
- les comptages des clients et des transactions restaurés, comparés aux relevés
  de production au moment de la sauvegarde.

Masquer les secrets et les données personnelles dans les preuves. Ne pas
publier l’archive elle-même dans le dépôt ou la vidéo.

### 10.8. Ouvrir l’application locale avec la base restaurée

Après la restauration de la section 10.6, depuis CLIENT à la racine du dépôt :

```bash
python3 infra/scripts/lancer-restauration.py
```

Le lanceur vérifie que `cafe-restauration-a8` est bien le conteneur de test isolé,
l’arrête pour éviter deux PostgreSQL sur un même volume, puis réutilise ce volume
avec [docker/compose.restore.yaml](../docker/compose.restore.yaml). La pile
`cafe-restauration-web` démarre PostgreSQL, applique les migrations du code local,
collecte les fichiers statiques et démarre Django et nginx. Les opérations faites
dans cette interface modifient la copie restaurée. Conserver les preuves de
restauration avant de faire ces essais.

Ouvrir **http://localhost:8001** et se connecter avec un compte présent dans la
sauvegarde. La base locale habituelle et la production ne sont pas utilisées.
Seul nginx publie un port, sur `127.0.0.1` ; PostgreSQL et Gunicorn restent sur
un réseau Docker interne sans Cloudflare.

Si la restauration utilisait un autre nom, ajouter `--container NOM_DU_CONTENEUR`.
Pour choisir un autre port lors du premier lancement, ajouter `--port 8002`.
Par exemple, pour ouvrir une seconde restauration nommée `BLA` pendant que le
premier essai utilise le port 8001 :

```bash
python3 infra/scripts/lancer-restauration.py --container BLA --port 8002
```

Chaque conteneur source personnalisé reçoit un projet Compose et un fichier
`.deploy/restauration-web-IDENTIFIANT.env` distincts. Utiliser un port libre pour
chaque pile. Les commandes de journaux et d’arrêt propres à la pile sont affichées
par le lanceur.

Le lanceur conserve le volume, le port et une clé Django locale dans
`.deploy/restauration-web.env`, exclu de Git, et refuse de changer silencieusement
la base ou le port d’une configuration existante. Relancer la même commande pour
redémarrer cette pile. Ce chemin sans identifiant concerne le conteneur par
défaut `cafe-restauration-a8`.

Pour consulter les journaux ou arrêter l’application, depuis la racine :

```bash
docker compose --project-name cafe-restauration-web \
  --env-file .deploy/restauration-web.env \
  -f docker/compose.restore.yaml logs --tail 100

docker compose --project-name cafe-restauration-web \
  --env-file .deploy/restauration-web.env \
  -f docker/compose.restore.yaml down
```

Le volume PostgreSQL est déclaré externe et reste conservé après `down`.
Ne pas redémarrer l’ancien conteneur `cafe-restauration-a8` pendant que la pile
Web utilise son volume.

## 11. Exploitation après la première installation

- **Mettre à jour le code** : pousser sur votre `main`, démarrer le runner, puis
  exécuter `python3 infra/scripts/suivre-deploiement.py --lancer`. Les volumes
  PostgreSQL restent en place ; ne pas retransférer la base locale.
- **Déployer une autre version** : `--lancer --ref NOM_BRANCHE_TAG_OU_SHA` ; le
  workflow lui-même reste chargé depuis `main`. Adapter les règles de déploiement
  de l'environnement si elles doivent autoriser un autre ref du workflow.
- **Revoir le résumé** : `python3 infra/scripts/suivre-deploiement.py ID_EXECUTION`.
- **Changement d'IP ou ajout d'une clé publique** : modifier les variables de
  `production`, puis redéployer. Garder les clés des utilisateurs encore autorisés.
- **Secrets** : garder les valeurs initiales dans le gestionnaire. Ne pas régénérer
  les identifiants PostgreSQL à chaque lancement et ne pas partager les clés privées.
- **Arrêter le runner local** : `Ctrl+C` dans son terminal, une fois les jobs
  terminés. Cela arrête l'écoute des jobs, pas le site ni sa facturation AWS.
- **Conserver les données** : ne jamais utiliser `docker compose down -v`,
  supprimer les volumes, effacer les états Terraform ou détruire l'infrastructure
  pour une simple mise à jour.

## 12. Liste de contrôle finale

- [ ] Le dépôt personnel contient le workflow et les scripts sur `main`.
- [ ] L'état Terraform est dans le bucket noté ; le rôle OIDC vise les bons ID.
- [ ] Les six variables et trois secrets existent dans `production`.
- [ ] La clé privée reste sur CLIENT et l'agent SSH peut l'utiliser.
- [ ] Le runner est Ubuntu Linux x64 avec Docker utilisable sans `sudo`.
- [ ] Le tunnel publie le bon domaine vers `https://proxy:8443`, avec Origin Server Name et vérification TLS activée.
- [ ] Le timer `cafedolbeau-tls.timer` est actif et le renouvellement à blanc fonctionne.
- [ ] Le pipeline est réussi et le résumé indique le SHA, l'instance et le DNS.
- [ ] La base source a été identifiée par son projet et ses comptages.
- [ ] Les écritures locales sont arrêtées et le code source correspond à la version déployée.
- [ ] Le chemin de sauvegarde distante a été conservé et le transfert a réussi.
- [ ] Une sauvegarde de production a été téléchargée avec le script et son SHA-256 vérifié.
- [ ] Cette sauvegarde a été restaurée dans une base locale de test ; les résultats et les preuves A8 sont conservés.
- [ ] Les comptages, la connexion des utilisateurs et les accès métier ont été vérifiés.
- [ ] Les utilisateurs travaillent désormais sur le site ; aucun import récurrent ne remplace leurs nouvelles opérations.
