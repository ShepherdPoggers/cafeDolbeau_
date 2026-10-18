# Migrer les données de la V1 vers la V2

## Conservation des données

Les migrations V1 `0001` à `0008` sont identiques à celles des tags existants, dont `v1.0.0.4`. La V2 applique ensuite les migrations `0009` à `0016` sans supprimer les clients ni recalculer leurs soldes.

Les trois compteurs de `Client` conservent leur forme et leurs valeurs :

| Donnée | Champ conservé |
| --- | --- |
| Achats cumulés servant au calcul des étampes | `nombre_cafes_achetes` |
| Récompenses en réserve | `nombre_cafes_gratuits` |
| Cafés restants sur les cartes prépayées | `nombre_cafes_prepayes` |

Les étampes vers la prochaine récompense correspondent à `nombre_cafes_achetes % seuil`. Le seuil est de 10 en V1 et reste à 10 après les migrations V2. La commande V2 `python src/manage.py balances` affiche ces étampes et les trois compteurs.

Aucune reconstitution des soldes n’est nécessaire. Les informations d’audit absentes de la V1 restent inconnues, comme expliqué dans l’[ADR-0008](adr/0008-MIGRATION_V1.md).

## Mettre à jour une base existante

1. Arrêter le serveur V1 et sauvegarder `src/db.sqlite3` ainsi que le code V1.
2. Avec le code V1 et l’environnement virtuel activé, enregistrer les clients avant la mise à jour :

   ```bash
   python src/manage.py dumpdata CafeDolbeau.Client --indent 2 --output clients-v1.json
   ```

3. Récupérer le code V2 en conservant **le même fichier `src/db.sqlite3`**. Si `CAFE_DB_PATH` est défini en V2, vérifier qu’il désigne cette base.
4. Depuis la racine du dépôt, mettre à jour les dépendances et appliquer les migrations :

   ```bash
   python -m pip install -r requirements.txt
   python src/manage.py migrate
   python src/manage.py check
   python src/manage.py showmigrations
   python src/manage.py balances
   ```

5. Comparer les soldes affichés avec les compteurs enregistrés dans `clients-v1.json`.
6. Avec un superutilisateur existant, attribuer les groupes Barista ou Gérant aux anciens employés. Leurs comptes et mots de passe sont conservés, mais les groupes ne leur sont pas attribués automatiquement.
7. Vérifier l’historique et les accès, puis relancer le serveur.

Sous Windows PowerShell, remplacer `python` par `.\.venv\Scripts\python.exe`. Pour préparer l’environnement virtuel, voir le [README](../README.md#prérequis).

En cas d’échec, restaurer la sauvegarde de la base avec le code V1. Le chargement de données de démonstration ne fait pas partie de la mise à jour d’une base existante.

## Reproduire la vérification avec les données de démonstration V1

Depuis le code V2, préparer l’environnement virtuel et les dépendances selon le README. Exécuter les commandes à la racine du dépôt, dans le même terminal. Le fichier `src/db.sqlite3` doit être absent : le script refuse d’écraser une base existante.

### 1. Créer la base de démonstration V1

```bash
python scripts/donnees_v1.py --database src/db.sqlite3
```

Le script applique uniquement les migrations V1 `0001` à `0008`, charge 6 clients et 12 transactions, puis affiche leurs soldes avant migration. Il crée aussi les comptes de démonstration avec le mot de passe `CafeTest-2026!`, dont le superutilisateur `admin_test`.

Les clients, leurs soldes et leurs transactions sont définis directement dans le script. Ils reprennent le jeu de démonstration validé avec les services du tag V1 `v1.0.0.4`. Le script utilise les modèles historiques V1 pour les créer ; il ne crée pas les colonnes ni les tables V2.

### 2. Migrer normalement vers la V2

```bash
python src/manage.py migrate
python src/manage.py check
python src/manage.py balances
```

Comparer les soldes affichés avec ceux du script : ils doivent être identiques au tableau ci-dessous. Le même fichier `src/db.sqlite3` est conservé et aucune donnée n’est rechargée. Après la migration, utiliser `admin_test` pour attribuer les rôles Barista ou Gérant aux autres comptes.

## Résultat de notre vérification

Essai effectué le 18 octobre 2026 : base créée au schéma V1 avec `scripts/donnees_v1.py`, puis migrations V2 appliquées sur ce même fichier SQLite. Les migrations `0009` à `0016` et `check` ont réussi. Les achats cumulés, récompenses et prépayés sont identiques pour les 6 clients ; les étampes calculées le sont également.

Chaque cellule indique **avant / après** :

| Client | Achats cumulés | Étampes | Récompenses en réserve | Cafés prépayés restants |
| --- | --- | --- | --- | --- |
| Alice Tremblay | 9 / 9 | 9 / 9 | 0 / 0 | 0 / 0 |
| Benoît Gagnon | 12 / 12 | 2 / 2 | 1 / 1 | 0 / 0 |
| Camille Roy | 20 / 20 | 0 / 0 | 0 / 0 | 17 / 17 |
| Dominique Fortin | 17 / 17 | 7 / 7 | 0 / 0 | 10 / 10 |
| Élodie Simard | 33 / 33 | 3 / 3 | 1 / 1 | 10 / 10 |
| Client sans solde | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

Sortie de `balances` après la migration, identique à l’export CSV des mêmes valeurs avant la migration :

```csv
id,client,cafes_achetes,etampes,recompenses_en_reserve,cafes_prepayes
1,Alice Tremblay,9,9,0,0
2,Benoît Gagnon,12,2,1,0
3,Camille Roy,20,0,0,17
4,Dominique Fortin,17,7,0,10
5,Élodie Simard,33,3,1,10
6,Client sans solde,0,0,0,0
```

Les 12 transactions existantes conservent leurs identifiants, clients, types, quantités et dates. Les 5 comptes de démonstration conservent aussi leurs identifiants, mots de passe et états. Le script refuse une seconde exécution sur la même base sans la modifier.

La conservation des soldes et de l’historique a également été vérifiée avec une base créée par le code du tag `v1.0.0.4`. Les fichiers des migrations V1 ont été comparés à ceux des cinq tags V1 : aucune différence.
