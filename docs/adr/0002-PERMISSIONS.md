# ADR-0002 — Des employés et des permissions

- **Statut :** Accepté
- **Date :** 2026-10-08
- **Demande concernée :** §3.6

## Contexte
À la demande du patron, nous devons ajouter des permissions pour restreindre les accès.
Il faut déterminer si les baristas ont le droit d'annuler des transactions. 



## Décision
Les baristas peuvent annuler les transactions qu'ils ont faites si elles sont dans les 10 dernières transactions du client. 

## Options écartées
**Seulement le gérant peut annuler les transactions**
Cette décision a été écartée pour les raisons suivantes :
1. Pour éviter de déranger constamment le gérant pour des erreurs de manipulation.
2. Pour permettre une correction si le gérant est absent.



## Conséquences
Cette décision ajoute des vérifications supplémentaires puisqu'on doit valider si le barista connecté est la source de la transaction. 

Il y a peu de risques d'abus volontaire est limité, puisque le barista ne peut qu'annuler les transactions qu'il a faites récemment. Par ailleurs, une trace des annulations est conservée dans une table de la BD, ce qui facilite la réparation d'une plus grosse erreur. 
