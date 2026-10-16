# ADR-0001 — Compteur ou historique

- **Statut :** Accepté  
- **Date :** 2026-10-08
- **Demande concernée :** §2

## Contexte
Suite à l'analyse des nouvelles demandes du patron, nous avons dû réexaminer notre choix de la V1. 

## Décision
Nous allons conserver l'état actuel du programme : un compteur et un historique cohabitent. Le compteur a préséance sur l'historique ; il se modifie au fur et à mesure qu'un client effectue des transactions.


## Options écartées
**Retirer les compteurs et calculer à partir de l'historique**    
Cette option a été écartée parce que :
1. Il faut à chaque fois relire l'historique du client depuis le début.
2. C'est plus simple de conserver notre méthode qui est déjà implémentée.
3. Il devient plus difficile de modifier une valeur spécifique telle que le nombre de cafés prépayés.


## Conséquences
Cette décision rend plus rapide le chargement d'un client puisque le programme ne doit pas lire à chaque fois toutes les transactions. Cependant, cela rajoute un niveau de complexité lors de la suppression puisqu'il faut modifier chaque compteur lors de l'annulation d'une transaction. 

