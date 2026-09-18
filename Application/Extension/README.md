# BIC Detector — extension navigateur

Interface finale du système de détection de codes BIC (SmartContainer AI) : connexion à
une caméra RTSP (typiquement un téléphone), aperçu live, enregistrement, puis analyse
automatique via le backend Python existant (YOLO + OCR + validation ISO 6346 +
déduplication — **aucune logique dupliquée en JavaScript**).

```
Extension (popup)
   ↓ HTTP (fetch)
services/backend-api.js   ← seul point d'appel réseau
   ↓
Backend Flask local (Application/backend/app.py, http://localhost:5000)
   ↓
rtsp.py (source caméra) → labo.py (YOLO + OCR + validation + dédup, Tasks 1/2)
```

## État d'avancement

| Phase | Contenu | Statut |
|---|---|---|
| B | Structure, `manifest.json`, popup minimal | ✅ |
| C | Connexion backend, `rtspConnect`, aperçu MJPEG live | ✅ |
| D | Démarrer/arrêter l'enregistrement, chronomètre | 🔜 |
| E | Lancer `/api/labo/detect-video`, afficher les codes BIC détectés | 🔜 |
| F | UI/UX finale, gestion d'erreurs exhaustive, tests | 🔜 |

`services/backend-api.js` expose déjà `rtspRecordStart/Stop` et `detectVideo` (Phases D/E)
— écrits maintenant pour fixer le contrat une fois pour toutes, **pas encore appelés**
par `popup.js`.

## Charger l'extension (mode développeur)

1. Lancer le backend local : `python Application\backend\app.py` (voir [README racine](../../README.md))
2. Chrome/Edge/Brave/Opera/Vivaldi → `chrome://extensions` (ou équivalent `edge://extensions`…)
3. Activer le **mode développeur**
4. **Charger l'extension non empaquetée** → sélectionner ce dossier (`Application/Extension/`)
5. Épingler l'icône BIC Detector dans la barre d'outils, cliquer dessus

## Structure

```
Application/Extension/
├── manifest.json            ← Manifest V3
├── icons/                   ← 16/32/48/128px
├── config/default.js        ← BACKEND_URL (http://localhost:5000 par défaut)
├── src/
│   ├── popup/                popup.html / .css / .js — écran principal
│   ├── background/           service-worker.js — MV3, minimal pour l'instant
│   ├── services/              backend-api.js — TOUT appel réseau passe par ici
│   ├── utils/                  status.js — état 🟢🟡🔴⚠️ partagé
│   ├── components/            (réservé — vue résultats, Phase E)
│   └── styles/                tokens.css — palette partagée avec le Labo
```

## Compatibilité navigateurs

Manifest V3, ciblage Chromium en premier (Chrome/Edge/Brave/Opera/Vivaldi — support
natif identique). **Firefox** supporte MV3 mais avec des `background.scripts` (event
page) plutôt qu'un `service_worker` complet : à adapter via `browser_specific_settings`
si Firefox devient une cible, non fait pour ce prototype (Chrome-first).

## Pourquoi aucune logique métier ici

`host_permissions` limite l'extension à `http://localhost:5000/*` et
`http://127.0.0.1:5000/*` — elle ne fait jamais tourner YOLO/OCR, ne lit jamais un flux
`rtsp://` directement (le navigateur ne sait pas le faire), et ne réimplémente aucune
règle de validation ISO 6346. Le backend Flask existant (`Application/backend/`) reste
l'unique moteur de traitement — voir [docs/API_CONTRACTS.md](../../docs/API_CONTRACTS.md).
