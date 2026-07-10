# Bilan de travail — Plateforme de détection d'objets (ProjetMarsa)

**Stagiaire** : Mohamed Mansouri
**Période** : après la phase exploratoire TestYolo
**Dépôt** : https://github.com/medMansouri25/ProjetContainer_AI

---

## 1. Contexte et objectif

La phase TestYolo avait validé la faisabilité : détecter des conteneurs maritimes avec YOLO11m et lire leur matricule par OCR. Ce bilan couvre l'étape suivante : transformer ce prototype en **plateforme générique de détection**, capable d'apprendre *n'importe quelle classe d'objet* (conteneurs, fruits, véhicules...) sans réentraîner de zéro et sans perdre les classes déjà apprises.

L'idée directrice retenue : **le dataset est la mémoire du système, le modèle n'en est qu'une représentation dérivée**. Toute l'architecture découle de ce principe.

## 2. Architecture réalisée : pipeline dataset-centric

Le code ML a été entièrement refondu en **4 fichiers** (au lieu de 7 scripts fragmentés), chacun avec une API Python propre et une CLI :

```
Application/
├── ml/
│   ├── dataset.py    ← gestion des classes, imports, annotation, versioning
│   ├── train.py      ← fine-tuning incrémental
│   ├── evaluate.py   ← évaluation versionnée + comparaisons
│   └── predict.py    ← inférence avec le meilleur modèle
├── dataset/
│   ├── classes.json      ← classes dynamiques {"0":"Conteneur","1":"Fruit"}
│   ├── manifest.json     ← registre de chaque image (classe, validée, split)
│   ├── raw/<Classe>/     ← images brutes par classe, jamais supprimées
│   ├── versions/v1..vN/  ← photographies figées du dataset à chaque entraînement
│   └── current/          ← dernière version (pointée par data.yaml)
├── models/
│   ├── best_v1.pt, best_v2.pt   ← un modèle par version
│   └── metadata.json            ← métriques, hyperparamètres, date, classes
└── reports/run_NNN/             ← rapports par entraînement/évaluation
```

### Principes clés

- **Classes dynamiques** : `dataset.py add-class Voiture` suffit à déclarer une nouvelle classe ; aucun code à modifier.
- **Fine-tuning incrémental** : chaque entraînement repart du dernier `best_vN.pt` (jamais du modèle officiel après v1). Le modèle n'oublie pas les classes existantes quand on en ajoute une.
- **Versioning complet** : chaque entraînement sait exactement sur quelles images il a appris — traçabilité et comparaisons honnêtes entre versions.
- **Annotation au choix à l'import** : `--annotation auto` (bbox pleine image), `sam2` (segmentation SAM2 par point central, class-agnostic donc générique), `manual` (labels fournis).
- **Deux modes d'entraînement** : quotidien (rapide) et périodique avec `--tune` (recherche d'hyperparamètres via `model.tune()`).

### Méthodologie de développement

Tout le code a été développé en **TDD** (Test-Driven Development, cycle red-green-refactor) : chaque fonctionnalité a d'abord été spécifiée par un test (les appels à ultralytics étant mockés à la frontière), implémentée jusqu'au vert, les tests étant ensuite supprimés pour garder le dépôt minimal. Environ 35 tests ont validé le pipeline au fil des missions.

## 3. Datasets constitués

| Source | Images | Contenu | Traitement |
|--------|--------|---------|------------|
| Dataset conteneurs (fourni) | 5025 | conteneurs maritimes annotés | migré vers `raw/Conteneur/` |
| Roboflow fruits n°1 | 150 | Apple/Banana/Grapes | 3 classes fusionnées → `Fruit` |
| Roboflow fruits n°2 | 1102 | 19 classes (cerises, agrumes...) | classes non-fruits (riz, thé, conserves) **filtrées**, reste remappé → `Fruit` |
| Roboflow fruits n°3 | 1309 | pomme, citron, orange, poire, fraise | remappé → `Fruit` |

Total : **7586 images, 2 classes**. Les labels YOLO de chaque source ont été remappés automatiquement vers notre nomenclature (`0=Conteneur, 1=Fruit`).

## 4. Problème identifié puis résolu : le déséquilibre de classes

Le premier entraînement 2 classes (`best_v1`, 20 epochs) a donné sur le split test :

- Conteneur : mAP50 84.7 % — solide
- **Fruit : recall 40.9 %** — le modèle *ratait* 6 fruits sur 10 (avec 150 images seulement)

L'analyse de la matrice de confusion a montré un point important : **0 % de confusion entre classes** (les morphologies sont trop différentes) — le problème était l'*invisibilité* des fruits (détectés comme fond), pas la confusion. Diagnostic : manque de données, aggravé par le déséquilibre 97/3.

