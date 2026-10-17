# Conception Café Dolbeau


## Implémentation 

### Structure du projet

```text
.                   # Configuration de VS Code
├── AI-USAGE.md                  # Utilisation de l'intelligence artificielle
├── README.md
├── requirements.txt
├── docs/                        # Documentation du projet
│   ├── adr/                     # Décisions d'architecture (0001 à 0007)
│   ├── conception.md
│   └── retrospection-V1.md
└── src/
    ├── manage.py                # Commandes Django
    ├── config/                  # Configuration du projet Django
    │   ├── __init__.py
    │   ├── asgi.py
    │   ├── settings.py
    │   ├── urls.py
    │   └── wsgi.py
    └── CafeDolbeau/              # Application Django
        ├── __init__.py
        ├── admin.py             # Administration des modèles
        ├── admin_fusions.py     # Administration des fusions de clients
        ├── admin_site.py        # Personnalisation du site d'administration
        ├── apps.py              # Configuration de l'application
        ├── forms/               # Formulaires
        │   ├── __init__.py
        │   ├── forms.py
        │   ├── forms_annulation.py
        │   └── forms_rapports.py
        ├── migrations/          # Migrations de la base de données (0001 à 0014)
        ├── models.py            # Modèles de données
        ├── permissions.py       # Gestion des permissions
        ├── rapports.py          # Calcul des rapports
        ├── services.py          # Logique métier des opérations
        ├── static/
        │   └── CafeDolbeau/      # Ressources JavaScript et CSS
        │       ├── cafes.js
        │       ├── rapports.js
        │       ├── recherche.js
        │       └── style.css
        ├── templates/           # Pages et fragments HTML
        │   ├── admin/           # Personnalisation des pages d'administration
        │   │   ├── CafeDolbeau/
        │   │   │   ├── client/
        │   │   │   │   ├── confirmer_fusion.html
        │   │   │   │   └── confirmer_suppression.html
        │   │   │   ├── employe/
        │   │   │   │   └── add_form.html
        │   │   │   ├── fusionclient/
        │   │   │   │   └── confirmer_annulation.html
        │   │   │   └── transactioncafe/
        │   │   │       └── change_form.html
        │   │   └── login.html
        │   ├── registration/
        │   │   └── login.html
        │   ├── 403.html
        │   ├── accueil.html
        │   ├── ajouter_cafes.html
        │   ├── annuler_transaction.html
        │   ├── detail_totaux_rapport.html
        │   ├── en_tete.html
        │   ├── rapports.html
        │   ├── resultats_recherche.html
        │   ├── tableau_rapport.html
        │   └── transactions_cafe.html
        ├── test/                # Tests Django
        │   ├── __init__.py
        │   ├── test_admin_employes.py
        │   ├── test_annulations.py
        │   ├── test_auth.py
        │   ├── test_fusions_clients.py
        │   ├── test_parametres.py
        │   ├── test_rapports.py
        │   ├── test_suppression_clients.py
        │   └── tests.py
        ├── tests_js/            # Tests JavaScript
        │   └── rapports.test.cjs
        └── views/               # Vues Django
            ├── __init__.py
            ├── views.py
            └── views_rapports.py
```


### Clients


Un client est constitué de : 
- un ID (Clé primaire)
- nom complet
- un numéro de téléphone (UNIQUE)
- un courriel (UNIQUE)
- le nombre de cafés prépayés qu'il possède 
- le nombre total de cafés achetés
- le nombre total de cafés gratuits
- est_actif 

Lors de l'inscription, le client doit donner son courriel ou son numéro de téléphone. C'est aussi possible de donner les deux. 
Cette vérification est faite à l'aide de la redéfinition de la fonction `clean` de la classe `Model`.
On peut chercher un client à l'aide de l'un de ces trois champs: nom, téléphone ou courriel. 
Le téléphone et le courriel permettent de distinguer deux homonymes.

Pour faciliter l'inscription des clients, nous avons choisis de permettre la création d'un compte autant avec le téléphone qu'avec le courriel.
Pour les cafés, nous avons préféré que ce soit des attributs du client puisqu'au final, ce ne sont que des chiffres incrémentés et décrémentés. Cela ne servait à rien de complexifié notre BD avec des tables séparés.
Les cafés gratuits ont été mis à part pusiqu'ils ne sont pas considérés dans le nombre total de café: ils n'ont pas été achetés.

