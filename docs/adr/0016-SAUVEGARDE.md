# ADR-0016 — Une sauvegarde réelle

- **Statut :** Accepté  
- **Date :** 2026-11-23
- **Demande concernée :** §4.3.A8

## Contexte
Des sauvegardes de la base en production doivent pouvoir être exécuté et restauré. 


## Décision
Un script `sauvegardepostgres.py` automatise l'utilisation de `pg_dump` et archive la bd. Par la suite, elle peut être restaurée avec le script `` 


## Options écartées
- Faire un `pg_dump` et un `pg_restore` manuellement.
    Cela aurait impliqué des manipulations manuelles avec possibilité d'erreurs à chaque fois qu'on souhaite faire une sauvegarde de la BD.


## Conséquences
L'opération s'effectue plus rapidement et est beaucoup plus simple à lancer. 