# Task — Détection et labellisation d'objets par YOLO

## Objectif

Développer un pipeline complet permettant à l'utilisateur d'importer ou de capturer des images d'un objet, d'entraîner un modèle de détection sur ces images, puis d'obtenir automatiquement le libellé de l'objet entraîné.

---

## Flux attendu

### 1. Input — Collecte d'images *(caméra dans les versions à venir)*

L'utilisateur importe une ou plusieurs images en entrée. Les images sont présentées une à une pour validation manuelle. Seules les images acceptées par l'utilisateur alimentent le dataset.

### 2. Traitement — Entraînement du modèle

Les images validées sont utilisées pour entraîner un modèle YOLO (fine-tuning sur les classes définies). Le pipeline couvre les trois phases standard : entraînement, validation et test. Les métriques sont remontées à l'utilisateur à l'issue de l'entraînement.

### 3. Output — Prédiction et libellé

Une fois le modèle entraîné, l'utilisateur importe une image. Le système retourne le libellé de chaque objet détecté, son score de confiance, et sa localisation dans l'image.

---

## Critère de succès

L'utilisateur peut aller de bout en bout :

**Importer ou capturer des images → Validation manuelle → Entraînement → Prédiction**

et obtenir le libellé correct d'un objet sur lequel le modèle a été entraîné.

---

## Notes

- La capture via caméra est prévue dans une version ultérieure du pipeline.
- Le fine-tuning s'appuie sur un modèle YOLO pré-entraîné (transfer learning).
- Les métriques d'entraînement (mAP, précision, rappel) sont à exposer à l'utilisateur en fin de cycle.