Un client peut être désactivé dans quel cas aucune transaction ne peut être ajouté sur son profil. Si il est désactivé : `est_actif = false` sinon : `est_actif = true`

#### Suppression d'un client
Avant d'effectuer une supression, il y a une validation des permissions de l'employé, si le client n'est pas dans une fusion en cours et si les compteurs du client n'ont pas étés modifiés depuis la dernière confirmation. 
La supression va comme suit: 
1. Si il n'existe pas, on crée le client fictif avec l'id `-1` et nommé `Client Supprimé`
2. Les transactions du client à supprimé sont transférés au client fictif
3. On enregistre la supression dans le journal d'administration
4. On supprime la fiche du client avec `delete()`

#### Fusion de deux clients
Lors d'une fusion, deux clients doivent être sélectionné et il faut choisir quel compte conserver pour la fusion. Le client conservé est appelé `client conservé` et l'autre `client source` 
Avant d'effectuer la fusion, il y a une validation des permissions de l'employé, que les deux clients sont actifs, qu'aucune autre fusion en cours ne les concernes et que leurs compteurs n'ont pas étés modifiés depuis la dernière confirmation. 
La fusion va comme suit:
1. Les compteurs deux clients sont additionnés (aucun café gratuit n'est accordé)
2. Les transactions du `client source` sont transférés au `client conservé`
3. Le client source est désactivé

Le retour en arrière est possible tant qu'aucune transaction n'est fait sur le `client conservé`. Suite à une transaction la fusion est définitive et le `client source` est supprimé. 

### Achat d'article

Lorsqu'un client achète un café, le modèle `TransactionCafe` est utilisé. 
Ce modèle contient les attributs suivant:
- `type_transaction` -> Permet de savoir si la transaction est un achat, un café prépayé, un café gratuit ou une utilisation de café prépayé/gratuit.
- `client` -> ID du client.
- `client_origine_id` -> Si un client est supprimé cet attribue permet de le différencier des autres
- `quantite` -> Nombre de cafés.
- `date_creation` -> Date de la transaction.
- `employe` -> Employé ayant enregistré la transaction.
- `operation_id` -> UUID commun aux lignes d’une même opération, permettant de les regrouper pour une annulation.
- `variation_achetes` -> Variation du compteur de cafés achetés causée par cette ligne.
- `variation_prepayes` -> Variation du compteur de cafés prépayés causée par cette ligne.
- `variation_gratuits` -> Variation du compteur de cafés gratuits causée par cette ligne.

Les variations mémorisent les effets de chaque ligne pour pouvoir les inverser lors d’une annulation. Une valeur positive ajoute des cafés, une valeur négative en retire et zéro laisse le compteur inchangé. Pour les anciennes transactions, ces champs peuvent être à `NULL` : leurs effets doivent alors être renseignés par un gérant avant l’annulation.

type_transaction permet de savoir quoi faire selon le type de transaction via la vue `ajouter_cafes_client`, qui utilise la fonction `ajouter_cafes`.

- **ACHAT** -> Achat classique: on incrémente de *quantite* le nombre de cafés et on vérifie si un café doit être gratuit.
- **PREPAYE** -> Ajout de *quantite* × *quantite* cafés prépayés dans le client + *quantite* café gratuit.
- **GRATUIT** -> Affiche un message pour féliciter le client et ajoute un café gratuit.
- **UTILISE** -> Utilisation de *quantite* cafés prépayés.


#### Onzième café gratuit et cartes prépayées

##### Calcul café gratuit

Pour calculer le nombre de cafés gratuits accordés au client, l'opération suivante est utilisé : 

- **gratuit** : Nombre de cafés gratuits accordés lors de la transaction;
- **total** : Nombre de cafés achetés par le client avant la transaction;
- **achat** : Nombre de cafés achetés par le client lors de la transaction, excluant les cafés prépayés;
- **quantite** : Nombre de cafés nécessaire avant d'obtenir un café gratuit.

```math
gratuit = (total + achat)\;\mathrm{DIV}\;quantite - total\;\mathrm{DIV}\;quantite
```

Ce calcul ce fait à l'aide d'une méthode du modèle [ParametresCafe](#paramètre-des-cafés-gratuit)


##### Explication de la logique

Initialement, les cafés gratuits étaient immédiatement consommés, mais pour laisser plus de fléxibilité aux clients, nous avions migré les cafés gratuits vers les cafés prépayés. Lorsque 10 cafés étaient achetés, on ajoutait 1 au compteur prépayé. Pour ajouter de la clarté visuelle et de la compréhension, les cafés gratuits sont maintenant enregistrés dans leur propre compteur. Le café gratuit n'est jamais comptablisé dans le total afin d'éviter un décalage qui pourrait privé le client d'un café gratuit. Les cafés gratuits n'expirent jamais.

Au début du projet, on ajoutait directement 11 cafés aux compteurs du total et des cafés prépayés, mais puisque nous avons changé la méthode pour calculer les cafés gratuits, cela causait un décalage. 
Dans la V1, chaque carte prépayée contient 10 cafés et un café gratuit. Lors de l'achat d'une telle carte, 10 cafés sont ajoutés au compteur de cafés prépayés du client et un café est ajouté au compteur des cafés gratuits. 
C'est toujours le cas dans la V2. Si la règle des cafés gratuit n'est pas égal au nombre de café prépayé par carte, le prix moyen du café sur la carte va différé de celui des achats courrants. 

###### Tableau explicatif

| Situation | Résultat attendu pour quantite = 10 |
|---|---|
| 9 cafés achetés, puis achat de 1 café | Total acheté : 10 ; ajout de 1 récompense |
| Utilisation de cette récompense | Solde gratuit diminué de 1 ; total acheté inchangé |
| Achat de 2 cartes | +20 achetés, +20 prépayés, +2 gratuits |

##### Consommation

Lorsqu'un client achète un café, il peut décider d'utiliser ou non ses cafés prépayés/gratuits. Les cafés gratuits sont consommés en premier puis les cafés prépayés. 
Un client peut décider de seulement utiliser un certain nombre de cafés prépayés/gratuits et de payer le reste. Il suffit au caissier d'enregistrer une première opération, puis une seconde.

#### Annuler une transaction
Une annulation procède ainsin: 
1. Une verrifcation est des permission effectué
2. Regrouppement des lignes de la transaction grace à leur uuid en commun
   - Si les transactions date de la V1 c'est à l'employé de lié les transactions ensemble
   - Si les paramètres de variation sont NULL l'employé doit les spécifiés
3. Les opérations sont inversés dans le bon client.
    - Les compteurs ne descendent jamais sous 0
4. L'annulation est enregistré dans la table `annulationTransaction`
5. La propriété annulé est attribuer à l'opération

### Paramètre des cafés gratuit
Pour simplifier les paramètre des cafés gratuits, une section complète dans l'administration a été ajouté. Cette section découle du modèle `ParametreCafes`. Ce modèle a comme attribut: 
- `id` -> identifiant numérique
- `cafes_pour_gratuite` -> Le nombre de café pour en avoir un gratuit (*quantite*)
- `cafes_pour_gratuite_precedent` -> Le nombre precedant de café pour en avoir un gratuit
- `date_application` -> La date à la quelle on utilise `cafes_pour_gratuite` au lieu de `cafes_pour_gratuite_precedent`

Il a comme méthode: 
- `calculer_cafes_gratuits()` -> Permet de calculer le nombre de café gratuit à accorder
- `charger` -> Permet de charger le modèle en objet et le retourne
- `seuil_gratuite_actif` -> Retourne le bon seuil de café selon 

Il permet d'avoir une certaine flexibilité si il advient que de nouvelle règle ou contrainte doive être implémenté.

### Création des rapports
Pour créer des rapports: 
1. Le gérant doit sélectionner les types de transaction et la période de temps
2. Les paramètres sont valider à l'aide de la classe `RapportForm`
3. Une requête récupère les informations associés aux paramètre sélectionné 
4. Calcul des quantités (Net = quantitéTotal - annulée)
5. Les données sont regroupés dans un objet `Rapport`, les détails par transactions sont dans des objets `EvenementRapport`. Tous ces objets sont en mémoire, aucun n'est en BD.
6. La vue transmet un résultat en HMTL, il est possible d'exporter le rapport en excel grâce à la librairie `openpyxl`

### Gestions des permissions

### Choix techniques

Nous avons centralisé le calcul des cafés dans le fichier service.py.
Dans ce fichier, on retrouve la fonction `ajouter_cafes`.
`ajouter_cafes` utilise `@transaction.atomic`, qui garantit que les compteurs et l'historique sont enregistrés ensemble. Cette fonction gère chaque transaction. 
`transaction_prepayes` gère le cas particulier de l'achat d'une carte prépayée. 

#### Migration des données
