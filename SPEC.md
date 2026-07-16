# SmartContainer_AI — Spécification (Spec-Driven Development)

> Document de référence destiné à être consommé par **Claude Code**.
> Il décrit **quoi construire et pourquoi**, pas l'implémentation ligne à ligne.
> Toute décision de code doit rester cohérente avec les invariants listés ici.

---

## 1. Contexte & objectif

Système d'aide à l'**enregistrement et à la vérification des camions** à un point de contrôle du **terminal portuaire (Marsa Maroc, Port de Casablanca)**.

Aujourd'hui, l'enregistrement d'un camion (conteneur + chauffeur + documents) est **saisi manuellement**. L'objectif est un système qui **reconnaît automatiquement** les informations visibles (plaque, code conteneur, identité chauffeur…), les **regroupe en un dossier de passage unique**, les fait **valider par un agent**, puis les enregistre.

Le projet reprend et étend l'existant (détection image + validation manuelle + base de données), sans le jeter.

---

## 2. Roadmap (horizons)

| Phase | Entrée | État |
|---|---|---|
| **Existant (V1)** | Import d'image | Fait / à consolider |
| **Phase actuelle** | Vidéo via caméra téléphone | À construire |
| **Phase suivante** | Caméra IP fixe via **RTSP** (prévoir comme extension) | Prévu |
| **Perspective** | Système embarqué complet autonome | Long terme |

---

## 3. Principe architectural central

Trois piliers structurent tout le système :

1. **Temps réel** — le camion ne s'arrête pas longtemps : la détection doit être rapide, sur flux vidéo, avec une latence maîtrisée (cadence FPS + tracking).
2. **Briques indépendantes exposées en API** — chaque détecteur (plaque, code ISO, CIN…) est un **service autonome**, réutilisable par n'importe quelle application cliente (app web, mobile, extension, système embarqué, app tierce).
3. **Linking (agrégation différée)** — les briques produisent des fragments à des instants différents ; l'application les **regroupe en un dossier de passage unique**.

### Frontière essentielle (à ne jamais violer)

| Couche | Rôle | Contient de la logique métier Marsa ? |
|---|---|---|
| **Services de détection** (API modèles) | `image → info` pur | ❌ NON — génériques, réutilisables |
| **Application orchestratrice** | appelle les API, agrège (linking), valide, enregistre | ✅ OUI — spécifique au métier |

> **Invariant** : aucune logique métier (linking, validation, base de données, notion de « passage ») ne doit vivre dans un service de détection. Un service reçoit une image, renvoie un JSON structuré, point.

---

## 4. Flux logique global

```
   [Mode 1: Flux vidéo]        [Mode 2: Import image]
   (caméra tel / RTSP)          (photo, fichier)
          │                            │
          └─────────────┬──────────────┘
                        ▼
              ┌───────────────────┐
              │  Point d'entrée   │  normalise : vidéo = suite d'images
              │  unifié           │  (gère la cadence FPS + tracking)
              └─────────┬─────────┘
                        │  (envoie des images)
          ┌─────────────┼──────────────┐
          ▼             ▼              ▼
     [SVC plaque]  [SVC code ISO]  [SVC CIN/permis]   ← API indépendantes
          │             │              │
          └─────────────┴──────┬───────┘
                               ▼
                     ┌───────────────────┐
                     │  AGRÉGATEUR       │  linking → dossier de passage
                     └─────────┬─────────┘
                               ▼
                     ┌───────────────────┐
                     │ VALIDATION manuelle│  agent confirme/corrige
                     └─────────┬─────────┘
                               ▼
                        [Enregistrement DB]
```

**Point clé** : une **vidéo est une suite d'images**. Les détecteurs ne connaissent qu'une seule chose : *une image*. Le point d'entrée transforme la source (vidéo ou fichier) en flux d'images ; tout le reste de la chaîne est commun aux deux modes.

---

## 5. Composants

### 5.1 Services de détection (API — réutilisables)

Chaque service est **autonome, sans état, sans métier**. Contrat commun :

- **Entrée** : une image (upload ou base64).
- **Sortie** : JSON `{ résultat, score_de_confiance, bounding_box }`.
- **Indépendance** : déployable/améliorable séparément sans impacter les clients tant que le contrat entrée/sortie ne change pas.

Services prévus :

| Service | Rôle | Sortie attendue |
|---|---|---|
| `svc-plaque` | Détection + lecture plaque camion (dont **nouveau format marocain Casablanca**) | matricule + confiance |
| `svc-container` | Détection conteneur + lecture **code ISO/BIC** (4 lettres + 6 chiffres + 1 clé) | code + validation clé + confiance |
| `svc-driver` | Lecture **CIN ou permis de conduire** | identifiant + confiance |
| `svc-marks` *(optionnel)* | Icônes IMDG / avaries conteneur | labels + confiance |

