# ADR-0016 — Une sauvegarde réelle

- **Statut :** Accepté  
- **Date :** 2026-11-23
- **Demande concernée :** §4.3.A8

## Contexte
Des sauvegardes de la base en production doivent pouvoir être exécutées et restaurées. 


## Décision
La sauvegarde et la restauration du site web sont deux opérations distinctes. Le script `infra/scripts/sauvegarder-postgres.py` crée une archive de la base de données. Au besoin, `infra/scripts/restaurer-postgres.py` restaure cette sauvegarde, puis `infra/scripts/lancer-restauration.py` démarre le site web avec les données restaurées.


## Options écartées
- Faire un `pg_dump` et un `pg_restore` manuellement.
    Cela aurait impliqué des manipulations manuelles avec possibilité d'erreurs à chaque fois qu'on souhaite faire une sauvegarde de la BD.


## Conséquences
L'opération s'effectue plus rapidement et est beaucoup plus simple à lancer.
