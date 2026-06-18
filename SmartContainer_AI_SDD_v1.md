# SmartContainer_AI
## Specification-Driven Development (SDD)
**Version 1.0 — Juin 2026**
Stage DSI — Marsa, Maroc

---

| Champ | Détail |
|---|---|
| **Projet** | SmartContainer_AI |
| **Version** | 1.0 — Version initiale |
| **Date** | Juin 2026 |
| **Auteur** | Stagiaire — Mohammed Mansouri|
| **Encadrant** | Tuteur de stage |
| **Statut** | En attente de validation |

---

## 1. Contexte et objectif du projet

SmartContainer_AI est une application intelligente de gestion et de suivi de conteneurs maritimes. Elle permet la détection automatique des données inscrites sur les conteneurs via une caméra ou une image importée, leur affichage à l'utilisateur pour validation, puis leur enregistrement en base de données.

Ce document constitue la spécification technique de la Version 1 (V1.0) du projet, rédigé dans le cadre d'une approche Specification-Driven Development (SDD). Il a pour objectif de définir précisément le périmètre fonctionnel, l'architecture technique et les spécifications de chaque composant avant le début du développement.

### 1.1 Utilisateurs cibles

L'application est destinée aux **agents portuaires et logisticiens** chargés de l'identification et du suivi des conteneurs maritimes dans leur activité quotidienne.

### 1.2 Problématique

L'identification manuelle des conteneurs est une opération répétitive, lente et sujette aux erreurs humaines. SmartContainer_AI automatise cette étape grâce à l'intelligence artificielle, tout en maintenant une **validation humaine** avant tout enregistrement afin de garantir la fiabilité des données.

---

## 2. Périmètre — Version 1

La Version 1 couvre le cycle complet suivant :

1. Capture d'une image de conteneur via la caméra du navigateur ou import d'un fichier image.
2. Détection automatique du conteneur dans l'image par le modèle YOLOv8.
3. Extraction des données textuelles visibles sur le conteneur par le moteur EasyOCR.
4. Affichage des résultats à l'utilisateur avec possibilité de correction manuelle.
5. Confirmation par l'utilisateur avant enregistrement.
6. Enregistrement des données validées en base de données.

### 2.1 Hors périmètre (Version 1)

Les éléments suivants sont exclus de la Version 1 et feront l'objet de versions ultérieures :

- Prédiction du contenu du conteneur par modèle IA entraîné.
- Application mobile (Flutter ou Kotlin).
- Tableau de bord analytique et reporting.
- Gestion multi-utilisateurs et système de rôles.

---

## 3. Architecture technique

### 3.1 Vue d'ensemble

L'architecture suit un modèle client-serveur avec séparation stricte entre le frontend (navigateur) et le backend (Flask sur VPS). La communication est sécurisée par Cloudflare Tunnel.

| Couche | Composant | Rôle |
|---|---|---|
| **Frontend** | Navigateur web | Interface utilisateur — caméra, affichage, validation |
| **Réseau** | Cloudflare Tunnel | Exposition HTTPS sécurisée — indispensable pour l'accès caméra |
| **Backend** | Flask (Python) | API REST — orchestre la détection et l'enregistrement |
| **IA** | YOLOv8 + EasyOCR | Détection du conteneur et extraction des données textuelles |
| **Infrastructure** | Docker — VPS Contabo | Conteneurisation et hébergement permanent |
| **Base de données** | Neon (PostgreSQL) | Stockage cloud des données validées |

### 3.2 Flux d'une requête

Le flux complet d'une opération de détection se déroule comme suit :

1. L'utilisateur ouvre l'application dans son navigateur et accède à la caméra via l'API `getUserMedia`.
2. Il capture une image du conteneur ou importe un fichier image.
3. Le navigateur envoie l'image au backend Flask via une requête HTTP POST (`fetch API`), transitée par Cloudflare Tunnel en HTTPS.
4. Flask reçoit l'image et la transmet à YOLOv8 pour la détection du conteneur.
5. Les zones détectées sont passées à EasyOCR pour l'extraction du texte.
6. Flask renvoie les résultats en JSON au navigateur.
7. L'interface affiche les données extraites. L'utilisateur peut les corriger.
8. L'utilisateur confirme. Le navigateur envoie une requête de sauvegarde.
9. Flask enregistre les données validées dans Neon (PostgreSQL).

```
Navigateur (caméra + interface)
        │  HTTPS via Cloudflare Tunnel
        ▼
   Flask — API REST
        │
   ┌────┴────┐
   ▼         ▼
YOLOv8    EasyOCR
   └────┬────┘
        │  résultats JSON
        ▼
  Neon (PostgreSQL)
```

---

## 4. Stack technique

### 4.1 Backend

| Technologie | Version | Justification |
|---|---|---|
| **Python** | 3.11+ | Langage principal — écosystème IA riche |
| **Flask** | 3.x | Framework léger pour API REST |
| **YOLOv8** | Ultralytics | Détection d'objets temps réel, pré-entraîné |
| **EasyOCR** | 1.7+ | OCR multilingue basé deep learning |
| **SQLAlchemy** | 2.x | ORM Python pour PostgreSQL |