> Note technique : les zones **manuscrites** de certains documents (n° opération, CIN écrits à la main) ne sont **pas** couvertes par l'OCR standard → prévoir saisie manuelle validée plutôt qu'OCR automatique sur ces zones.

### 5.2 Point d'entrée / capture

- **Mode import image** : reçoit un fichier → une image → détecteurs.
- **Mode vidéo** : reçoit un flux (webcam téléphone, plus tard **RTSP**) → découpe en frames.
- Doit gérer la **cadence (FPS)** et le **tracking** : ne pas lancer l'OCR sur chaque frame, mais détecter/suivre un objet et déclencher la lecture **une seule fois** quand l'image est stable et nette (levier principal de réduction de latence).
- Le support **RTSP** doit être pensé comme une **extension** enfichable, pas comme une réécriture.

### 5.3 Agrégateur (linking)

Regroupe les fragments détectés en un **dossier de passage** unique. Deux stratégies combinées :

- **Par contexte** (temps + emplacement/voie) : propose une association automatique.
- **Par clé métier** (ex. **N° Opération** présent sur les documents Marsa) : confirme/verrouille l'association.

Doit gérer un **état « association en attente »** : ex. un conteneur détecté sans que la CIN chauffeur ait encore été scannée → possibilité de **lier ultérieurement** les deux entités.

### 5.4 Validation manuelle *(cœur de la V1 — invariant)*

- Aucune donnée n'est enregistrée **sans confirmation d'un agent**.
- L'agent voit les résultats détectés (avec confiance), peut **corriger** avant enregistrement.
- Se place **après** l'agrégateur, **avant** l'écriture en base.

### 5.5 Persistance

- Base de données pour les dossiers de passage confirmés.
- Historique consultable.

---

## 6. Entités métier (dossier de passage)

Un **dossier de passage** agrège (champs indicatifs, à préciser avec le tuteur) :

- **Conteneur** : code ISO/BIC, dimension (DIM), P/V, statut manutention
- **Camion** : matricule / plaque
- **Chauffeur** : CIN ou permis
- **Documents** : N° DUM (mainlevée), N° Opération, Booking
- **Transporteur** : raison sociale
- **Méta** : source (image/vidéo), horodatage, voie, scores de confiance, statut (`en_attente` / `validé`)

> Les champs exacts et obligatoires restent à confirmer avec le tuteur (voir §9).

---

## 7. Invariants (règles à ne jamais casser)

1. Un **service de détection ne contient aucune logique métier** ; entrée = image, sortie = JSON.
2. Le **contrat d'API** (entrée/sortie) est stable : on peut changer le modèle derrière sans casser les clients.
3. **Aucun enregistrement sans validation manuelle** d'un agent.
4. **Vidéo et image** partagent le même pipeline aval (via normalisation en images).
5. Sur le **VPS partagé**, ne pas perturber les projets des autres (ports, ressources scopés).
6. Le support **RTSP** est une extension, pas une refonte.

---

## 8. Stack technique (référence)

- **Détection/OCR** : YOLOv11s (Ultralytics) ; OCR à réévaluer pour le temps réel (EasyOCR trop lent en vidéo → envisager PaddleOCR / accélération).
- **Services API** : Python (FastAPI recommandé pour des micro-services de détection).
- **Application/orchestration** : Flask (existant) ou service dédié.
- **Frontend** : HTML/CSS/JS, `getUserMedia` pour la caméra.
- **Base de données** : PostgreSQL (Neon).
- **Infra** : Docker, Contabo VPS (Ubuntu 24.04), Cloudflare Tunnel (HTTPS requis pour l'accès caméra navigateur).
- **CI/CD** : GitHub Actions + Docker Hub.

---

## 9. Questions ouvertes (à trancher avec le tuteur)

- Champs exacts à extraire au-delà du code BIC .
- Clé de linking retenue : N° Opération comme clé métier officielle ? oui
- Authentification agent nécessaire dès cette phase ? non à prévoir et stocker dans les handoff
- Objectif de latence chiffré (FPS cible, délai max par détection) ? on sait pas

---

## 10. Ce que Claude Code doit faire avec ce document

- Traiter ce fichier comme la **source de vérité** de l'intention produit.
- Respecter les **invariants (§7)** dans toute proposition de code.
- Construire de manière **incrémentale** : d'abord consolider le mode image + validation + DB (existant), puis ajouter la couche vidéo, puis le linking, puis RTSP.
- Ne jamais mélanger les couches **détection (générique)** et **application (métier)**.
- Signaler tout point du code qui exigerait de trancher une **question ouverte (§9)** avant d'avancer.
