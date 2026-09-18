# DECISIONS — Architecture Decision Records (ADR)

> **Dernière mise à jour** : 2026-09-18
> Format : contexte → décision → conséquences. Une décision n'est modifiée que par un nouvel ADR qui la remplace.

---

## ADR-1 — Dataset-as-memory : le dataset est la source de vérité (2026-07-01)

**Contexte** : scripts ML fragmentés, données et modèles non reproductibles.
**Décision** : architecture dataset-centric — `raw/` (jamais supprimé) → `versions/vN` (snapshots) → `current/` ; modèles versionnés `best_vN.pt` + `metadata.json` ; **benchmark figé** (les images `split: test` ne retournent jamais en train) ; fine-tuning incrémental depuis le dernier best.
**Conséquences** : reproductibilité, comparaisons honnêtes inter-versions, pas de fuite de données. Les snapshots sont volumineux mais **régénérables** (cf. ADR-9).

## ADR-2 — Équilibrage : dataset complet (v_A) bat la rotation par plafonnement (v_B) (2026-07-02)

**Contexte** : déséquilibre 5025 Conteneur / 150 Fruit, recall Fruit 40.9 %.
**Décision** : expérience contrôlée sur benchmark figé — v_A (tout le dataset) vs v_B (rotation cap 100/classe × 3 runs incrémentaux). **v_A gagne : 90.7 % vs 77.0 % mAP50.**
**Conséquences** : à cette échelle, le volume de données prime sur l'échantillonnage malin. La rotation reste codée (`--balance rotate`) pour un futur passage à l'échelle. v_B a aussi démontré l'**oubli catastrophique** → fonde ADR-3.

## ADR-3 — Un modèle spécialiste séparé par tâche, pas des classes empilées (2026-07-07)

**Contexte** : besoin de localiser la zone du code BIC ; fine-tuner best_v2 uniquement sur des images BIC aurait effacé Conteneur/Fruit (démontré par v_B).
**Décision** : modèle **séparé** `models/bic/best_v1.pt` (1 classe, 6289 images dédiées) ; pipeline à 2 modèles (conteneur puis zone).
**Conséquences** : 99.5 % mAP50 sans toucher au modèle principal ; coût = 2 inférences/scan (acceptable) ; mécanique réutilisée pour le modèle char (ADR-6).

## ADR-4 — Le chiffre de contrôle ISO 6346 comme juge de paix de l'OCR (2026-07-06)

**Contexte** : EasyOCR confond des caractères (O/0, I/1…) ; comment savoir si une lecture est bonne ?
**Décision** : toute lecture passe par la validation mathématique ISO 6346 ; normalisation **par position** (4 lettres + 7 chiffres) ; le chiffre de contrôle sert aussi de **code correcteur** (réparation, solveur de caractère unique inconnu) ; un code non validé n'est jamais affiché en vert.
**Conséquences** : quasi-zéro faux positifs présentés comme sûrs ; la logique (`resolve_bic`) est **agnostique du moteur** — réutilisée telle quelle par le lecteur caractère.

## ADR-5 — Front statique Vercel + API VPS, reliés par un vrai domaine (2026-07-08)

**Contexte** : besoin d'une URL publique HTTPS (caméra) ; Vercel ne peut pas héberger le ML (250 Mo vs ~2 Go) ; tunnels gratuits instables et DuckDNS **bloqué par les FAI marocains** (testé).
**Décision** : découplage front (Vercel) / backend IA (VPS) ; domaine OVH `containerai-marsa-maroc.online` ; **Caddy** sur le VPS pour le TLS automatique (remplace le tunnel Cloudflare provisoire).
**Conséquences** : URL fixe professionnelle, zéro maintenance TLS, front rapide mondialement ; nécessite CORS sur l'API (cf. SECURITY).

## ADR-6 — EasyOCR principal, YOLO caractère en secours (2026-07-10)

