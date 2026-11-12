# ADR-0009 — Comment différencier deux succursales

- **Statut :** Accepté  
- **Date :** 2026-11-08
- **Demande concernée :** §3.2.1

## Contexte
Une nouvelle succursale va être inauguré, il faut adapter l'application pour qu'elle puisse fonctionner avec les deux succursales. L'application devra être indépendante des machines sur places, les deux succursales parlent à la même instance de l'application. 

## Décision
Chaque succursale sera identifié à l'aide d'un id unique. Un paramètre dans l'url qui représente cet ID sera ajouté. Il sera transmi au serveur à chaque requête. 

## Options écartées
Un menu de sélection de la succursale lors de la connexion de l'employé, cet option risque d'amener des erreurs humaines qu'on pourrait évité. Par exemple, un employé travail dans deux succursales et se trompe de succursale, les chiffres des rapports seront alors faussés.


## Conséquences
À chaque fois qu'on met en place une nouvelle caisse le bon URL doit être mis manuellement, il peut y avoir des erreurs. Une tel erreur peut être difficile à détecté mais à moins de chance de survenir puisque la sélection est fait une seule fois.  