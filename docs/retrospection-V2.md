# Rétrospection V2

## Problème d'implémentation

### Plusieurs cafés
Pour implémenter dans la V3 nous allons ajouter une table sucursale, une clé étrangère sera ajouté à la table transaction pour lié chaque transaction à la bonne sucursale. Les transactions existantes seront assoicé à la première sucursale. 

### Une seule fidélité
Il n'y aura pas de modification à faire pour rendre la fidélité global puisqu'elle n'est pas relié aux transactions mais à un compteur présent dans chaque client.

### Chacun son café
Une table devra être ajouté pour associé la sucursale à ses employés. Les permissions du rôle gérant devront être modifié. Le rôle propriétaire sera ajouté. 
Les restrictions seront vérifiés à l'aide d'un ID de chaque sucursale envoyé dans les requêtes nécéssaires.

### Les rapports du réseau
Pour les rapports, on devra ajouté une selection de la sucursale.


## Des conteneurs prêts pour la production

## Ce qui nous a surpris 
Nous attendions à ce que l'ajout de sucursale vienne et au déploiement web de l'application mais, on ne s'attendait pas à devoir changer de `système de gestion de base de données` (SGBD).

## Décision de la V2 qu'on changerait