### 4.2 Frontend

| Technologie | Rôle |
|---|---|
| **HTML5 / CSS3** | Structure et mise en forme de l'interface |
| **JavaScript (ES6+)** | Logique client — capture, fetch, affichage des résultats |
| **getUserMedia API** | Accès natif à la caméra depuis le navigateur |

### 4.3 Infrastructure

| Composant | Détail |
|---|---|
| **VPS Contabo** | Ubuntu 24.04 LTS — 144 Go stockage — IP : 37.60.246.169 |
| **Docker** | Conteneurisation de Flask, YOLO/OCR et cloudflared |
| **Cloudflare Tunnel** | Exposition HTTPS sans ouverture de port — nécessaire pour `getUserMedia` |
| **Neon** | PostgreSQL cloud — plan gratuit — connexion via SQLAlchemy |

---

## 5. Spécifications fonctionnelles

### 5.1 Module de capture d'image

**Description**
L'utilisateur peut fournir une image du conteneur de deux manières : via la caméra en temps réel, ou via l'import d'un fichier image depuis son appareil.

**Comportement attendu**
- Affichage du flux caméra en direct dans l'interface.
- Bouton de capture qui gèle le flux et extrait une image fixe.
- Champ d'import de fichier acceptant les formats JPG, PNG et WEBP.
- Prévisualisation de l'image capturée ou importée avant envoi.
- Bouton d'envoi vers le backend pour analyse.

---

### 5.2 Module de détection IA

**Description**
Le backend reçoit l'image et exécute le pipeline de détection en deux étapes : localisation du conteneur par YOLOv8, puis extraction du texte par EasyOCR.

**Comportement attendu**
- YOLOv8 détecte et localise le conteneur dans l'image (bounding box).
- La zone détectée est recadrée et transmise à EasyOCR.
- EasyOCR extrait les données textuelles visibles sur le conteneur.
- Le résultat est retourné au frontend au format JSON.
- En cas d'échec de détection, un message d'erreur explicite est renvoyé.

---

### 5.3 Module de validation utilisateur

**Description**
Les données extraites sont affichées à l'utilisateur dans un formulaire éditable. Celui-ci peut corriger les informations avant de confirmer l'enregistrement.

**Comportement attendu**
- Affichage des données détectées dans des champs de saisie pré-remplis.
- Possibilité de modifier chaque champ manuellement.
- Bouton « Confirmer » pour valider et enregistrer.
- Bouton « Recommencer » pour relancer une nouvelle capture.
- Aucun enregistrement ne peut être effectué sans confirmation explicite de l'utilisateur.

---

### 5.4 Module d'enregistrement

**Description**
Après confirmation, les données sont persistées dans la base de données Neon (PostgreSQL).

**Comportement attendu**
- Les données validées sont envoyées à Flask via une requête POST.
- Flask les enregistre dans Neon via SQLAlchemy.
- Un message de confirmation est affiché à l'utilisateur en cas de succès.
- Un message d'erreur est affiché en cas d'échec d'enregistrement.

---

## 6. Spécifications API

Flask expose les endpoints suivants :

| Méthode | Endpoint | Entrée | Sortie |
|---|---|---|---|
| `POST` | `/api/detect` | Image (multipart) | JSON : données détectées + score de confiance |
| `POST` | `/api/save` | JSON validé | JSON : confirmation d'enregistrement + ID |
| `GET` | `/api/health` | — | JSON : statut du serveur et des modèles IA |

---

## 7. Schéma de base de données

### Table : `container_scans`

| Champ | Type | Contrainte | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY | Identifiant unique de l'enregistrement |
| `detected_data` | JSONB | NOT NULL | Données extraites par l'OCR (avant correction) |
| `validated_data` | JSONB | NOT NULL | Données validées et confirmées par l'utilisateur |
| `confidence_score` | FLOAT | | Score de confiance retourné par YOLOv8 |
| `image_path` | TEXT | | Chemin ou référence de l'image analysée |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Horodatage de l'enregistrement |

> **Note :** Le champ `detected_data` stocke les données brutes issues de l'OCR, et `validated_data` les données après éventuelle correction par l'utilisateur. Cette séparation permet de mesurer la précision du système dans le temps.

---



## 9. Planning prévisionnel — Version 1

| # | Phase | Tâches principales | Statut |
|---|---|---|---|
| 1 | Recherche préliminaire | YOLO, OCR, Docker, Cloudflare, Transformers | En cours |
| 2 | Configuration infrastructure | VPS, Docker, Cloudflare Tunnel, Neon | À faire |
| 3 | Développement backend | Flask API, intégration YOLO + OCR | À faire |
| 4 | Développement frontend | Interface web, caméra, validation | À faire |
| 5 | Tests et ajustements | Tests end-to-end, corrections | À faire |
| 6 | Perspectives (optionnel) | App mobile ou système embarqué | Optionnel |

---

*Document rédigé dans le cadre du stage — Marsa, Maroc — Juin 2026.*
