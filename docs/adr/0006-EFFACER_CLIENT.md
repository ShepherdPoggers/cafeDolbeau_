# ADR-0006 — Anonymiser ou supprimer

- **Statut :** Accepté 
- **Date :** 2026-10-10
- **Demande concernée :** §3.4

## Contexte
Pour des questions de conformité juridique, notre patron nous demande de rendre possible la suppression des informations personnelles d'un client. Nous devons choisir si le client sera anonymisé ou complètement supprimé. 

## Décision
Nous supprimons le client ; les transactions sont transférées vers un client fictif.

## Options écartées
**Anonymiser le client**
Puisque dans la table client il n'y a que des informations personnelles, ça ne sert à rien de conserver une ligne avec des informations bidons.

## Conséquences
Nous avons dû rajouter une colonne dans transactions pour différencier le client d'origine parmi toutes les transactions associées au client fictif. 
