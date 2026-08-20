# Détail partie Labo — historique et guide d'implémentation

> Document technique décrivant, dans l'ordre où elles ont été construites, toutes les
> fonctionnalités du **Labo** (`/labo`) : comparaison de modèles de détection, lecture
> OCR, mode vidéo et source caméra RTSP. Rédigé pour permettre à quelqu'un d'autre de
> reproduire ou reprendre l'implémentation sans avoir suivi le projet au jour le jour.
>
> Fichiers concernés : `Application/backend/labo.py`, `Application/backend/labo.html`,
> `Application/backend/rtsp.py`, `Application/backend/app.py` (routes `/labo` et
> `/api/labo/*`).

---

## 0. Pourquoi le Labo existe

Le pipeline de production (`app.py` historique) appelle un seul modèle de détection et
un seul moteur OCR, sans moyen simple de comparer des alternatives. Dès qu'il a fallu
choisir entre plusieurs modèles entraînés (campagne de benchmark BIC, modèles fournis
par le tuteur, nouveaux détecteurs multi-codes), il est devenu nécessaire d'avoir un
outil séparé qui :

1. **découvre automatiquement** tous les modèles disponibles sur disque (pas de liste
   codée en dur à maintenir),
2. exécute une **inférence sur une image ou une vidéo importée**, sans toucher à la
   base de données ni au flux de validation métier,
3. affiche les résultats **côte à côte** (une carte par modèle) pour comparer visuellement.

Le Labo est donc un outil de **développement/évaluation**, pas un service métier — il
vit à côté de l'application (page `/labo`, endpoints `/api/labo/*`), sans jamais écrire
dans PostgreSQL.

Prérequis d'infrastructure (posé avant le Labo lui-même, cf. `serveLocal.bat`) : le
backend Flask tourne **en local sur un PC avec GPU**, YOLO et EasyOCR chargés sur CUDA.
C'est ce qui rend une inférence à ~0,5 s viable pour un usage interactif, contre 4-25 s
sur le VPS CPU de production. Sans ce socle, comparer des modèles à la volée dans un
labo serait trop lent pour être utile.

---

## 1. Chronologie des ajouts

| Étape | Période | Ce qui a été ajouté |
|---|---|---|
| 1 | 2026-07-29 | Labo v1 : page `/labo`, découverte de modèles, inférence image, une carte par modèle |
| 2 | 2026-08-05 → 08-11 | Modèles du tuteur intégrés (détecteurs + OCR caractère), mode **ensemble** multi-modèles, correction du critère `valid` |
| 3 | 2026-08-12 → 08-13 | Détection **multi-codes** (config11/config14), routage OCR par classe, upscale des petits crops |
| 4 | 2026-08-13 | Mode **vidéo** : échantillonnage 5 FPS, streaming NDJSON, agrégation + déduplication temporelle |
| 5 | 2026-08-17 | Source **caméra RTSP** : aperçu live MJPEG, enregistrement, réinjection dans le pipeline vidéo |

Chaque étape est reprise en détail ci-dessous.

---

## 2. Étape 1 — Labo image : découverte de modèles + inférence

### 2.1 Objectif

Une page où l'on importe une image, on coche un ou plusieurs modèles de détection de
zone BIC, et on obtient pour chacun : les boîtes détectées, le temps d'inférence,
l'image annotée, et en option la lecture OCR de la meilleure zone.

### 2.2 Découverte des modèles — `labo.discover_models(models_root)`

Plutôt que de coder en dur une liste de modèles, la fonction **scanne le disque** à
chaque appel (`Application/models/`) et retourne une liste uniforme :

```python
{"id": "bic/best_v1", "label": "BIC serveur (yolo11s) v1",
 "path": "...", "map50_95": 0.813, "imgsz": 640, "group": "mien"}
```

Trois familles de dossiers sont scannées :

- **`_VERSIONED_DIRS`** : `bic/best_v*.pt` et `bic_browser/best_v*.pt` — modèles
  "officiels", versionnés. Un `metadata.json` à côté donne le mAP50-95 de chaque version.
- **`bic_bench/best_config*.pt`** : sorties de la campagne de benchmark d'hyperparamètres
  (10 configs, voir ADR-13). Même mécanique de `metadata.json`.
