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
        ├── migrations/      # Modification de la base de donné
        ├── static/          # Javascript et CSS du site web
        ├── templates/       # Pages HTLM
        ├── admin.py         # Ajout de la gestion des clients dans la page admin
        ├── apps.py          # Déclaration de la config de l'app django
        ├── forms.py         # Définition des différents formulaires 
        ├── models.py        # Définiion des modèles qui seront présent dans la BD (`Client` et `TransactionCafe`)
        ├── services.py      # Traitement de la transaction coté logique
        ├── tests.py         # Tests unitaire
        └── vies.py          # Logique de la page accueil et ajouter_cafes
```


### Clients


Un client est constitué de : 
- nom complet 
- un numéro de téléphone 
- un courriel 
- le nombre de café prépayé qu'il possède 
- le nombre total de café acheté
- le nombre total de café gratuit

Lors de l'inscription le client doit  donné son courriel ou son téléphone ou les deux. 
Cette vérification est fait à l'aide de la redifinition de la fonction `clean` de la classe Model.
On peut chercher un client à l'aide d'un de ces trois champs. Le téléphone et le courriel permettent de distinguer deux homonymes. 

### Achat d'article

Lorsqu'un client achète un café la Model `TransactionCafe` est utilisé. 
Ce modèle contient les attributs:
- type_transaction
- client
- quantite
- date_creation

type_transaction permet de savoir quoi faire selon la bonne transaction dans la view `ajouter_cafes_client`  qui utilise la fonction ``ajouter_cafes``

- **ACHAT** -> Achat classique on incrément de *quantite* le nombre de café et on vérifie si un café doit etre gratuit.
- **PREPAYE** -> Ajout de *quantite* * 10 café prépayé dans le client plus *quantite* café gratuit.
- **GRATUTI** -> Affiche un message pour félicité le client et ajout d'un café gratuit.
- **UTILISE** -> Utilisation de *quantite* café prépayé, on baisse le nombre total de *quantite* jusqu'à ce qu'il soit épuisé,puis on fait la même chose pour les cafés gratuits, on utilise **ACHAT** pour le reste. 

#### Onzième Café gratuit et cartes prépayés

##### Calcul café gratuit

Pour calculer le nombre de café gratuit accordé au client l'opération suivante est utilisé : 

- **gratuit** : Nombre de café gratuits accordés lors de la transaction
- **total** : Nombre de café achetés par le client avant la transaction
- **achat** : Nombre de café achetés par le client lors de la transaction excluant les cafés prépayés

```math
gratuit = (total + achat) \operatorname{DIV} 10 - total\operatorname{DIV} 10
```

##### Explication de la logique

Initialement les cafés gratuits imédiatement consommé soit le onzième, mais pour laisser de la fléxibilité aux clients nous avons migrés les cafés gratuits vers les cafés prépayé. Lorsque 10 cafés étaient achetés on ajoutait 1 au compteur prépayé. Pour ajouter de la clareté, les cafés gratuits sont maintenant enregistrés dans leur compteur à part. Le café gratuit n'est jamais comptabliser dans le total pour éviter un décalage et privé le client d'un café gratuit. 

Au début du projet,  on ajoutait directement 11 cafés aux compteur de total et de prépayé, mais à cause du décalage mais puisque nous avons changé la méthode pour calculer les cafés gratuits cela causait un décalage. 
Désormais, Chaque carte prépayés contiennent 10 cafés et un café gratuit, lors de l'achat d'une tel carte 10 cafés sont ajoutés au compteur total et 10 cafés sont ajoutés au compteur de café prépayés du client et un café est ajouté au compteur des cafés gratuits. 

##### Consomation

Lorsqu'un client achète un café il peut décidé d'utiliser ou non ses cafés prépayés/gratuits. Les cafés prépayés sont consomés puis les cafés gratuits. 
Si il veut il peut décider de seuelement en utiliser un certain nombre. Cela demendera au caissier d'enregistrer une première opération puis une seconde. 