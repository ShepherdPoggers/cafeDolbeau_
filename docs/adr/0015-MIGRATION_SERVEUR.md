# ADR-0015 — Application des migrations

- **Statut :** Accepté  
- **Date :** 2026-11-23
- **Demande concernée :** §4.3.3

## Contexte
Lorsqu'une mise à jour a lieu sur le serveur, il faut appliquer les différentes migrations à la BD.

## Décision
Les migrations s'appliquent automatiquement au démarrage en production.


## Options écartées

- Exécuter les migrations manuellement en SSH
    Puisque tout va être automatisé, ça ajoute une couche inutile. 
- Exécuter les migrations au démarrage du conteneur
    À chaque redémarrage de `app` on relancerait la vérification des migrations ce qui est inutile puisqu'on vérifie tandis que l'app n'a pas changé.


## Conséquences
C'est un peu plus long à mettre en place, mais lorsque ce sera fait, aucune interaction ne sera nécessaire.