- **`multicode/best.pt` et `multicode/best_config14.pt`** : détecteurs multi-codes
  (ajoutés à l'étape 3), listés explicitement car ce sont des noms de fichiers fixes,
  pas un pattern à glober.

**Point important — `imgsz`** : chaque modèle doit être inféré à la **résolution de
son entraînement** (`_train_imgsz`), sinon les performances chutent fortement (un modèle
entraîné à 1280 px et inféré à 640 px est fortement handicapé). Cette résolution est lue
dans `metadata.json` (clé `params.imgsz` ou `hyperparameters.imgsz` selon le schéma) et
stockée avec le modèle, pas redemandée à chaque appel.

### 2.3 Chargement et cache — `_get_model(path)`

Un dict global `_model_cache = {}` évite de recharger un modèle `.pt` à chaque requête
(chargement = plusieurs centaines de ms). Clé = chemin du fichier.

Le chargement tente d'abord **ultralytics** (`YOLO(path)`), avec une **micro-inférence
de validation** sur une image 64×64 noire : certains poids se chargent sans erreur mais
plantent seulement à l'inférence (`forward() got 'embed'`…). Autant échouer ici,
une seule fois, plutôt qu'au premier scan utilisateur.

### 2.4 Inférence — `run_detect(model_path, source, conf, imgsz, annotate=True)`

Fonction unique utilisée par **tous** les modes (image, vidéo). Contrat de sortie :

```python
{"time_ms": 42, "boxes": [{"x":.., "y":.., "w":.., "h":.., "conf":.., "cls":..}, ...],
 "annotated_b64": "<jpeg base64>" | None}
```

`source` accepte soit un **chemin fichier** (mode image), soit directement une **frame
ndarray BGR** (mode vidéo — évite d'écrire chaque frame sur disque). `annotate=False`
saute le rendu de l'image annotée (`plot()` + encodage JPEG), ce qui compte quand on
traite des dizaines de frames par seconde en vidéo.

### 2.5 Endpoint — `POST /api/labo/detect`

- Reçoit `image` (fichier) + `model_id` + `ocr` (0/1) + `ocr_engine`.
- Sauvegarde l'image dans `UPLOAD_FOLDER` sous un nom `labo_<uuid>.jpg`.
- Résout `model_id` en modèle(s) via `discover_models`, lance `run_detect`.
- Retourne : `time_ms`, `boxes`, `annotated` (data-URI), `zones` (une entrée par boîte,
  crop + code lu), `ocr` (liste dédupliquée de codes).

### 2.6 Frontend — page `/labo`

`app.py` sert `labo.html` en statique sur la route `GET /labo` (fichier à côté de
`app.py`, pas dans `frontend/`, car c'est un outil de dev, pas l'app livrée).

`labo.html` (page autonome, JS vanilla, pas de framework) :
- zone de dépôt d'image (`#drop`, drag&drop + `<input type="file">`),
- `loadModels()` : `GET /api/labo/models` → construit la liste de cases à cocher
  (une par modèle, groupées "mien"/"tuteur" avec leur mAP50-95 affiché),
- bouton **Comparer la sélection** → `POST /api/labo/detect` **une fois par modèle
  coché individuellement** (ou en mode ensemble, voir §3.3) → une carte de résultat par
  modèle (`renderCard`) : image annotée, liste des zones, code lu, temps.

---

## 3. Étape 2 — Modèles du tuteur, mode ensemble, correction du critère `valid`

### 3.1 Modèles du tuteur intégrés

Le tuteur a fourni deux familles de poids, placées sous `RessourceFourni/` (hors
`Application/models/`, car ce ne sont pas des modèles entraînés par nous) :

- `RessourceFourni/*/region_models/*.pt` — détecteurs de **zone** BIC alternatifs
  (`ctn_region_archive_best`, `yolo26m_p2_best`, `yolo26m_main_best`, …).
- `RessourceFourni/*/ocr_models/*.pt` — détecteurs de **caractères** (36 classes
  0-9/A-Z), qui lisent chaque caractère indépendamment de son orientation.

`labo.discover_tutor_region_models()` et `labo.discover_ocr_engines()` gobent ces deux
dossiers (`glob` sur `*/region_models/*.pt` et `*/ocr_models/*.pt`, sans dépendre du nom
exact du dossier parent — utile car il contient des caractères accentués).

**Piège technique — double runtime YOLO.** Certains poids du tuteur sont au format
**YOLOv5** (2022-2023), incompatible avec la version d'ultralytics installée pour YOLOv8+.
`_get_model()` retente donc avec le paquet `yolov5` en repli (`_enable_v5()`), qui règle
trois obstacles :
1. `torch >= 2.6` impose `weights_only=True` par défaut ; le code v5 appelle
   `torch.load` sans ce paramètre → on repasse `torch.load` en `weights_only=False`
   globalement (poids locaux fournis par le tuteur, confiance équivalente à un `.pt`
   chargé par ultralytics).
2. Des poids entraînés sous Linux embarquent un `PosixPath` dans leur pickle,
   non instanciable sous Windows → `pathlib.PosixPath = pathlib.WindowsPath`.
3. Une tentative ultralytics échouée laisse des alias dans `sys.modules['models'/'utils']`
   (couche de compatibilité) ; le dépicklage v5 suivant instancierait alors des classes
   ultralytics par erreur → les alias sont **réécrits avant chaque chargement v5**, pas
   seulement au premier.

Les classes `_V5Model` / `_V5Result` / `_V5Box` adaptent l'API v5 (`model(img, size=…)`,
résultat `.xyxy[0]`) à l'interface `.predict()` / `.boxes` attendue par `run_detect()`,
pour que le reste du code ignore complètement quel runtime a chargé le modèle.

### 3.2 Moteur OCR alternatif — détecteur de caractères

Historiquement, la lecture passait uniquement par EasyOCR (`ocr.extract_bic`). Les
modèles du tuteur ajoutent une alternative : un YOLO 36 classes qui détecte et
classe chaque caractère, branché via `char_reader.read_bic(crop, model_path=…)`.
Intérêt : insensible à l'orientation du texte (contrairement à EasyOCR, en échec
systématique sur les codes BIC **verticaux**).

