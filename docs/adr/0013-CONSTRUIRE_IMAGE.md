# ADR-0013 — Construire localement ou sur le serveur 

- **Statut :** Accepté  
- **Date :** 2026-11-23
- **Demande concernée :** §4.3.1

## Contexte
Nous devons maintenant déployer l'application sur un serveur à l'aide de docker compose. La construction des images peut se faire sur le serveur ou sur notre poste local.

## Décision
Construire l'application localement puis envoyer seulement l'image, le .env et le compose.yaml . 

## Options écartées
Construire l'application sur le serveur. Si une mise à jour est faite, c'est tout le code à chaque fois qui doit être envoyé sur le serveur. On met alors beaucoup trop de choses inutiles.

## Conséquences

Il devient plus simple de faire une mise à jour, il faut seulement envoyer la nouvelle image. C'est aussi moins demandant au serveur qui n'a pas besoin de construire l'image. 
