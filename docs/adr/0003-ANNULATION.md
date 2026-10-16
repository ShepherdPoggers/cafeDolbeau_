# ADR-0003 — Modalité d'annulation

- **Statut :** Accepté      
- **Date :** 2026-10-08
- **Demande concernée :** §3.1

## Contexte
Le patron nous a demandé d'ajouter une fonction pour annuler les transactions.
1. Il faut déterminer ce qu'on fait si un café gratuit accordé par erreur a été consommé.
2. Il faut déterminer le temps limite pour annuler une transaction.

## Décision
1. Le client n'est pas pénalisé ; la faute revient au commerce. La transaction qui a accordé le café est marquée comme annulée. Si le nombre total de cafés gratuits est plus grand que 0, on retire un café gratuit ; sinon, on ne fait rien. 
2. Il n'y a pas de temps limite pour annuler une transaction, les gérants peuvent annuler n'importe quelle transaction.

## Options écartées
**Diminuer sous 0 le compteur de cafés gratuits**
Nous considérons que l'erreur revient au commerce ; cela n'avait aucun sens de demander au client d'acheter le double de cafés avant d'avoir le prochain.

**Mettre une limite de temps pour annuler une transaction**
Une erreur peut être repérée n'importe quand et son annulation peut être nécessaire dans plusieurs cas, comme un balancement des comptes ; il est donc plus logique de laisser la liberté au gérant d'annuler n'importe quelle transaction. 


## Conséquences
Il faut ajouter une vérification pour éviter que le compteur de cafés gratuits descende sous 0. 
Pour la limite de temps, c'est plus simple à gérer puisqu'il n'y a pas de vérification temporelle à effectuer.
