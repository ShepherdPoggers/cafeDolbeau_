# Conception Café Dolbeau


## Implémentation 

### Structure du projet

```text
.
├── README.md
├── requirements.txt
├── .vscode/                 # Configuration de lancement VS Code
├── docs/                    # Documentation et schémas
└── src/
    ├── manage.py            # Commandes Django
    ├── db.sqlite3           # Données locales, ignorées par Git
    ├── config/              # Paramètres et routes
    └── CafeDolbeau/
        ├── migrations/      # Modification de la base de données
        ├── static/          # Javascript et CSS du site web
        ├── templates/       # Pages HTML
        ├── admin.py         # Ajout de la gestion des clients dans la page d'administration
        ├── apps.py          # Déclaration de la config de l'app Django
        ├── forms.py         # Définition des différents formulaires 
        ├── models.py        # Définition des modèles qui seront présent dans la BD (`Client` et `TransactionCafe`)
        ├── services.py      # Traitement de la transaction coté logique
        ├── tests.py         # Tests unitaires
        └── views.py         # Logique de la page accueil et ajouter_cafes
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
- **PREPAYE** -> Ajout de *quantite* × 10 cafés prépayés dans le client + *quantite* café gratuit.
- **GRATUIT** -> Affiche un message pour féliciter le client et ajoute un café gratuit.
- **UTILISE** -> Utilisation de *quantite* cafés prépayés. On diminue le solde total de *quantite* jusqu'à ce qu'il soit épuisé, puis on fait la même chose pour les cafés gratuits. On utilise **ACHAT** pour le reste.

#### Onzième café gratuit et cartes prépayées

##### Calcul café gratuit

Pour calculer le nombre de cafés gratuits accordés au client, l'opération suivante est utilisé : 

- **gratuit** : Nombre de cafés gratuits accordés lors de la transaction;
- **total** : Nombre de cafés achetés par le client avant la transaction;
- **achat** : Nombre de cafés achetés par le client lors de la transaction, excluant les cafés prépayés.

```math
gratuit = (total + achat) \operatorname{DIV} 10 - total \operatorname{DIV} 10
```

##### Explication de la logique

Initialement, les cafés gratuits étaient immédiatement consommés, mais pour laisser plus de fléxibilité aux clients, nous avions migré les cafés gratuits vers les cafés prépayés. Lorsque 10 cafés étaient achetés, on ajoutait 1 au compteur prépayé. Pour ajouter de la clarté visuelle et de la compréhension, les cafés gratuits sont maintenant enregistrés dans leur propre compteur. Le café gratuit n'est jamais comptablisé dans le total afin d'éviter un décalage qui pourrait privé le client d'un café gratuit. Les cafés gratuits n'expirent jamais.

Au début du projet, on ajoutait directement 11 cafés aux compteurs du total et des cafés prépayés, mais puisque nous avons changé la méthode pour calculer les cafés gratuits, cela causait un décalage. 
Désormais, Chaque carte prépayée contient 10 cafés et un café gratuit. Lors de l'achat d'une telle carte, 10 cafés sont ajoutés au compteur total, 10 cafés sont ajoutés au compteur de cafés prépayés du client et un café est ajouté au compteur des cafés gratuits. 

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
Dans ce fichier, on retrouve les fonctions `ajouter_cafes` et `transaction_prepayes`. 
`ajouter_cafes` utilise le décorateur `@transaction.atomic`, qui garantit que les compteurs et l'historique sont enregistrés ensemble. Cette fonction gère chaque transaction. 
`transaction_prepayes` gère le cas particulier de l'achat d'une carte prépayée. 
