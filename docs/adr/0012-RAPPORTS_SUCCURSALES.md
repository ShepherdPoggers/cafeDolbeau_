# ADR-0012 — Gestion des rapports avec plusieurs succursales

- **Statut :** Accepté  
- **Date :** 2026-11-12
- **Demande concernée :** §3.2.4

## Contexte
Avec l'ajout de plusieurs succursales il faut pouvoir générer des rapports en fonctions de chacune d'entre elles. 
Notamment, il faut prendre en compte qu'un café gratuit obtenue dans un café x soit dépensé dans un café y.

## Décision
Toutes les transactions se retrouvent dans le rapport de la succursale qui les a enregistrés. L'obtention du café gratuit sera dans la succursale x et sa dépense dans y. 

## Options écartées
La dépense du café gratuit se retrouve dans le rapport de la succursale qui l'a attribué. Cette option a été écarté parcequ'il faudrait vérifier l'historique pour retrouvé la provenance du café gratuit. Cela complexifirait inutilement le programme. 

## Conséquences
Cela permet d'équilibrer correctement les rapports, la succursale sait quand elle "perd une vente". Par ailleurs, cela s'intègre mieux avec la [gestion de la fidélité avec plusieurs succursales](0011-PROMOTIONS.md) puisque lorsque la règle de fidélité est global et que les promotions ne se partagent pas forcémment entre les différentes succursales. 