**Contexte** : architecture du tuteur (OCR-par-détection, 36 classes) reproduite : mAP50 95.75 % sur *son* test. Mais benchmark sur conteneurs réels : EasyOCR 3/3, char 1/3 — le dataset tuteur est ~99 % plaques d'immatriculation.
**Décision** : inverser le plan initial — **EasyOCR reste principal**, le char n'intervient que si EasyOCR ne lit rien ; il ne peut jamais imposer un code (toujours validé ISO).
**Conséquences** : zéro régression, filet supplémentaire, architecture tuteur intégrée et documentée. Bascule possible si un dataset conteneurs-caractère est constitué (annoter `datasetEnt`).
**Remplace** : décision Q1-B du grill (char principal) — invalidée par les chiffres.

## ADR-7 — PyTorch CPU dans l'image Docker ; OpenVINO écarté (2026-07-08 / 2026-07-10)

**Contexte** : VPS sans GPU ; image 6 Go (pile CUDA inutile) ; tuteur suggérait OpenVINO.
**Décision** : wheels torch CPU (image ~2 Go) ; OpenVINO **testé puis écarté** — gain ×1.1 seulement, ses optimisations (AVX-512/VNNI) visent les Xeon Intel or le VPS est **AMD EPYC**. Levier retenu à la place : modèles plus petits (yolo11s pour le char) + warmup + resize entrées + budgets temps OCR.
**Conséquences** : builds/déploiements ~3× plus rapides ; latence scan 4-10 s (net) sur CPU ; le vrai temps réel (<2 s) exigera un GPU (roadmap).

## ADR-8 — CI qui ne peut plus mentir (2026-07-08)

**Contexte** : disque VPS saturé → `docker pull` échouait en silence → CI verte mais vieux code en prod.
**Décision** : `set -e` dans le script SSH, `docker image prune -af` avant chaque pull, **health check** post-déploiement (`/api/dashboard` doit répondre sinon CI rouge), volume persistant pour les uploads.
**Conséquences** : un déploiement vert = code réellement en ligne ; plus de saturation disque.

## ADR-9 — Purge des artefacts régénérables (2026-07-15)

**Contexte** : projet à 74 Go (snapshots 26 Go, current 11 Go, POC, expériences).
**Décision** : supprimer versions/, current/, raw/Fruit, TestYolo (tracké git → récupérable), exp_A/B ; conserver `raw/Conteneur`, `raw/NumeroBIC`, `dataset/char`, `datasetEnt` et **tous les best_*.pt**. `train.py` télécharge sa base automatiquement.
**Conséquences** : −42 Go ; avant un ré-entraînement du modèle principal, régénérer `current/` via `dataset.py version`.

## ADR-11 — Recentrage vision-only + service Plaque marocaine (2026-07-18)

**Contexte** : le SPEC_V2 §8 postulait 4 services IA (Plaque, Container, Driver, Documents) et un linking verrouillé par le **N° d'Opération**. L'analyse du matériel terrain transmis par le tuteur (documents Marsa réels, photos/vidéos au point de contrôle) a montré que les champs Camion/CIN/N° d'Opération sont **manuscrits sur un document papier** — OCR non fiable — et que la seule entité à lecture visuelle fiable est le **conteneur** (chiffre de contrôle ISO, ADR-4). Décision produit du tuteur : **ne pas traiter les documents**, se concentrer sur la détection **immatriculation + code ISO** (icônes IMDG en perspective), **à partir de la vidéo**.
**Décision** :
- Périmètre **vision-only depuis vidéo/webcam** ; services retenus : **Container** (existe) + **Plaque** (construit ici) ; **Driver** et **Documents** abandonnés.
- **Conteneur = ancre** du dossier ; la plaque est un attribut **facultatif**, liable en différé (un conteneur peut être scanné seul au sol). Cardinalité de départ : **1 camion = 1 conteneur**.
- **Pas de moteur de tracking** : capture assistée, l'opérateur vise (repère visuel de distance) ; l'OCR ne se déclenche que sur la frame nette (principe SPEC §7 conservé, déclencheur = humain).
- **Clé de linking N° d'Opération abandonnée** (elle vivait sur le document).
- Service **Plaque** : YOLO11s détection zone (dataset Roboflow *moroccan-dataset*, split 70/20/10 anti-fuite) + EasyOCR arabe/anglais + **validation de forme** `<série>-<lettre>-<région>` (pas de clé de contrôle). Endpoint `POST /api/scan-plaque`.
**Conséquences** : périmètre réduit et réaliste ; le risque bascule sur le **dataset plaque** (chemin critique, Q2) et la **lecture de la lettre arabe** (peu fiable → `?` à saisir, dont la nouvelle série **ط** absente du dataset). Le vrai « temps réel » reste borné par le VPS CPU (ADR-7) → capture assistée plutôt que 30 fps.
**Remplace** : les hypothèses multi-services (Driver/Documents) et la stratégie de linking par clé métier du SPEC_V2 §8/§10.3.

