# SECURITY — Sécurité et authentification

> **Dernière mise à jour** : 2026-07-16

## État actuel (V1)

### Transport & exposition

| Élément | Mesure |
|---|---|
| Front (Vercel) | HTTPS natif, domaine `containerai-marsa-maroc.online` (+ www, redirection 308) |
| Backend | **Caddy** : TLS automatique Let's Encrypt (émission + renouvellement), reverse proxy → `localhost:5001` |
| Caméra navigateur | `getUserMedia` exige un contexte sécurisé → HTTPS de bout en bout (exigence SPEC §5.3) |
| Flask | jamais exposé directement ; bind 5001 derrière Caddy uniquement |

### Secrets

| Secret | Stockage | Jamais dans |
|---|---|---|
| `DATABASE_URL` (Neon) | `.env` local (gitignoré) + **secret GitHub Actions** → injecté au `docker run` | code, image Docker, dépôt |
| `DOCKER_USERNAME/PASSWORD`, `VPS_SSH_KEY`, `VPS_HOST/PASSWORD` | secrets GitHub Actions | idem |

`.gitignore` couvre aussi : uploads runtime, bilans tuteur (`BILAN_*.md`), datasets.

### Entrées utilisateur

- Upload : extensions whitelistées (`.jpg/.jpeg/.png/.webp/.bmp`), nom de fichier
  régénéré (`uuid4`) — pas de path traversal ; images servies via `send_from_directory`.
- BIC : normalisé (`[A-Z0-9]`, 11 chars max côté UI) avant insertion ; requêtes SQL
  **paramétrées** (psycopg2) — pas d'injection.
- Front : échappement HTML des données affichées (`esc()` dans history/dashboard JS).

### CORS

`Access-Control-Allow-Origin: *` sur `/api/*` et `/uploads/*` — **assumé** en V1 :
API publique en lecture/scan, aucune donnée sensible, pas de cookies/session.
À restreindre au domaine du front dès qu'une authentification existera.

## Limites connues (V1 — assumées)

1. **Pas d'authentification** : quiconque a l'URL peut scanner/confirmer/supprimer.
   Périmètre V1 validé ; question ouverte **Q4** du SPEC (auth des agents).
2. CORS `*` (cf. ci-dessus, lié à l'absence d'auth).
3. Pas de rate-limiting (un scan = plusieurs secondes CPU → DoS facile). À traiter
   avec l'auth (Caddy `rate_limit` ou middleware Flask).
4. SSH VPS par mot de passe possible (la CI utilise une clé) — durcissement
   recommandé : désactiver l'auth par mot de passe.

## Cible (avec SPEC_V2)

- **Authentification agents** (Q4) : sessions ou JWT portés par l'orchestrateur ;
  les services IA restent sans état (l'auth ne les concerne pas — invariant I1).
- Journal d'audit : qui a validé quel dossier (la table `detection` + `validated_at`
  posent la base).
- CORS restreint + rate limiting sur `/api/scan`.
