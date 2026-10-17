# ADR-0004 — Gestion des annulations dans les rapports

- **Statut :** Accepté
- **Date :** 2026-10-09
- **Demande concernée :** §3.2

## Contexte

Il faut définir à quelle période rattacher les annulations dans les rapports.

## Décision

Les transactions sont comptabilisées à leur date de création et les annulations à leur date d’annulation. Les rapports affichent les quantités enregistrées, annulées et nettes, à l’écran comme dans l’export Excel.

## Options écartées

**Rattacher l’annulation à la date de la transaction d’origine :** cela modifierait les résultats d’une période passée et masquerait la chronologie des événements.

## Conséquences

Le détail permet de consulter la date et l’auteur des annulations. Une transaction et son annulation peuvent apparaître dans deux périodes différentes ; le total net d’une période peut donc être négatif.
