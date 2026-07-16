# CLAUDE.md — Instructions permanentes du projet

## TÂCHE PERMANENTE : maintenir `docs/` à jour

À **chaque** changement significatif du projet, mettre à jour le(s) document(s)
concerné(s) dans `docs/` **dans le même travail** (pas « plus tard »), et actualiser
leur ligne « Dernière mise à jour ». Ce n'est pas optionnel.

La documentation doit toujours refléter l'**état réel du code**. Chaque doc distingue
l'« état actuel » (vérifiable dans le code) de la « cible SPEC_V2 » — ne jamais décrire
comme fait ce qui ne l'est pas. Source de vérité de l'intention produit : `SDD/SPEC_V2.md`.

### Quel changement → quel document

| Type de changement | Document(s) à mettre à jour |
|---|---|
| Nouvel endpoint / modification d'API | `docs/API_CONTRACTS.md` |
| Nouveau modèle IA, ré-entraînement, nouvelles métriques | `docs/AI_MODELS.md` |
| Changement du flux de traitement (image/vidéo) | `docs/PIPELINES.md` |
| Nouvelle entité / champ métier ou BDD | `docs/DOMAIN_MODEL.md`, `docs/DATABASE.md` |
| Changement d'architecture / séparation de service | `docs/ARCHITECTURE.md` |
| Déploiement, CI/CD, infra, incident résolu | `docs/DEPLOYMENT.md` |
| Sécurité, auth, CORS | `docs/SECURITY.md` |
| Linking / dossier de passage | `docs/LINKING_ENGINE.md` |
| Avancement de version, nouveau chantier | `docs/ROADMAP.md`, `docs/SPEC.md` (état) |
| **Toute décision structurante** | **nouvel ADR dans `docs/DECISIONS.md`** |

### Règle des ADR

Une décision d'architecture ne se réécrit **jamais** : on ajoute un **nouvel ADR** qui
remplace l'ancien (mentionner « Remplace ADR-N »). L'historique des choix (y compris les
retours en arrière) est précieux — c'est ce que le tuteur veut voir.

### Portée git

- `docs/*.md` (les 12 documents) : **versionnés**, poussés sur GitHub.
- `docs/tasks/`, `docs/handoffs/` (trackers AB Method) : **hors git**, locaux.
- Bilans `BILAN_*.md` : **hors git** (jamais poussés).

## Rappels projet

- Méthode AB obligatoire : grill → tracker → missions TDD (mocks aux frontières, tests
  supprimés après green). Toute bascule moteur/archi = benchmark chiffré sur données réelles.
- Invariants SPEC_V2 §13 : un service IA ne contient jamais de métier ; validation humaine
  obligatoire avant enregistrement ; VPS partagé → scoping strict des ports.
- Commits : messages en français, terminer par `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
