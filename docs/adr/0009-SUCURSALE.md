# ADR-0009 — Comment différencier deux sucursales

- **Statut :** Accepté  
- **Date :** 2026-11-08
- **Demande concernée :** §3.2.1

## Contexte
Une nouvelle sucursale va être inauguré, il faut adapter l'application pour qu'elle puisse fonctionner avec les deux sucursales. L'application devra être indépendante des machines sur places, les deux sucursales parlent à la même instance de l'application. 

## Décision
Chaque sucursale sera identifié à l'aide d'un id unique. Un paramètre dans l'url qui représente cet ID sera ajouté. Il sera transmi au serveur à chaque requête. 

## Options écartées
Un menu de sélection de la sucursale lors de la connexion de l'employé, cet option risque d'amener des erreurs humaines qu'on pourrait évité. Par exemple, un employé travail dans deux sucursales et se trompe de sucursale, les chiffres des rapports seront alors faussés.


## Conséquences
À chaque fois qu'on met en place une nouvelle caisse le bon URL doit être mis manuellement, il peut y avoir des erreurs. Une tel erreur peut être difficile à détecté mais à moins de chance de survenir puisque la sélection est fait une seule fois.  