Dans `/api/labo/detect`, le moteur est choisi par `ocr_engine` (`"easyocr"` ou
`"tuteur/ocr/<nom>"`) et **pré-chargé avant la boucle OCR** — un modèle illisible
lèverait sinon une exception au milieu du traitement, que Flask transformerait en page
d'erreur HTML (le front afficherait alors `Unexpected token '<'` au lieu du vrai motif).

### 3.3 Mode ensemble — `run_detect_ensemble(models, image_path, conf, iou_thr)`

Constat mesuré (ADR-14/17) : les modèles disponibles sont **complémentaires, pas
hiérarchisés** — sur un petit échantillon, chaque modèle rate des zones que d'autres
trouvent, sans qu'aucun ne domine systématiquement. `model_id` accepte donc soit un seul
identifiant, soit **plusieurs séparés par des virgules** : chaque modèle tourne, les
boîtes sont fusionnées, puis dédupliquées par recouvrement :

```python
def _iou(a, b): ...          # intersection / union de deux boîtes {x,y,w,h}

def run_detect_ensemble(models, image_path, conf=0.15, iou_thr=0.5):
    # 1. lance run_detect() pour chaque modèle, cumule les boîtes avec `found_by`
    # 2. trie par confiance décroissante
    # 3. garde une boîte seulement si elle ne recouvre pas (IoU > iou_thr) une
    #    boîte déjà gardée de meilleur score
```

C'est cette combinaison (`ctn_region_archive` + `yolov8s_augmented`) qui a fini
**câblée en production** (`capture.js`, hors labo).

### 3.4 Correction du critère `valid` (ADR-16)

Un bug de confiance a été trouvé en observant le Labo sur des photos terrain : quand le
chiffre de contrôle lu ne correspondait pas au calcul, le pipeline le **remplaçait**
silencieusement et renvoyait quand même `valid: True`. Des codes **faux** s'affichaient
donc en vert « valide ». Correction (dans `ocr.py`/`char_reader.py`, réutilisée par le
Labo) : `valid` signifie désormais strictement « le chiffre lu sur l'image est
conforme » ; un chiffre recalculé donne `valid=False, corrected=True`. Le tri des
résultats (`sort(key=lambda o: (not o["valid"], -o["conf"]))`) place les codes
authentiques en premier, quelle que soit la confiance de détection — celle-ci ne
prédit pas la justesse de la lecture.

