# ADR-0009 — Comment différencier deux succursales

- **Statut :** Accepté  
- **Date :** 2026-11-08
- **Demande concernée :** §3.2.1

## Contexte
Une nouvelle succursale va être inaugurée, il faut adapter l'application pour qu'elle puisse fonctionner avec les deux succursales. L'application devra être indépendante des machines sur place, les deux succursales parlent à la même instance de l'application. 

## Décision
Chaque succursale sera identifiée à l'aide d'un id unique. Un paramètre dans l'url qui représente cet ID sera ajouté. Il sera transmis au serveur à chaque requête. 

## Options écartées
Un menu de sélection de la succursale lors de la connexion de l'employé, cette option risque d'amener des erreurs humaines qu'on pourrait éviter. Par exemple, un employé travaille dans deux succursales et se trompe de succursale, les chiffres des rapports seront alors faussés.


## Conséquences
À chaque fois qu'on met en place une nouvelle caisse la bonne URL doit être mise manuellement, il peut y avoir des erreurs. Une telle erreur peut être difficile à détecter mais a moins de chances de survenir puisque la sélection est faite une seule fois.  