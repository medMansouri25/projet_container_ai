# PIPELINES — Flux Image / Vidéo

> **Dernière mise à jour** : 2026-07-18

## Pipeline image (V1 — implémenté, en production)

```
Image (upload / capture caméra)
  │  _limit_image_size : plafonnée à 1600 px (photos téléphone)
  ▼
[Étage 1] YOLO conteneur (best_v2.pt)          → bbox conteneur, orientation
  ▼
[Étage 2] YOLO zone BIC (bic/best_v1.pt, seuil 0.15)
  │   · zone contrainte DANS le conteneur détecté (anti-voisin)
  │   · marge directionnelle 40 %/15 % (capture la case du chiffre de contrôle)
  │   · si AUCUN conteneur mais zone trouvée → gros plan, lecture directe
  ▼
[Étage 3] Lecture (_extract_bic, app.py)
  │   1. EasyOCR (principal) — pipeline durci :
  │      · _detect_text_orientation : lignes vs colonnes (les caractères, pas la boîte)
  │      · horizontal : variantes (brut/CLAHE/Otsu) × échelles, tri ordre de lecture
  │      · vertical empilé : masque HSV adaptatif → colonnes → OCR caractère/caractère
  │      · budget temps 25 s (zone) / 15 s (repli conteneur entier)
  │   2. YOLO caractères (char/best_v2.pt) — SECOURS si EasyOCR ne lit rien
  ▼
[Validation ISO 6346] resolve_bic (commun aux deux moteurs)
  │   · normalisation par position (O↔0, I↔1…), scoring des candidats
  │   · chiffre de contrôle : validation, réparation, solveur de caractère inconnu
  ▼
Proposition à l'agent (badge lu/recalculé/invalide + champ éditable)
  ▼
Validation humaine → POST /confirm → PostgreSQL          [invariant I3]
```

**Latence mesurée (VPS CPU)** : ~4-10 s horizontal net, ~20-40 s vertical difficile.
Warmup au démarrage du conteneur (modèles préchargés, EasyOCR cuit dans l'image Docker).

## Pipeline plaque (service Plaque — pipeline construit 2026-07-18)

```
Image (upload / capture caméra)
  │  _limit_image_size : plafonnée à 1600 px
  ▼
[Étage 1] YOLO zone plaque (plaque/best_vN.pt)   → bbox plaque + crop
  │   · None si modèle absent (trainImmat.bat non lancé) → found:false
  ▼
[Étage 2] EasyOCR arabe+anglais (pipeline/plaque.py)
  │   · allowlist chiffres + lettres de catégorie ; variantes brut/CLAHE × échelles
  │   · budget temps 12 s
  ▼
[Normalisation format marocain] resolve_plaque
  │   · la lettre arabe sépare série (gauche) / région (droite)
  │   · lettre non lue → '?' (validation de FORME, pas de clé de contrôle)
  ▼
Proposition à l'agent : champ pré-rempli « <série> - <lettre> - <région> »
  ▼
Validation humaine                                        [invariant I3]
```

Miroir du flux BIC mais **sans clé mathématique** : la plaque marocaine n'a pas
de chiffre de contrôle → le juge de paix est la **forme**, plus faible, d'où le
rôle accru de la validation humaine. Entrée `POST /api/scan-plaque`.

## Pipeline vidéo (V2 — cible SPEC_V2 §7, non commencé)

```
Flux vidéo (caméra téléphone, puis RTSP en V3)
  ▼
Normalisation en frames (cadence FPS maîtrisée)
  ▼
Tracking : identifier et SUIVRE chaque objet entre frames
  ▼
Sélection de frame stable/nette par objet suivi
  ▼
── même pipeline aval que l'image (étages 1-3 + validation) ──
```

**[EXIGENCE SPEC]** L'OCR n'est jamais exécuté sur chaque frame : le tracking suit
l'objet, la lecture est déclenchée **une seule fois** sur une frame choisie.
C'est le cœur de la maîtrise de latence (risque R1).

**[EXIGENCE SPEC]** Le pipeline aval est **commun** image/vidéo (invariant I2) —
la couche capture normalise, rien d'autre ne change.

### Briques à construire pour V2

| Brique | Piste technique |
|---|---|
| Capture vidéo web | getUserMedia + envoi de frames échantillonnées |
| Tracking | ByteTrack/BoT-SORT (intégrés à Ultralytics `model.track()`) |
| Sélection de frame | score de netteté (variance du Laplacien) + stabilité bbox |
| Anti-redéclenchement | un objet suivi = une seule lecture (cache par track_id) |
