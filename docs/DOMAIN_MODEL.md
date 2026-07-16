# DOMAIN_MODEL — Entités métier

> **Dernière mise à jour** : 2026-07-16

## Concepts métier

| Terme | Définition |
|---|---|
| **Code BIC / ISO 6346** | Identifiant de conteneur : 3 lettres propriétaire + catégorie (U/J/Z) + 6 chiffres série + 1 **chiffre de contrôle** (affiché dans une case). Ex. `TLNU 910146 4`. |
| **Chiffre de contrôle** | Calculé depuis les 10 premiers caractères (lettres → valeurs, multiples de 11 sautés, pondération 2^i, mod 11 mod 10). Sert de **preuve mathématique** de lecture et de **code correcteur** (un caractère inconnu est résoluble). |
| **Zone BIC** | Région du marquage sur le conteneur (4 faces, souvent haut-droite, parfois **vertical en caractères empilés**). |
| **Scan** | Passage d'une image dans le pipeline + validation humaine du code. Entité centrale de la V1. |
| **Dossier de passage** | (Cible V2+) Agrégat d'un passage camion : conteneur + plaque + chauffeur + documents, constitué par linking. |
| **N° d'Opération** | Clé métier Marsa candidate pour verrouiller le linking (question ouverte Q3). |

## Modèle actuel (V1)

Une seule entité persistée — le **Scan validé** :

```
Scan
├── id              (serial)
├── bic             (varchar 11, normalisé majuscules)
├── ocr_confidence  (real, nullable)
├── image_path      (text — chemin dans le volume uploads)
└── created_at      (timestamptz)
```

La **validité ISO** n'est pas stockée : elle est recalculée à l'affichage
(`ocr.validate_check_digit`) — le code est la seule vérité, la validité en dérive.

## Modèle cible (SPEC_V2 §12 — hypothèse à valider)

```
DossierPassage (id, statut, source, createdAt, validatedAt, voie)
 ├── 0..1 Camion     (plaque)
 ├── 0..1 Conteneur  (codeISO, dimension)
 ├── 0..1 Chauffeur  (identifiant)
 └── 0..* Document   (type, référence)

Detection (type, valeur, confidence, bbox, timestamp)
```

**Séparation intentionnelle** : l'entité métier (Camion, Conteneur…) porte l'information
**validée** ; la `Detection` porte la **preuve brute** IA, horodatée — support du linking
et de la traçabilité de la validation.

Statuts du dossier : `Ouvert → EnAttente (fragments partiels) → Complet → Validé | Abandonné`.

⚠️ Les champs obligatoires au-delà du code ISO sont une **question ouverte (Q1)** —
les documents Marsa fournis illustrent le métier, ils ne définissent pas le schéma.

## Migration V1 → cible

Le `Scan` actuel correspond à un futur couple `Conteneur + Detection` d'un
`DossierPassage` mono-entité. La table `scans` pourra être migrée telle quelle
(chaque scan = dossier de passage réduit au conteneur).
