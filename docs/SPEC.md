# SPEC — Vision globale du projet

> **Dernière mise à jour** : 2026-07-16 · Source de vérité détaillée : [SDD/SPEC_V2.md](../SDD/SPEC_V2.md)

## Vision

**SmartContainer_AI** est une plateforme IA pour **automatiser l'enregistrement des camions** entrant au terminal portuaire (Marsa Maroc, Port de Casablanca). Le système reconnaît automatiquement les informations visibles (conteneur, plaque, chauffeur, documents), les agrège en un **dossier de passage**, les soumet à **validation humaine**, puis les enregistre.

**Principe fondateur** : l'IA **propose**, l'agent humain **dispose**. Aucun enregistrement automatique.

## Principes directeurs (SPEC_V2 §2)

| # | Principe | Énoncé |
|---|----------|--------|
| P1 | Temps réel | Latence minimale — le camion ne reste que quelques secondes |
| P2 | Modularité | Chaque modèle IA = service indépendant, sans logique métier |
| P3 | Orchestration | Une application centrale porte toute la logique métier |
| P4 | Linking | Fragments détectés à des instants différents → même dossier |
| P5 | Validation | Aucune donnée enregistrée sans validation humaine |
| P6 | Évolutivité | Ajouter un modèle IA sans modifier les autres |

## État d'avancement

| Version | Contenu | Statut |
|---------|---------|--------|
| **V1 — Image** | Scanner BIC conteneur : upload/caméra → détection → OCR → validation → historique | ✅ **Déployée en production** (`containerai-marsa-maroc.online`) |
| **V2 — Vidéo** | Flux caméra, tracking, OCR sur frame stable | 🔜 Cible actuelle |
| **V3 — RTSP** | Caméra IP, même pipeline aval | Prévu |
| **V4 — Embarqué** | Autonomie matérielle sur site | Perspective |

### Ce que la V1 réalise aujourd'hui

- Détection du conteneur (YOLO11m fine-tuné, 90.7 % mAP50)
- Localisation de la zone du code BIC (modèle spécialiste, 99.5 % mAP50)
- Lecture OCR (EasyOCR durci + moteur caractère YOLO en secours) avec **validation/réparation ISO 6346** (chiffre de contrôle)
- Validation humaine (correction du code avant enregistrement)
- Historique + dashboard analytique (PostgreSQL Neon)
- Production : front Vercel + backend VPS (Docker + Caddy HTTPS) + CI/CD

### Écart V1 → cible SPEC_V2

- Services IA manquants : **Plaque**, **Driver (CIN/permis)**, **Documents** (DUM, booking…)
- **Linking engine** (dossier de passage multi-entités) : non commencé — voir [LINKING_ENGINE.md](LINKING_ENGINE.md)
- **Vidéo + tracking** : non commencé — voir [PIPELINES.md](PIPELINES.md)
- Authentification agents : hors périmètre V1 (question ouverte Q4)

## Invariants absolus (SPEC_V2 §13 — résumé)

1. Un service IA ne contient jamais de logique métier (image → JSON)
2. Vidéo et image partagent le même pipeline aval
3. Aucun enregistrement sans validation humaine
4. Contrats d'interface stables ; le modèle interne peut évoluer
5. Seul l'orchestrateur coordonne les services IA
6. VPS partagé : scoping strict des ports/ressources

## Questions ouvertes (à trancher avec le tuteur)

Voir SPEC_V2 §14 : champs obligatoires (Q1), dataset plaques marocaines (Q2), N° d'Opération comme clé de linking (Q3), authentification (Q4), objectif chiffré de latence (Q5), manuscrit (Q6), intégration SI Marsa (Q7).

## Index de la documentation

| Document | Contenu |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Architecture logicielle (actuelle + cible) |
| [API_CONTRACTS.md](API_CONTRACTS.md) | Contrats REST |
| [DOMAIN_MODEL.md](DOMAIN_MODEL.md) | Entités métier |
| [PIPELINES.md](PIPELINES.md) | Flux image / vidéo |
| [AI_MODELS.md](AI_MODELS.md) | Modèles IA et métriques |
| [LINKING_ENGINE.md](LINKING_ENGINE.md) | Mécanisme d'association |
| [DATABASE.md](DATABASE.md) | Modèle de données |
| [SECURITY.md](SECURITY.md) | Sécurité |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker, VPS, CI/CD |
| [DECISIONS.md](DECISIONS.md) | ADR — décisions d'architecture |
| [ROADMAP.md](ROADMAP.md) | Évolution du projet |
