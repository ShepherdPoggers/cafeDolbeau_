# ADR-0016 — Une sauvegarde réel

- **Statut :** Accepté  
- **Date :** 2026-11-23
- **Demande concernée :** §4.3.A8

## Contexte
Des sauvegardes doivent pouvoir être exécuté


## Décision
Les migrations s'appliquent automatiquement au démarage en production.


## Options écartées

- Executer les migrations manuellement en SSH
    Puisque tout va être automatisé, ça ajoute une couche inutile. 
- Executer les migrations au démarage du conteneur
    À chaque redémarage de `app` on relancerait la vérification des migrations ce qui est inutile puisqu'on vérifie tandis que l'app n'a pas changé.


## Conséquences
C'est un peu plus long à mettre en place mais lorsque ce sera fait, aucune interaction ne sera nécéssair.