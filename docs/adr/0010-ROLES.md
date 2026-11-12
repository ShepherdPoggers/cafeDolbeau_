# ADR-0010 — Séparation des permissions entre chaque café

- **Statut :** Accepté  
- **Date :** 2026-11-08
- **Demande concernée :** §3.2.3

## Contexte
Avec l'ajout d'une nouvelle sucursalle nous devons nous assurer que les permissions sont biens restreintes à chaque succursales.

## Décision
La fiche client appartient à tous le réseau. Tous les gérants ont accès à tous les clients. 

## Options écartées
Ségrégué les clients selons les succursales. Cela aurait rendu difficile la promotion de fidélité entre chaque café et aurait complexifé l'architecture lorsqu'un client est inscrit dans deux succursales différentes. 

## Conséquences
Le propriétaire doit faire confiance à ses gérants pour bien fusionner et/ou supprimé les clients puisque cela peut affecter l'entièreté du réseau.