## ADR-10 — Méthode de travail : AB Method + benchmarks avant bascule (transverse)

**Décision** : tout chantier passe par grill (décisions explicites) → tracker → missions TDD (mocks aux frontières ultralytics/easyocr/psycopg2, tests supprimés après green) ; toute bascule de moteur/architecture est décidée par **benchmark chiffré sur données réelles** (cf. ADR-2, ADR-6, ADR-7).

## ADR-19 — Labo vidéo reconstruit sans tracking : dédup a posteriori plutôt que suivi d'objet (2026-09-18)

**Contexte** : le disque local portant l'intégration du Labo (`app.py` branché sur
`labo.py`/`labo.html`, module `rtsp.py`) est tombé en panne — seuls `labo.py`
(cœur détection/OCR) et `labo.html` (front déjà complet, 3 onglets Image/Vidéo/RTSP)
avaient été poussés sur GitHub ; le branchement des routes ne l'avait jamais été. Cette
note documente la reconstruction du pipeline **vidéo** (le RTSP reste à refaire,
prochain chantier).

**Décision** :
- Reconstruction à l'identique du contrat déjà attendu par `labo.html` (`/api/labo/models`,
  `/api/labo/detect`, `/api/labo/detect-video` en NDJSON) plutôt que redesign — le front
  existant contraint et valide l'implémentation.
- **Pas de tracking d'objet** dans cette version : chaque frame échantillonnée à
  `VIDEO_ANALYSIS_FPS=5` est traitée indépendamment par le pipeline image existant
  (`run_detect` + `read_zones`, aucune duplication) ; la déduplication d'un même
  conteneur filmé sur plusieurs frames se fait **après coup** sur les codes lus
  (`_consolidate_codes`, comparaison au représentant du cluster, ≤3 caractères d'écart
  à longueur égale — jamais de chaînage proche-en-proche pour ne pas fusionner deux
  conteneurs différents).
- Modèles pointés explicitement comme « meilleurs » (`Application/models/bestYolo.pt` =
  config11 multi-code, `bestOCR.pt` = OCR caractère tuteur best mesuré ADR-17) exposés
  comme entrées `best/yolo` / `best/ocr` de premier plan dans `/api/labo/models`, en plus
  des entrées déjà découvertes automatiquement (fichiers identiques par contenu).
- Budget EasyOCR réduit à 6 s (`LABO_OCR_TIME_BUDGET`) contre 25 s en production : un
  détecteur multi-code peut remonter jusqu'à 20 zones par frame, x5 frames/s — le budget
  de prod (pensé pour 1 zone par scan) ferait exploser le temps de traitement.

**Conséquences** : validé de bout en bout sur vidéo réelle (matériel tuteur) —
`CAIU6563528` détecté sur 14/34 frames, chiffre de contrôle réparé automatiquement.
Écart assumé avec la cible SPEC_V2 §7 (tracking `model.track()`, une seule lecture par
objet suivi) : le Labo réexécute OCR sur chaque frame échantillonnée, coût acceptable en
outil de dev GPU local, **à corriger avant toute intégration production à fort volume**
(cf. PIPELINES.md). Le RTSP (`rtsp.py`, endpoints `/api/labo/rtsp/*`) reste à
reconstruire ; le front les appelle déjà.
