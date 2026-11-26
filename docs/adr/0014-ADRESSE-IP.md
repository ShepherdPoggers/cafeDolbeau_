# ADR-0014 — Choix du type d'IP attribué

- **Statut :** Accepté  
- **Date :** 2026-11-23
- **Demande concernée :** §4.3.2

## Contexte
Nous devons maintenant déployer l'application sur un serveur. Cette application doit pouvoir être accessible depuis internet. 

## Décision
Nous avons choisi de prendre une ip dynamique.

## Options écartées

Attribuer une IP élastique. Puisque nous allons utiliser un nom de domaine personnalisé pour l'accès au site (*cafedolbeau.monDNS.com*) et le dns attribué par AWS pour la connexion ssh, il devient inutile de payer pour une telle adresse.

## Conséquences
Nous payons seulement pour le DNS shepherdpoggers au lieu de payer pour l'IP élastique en supplément. 
