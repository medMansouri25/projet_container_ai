# LINKING_ENGINE — Mécanisme d'association

> **Dernière mise à jour** : 2026-07-16 · **Statut : cible SPEC_V2 §10 — non implémenté**

## Problème

Les entités d'un même camion sont détectées à des **instants différents** :
conteneur en frame N, plaque en frame N+40, CIN en frame N+110. Le système doit
relier ces fragments dans un **même dossier de passage** (principe P4).

## Cycle de vie du dossier de passage

```
[premier fragment] → Ouvert
Ouvert → EnAttente          (fragments partiels)
EnAttente → EnAttente       (nouveau fragment relié)
EnAttente → Complet         (entités requises présentes)
Complet → Validation → Enregistré | Abandonné
```

**[EXIGENCE]** L'état « association en attente » est obligatoire : un dossier peut
exister incomplet (conteneur détecté avant le scan de la CIN) et être complété plus tard.

## Stratégies de liaison (hypothèses SPEC_V2 à valider)

| Stratégie | Mécanisme | Rôle |
|---|---|---|
| **Par contexte** | fenêtre de temps + emplacement/voie | **propose** l'association automatiquement |
| **Par clé métier** | **N° d'Opération** (agrège déjà conteneur+camion+chauffeur côté Marsa) | **confirme/verrouille** l'association |

⚠️ Le N° d'Opération comme clé officielle est la **question ouverte Q3** (tuteur).

**Risque R3** : deux camions rapprochés confondus par le contexte seul → la clé métier
est le garde-fou ; en son absence, l'ambiguïté est présentée à l'agent (validation humaine).

## Esquisse d'implémentation (pour le moment venu)

- Entité `DossierPassage` avec statut (voir [DOMAIN_MODEL.md](DOMAIN_MODEL.md)) ; chaque
  `Detection` entrante est rattachée au dossier **ouvert** de la voie courante dans la
  fenêtre temporelle, sinon en crée un.
- Paramètres à calibrer : durée de la fenêtre (≈ temps de passage d'un camion), politique
  de fermeture (timeout), règle en cas de conflit (2 conteneurs dans la fenêtre → 2 dossiers, arbitrage humain).
- Le linking vit dans l'**orchestrateur** (invariant I7) — jamais dans un service IA.

## Préfiguration en V1

La V1 est mono-entité (conteneur seul) : chaque scan validé équivaut à un dossier
réduit. Le champ `engine` et les timestamps des scans posent déjà la traçabilité
« Detection → validation » qui sera généralisée.
