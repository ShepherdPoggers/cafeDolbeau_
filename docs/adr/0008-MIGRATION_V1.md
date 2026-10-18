# ADR-0008 — Conserver les soldes de la V1

- **Statut :** Accepté
- **Date :** 2026-10-18

## Contexte

La V2 doit mettre à jour une base V1 sans modifier les soldes des clients.

## Décision

Conserver les trois compteurs de `Client` : achats cumulés, cafés gratuits en réserve et cafés prépayés restants. Les migrations V1 `0001` à `0008` restent intactes ; les migrations suivantes ajoutent les fonctions V2 sans recalculer ces compteurs.

Les soldes ne changent pas de forme et ne nécessitent aucune reconstitution. Les anciens historiques sont conservés. Les nouveaux champs d'audit `employe`, `operation_id` et `variation_*` restent à `NULL` sur les transactions V1 : l'auteur, le regroupement des lignes et la répartition d'une consommation entre crédits gratuits et prépayés ne sont pas connus avec certitude.

## Conséquences

La commande `balances` et la vérification décrite dans [migration.md](../migration.md) permettent de comparer les soldes. L'annulation d'une ancienne opération exige qu'un gérant renseigne les informations manquantes.
