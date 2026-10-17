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

Lors de l'inscription, le client doit donner son courriel ou son numéro de téléphone. C'est aussi possible de donner les deux. 
Cette vérification est faite à l'aide de la redéfinition de la fonction `clean` de la classe `Model`.
On peut chercher un client à l'aide de l'un de ces trois champs: nom, téléphone ou courriel. 
Le téléphone et le courriel permettent de distinguer deux homonymes.

Pour faciliter l'inscription des clients, nous avons choisis de permettre la création d'un compte autant avec le téléphone qu'avec le courriel.
Pour les cafés, nous avons préféré que ce soit des attributs du client puisqu'au final, ce ne sont que des chiffres incrémentés et décrémentés. Cela ne servait à rien de complexifié notre BD avec des tables séparés.
Les cafés gratuits ont été mis à part pusiqu'ils ne sont pas considérés dans le nombre total de café: ils n'ont pas été achetés.

### Achat d'article

Lorsqu'un client achète un café, le modèle `TransactionCafe` est utilisé. 
Ce modèle contient les attributs suivant:
- `type_transaction` -> Permet de savoir si la transaction est un achat, un café prépayé, un café gratuit ou une utilisation de café prépayé/gratuit.
- `client` -> ID du client.
- `quantite` -> Nombre de cafés.
- `date_creation` -> Date de la transaction.

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

##### Explication de la logique

Initialement, les cafés gratuits étaient immédiatement consommés, mais pour laisser plus de fléxibilité aux clients, nous avions migré les cafés gratuits vers les cafés prépayés. Lorsque 10 cafés étaient achetés, on ajoutait 1 au compteur prépayé. Pour ajouter de la clarté visuelle et de la compréhension, les cafés gratuits sont maintenant enregistrés dans leur propre compteur. Le café gratuit n'est jamais comptablisé dans le total afin d'éviter un décalage qui pourrait privé le client d'un café gratuit. Les cafés gratuits n'expirent jamais.

Au début du projet, on ajoutait directement *quantite* + 1 cafés aux compteurs du total et des cafés prépayés, mais puisque nous avons changé la méthode pour calculer les cafés gratuits, cela causait un décalage. 
Désormais, Chaque carte prépayée contient *quantite* cafés et un café gratuit. Lors de l'achat d'une telle carte, *quantite* cafés sont ajoutés au compteur de cafés prépayés du client et un café est ajouté au compteur des cafés gratuits. 

###### Tableau explicatif

| Situation | Résultat attendu |
|---|---|
| 9 cafés achetés, puis achat de 1 café | Total acheté : 10 ; ajout de 1 récompense |
| Utilisation de cette récompense | Solde gratuit diminué de 1 ; total acheté inchangé |
| Achat de 2 cartes | +20 achetés, +20 prépayés, +2 gratuits |

##### Consommation

Lorsqu'un client achète un café, il peut décider d'utiliser ou non ses cafés prépayés/gratuits. Les cafés gratuits sont consommés en premier puis les cafés prépayés. 
Un client peut décider de seulement utiliser un certain nombre de cafés prépayés/gratuits et de payer le reste. Il suffit au caissier d'enregistrer une première opération, puis une seconde.

### Choix techniques

Nous avons centralisé le calcul des cafés dans le fichier service.py.
Dans ce fichier, on retrouve la fonction `ajouter_cafes`.
`ajouter_cafes` utilise `@transaction.atomic`, qui garantit que les compteurs et l'historique sont enregistrés ensemble. Cette fonction gère chaque transaction. 
`transaction_prepayes` gère le cas particulier de l'achat d'une carte prépayée. 
