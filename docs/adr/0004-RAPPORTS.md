# ADR-0004 — Gestion des annulations dans le rapport

- **Statut :** Accepté       
- **Date :** 2026-10-09
- **Demande concernée :** §3.2

## Contexte
Le comptable a besoin de l'historique et d'un compte rendu des transactions. Le patron nous a demandé de permettre une génération flexible des rapports. Il faut définir comment gérer les annulations de transactions dans le rapport. 

## Décision
Une annulation est prise en compte dans le rapport et est affichée précisément dans les détails. Au moment de la génération du rapport, l'annulation est prise en compte.

## Options écartées
**Afficher les annulations dans la période où elles ont été effectuées**
Cette méthode implique trop d'allers-retours entre les rapports pour s'assurer qu'il n'y a pas d'erreur. 

## Conséquences
Cette décision est plus visuelle : on voit que mardi, 10 cafés ont été achetés et 3 ont été annulés. Cependant, c'est légèrement moins précis pour le comptable : s'il veut savoir à quel moment la transaction a été annulée, il ne peut pas. 
