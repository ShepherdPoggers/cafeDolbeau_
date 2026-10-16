# ADR-0005 — Changement de la règle des cafés gratuits

- **Statut :** Accepté
- **Date :** 2026-10-09
- **Demande concernée :** §3.3

## Contexte
Le patron veut pouvoir changer après combien de cafés un client reçoit un café gratuit. Il faut définir comment traiter les cafés déjà accumulés avant le changement. 

## Décision
La nouvelle règle s'applique aux étampes déjà accumulées. 

## Options écartées
**Appliquer la nouvelle règle après le prochain café gratuit**
Cela impliquerait de conserver un historique des règles dans une table et d'ajouter une colonne dans le client pour référencer la règle. Après un café gratuit accordé à un client, on pointe maintenant vers la règle la plus récente.  

Cela rajoute une complexité inutile, que ce soit par le changement individuel de la règle, la création d'une nouvelle colonne ou d'une nouvelle table pour accommoder les clients qui avaient déjà des cafés accumulés. Aussi, nous considérons que c'est un changement relativement rare. 

## Conséquences
Cela cause des inégalités : par exemple, si la règle passe de 10 à 11 et qu'un client est à son 9e café, il lui en faut 2 de plus pour atteindre son café gratuit. De même, si un client est à son 10e café, il a déjà eu son café et en aura un nouveau au prochain café.