---

## 4. Étape 3 — Détection multi-codes (config11 / config14)

### 4.1 Pourquoi

Les détecteurs précédents étaient entraînés sur un dataset **un seul code par image**
et échouaient sur les scènes réelles (plusieurs conteneurs empilés). Un nouveau dataset
(`MultiCodeBic`, Roboflow) et deux modèles dédiés ont été entraînés :

- **config11** (`Application/models/multicode/best.pt`) : YOLO11s, imgsz **960**,
  5 classes distinguant numéro/type et orientation horizontale/verticale
  (`Hnumber`, `Hpnumber`, `Htype`, `Vnumber`, `Vtype`).
- **config14** (`Application/models/multicode/best_config14.pt`) : même dataset,
  architecture **tête P2** (`Application/ml/yolo11s-p2.yaml`, stride 4 en plus de
  P3/P4/P5 — dédiée aux très petits objets), imgsz **1280**.

`discover_models()` les liste explicitement (noms de fichiers fixes) plutôt que par glob.

### 4.2 Routage OCR par classe

Avec des classes multiples, certaines zones détectées ne sont **pas des codes BIC** —
`Htype`/`Vtype` correspondent au code taille ISO (`22G1`, `45G1`). Le Labo (et la
production) les **exclut de l'OCR** :

```python
_TYPE_CLASSES = {"Htype", "Vtype"}
...
if do_ocr and cls not in _TYPE_CLASSES:
    ...
```

Un modèle mono-classe (les anciens détecteurs bic/bic_bench) a `cls=""`, jamais dans
`_TYPE_CLASSES` : le filtre ne change rien à leur comportement (rétro-compatibilité).

### 4.3 Agrandissement des petits crops — `_prep_crop(crop)`

Les boîtes multi-codes sont minuscules (médiane 0,51 % de l'image). Avant l'OCR, un
crop dont le petit côté est < 180 px est agrandi (×jusqu'à 3, `cv2.INTER_CUBIC`) :
le détecteur de caractères lit mieux des glyphes plus grands.

### 4.4 `read_zones()` — cœur partagé OCR-par-zone

C'est la fonction pivot, **réutilisée telle quelle par le mode image ET le mode
vidéo** (extraite à l'étape 4 sans changement de comportement) :

```python
def read_zones(img_bgr, boxes, read_fn, do_ocr=True, want_crops=True, max_zones=20):
    # pour chaque boîte (triée par confiance, plafond max_zones=20) :
    #   1. crop avec marge 6%
    #   2. skip OCR si cls dans _TYPE_CLASSES
    #   3. _prep_crop() puis read_fn(crop, vertical=False) puis vertical=True si échec
    #   4. déduplication par code déjà vu (`seen`)
    # retourne (zones, results) — results triés authentiques d'abord (ADR-16)
```

`read_fn` est injecté par l'appelant (`_read` dans `/api/labo/detect`) : c'est ce qui
permet de brancher EasyOCR ou n'importe quel moteur caractère du tuteur sans dupliquer
la boucle.

---

## 5. Étape 4 — Mode vidéo

### 5.1 Objectif et contrainte

Traiter une vidéo importée avec le **même pipeline** que l'image (`run_detect` +
`read_zones`), sans dupliquer de logique, et sans faire tourner YOLO sur chaque frame
(coût prohibitif).

### 5.2 Échantillonnage — `VIDEO_ANALYSIS_FPS = 5`

Quel que soit le FPS d'origine de la vidéo, seules ~5 frames par seconde sont
**décodées et analysées** :

```python
step = max(1, round(orig_fps / VIDEO_ANALYSIS_FPS))   # ex. 30 fps → step=6
...
while True:
    grabbed = cap.grab()          # avance sans décoder — frames sautées = gratuites
    if not grabbed: break
    idx += 1
    if idx % step != 0:
        continue
    ok, frame = cap.retrieve()    # décode SEULEMENT la frame retenue
```

`cap.grab()` avance le curseur sans décompresser l'image ; seul `cap.retrieve()` (appelé
uniquement sur les frames gardées) fait le travail coûteux. C'est ce qui rend
l'échantillonnage réellement économe, pas seulement "on ignore le résultat".

### 5.3 Réponse en streaming — NDJSON

`POST /api/labo/detect-video` retourne un flux `application/x-ndjson` (une ligne JSON
par événement), consommé côté front avec un lecteur de flux (`fetch` + `body.getReader()`).
Trois types de lignes :

1. **`meta`** (une fois, avant traitement) : nom de fichier, durée, fps/résolution
   d'origine, nombre de frames à analyser.
2. **`progress`** (une par frame analysée) : index de frame, `%`, FPS de traitement
   réel, nombre de codes uniques trouvés jusqu'ici — permet une barre de progression
   en direct.
3. **`done`** (une fois, à la fin) : liste finale des codes consolidés.

Générateur Python (`_stream_video_detection` → fonction interne `generate()`) : un
générateur Flask standard, `yield` d'une ligne JSON à la fois, `Response(stream_with_context(...))`.

### 5.4 Agrégation temporelle

Un dict `agg = {bic: {...}}` accumule les lectures au fil des frames. Pour un code déjà
vu : incrémente `count` (nombre de frames/votes), garde la **meilleure** occurrence
(confiance la plus haute, ou passage à `valid=True` si une meilleure lecture authentique
apparaît). Pour un nouveau code : `_best_crop_for()` retrouve, parmi les boîtes de la
frame courante, celle dont l'OCR redonne ce `bic`, pour illustrer le résultat avec un
crop représentatif.

### 5.5 Consolidation floue — `_consolidate_codes(codes, max_diff=3)`

Constat terrain : un **même conteneur physique**, filmé sur plusieurs frames avec flou
de mouvement, produit des lectures OCR légèrement différentes d'une frame à l'autre —
parfois deux variantes valident même **chacune** leur propre chiffre de contrôle
(ex. `MAMU6698882` / `HMMU6698882`). Sans regroupement, un même conteneur apparaîtrait
comme plusieurs "codes" distincts dans le résultat.

Algorithme : chaque code est comparé au **représentant** d'un cluster existant (jamais
de chaînage proche-en-proche, pour ne pas fusionner deux conteneurs réellement
différents) ; "proche" = même longueur et ≤ `max_diff` caractères différents à position
égale. Le représentant du cluster = le meilleur (`authentique > votes > confiance`).
Chaque cluster final expose `candidates` (toutes les variantes lues) et `variants`
(les codes autres que le représentant), pour que l'interface puisse afficher le doute
au lieu de le cacher.

