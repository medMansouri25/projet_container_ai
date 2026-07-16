# DEPLOYMENT — Docker, VPS, CI/CD

> **Dernière mise à jour** : 2026-07-16

## Topologie de production

| Composant | Hébergement | URL |
|---|---|---|
| Front statique | **Vercel** (repo GitHub, Root Directory = `frontend`, preset Other) | `containerai-marsa-maroc.online` (+ `www`, 308) |
| Backend + IA | **VPS Contabo** (AMD EPYC, sans GPU) — Docker + Caddy | `api.containerai-marsa-maroc.online` |
| Base | **Neon PostgreSQL** (cloud) | via `DATABASE_URL` |
| DNS | **OVH** : `A @ → 216.198.79.1` (Vercel), `CNAME www → vercel-dns`, `A api → 37.60.246.169` | |

## Image Docker (`Dockerfile`)

- Base `python:3.11-slim` + libs OpenCV (`libgl1`, `libglib2.0-0`)
- **PyTorch CPU** (index `download.pytorch.org/whl/cpu`) — pas de pile CUDA (~6 Go → ~2 Go)
- **Modèles EasyOCR cuits dans l'image** (pas de téléchargement au premier scan)
- Code : `Application/backend/`, `Application/ml/`, `data.yaml`, **tous les modèles** (`Application/models/` : best_v1/v2, bic/, char/)
- `CMD python Application/backend/app.py` (port 5000 interne → 5001 publié)
- Au démarrage : **warmup** (thread) précharge YOLO ×2 + EasyOCR

## CI/CD (`.github/workflows/deploy.yml`)

Déclencheur : push sur `main` — **sauf** `frontend/**`, `api_base.txt`, `**.md`
(le front est redéployé par Vercel directement, ~10 s).

```
build-and-deploy:
  1. docker build + push → Docker Hub mansourimed25/smartcontainer-ai:latest
  2. SSH VPS (set -e : tout échec = CI rouge) :
     git pull /root/stage-med
     docker image prune -af          ← anti « disque plein » (5-6 Go/image)
     docker pull … :latest
     docker rm -f smartcontainer + attente suppression effective
     docker run -d --restart unless-stopped -p 5001:5000
        -e DATABASE_URL=<secret>
        -v /root/smartcontainer_uploads:/app/Application/backend/uploads
     health check : /api/dashboard doit répondre < 2 min sinon exit 1
```

Durée : ~5-10 min. Secrets requis : `DOCKER_USERNAME/PASSWORD`, `VPS_SSH_KEY`, `DATABASE_URL`.

## VPS — services persistants

| Service | Rôle | Survit au reboot |
|---|---|---|
| `docker` (conteneur `smartcontainer`) | app Flask + modèles | ✅ `--restart unless-stopped` |
| `caddy` (systemd) | TLS auto + reverse proxy 443 → 5001 (`/etc/caddy/Caddyfile`) | ✅ |
| volume `/root/smartcontainer_uploads` | images scannées (persistance inter-déploiements) | ✅ |

**VPS partagé (invariant I9)** : ports utilisés par ce projet = 5001, 80/443 (Caddy).
Ne pas toucher aux autres conteneurs (`yolo-*`, `phishing-*`, `flask_projet_*`).

## Pannes connues & leçons (voir aussi [DECISIONS.md](DECISIONS.md))

| Incident | Cause | Correctif en place |
|---|---|---|
| CI verte mais vieux code en prod | disque plein → `docker pull` échouait en silence | `set -e` + prune avant pull + health check post-déploiement |
| Vignettes cassées | uploads dans le conteneur, effacés à chaque déploiement | volume persistant |
| « prune already running » | 2 runs CI simultanés sur le VPS | relancer le run échoué (les runs se suivent normalement) |
| Front « Failed to fetch » | vieux conteneur sans CORS/API | attendre fin CI ; health check l'empêche désormais |

## Procédures

- **Déployer** : `git push origin main` (rien d'autre).
- **Logs prod** : `ssh root@37.60.246.169` puis `docker logs -f smartcontainer`.
- **Rollback** : `docker run` d'un tag/digest précédent depuis Docker Hub (ou revert git + push).
- **Redémarrage VPS** : tout revient seul (Docker + Caddy), ~1-2 min.
