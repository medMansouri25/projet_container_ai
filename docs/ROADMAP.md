# ROADMAP — Évolution du projet

> **Dernière mise à jour** : 2026-09-19

## Trajectoire (SPEC_V2 §4)

```
V1 Image ──► V2 Vidéo caméra ──► V3 Caméra IP RTSP ──► V4 Embarqué
(✅ prod)      (cible actuelle)      (extension capture)    (perspective)
```

**[EXIGENCE]** V1 n'est pas jetable : le pipeline aval (détection → agrégation →
validation → persistance) est commun à toutes les versions. RTSP se conçoit comme
extension **enfichable** de la capture (invariant I10).

## ✅ Réalisé

### Phase ML (juin → 03/07)
- POC TestYolo (YOLO + EasyOCR) → validation de faisabilité
- Architecture dataset-as-memory, benchmark figé, fine-tuning incrémental (ADR-1)
- Expérience équilibrage v_A/v_B → best_v2 90.7 % mAP50 (ADR-2)

### Application web V1 (06/07 → 08/07)
- Scanner BIC complet : upload + caméra → 3 étages → validation → historique + dashboard
- OCR industriel : ISO 6346 (validation/réparation/solveur), vertical empilé, orientation par caractères, anti-faux-positifs (ADR-4)
- Modèle spécialiste zone BIC 99.5 % (ADR-3)
- Production : Vercel + domaine OVH + Caddy + CI durcie + responsive mobile (ADR-5, ADR-7, ADR-8)

### Moteur caractère (10/07)
- Architecture du tuteur reproduite (YOLO 36 classes, 95.75 % mAP50) — intégrée en secours d'EasyOCR après benchmark (ADR-6)

### Hygiène (15-16/07)
- Purge 42 Go d'artefacts régénérables (ADR-9) ; documentation `docs/` structurée

### Labo — multi-code, vidéo, RTSP (20/08 → 18/09)
- Détection multi-code config11 + OCR caractère tuteur augmenté intégrés au Labo (ADR-18)
- **Labo vidéo expérimental** : import vidéo → échantillonnage 5 FPS → pipeline image
  réutilisé tel quel → agrégation/déduplication des codes BIC (ADR-19). Pas de tracking
  d'objet (dédup a posteriori) — écart assumé avec la cible SPEC_V2 §7, voir PIPELINES.md.
- **Labo caméra RTSP** : `rtsp.py`, connexion bornée par timeout, aperçu MJPEG,
  enregistrement `.mp4` réinjecté dans le Labo vidéo (ADR-20). Gestion d'erreur testée
  (URL invalide/injoignable) ; connexion à une vraie caméra **non testée** (pas de
  matériel disponible) — à valider par l'utilisateur.
  Les deux chantiers reconstruits le 18/09 après perte du disque local ayant porté le
  branchement initial (jamais poussé sur GitHub).
- **Extension "BIC Detector" — prototype B→E** (`Application/Extension/`, ADR-21) :
  Manifest V3, popup connecté au backend local (aucun nouvel endpoint), parcours complet
  RTSP → live → enregistrement → analyse → résultats filtrables. Phase E validée avec
  une vraie vidéo (simulant un enregistrement RTSP). Non testé : chargement comme
  vraie extension Chrome, connexion à une caméra réelle (mêmes limites que le Labo RTSP).
- **RTSP validé avec une vraie caméra** (utilisateur, 2026-09-18 soir) : un enregistrement
  réel (378 frames, 60 FPS, 1080×1920) confirme que le Labo fonctionne de bout en bout
  avec du matériel réel — ADR-20/21 partiellement dé-risqués.
- **Copier un code BIC** (Labo + Extension, 2026-09-19) : bouton 📋 à côté de chaque code
  affiché (image, galerie de zones, vidéo, extension), `navigator.clipboard.writeText`.
- **Caméra RTSP dans `capture.html` (app de production)** (ADR-22, 2026-09-19) : 4ᵉ
  source pour la détection client existante (ONNX navigateur), backend local requis
  (contrainte réseau structurelle — VPS ≠ LAN téléphone). Validé : chargement de page,
  panneau RTSP, gestion d'erreur, lecture de pixels cross-origin. Non testé : vraie
  caméra dans cette page précise.
- **`lancer_tout.bat`** : script racine qui démarre le backend local et ouvre Labo +
  application (prod) + dossier de l'extension.

## 🔜 Prochaines étapes (ordre suggéré)

| # | Chantier | Contenu | Dépendances |
|---|---|---|---|
| 1a | **Validation matérielle réelle (extension + capture.html)** | Charger l'extension dans Chrome (`chrome://extensions`) et tester la caméra RTSP de `capture.html`, avec une vraie caméra/téléphone (le Labo, lui, est déjà validé avec du matériel réel) | aucune |
| 1b | **Extension Phase F** | Gestion d'erreurs exhaustive (backend indisponible, session expirée, vidéo invalide…), design final, tests, doc utilisateur | 1a |
| 1c | **V2 vidéo — tracking réel** | `model.track()` (ByteTrack), sélection de frame nette, OCR **unique** par objet suivi (le Labo actuel réexécute l'OCR par frame échantillonnée) | 1a/1b validés |
| 2 | **Extraction service API Container** | sortir le pipeline conteneur en service au contrat SPEC (image→JSON) ; l'app devient orchestrateur | facilite 3-5 |
| 3 | **API Plaque** | détection + lecture plaque (nouveau format marocain) | **Q2 : dataset** |
| 4 | **Linking engine** | dossier de passage multi-entités, fenêtre contextuelle + clé N° d'Opération | **Q3** ; 2-3 |
| 5 | **API Driver / Documents** | CIN/permis ; DUM, booking (manuscrit = saisie manuelle) | **Q1, Q6** |
| 6 | **Authentification agents** | sessions/JWT dans l'orchestrateur, CORS restreint, rate limiting | **Q4** |

## Améliorations continues (non bloquantes)

- Char reader dominant : annoter `datasetEnt` (6289 codes conteneurs) au niveau caractère, ré-entraîner, re-benchmarker (ADR-6)
- Export scans CSV/Excel depuis le dashboard
- Ré-entraînement périodique avec les images confirmées (boucle d'amélioration)
- GPU serveur si besoin de < 2 s/scan (Q5 : objectif chiffré à définir)

## Questions ouvertes bloquantes (tuteur — SPEC_V2 §14)

Q1 champs obligatoires · Q2 dataset plaques · Q3 N° d'Opération · Q4 auth ·
Q5 latence cible · Q6 manuscrit · Q7 intégration SI Marsa