### 5.6 Endpoint — `POST /api/labo/detect-video`

- `_resolve_detector_engine()` (factorisé, partagé avec le mode RTSP) : résout
  `model_id` + `ocr_engine` en `(matches, engine, read_fn)`.
- Source : soit un **fichier uploadé** (`video`, extensions autorisées
  `.mp4/.avi/.mov/.mkv/.webm/.m4v`), soit un **enregistrement RTSP déjà sur le
  serveur** (`recording=<nom>`, voir §6.5) — dans les deux cas, le même générateur
  `_stream_video_detection()` est appelé. Un upload est supprimé après traitement
  (`cleanup=True`) ; un enregistrement RTSP est conservé (`cleanup=False`).

### 5.7 Frontend — onglet Vidéo

`labo.html` : bascule d'onglet (`setMode("video")`) qui affiche `#video-preview` au lieu
de `#preview`, et le bouton `#run-video` au lieu de `#run`. `runVideoAnalysis(fd, modelId)`
lit le flux NDJSON ligne par ligne, met à jour une barre de progression
(`renderVideoProgress`) et affiche la liste finale des codes (`renderVideoCodes`), avec
une case « masquer les lectures incertaines » qui sépare les codes **confirmés**
(authentique OU ≥ 2 frames) des lectures à un seul vote.

---

## 6. Étape 5 — Source caméra RTSP

### 6.1 Principe directeur : RTSP = simple source, pas un nouveau pipeline

Objectif explicite : faire évoluer le Labo vers une caméra de téléphone temps réel
**sans toucher** au pipeline vidéo validé à l'étape 4. Le module `rtsp.py` est donc
**totalement découplé de YOLO/OCR** — son seul rôle est de produire, à partir d'un flux
caméra, soit des frames pour un aperçu live, soit un fichier `.mp4` réinjecté ensuite
dans le pipeline vidéo existant (exactement comme le ferait un upload manuel).

