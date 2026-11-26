# ADR-0011 — Gestion de la fidélité avec plusieurs succursales

- **Statut :** Accepté  
- **Date :** 2026-11-12
- **Demande concernée :** §3.2.2

## Contexte
Maintenant qu'on a plusieurs succursales, la règle des cafés gratuits nous devons définir comment cette dernière se comportera dans les différents cafés. 

## Décision
Une nouvelle catégorie a été ajoutée, les : **promotions temporaires**. Les promotions ont un nombre de cafés à acheter pour avoir un café gratuit, une date de début et une date de fin. Une promotion temporaire peut être appliquée aux succursales souhaitées. Les succursales qui partagent une même promotion partagent aussi le compteur, lié à cette promotion, de chaque client. 

## Options écartées
1. Une règle globale sans possibilité de la changer de façon individuelle.
    Cette solution ne permet pas de flexibilité. C'est pourtant une pratique courante de permettre aux différentes succursales d'avoir différentes promotions, par exemple, pour inaugurer une nouvelle succursale.

2. Chaque café possède sa propre règle modifiable, mais partage les cafés gratuits des clients.
    Cela réduit la rétention des clients puisque leur compteur ne les suit pas partout.

## Conséquences
La solution choisie complexifie la validation dans le code. Elle rajoute une couche supplémentaire, le programme doit vérifier si la succursale fait partie d'une promotion, puis, récupérer le bon compteur associé au client. De plus, pour conserver le bon fonctionnement de la règle des cafés gratuits dans les cafés qui ne font pas partie d'une promotion il faut ajouter un compteur qui fait abstraction des achats sous promotion.