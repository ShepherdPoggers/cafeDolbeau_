# ADR-0011 — Gestion de la fidélité avec plusieurs succursales

- **Statut :** Accepté  
- **Date :** 2026-11-12
- **Demande concernée :** §3.2.2

## Contexte
Maintenant qu'on a plusieurs succursale, la règle des cafés gratuits nous devons définir commence cette dernière se comportera dans les différents cafés. 

## Décision
Une nouvelle catégorie a été ajouté, les : **promotions temporaires**. Les promotions ont un nombre de cafés à acheté pour avoir un café gratuit, une date de début et une date de fin. Une promotion temporaire peut être appliqué aux succursales souhaités. Les succursales qui partagent une même promotion partagent aussi le compteur, lié à cette promotion, de chaque client. 

## Options écartées
1. Une règle global sans possibilité de la changé de façon individuelle.
    Cette solution ne permet pas de flexibilité. C'est pourtant une pratique courrante de permette aux différentes succursale d'avoir différentes promotions, par exemple, pour inauguré une nouvelle succursale.

2. Chaque café possède sa propre règle modifiable, mais partage les cafés gratuits des clients.
    Cela réduit la rétension des clients puisque leur compteur ne les suit pas partout.

## Conséquences
La solution choisi complexifie la validation dans le code. Elle rajoute une couche supplémentair, le programme doit vérifier si la succursale fait partie d'une promotion, puis, récupérer le bon compteur associé au client. 