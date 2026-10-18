# Conception Café Dolbeau

## Table des matières

- [Implémentation](#implémentation)
  - [Structure du projet](#structure-du-projet)
  - [Clients](#clients)
    - [Suppression d'un client](#suppression-dun-client)
    - [Fusion de deux clients](#fusion-de-deux-clients)
  - [Achat d'articles](#achat-darticles)
    - [Onzième café gratuit et cartes prépayées](#onzième-café-gratuit-et-cartes-prépayées)
      - [Calcul des cafés gratuits](#calcul-des-cafés-gratuits)
      - [Explication de la logique](#explication-de-la-logique)
        - [Tableau explicatif](#tableau-explicatif)
      - [Consommation](#consommation)
    - [Annuler une transaction](#annuler-une-transaction)
  - [Paramètres des cafés gratuits](#paramètres-des-cafés-gratuits)
  - [Création des rapports](#création-des-rapports)
  - [Gestion des permissions](#gestion-des-permissions)
  - [Choix techniques](#choix-techniques)
    - [Centralisation de la logique métier](#centralisation-de-la-logique-métier)
    - [Cohérence des données](#cohérence-des-données)
    - [Migration des données](#migration-des-données)

## Implémentation

### Structure du projet

```text
.                               # Racine du projet
├── docs/                        # Documentation du projet
│   ├── adr/                     # Décisions d'architecture (0001 à 0007)
│   ├── conception.md
│   └── retrospection-V1.md
├── src/
│   ├── config/                  # Configuration du projet Django
│   │   ├── __init__.py
│   │   ├── asgi.py
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   ├── CafeDolbeau/             # Application Django
│   │   ├── admin/               # Administration Django
│   │   │   ├── __init__.py
│   │   │   ├── admin.py         # Administration des modèles
│   │   │   ├── admin_fusions.py # Administration des fusions de clients
│   │   │   └── admin_site.py    # Personnalisation du site d'administration
│   │   ├── forms/               # Formulaires
│   │   │   ├── __init__.py
│   │   │   ├── forms.py
│   │   │   ├── forms_annulation.py
│   │   │   └── forms_rapports.py
│   │   ├── migrations/          # Migrations de la base de données (0001 à 0016)
│   │   ├── static/              # Fichiers CSS et JavaScript
│   │   ├── templates/           # Pages et fragments HTML
│   │   ├── test/                # Tests Django
│   │   ├── tests_js/            # Tests JavaScript
│   │   ├── views/               # Vues Django
│   │   │   ├── __init__.py
│   │   │   ├── views.py
│   │   │   └── views_rapports.py
│   │   ├── __init__.py
│   │   ├── apps.py              # Configuration de l'application
│   │   ├── models.py            # Modèles de données
│   │   ├── permissions.py       # Gestion des permissions
│   │   ├── rapports.py          # Calcul des rapports
│   │   └── services.py          # Logique métier des opérations
│   └── manage.py                # Commandes Django
├── .gitignore                   # Fichiers exclus du suivi Git
├── AI-USAGE.md                  # Utilisation de l'intelligence artificielle
├── README.md
└── requirements.txt
```


### Clients


Un client est constitué des éléments suivants :

- un ID (clé primaire)
- un nom complet
- un numéro de téléphone (UNIQUE)
- un courriel (UNIQUE)
- le nombre de cafés prépayés qu'il possède
- le nombre total de cafés achetés
- le nombre total de cafés gratuits
- est_actif

Lors de l'inscription, le client doit donner son courriel ou son numéro de téléphone. Il est aussi possible de donner les deux.
Cette vérification est faite à l'aide de la redéfinition de la fonction `clean` de la classe `Model`.
On peut chercher un client à l'aide de l'un de ces trois champs : nom, téléphone ou courriel.
Le téléphone et le courriel permettent de distinguer deux homonymes.

Pour faciliter l'inscription des clients, nous avons choisi de permettre la création d'un compte autant avec le téléphone qu'avec le courriel.
Pour les cafés, nous avons préféré en faire des attributs du client puisqu'au final, ce ne sont que des chiffres incrémentés et décrémentés. Cela ne servait à rien de complexifier notre BD avec des tables séparées.
Les cafés gratuits ont été mis à part puisqu'ils ne sont pas considérés dans le nombre total de cafés : ils n'ont pas été achetés.

Un client peut être désactivé, auquel cas aucune transaction ne peut être ajoutée sur son profil. S'il est désactivé : `est_actif = false` ; sinon : `est_actif = true`.

#### Suppression d'un client

Avant d'effectuer une suppression, on vérifie les permissions de l'employé. On s'assure également que le client ne participe pas à une fusion en cours et que ses compteurs n'ont pas été modifiés depuis la dernière confirmation.
La suppression se déroule comme suit :

1. S'il n'existe pas, on crée le client fictif avec l'ID `-1`, nommé `Client Supprimé`.
2. Les transactions du client à supprimer sont transférées au client fictif.
3. On enregistre la suppression dans le journal d'administration.
4. On supprime la fiche du client avec `delete()`.

#### Fusion de deux clients

Lors d'une fusion, deux clients doivent être sélectionnés et il faut choisir quel compte conserver pour la fusion. Le client conservé est appelé `client conservé` et l'autre `client source`.
Avant d'effectuer la fusion, on vérifie les permissions de l'employé. On s'assure également que les deux clients sont actifs, qu'aucune autre fusion en cours ne les concerne et que leurs compteurs n'ont pas été modifiés depuis la dernière confirmation.
La fusion se déroule comme suit :

1. Les compteurs des deux clients sont additionnés (aucun café gratuit n'est accordé).
2. Les transactions du `client source` sont transférées au `client conservé`.
3. Le client source est désactivé.

Le retour en arrière est possible tant qu'aucune transaction n'est effectuée sur le `client conservé`. À la suite d'une transaction, la fusion est définitive et le `client source` est supprimé.

### Achat d'articles

Lorsqu'un client achète un café, le modèle `TransactionCafe` est utilisé.
Ce modèle contient les attributs suivants :

- `type_transaction` -> Permet de savoir si la transaction est un achat, un café prépayé, un café gratuit ou une utilisation de café prépayé/gratuit.
- `client` -> ID du client.
- `client_origine_id` -> Si un client est supprimé, cet attribut permet de le différencier des autres.
- `quantite` -> Nombre de cafés.
- `date_creation` -> Date de la transaction.
- `employe` -> Employé ayant enregistré la transaction.
- `operation_id` -> UUID commun aux lignes d’une même opération, permettant de les regrouper pour une annulation.
- `variation_achetes` -> Variation du compteur de cafés achetés causée par cette ligne.
- `variation_prepayes` -> Variation du compteur de cafés prépayés causée par cette ligne.
- `variation_gratuits` -> Variation du compteur de cafés gratuits causée par cette ligne.

Les variations mémorisent les effets de chaque ligne pour pouvoir les inverser lors d’une annulation. Une valeur positive ajoute des cafés, une valeur négative en retire et zéro laisse le compteur inchangé. Pour les anciennes transactions, ces champs peuvent être à `NULL` : leurs effets doivent alors être renseignés par un gérant avant l’annulation.

Le champ type_transaction permet de savoir quoi faire selon le type de transaction via la vue `ajouter_cafes_client`, qui utilise la fonction `ajouter_cafes`.

- **ACHAT** -> Achat classique : on incrémente de *quantite* le nombre de cafés et on vérifie si un café doit être gratuit.
- **PREPAYE** -> Ajout de *quantite* × 10 cafés prépayés dans le client + *quantite* cafés gratuits.
- **GRATUIT** -> Affiche un message pour féliciter le client et ajoute un café gratuit.
- **UTILISE** -> Utilisation de *quantite* cafés prépayés.


#### Onzième café gratuit et cartes prépayées

##### Calcul des cafés gratuits

Pour calculer le nombre de cafés gratuits accordés au client, l'opération suivante est utilisée :

- **gratuit** : Nombre de cafés gratuits accordés lors de la transaction ;
- **total** : Nombre de cafés achetés par le client avant la transaction ;
- **achat** : Nombre de cafés achetés par le client lors de la transaction, excluant les cafés prépayés ;
- **regle** : Nombre de cafés nécessaires avant d'obtenir un café gratuit.

```math
gratuit = (total + achat)\;\mathrm{DIV}\;regle - total\;\mathrm{DIV}\;regle
```

Ce calcul se fait à l'aide d'une méthode du modèle [ParametresCafe](#paramètres-des-cafés-gratuits).


##### Explication de la logique

Initialement, les cafés gratuits étaient immédiatement consommés, mais pour laisser plus de flexibilité aux clients, nous avions migré les cafés gratuits vers les cafés prépayés. Lorsque 10 cafés étaient achetés, on ajoutait 1 au compteur prépayé. Pour améliorer la clarté visuelle et la compréhension, les cafés gratuits sont maintenant enregistrés dans leur propre compteur. Le café gratuit n'est jamais comptabilisé dans le total afin d'éviter un décalage qui pourrait priver le client d'un café gratuit. Les cafés gratuits n'expirent jamais.

Au début du projet, on ajoutait directement 11 cafés aux compteurs du total et des cafés prépayés, mais puisque nous avons changé la méthode pour calculer les cafés gratuits, cela causait un décalage.
Dans la V1, chaque carte prépayée contient 10 cafés et un café gratuit. Lors de l'achat d'une telle carte, 10 cafés sont ajoutés au compteur de cafés prépayés du client et un café est ajouté au compteur des cafés gratuits.
C'est toujours le cas dans la V2. Si la règle des cafés gratuits n'est pas égale au nombre de cafés prépayés par carte, le prix moyen du café sur la carte va différer de celui des achats courants.

###### Tableau explicatif

| Situation | Résultat attendu pour regle = 10 |
|---|---|
| 9 cafés achetés, puis achat de 1 café | Total acheté : 10 ; ajout de 1 récompense |
| Utilisation de cette récompense | Solde gratuit diminué de 1 ; total acheté inchangé |
| Achat de 2 cartes | +20 achetés, +20 prépayés, +2 gratuits |

##### Consommation

Lorsqu'un client achète un café, il peut décider d'utiliser ou non ses cafés prépayés/gratuits. Les cafés gratuits sont consommés en premier, puis les cafés prépayés.
Un client peut décider de seulement utiliser un certain nombre de cafés prépayés/gratuits et de payer le reste. Il suffit au caissier d'enregistrer une première opération, puis une seconde.

#### Annuler une transaction

Une annulation se déroule ainsi :

1. Une vérification des permissions est effectuée.
   - Si les transactions datent de la V1, seul le gérant peut les annuler.
2. Regroupement des lignes de la transaction grâce à leur UUID commun.
   - Si les transactions datent de la V1, c'est à l'employé de lier les transactions manuellement.
   - Si les paramètres de variation sont NULL, l'employé doit les spécifier.
3. Les opérations sont inversées dans le bon client.
   - Les compteurs ne descendent jamais sous 0.
4. L'annulation est enregistrée dans la table `annulationTransaction`.


### Paramètres des cafés gratuits

Pour simplifier la gestion des paramètres des cafés gratuits, une section complète a été ajoutée dans l'administration. Cette section découle du modèle `ParametreCafe`. Ce modèle a les attributs suivants :

- `id` -> identifiant numérique
- `cafes_pour_gratuite` -> Le nombre de cafés pour en avoir un gratuit (*quantite*)
- `cafes_pour_gratuite_precedent` -> Le nombre précédent de cafés pour en avoir un gratuit
- `date_application` -> La date à laquelle on utilise `cafes_pour_gratuite` au lieu de `cafes_pour_gratuite_precedent`

Il a les méthodes suivantes :

- `calculer_cafes_gratuits()` -> Permet de calculer le nombre de cafés gratuits à accorder
- `charger` -> Permet de charger le modèle en objet et de le retourner
- `seuil_gratuite_actif` -> Retourne le bon seuil de cafés selon la date courante

Il permet d'avoir une certaine flexibilité si de nouvelles règles ou contraintes doivent être implémentées.

### Création des rapports

Pour créer des rapports :

1. Le gérant doit sélectionner les types de transactions et la période de temps.
2. Les paramètres sont validés à l'aide de la classe `RapportForm`.
3. Une requête récupère les informations associées aux paramètres sélectionnés.
4. Calcul des quantités (Net = quantitéTotal - annulée).
5. Les données sont regroupées dans un objet `Rapport` et les détails par transaction sont dans des objets `EvenementRapport`. Tous ces objets sont en mémoire ; aucun n'est en BD.
6. La vue transmet un résultat en HTML. Il est possible d'exporter le rapport en Excel grâce à la bibliothèque `openpyxl`.

### Gestion des permissions

Il y a deux rôles pour gérer les permissions : `barista` et `gérant`. Les permissions attribuées à ceux-ci sont respectivement `acces_base` et `acces_gerant`. Deux décorateurs de fonction sont utilisés pour valider les permissions de l'utilisateur : `@acces_base_requis` et `@gerant_requis`. Ces décorateurs sont placés au-dessus des différentes `views`. Lorsque certaines permissions sont demandées dans la page d'administration, des fonctions telles que `has_delete_permission` ou `has_add_permission` sont appelées. Cela permettra une modularité future des permissions ; par exemple, seul un **SUPERGÉRANT** pourrait modifier la règle du café gratuit.

### Choix techniques

#### Centralisation de la logique métier

Les opérations sur les cafés, les annulations, les suppressions et les fusions sont centralisées dans [services.py](src/CafeDolbeau/services.py).

#### Cohérence des données

Les opérations qui modifient plusieurs données utilisent la fonction `_avec_clients_verrouilles`. Celle-ci utilise `transaction.atomic()` pour garantir que toutes les données sont enregistrées ou que l'opération est complètement annulée. Cela évite de modifier les compteurs d'un client sans enregistrer la transaction correspondante.


#### Migration des données

Pour préserver l'intégrité des données de la `V1`, les champs ajoutés acceptent la valeur `NULL`. Les opérations qui nécessitent ces champs ajoutés se font manuellement pour les lignes qui datent de la `V1`.
