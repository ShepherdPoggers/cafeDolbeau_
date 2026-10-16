# ADR-0007 — Comment traiter une fusion

- **Statut :** Accepté
- **Date :** 2026-10-10
- **Demande concernée :** §3.5

## Contexte
Un client peut avoir fait deux comptes et veut maintenant les fusionner. Il faut déterminer :
1. Quel identifiant survit.
2. Comment traiter la règle des cafés gratuits.
3. Peut-on revenir en arrière ?

## Décision
1. Lors de la fusion, le gérant choisit quel client prend le dessus sur l'autre.
2. Un client ne peut pas obtenir de café gratuit lors de la fusion.
3. Une fusion est permanente après la première transaction sur le client fusionné.
## Options écartées
**Toute fusion est réversible à tout moment**
Nous avons écarté cette option puisqu'il faudrait conserver dans la base de données l'état de chaque client avant la fusion. 

**Aucun retour en arrière possible**
Nous avons écarté cette option car elle pénalisait trop l'erreur. 

## Conséquences
Si une erreur est faite, elle peut devenir irréversible et, dans ce cas, il faut tout refaire manuellement. Cependant, on économise de l'espace par rapport à un système où on peut revenir en arrière à tout moment. Mais on rajoute une couche de complexité par rapport à un système où aucun retour en arrière n'est possible. C'est un entre-deux. 