### 6.2 `RtspSession` — connexion et boucle de lecture

```python
class RtspSession:
    def __init__(self, url, recordings_dir): ...
    def open(self) -> (ok: bool, error: str|None)
    def _loop(self)          # thread daemon, tourne jusqu'à close()
    def latest_jpeg(self) -> bytes | None
    def start_recording(self) -> nom_fichier | None
    def stop_recording(self) -> (nom, secondes, frames)
    def status(self) -> dict
    def close(self)
```

**Ouverture bornée par timeout** (`open()`) : `cv2.VideoCapture(url, cv2.CAP_FFMPEG)`
est lancé dans un **thread avec `.join(8.0)`**, pour ne jamais bloquer indéfiniment sur
une URL injoignable. Le code distingue explicitement plusieurs échecs pour retourner un
message utile côté utilisateur : timeout réseau, flux non disponible (adresse/caméra
éteinte), flux ouvert mais aucune image reçue (codec non supporté).

Variables d'environnement FFMPEG posées **avant tout usage d'OpenCV** dans le module :

```python
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;5000000|max_delay;5000000")
```
(transport RTSP forcé en TCP, timeout socket 5 s — évite les flux UDP peu fiables sur
réseau Wi-Fi et les blocages FFMPEG internes.)

**Boucle de lecture** (`_loop`, thread daemon démarré après connexion réussie) : lit en
continu, stocke la dernière frame encodée en JPEG (`_store_frame`, sous verrou), et si
un enregistrement est actif, écrit la frame brute dans le `VideoWriter`. Compteur
d'échecs consécutifs : au-delà de `_READ_FAIL_MAX = 30` lectures ratées, la session se
marque `connected = False` avec une erreur ("connexion au flux perdue"), sans lever
d'exception qui casserait le thread silencieusement.

**Enregistrement** (`start_recording`/`stop_recording`) : `cv2.VideoWriter` avec
fourcc `mp4v`, résolution et FPS détectés à l'ouverture du flux. Fichier nommé
`recording_AAAA-MM-JJ_HH-MM-SS.mp4` dans `Application/backend/recordings/`.

### 6.3 Registre de sessions

Un dict module-level `_sessions = {}` (protégé par un verrou) associe un `session_id`
(uuid court) à chaque `RtspSession` ouverte. Permet de gérer plusieurs connexions en
parallèle et de retrouver une session par son id dans les endpoints suivants.

### 6.4 Endpoints RTSP (`app.py`)

| Route | Rôle |
|---|---|
| `POST /api/labo/rtsp/connect` | `url` (form) → ouvre la session, retourne `{session, connected, resolution, fps, ...}` ou `{error}` (400) |
| `GET /api/labo/rtsp/status/<sid>` | statut courant (connecté, résolution, fps, enregistrement en cours, erreur) |
| `GET /api/labo/rtsp/preview/<sid>` | **flux MJPEG** (`multipart/x-mixed-replace`), ~15 fps, généré en relayant `latest_jpeg()` en boucle avec un `time.sleep(0.06)` |
| `POST /api/labo/rtsp/record/start` | démarre l'écriture `.mp4`, retourne le nom de fichier |
| `POST /api/labo/rtsp/record/stop` | arrête, retourne `{recording, seconds, frames}` |
| `POST /api/labo/rtsp/disconnect` | ferme le thread et libère la session |

**Aperçu live = MJPEG, pas RTSP dans le navigateur.** Le navigateur ne sait pas lire un
flux RTSP nativement ; le serveur agit donc en relais : il lit le RTSP côté Python
(OpenCV/FFMPEG) et ré-expose les frames en `multipart/x-mixed-replace`, affichable
directement dans une balise `<img src="/api/labo/rtsp/preview/<sid>">`. **YOLO/OCR ne
tournent jamais sur ce flux live** — l'aperçu est un simple relais vidéo.

### 6.5 Réinjection dans le pipeline vidéo

