# Rétrospection V1

## Problème d'implémentation

### Annuler une transaction
Dans la V1, puisqu'on enregistre déjà les transactions, il nous suffit de faire l'opération inverse.
Cependant, certaines transactions sont enregistrées sur plusieurs lignes, mais rien ne les lie ensemble. Il va nécessairement falloir ajouter une colonne pour traiter ce cas lors de l'annulation. Par ailleurs, dans notre V1, si le type de transaction est `utilise`, ce type englobe autant la consommation de café prépayé que de café gratuit, alors il n'est pas possible de faire exactement l'opération inverse. 

Pour les anciennes transactions, on ne pourra pas les lier ; il faudra ajouter un mode manuel pour traiter ce cas. 


### Les rapports du patron
Puisqu'on enregistre déjà les transactions, faire les rapports ne demandera que de lire les lignes, de calculer des agrégats et d'effectuer d'autres opérations arithmétiques. Il faudra nécessairement ajouter une page pour créer les rapports. 

### Changer la règle du café gratuit
Ce n'est pas possible présentement. Cependant, la solution est simple : il suffit de remplacer le diviseur dans notre formule par une variable globale qui pourra être modifiée dans le site. 

### Effacer un client
Puisqu'on utilise la relation `on_delete=PROTECT`, seul un client sans transaction pouvait être supprimé dans la V1. Pour éviter de perdre des transactions, nous avons décidé d'ajouter un client buffer (id -1) auquel les transactions qui n'ont plus de client feront référence. Les informations du client seront toutes supprimées. 

### Fusionner deux fiches
La V1 ne propose aucun mécanisme de fusion des fiches. Nous allons devoir l'implémenter de 0.


### Des employés et des permissions
Mis à part le compte administrateur, aucune permission n'est en place sur notre site web. 
Django permet déjà d'avoir différents groupes de permissions et des utilisateurs ; il nous suffira d'adapter cela à notre solution. Nous allons devoir ajouter des vérifications de permissions pour les différentes pages/fonctionnalités. Nous allons devoir ajouter une colonne dans la table transaction pour prendre en compte l'employé qui l'a effectuée. 

## Ce qui nous a surpris 
On ne s'attendait pas à la demande de fusion des fiches. On s'attendait plus à des fonctionnalités comme la vente de différentes boissons et d'autres produits. Cependant, les autres demandes ne nous ont pas particulièrement surpris même si ce n'était pas ce qu'on prévoyait comme demande supplémentaire.

## Décision de la V1 qu'on changerait
Si la V1 était à refaire, nous changerions le modèle d'enregistrement des transactions pour que chaque ligne soit plus complète. Nous aurions dû implémenter la colonne pour relier les différentes lignes d'une même transaction dès le début et enregistrer les différentes variations. Nous aurions eu une base plus solide pour l'ajout des différentes fonctionnalités et nous aurions eu moins de code à modifier, et l'**extensibilité** du code aurait été améliorée. De plus, notre historique aurait été plus représentatif dès le départ. Ces informations sont aujourd'hui perdues pour les anciennes données. 

