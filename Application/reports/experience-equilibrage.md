# Expérience Équilibrage Dataset — Rapport Final

**Date** : 2026-07-02 (nuit)
**Question** : pour corriger le déséquilibre de classes (recall Fruit 40.9 % en baseline), vaut-il mieux entraîner sur **tout le dataset** (v_A) ou sur un **sous-ensemble plafonné à 100 images/classe avec rotation** entre entraînements successifs (v_B) ?
**Méthode** : benchmark figé de 1001 images de test (dont ~495 avec fruits) jamais vues à l'entraînement, identique pour toutes les évaluations. Les deux approches partent du même modèle `best_v1.pt` et profitent des mêmes 2411 nouvelles images de fruits (datasets Roboflow 2+3, classes non-fruits filtrées, remappées vers Fruit).

## Résultats sur le benchmark

| Modèle | mAP50 | mAP50-95 | Précision | Recall | R. Conteneur | R. Fruit |
|--------|-------|----------|-----------|--------|--------------|----------|
| Baseline v1 (référence) | 70.5 % | 50.9 % | 74.9 % | 58.8 % | 76.7 % | 40.9 % |
| **v_A — dataset complet** | **90.7 %** | **71.6 %** | **84.2 %** | **85.5 %** | **84.8 %** | **86.2 %** |
| v_B — rotation 1 | 71.9 % | 47.9 % | 71.8 % | 66.7 % | 75.5 % | 57.8 % |
| v_B — rotation 2 | 73.4 % | 50.2 % | 72.9 % | 68.2 % | 81.0 % | 55.4 % |
| v_B — rotation 3 | 77.0 % | 51.9 % | 74.3 % | 70.0 % | 78.6 % | 61.4 % |

Détail par classe (mAP50-95) :

| Modèle | Conteneur | Fruit |
|--------|-----------|-------|
| Baseline v1 | 65.5 % | 36.3 % |
| **v_A** | **70.3 %** | **72.9 %** |
| v_B rot. 3 | 55.3 % | 48.5 % |

## Verdict : v_A gagne nettement

**v_A améliore tout, partout** : +20 points de mAP50 global, recall Fruit de 40.9 % → 86.2 % (objectif >70 % largement dépassé), sans aucune régression Conteneur (84.8 % de recall, mAP50-95 en hausse). Le critère de victoire fixé avant l'expérience est rempli.

**v_B (rotation) : l'hypothèse d'accumulation se vérifie… mais trop lentement.** Le score monte à chaque rotation (71.9 → 73.4 → 77.0), donc le modèle n'oublie pas tout entre les rotations — l'intuition « il voit progressivement tout le dataset » n'est pas fausse. Mais :

1. **Le rythme d'accumulation est faible** : +5.1 points en 3 rotations. Pour rejoindre les 90.7 % de v_A, il faudrait extrapoler ~8-10 rotations supplémentaires — sans garantie de convergence, et en cumulant plus de temps GPU que v_A.
2. **La qualité de localisation régresse** : le mAP50-95 Conteneur passe de 65.5 % (baseline) à 51-55 % dans toutes les rotations. C'est la signature de l'oubli partiel : entraîné sur 100 conteneurs à la fois, le modèle perd en finesse de boîte ce qu'il avait appris sur 3953.
3. **100 images ne capturent pas la variance** : ports, angles, éclairages, types de conteneurs — chaque rotation ne voit qu'un échantillon étroit, et l'apprentissage oscille (recall Fruit : 57.8 → 55.4 → 61.4).

**Coût GPU** (l'argument opérationnel de v_B) : v_A ≈ 2 h (30 epochs × ~4 min sur 5761 images) ; v_B ≈ 35 min d'entraînement total. v_B est bien ~3.5× moins cher — mais livre 13.7 points de mAP50 en moins.

## Ce que l'expérience a aussi montré

- **La donnée bat la stratégie** : le vrai facteur du bond de performance est l'ajout des 2411 images de fruits. Elles ont même rééquilibré naturellement les instances (Conteneur 3953 vs Fruit 4882 en train v3), rendant le sur-échantillonnage initialement prévu pour v_A inutile (facteur de duplication = 1 → v_A est devenu « dataset complet » tout court).
- **Le benchmark figé était indispensable** : sans lui, chaque version aurait re-mélangé le test et aucune de ces comparaisons ne serait valide.
- **La rotation reste pertinente à une autre échelle** : avec 50 classes × 100 000 images, entraîner sur tout à chaque fois deviendrait impossible et le sous-échantillonnage tournant serait nécessaire. À l'échelle actuelle (2 classes, ~8000 images), chaque image compte.

## Recommandations

1. **Adopter v_A** : `Application/models/exp_A/best_v2.pt` devient le modèle de production → à promouvoir comme `models/best_v2.pt` officiel.
2. **Garder `--balance rotate` dans dataset.py** : inutile aujourd'hui, il devient l'outil du passage à l'échelle (>10 classes ou >50k images). Le seuil de bascule pourra être documenté dans un ADR.
3. **Continuer à enrichir les classes faibles en données réelles** plutôt qu'en astuces d'échantillonnage — c'est ce qui a produit +45 points de recall Fruit.
4. **Prochain entraînement : 40-60 epochs** — v_A plafonnait à peine à l'epoch 29-30 ; quelques points restent à prendre.

## Incidents et notes techniques

- **Deadlock dataloader Windows** : l'entraînement v_A s'est figé à l'epoch 31/40 (workers=8 + cache RAM). Le meilleur checkpoint (epoch 29, mAP50 val 86.7 %) a été conservé — les courbes plafonnaient déjà, impact négligeable sur le verdict. `train.py` est passé à `workers=2` en prévention.
- Les artefacts YOLO de v_A sont sous `runs/detect/Application/reports/exp_A/` (chemin relatif interprété par ultralytics) ; les métriques benchmark sous `Application/reports/exp_A/run_002/` et `exp_B/run_002/004/006/`.
- Datasets : v3 = base (benchmark enrichi), v4-v6 = rotations v_B. Modèles : `exp_A/best_v2.pt` (v_A), `exp_B/best_v2..v4.pt` (rotations 1-3).
