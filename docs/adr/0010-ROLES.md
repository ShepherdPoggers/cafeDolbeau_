# ADR-0010 — Séparation des permissions entre chaque café

- **Statut :** Accepté  
- **Date :** 2026-11-08
- **Demande concernée :** §3.2.3

## Contexte
Avec l'ajout d'une nouvelle succursale nous devons nous assurer que les permissions sont bien restreintes à chaque succursale.

## Décision
La fiche client appartient à tout le réseau. Tous les gérants ont accès à tous les clients. 

## Options écartées
Ségréguer les clients selon les succursales. Cela aurait rendu difficile la promotion de fidélité entre chaque café et aurait complexifié l'architecture lorsqu'un client est inscrit dans deux succursales différentes. 

## Conséquences
Le propriétaire doit faire confiance à ses gérants pour bien fusionner et/ou supprimer les clients puisque cela peut affecter l'entièreté du réseau.