C'est le point qui garantit qu'aucune logique n'est dupliquée : `POST
/api/labo/detect-video` accepte, en plus de l'upload classique, un paramètre
`recording=<nom_de_fichier>` qui pointe vers un fichier déjà présent dans
`RECORDINGS_DIR` (produit par `stop_recording`). Dans ce cas, `cleanup=False` (le
fichier reste disponible pour ré-analyse) et **le même générateur
`_stream_video_detection()`** est appelé — au pipeline, un enregistrement RTSP est
indiscernable d'une vidéo uploadée à la main.

### 6.6 Frontend — onglet Caméra RTSP

Troisième onglet de `labo.html` (`setMode("rtsp")`) :
- champ `#rtsp-url` + bouton **Connecter la caméra** → `POST /api/labo/rtsp/connect`,
  affiche le statut puis bascule `#rtsp-img.src` sur l'URL de preview MJPEG,
- boutons **Démarrer/Arrêter l'enregistrement** avec un chronomètre affiché
  (`#rtsp-rec-timer`),
- à l'arrêt de l'enregistrement, le nom de fichier obtenu est réutilisé directement par
  `runVideoAnalysis()` (même fonction que l'upload vidéo), avec `recording=<nom>` au
  lieu d'un `FormData` contenant un fichier.

---

## 7. Pièges et points d'attention pour une reprise

- **Double runtime YOLO (ultralytics + yolov5)** : indispensable pour charger les poids
  du tuteur. Reproduire l'ordre exact des opérations dans `_enable_v5()` (patch
  `torch.load`, alias `PosixPath`, **réécriture des alias `sys.modules` avant chaque
  chargement v5**, pas seulement au premier) — sauter une étape provoque des erreurs
  cryptiques (`fuse() got an unexpected keyword argument 'verbose'`).
- **`imgsz` par modèle** : ne jamais inférer à une résolution différente de
  l'entraînement ; toujours la lire depuis `metadata.json` (`_train_imgsz`).
- **Pré-charger le moteur OCR avant la boucle** (`char_reader._get_model(engine["path"])`)
  pour transformer un modèle illisible en erreur JSON propre plutôt qu'en page HTML
  Flask brute.
- **`cap.grab()` avant `cap.retrieve()`** en vidéo : inverser l'ordre ou décoder toutes
  les frames annule le bénéfice de l'échantillonnage FPS.
- **`_consolidate_codes` compare toujours au représentant du cluster**, jamais de
  proche en proche — un chaînage naïf finirait par fusionner des conteneurs différents
  sur une vidéo longue.
- **RTSP : timeout d'ouverture dans un thread séparé** — `cv2.VideoCapture(url, ...)`
  peut bloquer indéfiniment sur une URL injoignable ; sans le `.join(timeout)`, une
  mauvaise adresse gèlerait la requête Flask.
- **`_TYPE_CLASSES` doit rester synchronisé** avec les noms de classes réels du dataset
  multi-codes (`Htype`/`Vtype`) — un modèle futur avec d'autres noms de classes "non
  code" devra étendre cet ensemble.
- Les fichiers uploadés dans `UPLOAD_FOLDER` pour le Labo (`labo_<uuid>.jpg/.mp4`) ne
  sont **pas** nettoyés pour les images (contrairement aux vidéos, `cleanup=True` par
  défaut) — un nettoyage périodique du dossier `uploads/` reste à prévoir si le volume
  devient un problème.

---

## 8. Fichiers du Labo — carte rapide

| Fichier | Rôle |
|---|---|
| `Application/backend/labo.py` | Découverte de modèles, chargement/cache, inférence (`run_detect`, `run_detect_ensemble`), OCR par zone (`read_zones`) — cœur partagé image/vidéo |
| `Application/backend/rtsp.py` | Source caméra RTSP découplée (connexion, aperçu, enregistrement) — aucune dépendance YOLO/OCR |
| `Application/backend/labo.html` | Page front autonome (3 onglets : Image / Vidéo / Caméra RTSP), JS vanilla |
| `Application/backend/app.py` | Routes `/labo`, `/api/labo/models`, `/api/labo/detect`, `/api/labo/detect-video`, `/api/labo/rtsp/*` ; logique de streaming NDJSON et de consolidation vidéo |
| `Application/models/multicode/best.pt` | Modèle config11 (production multi-codes) |
| `RessourceFourni/ocr_modéle_tuteur/ocr_models/yolov8s_augmented_best.pt` | Meilleur moteur OCR caractère mesuré (ADR-17) |
| `Application/backend/recordings/` | Enregistrements RTSP `.mp4`, réutilisables par le pipeline vidéo |