## 5. Expérience comparative : deux stratégies d'équilibrage

Deux approches ont été confrontées **expérimentalement** plutôt que débattues :

- **v_A — dataset complet** : entraîner sur toutes les images (avec sur-échantillonnage automatique de la classe minoritaire si nécessaire).
- **v_B — rotation plafonnée** (mon hypothèse) : plafonner à 100 images/classe par entraînement, avec une sélection aléatoire *renouvelée* à chaque entraînement — le modèle voit progressivement tout le dataset sur plusieurs sessions, à coût GPU réduit.

### Protocole scientifique

1. **Benchmark figé** : le split test (1001 images dont ~495 avec fruits) est gravé dans le manifest — aucune de ces images ne retourne jamais à l'entraînement (`create_version()` a été modifié pour garantir cette étanchéité). Toutes les évaluations utilisent ce même jeu.
2. **Même point de départ** : les deux approches partent du même `best_v1.pt`, isolées dans des dossiers d'expérience séparés.
3. **Budget GPU comparable** : v_A = 1 × 40 epochs ; v_B = 3 rotations × 13 epochs en fine-tuning incrémental.
4. **Critère de victoire fixé à l'avance** : recall Fruit > 70 % sans faire tomber Conteneur sous 80 % de mAP50.

### Résultats sur le benchmark

| Modèle | mAP50 | Recall Fruit | Recall Conteneur |
|--------|-------|--------------|------------------|
| Baseline v1 | 70.5 % | 40.9 % | 76.7 % |
| **v_A (complet)** | **90.7 %** | **86.2 %** | **84.8 %** |
| v_B rotation 1 | 71.9 % | 57.8 % | 75.5 % |
| v_B rotation 2 | 73.4 % | 55.4 % | 81.0 % |
| v_B rotation 3 | 77.0 % | 61.4 % | 78.6 % |

### Enseignements

1. **v_A gagne nettement** (+13.7 points sur la meilleure rotation) et remplit le critère de victoire. `best_v2.pt` (issu de v_A) est promu modèle officiel.
2. **La rotation accumule réellement** (71.9 → 77.0 % : pas d'oubli catastrophique total) — l'hypothèse n'était pas fausse — mais trop lentement, et avec une régression de la finesse de localisation (mAP50-95 Conteneur : 65.5 → 55.3 %) : 100 images par rotation ne capturent pas la variance de 3953 conteneurs.
3. **La donnée bat la stratégie** : le facteur dominant du bond de performance est l'ajout de 2411 images de fruits, qui a d'ailleurs rééquilibré naturellement les instances (3953 vs 4882).
4. **La rotation reste pertinente à grande échelle** (des dizaines de classes × 100k images) : l'option `--balance rotate` est conservée dans le code pour ce scénario futur.

Rapport détaillé : `Application/reports/experience-equilibrage.md`.

## 6. Résultat final en conditions réelles

```
[image3.jpg]   ==> C'EST UN CONTENEUR (confiance 85%)
[banane.png]   ==> C'EST UN FRUIT (confiance 78%)
```

Le modèle final `best_v2.pt` : **mAP50 90.7 %, précision 84.2 %, recall 85.5 %** sur 1001 images jamais vues.

## 7. Difficultés rencontrées et résolues

| Problème | Résolution |
|----------|------------|
| Labels initiaux pleine-image (le modèle détectait la présence, pas la position) | diagnostic via prédictions réelles ; datasets ré-annotés proprement |
| Fuite de données potentielle entre versions (re-split aléatoire) | benchmark figé implémenté dans `create_version()` |
| Deadlock du dataloader PyTorch sous Windows (epoch 31/40) | checkpoint de la meilleure epoch récupéré ; `workers` réduit |
| Bug ultralytics `nc=1` (métriques scalaires vs tableaux) | correctif `np.atleast_1d` + test de régression |
| Datasets Roboflow hétérogènes (19 classes, dont non-fruits, noms chinois) | filtrage + remappage automatique des labels |
| Build Docker CI cassé après la refonte | chemins du Dockerfile mis à jour |

## 8. Prochaines étapes

1. **API web** : exposer le pipeline (import, entraînement, prédiction) via le backend Flask existant — architecture cible déjà spécifiée.
2. **Automatisation `import-roboflow`** : une commande unique pour télécharger/filtrer/remapper/importer un dataset Roboflow.
3. **OCR** : reconnecter la lecture de matricule (phase TestYolo) sur les bboxs précises du nouveau modèle.
4. **Entraînement long** (40-60 epochs) et mode `--tune` pour gagner les derniers points de mAP.
