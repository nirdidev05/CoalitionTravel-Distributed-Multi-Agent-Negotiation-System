# I4 : Lyon-Alger, catalogue v2 et référentiel des lieux — rapport de livraison

**Statut :** I4 livrée en entier (I4-A, I4-B et I4-C) et **clôturée le 2026-11-20**, après
reformulation du critère I4-A2, acceptée en revue : voir le §7.2.

**Historique de l'autorisation :**

- **La conception.** Le périmètre `docs/PHASE_I4_SCOPE_REVIEW.md` (révision 1) a été
  livré le 2026-11-20, puis la personne responsable du projet a demandé le « codage
  complet ».
- **La révision 1 n'avait pas encore été revue.** Ses treize décisions proposées
  (D-I4-1 à D-I4-13) ont donc servi de décisions de travail. Les écarts et précisions
  trouvés en codant sont listés au §6, pour être tranchés à la revue.
- **Les trois sous-étapes ont chacune leur section** (§3 à §5), leurs tests, leurs
  mutants et leur diff. Elles peuvent être revues séparément. La copie exacte de l'état
  de fin de chaque sous-étape a été conservée : les diffs par sous-étape ne reposent sur
  aucune reconstruction.

**Aucune opération Git** n'a été faite. Les 18 fichiers personnels n'ont pas été
touchés.

---

## 1. Base de référence (option A)

- **Manifeste :** `docs/PHASE_I4_BASELINE_MANIFEST.sha256`, soit 185 fichiers, avec la
  même règle de sélection qu'en I2 et I3. Son empreinte est
  `39af988953fe6dbc5f05645c1084ce5d2d1d22eef554b8b9cde81d3c05b15212`.
- **Copie complète :** dans le répertoire temporaire de la session. Elle est vérifiée par
  le manifeste : 185 fichiers OK sur 185.
- **La suite était verte sur la base :** `PYTHONHASHSEED=0 python -m pytest -q` donne
  **882 passed**.

---

## 2. Résultat d'ensemble

- **L'exemple de référence, sous forme structurée, produit une proposition
  `trip-proposal-v2` complète.**
  - **La demande :** Lyon → Alger, aller-retour, 2 voyageurs, 500 € par personne, départ
    le 2027-02-15 et retour le 2027-02-25, saisie avec l'alias « Algiers ».
  - **La résolution :** le résumé montre « Alger », et la proposition aussi.
  - **Les offres écartées le sont chacune pour sa raison :** retour trop tardif, aller
    simple, départ de Marseille.
  - **Le statut obtenu est `served_in_coalition` :** bloc de 6 places chez Brisolis,
    économie de 46,17 € pour la demande. Ce statut résulte des données figées : il
    n'était pas fixé d'avance et rien n'a été ajusté pour l'obtenir.
- **La non-régression v1 (K1) est prouvée à trois niveaux :**
  - **les empreintes figées de la base passent sans changement :** `ae759f83…`,
    empreintes P1.3, `admissibility_id`, `formation_run_id` et `result_sha256` du lot
    figé ;
  - **une preuve différentielle :** pour trois demandes v1, le code de la base et le
    nouveau code donnent les mêmes empreintes d'unité, digests économiques, clés de
    requête et clés de consolidation ;
  - **les sorties de la commande sur E3 sont identiques octet pour octet à celles
    d'I3 :** sortie standard et sortie d'erreur, en JSON et en texte, comparées aux
    empreintes relevées à l'essai d'installation d'I3.
- **L'empreinte exploratoire P4** ne peut plus être `997109ee…` avec le code d'I4, par
  construction. Les résultats métier sont identiques sur les 1 740 enregistrements :
  voir le §7.2. L'empreinte de performance `3024fef1…` est reproduite telle quelle.

---

## 3. I4-A : contrats et clés

### 3.1 Fichiers

| Fichier | Changement |
|---|---|
| `application/request_contracts.py` | champs de trajet ajoutés au brouillon et aux profils ; `is_route_request` (D-I4-1) ; `draft_document`, qui ne montre jamais un champ de trajet pour une demande v1 |
| `domain/traveler_profile.py` | fenêtres v2 effectives des profils |
| `domain/travel_unit.py` | `origin_key`, `trip_type` et leurs invariants |
| `application/profiles.py` | héritage des fenêtres v2 ; clé de consolidation conditionnelle (B5) |
| `application/travel_units.py` | origine et type de trajet de l'unité ; empreinte v3 conditionnelle |
| `domain/offer.py` | `OfferLeg` ; champs v2 de `OfferQuote` (`origin`, `outbound`, `return_leg`) ; C1 à C5 comme invariants ; C6 et l'homogénéité dans `OfferCatalog` |
| `domain/negotiation_request.py` | documents v3 conditionnels (`negotiation-request-key-v3`) ; contrôle de route (B11) |
| `domain/places.py` | nouveau : `PlaceDirectory` |
| `tests/test_i4_contracts.py` | nouveau |

### 3.2 Tests

`tests/test_i4_contracts.py` contient 29 tests au moment de la livraison d'I4-A, et 29
aujourd'hui. Deux d'entre eux ont été corrigés en I4-B (§4.3).

| Groupe | Contenu |
|---|---|
| Version d'une demande | un champ de trajet, à n'importe quel niveau, rend la demande v2 ; un document v1 garde exactement ses clés d'I3 |
| K1 | trois demandes v1 : empreintes calculées par le code de la base, figées, et égalées |
| K2 et K7 | chaque champ de trajet change chaque identité ; chaque champ public d'un forfait change la clé ; deux routes ne partagent jamais une clé |
| K3, K4, K5, K6 | casse, espaces, NFD et alias ; champ omis et `null` ; fenêtre héritée et surchargée ; renommage, permutation et découpage ; deux profils aux fenêtres différentes ne sont pas fusionnés |
| K8, K9 | étiquette v3, et document v2 sans champ de trajet ; une unité et une offre de routes différentes ne sont pas négociées |
| K10 | 80 unités tirées au hasard, graine fixe : clé égale si et seulement si document égal |
| Forfaits | aller simple et aller-retour valides ; C1 à C5 refusés, dans les deux cas ; C6 dans un catalogue ; pas de mélange v1 et v2 |
| Unités et lieux | invariants de route ; résolution, alias, collisions refusées |

---

## 4. I4-B : données, catalogue v2 et admissibilité v2

### 4.1 Fichiers

| Fichier | Changement |
|---|---|
| `domain/admissibility.py` | politique `NON_FINANCIAL_V2` et son registre `RULE_ORDER_V2` ; motifs v2 dans une table séparée (`RULE_REASONS_V2`) ; évaluation de route. Le registre v1, `RULE_ORDER` et `RULE_REASONS` sont inchangés |
| `application/lot_admissibility.py` | politique déduite (`None` par défaut) ; K9 |
| `application/request_understanding.py` | champs obligatoires v2 (`REQUIRED_FIELDS_V2`) et règles de validation v2. Le chemin v1 est inchangé |
| `application/trip_planning.py` | `route_key` d'une unité v2 : origine, destination et type de trajet (§6, point 1) |
| `infrastructure/catalog/json_catalog.py` | lecteur v2, choisi par la clé `format`. Le lecteur v1 est inchangé |
| `infrastructure/catalog/places.py` | nouveau : lecteur du référentiel et contrôle croisé avec le catalogue |
| `data/catalog/catalog_v2.json`, `places_v1.json`, `data/demand/demand_pool_v2.jsonl`, avec leurs manifestes | nouveaux (§4.2) |
| `tests/test_i4_catalog_admissibility.py` | nouveau |

### 4.2 Données v2 et règle de calibration

**Les règles d'écriture, fixées d'avance :**

- prix catalogue par place pour le forfait entier ;
- planchers privés à 70 % du prix catalogue ;
- prix par place non croissants avec la taille du groupe ;
- capacités telles que H2 tienne pour la plus grande demande admise (20 places),
  ajoutée au carnet ;
- budgets du carnet de part et d'autre des prix catalogue.

Ces règles sont écrites dans les manifestes.

**Le gel.** Les trois fichiers ont été écrits, puis figés par leur manifeste le
2026-11-20 à 04:57:37, **avant toute planification**. La première exécution qui négocie
sur ces données est un test d'I4-B, postérieur au gel. Aucun fichier n'a été modifié
depuis.

| Fichier | SHA-256 |
|---|---|
| `catalog_v2.json` | `cc5f07797ec2c929f388050fb1dff96a53ba58c9a6671ef73f8d872956697480` |
| `places_v1.json` | `c73912b440ebb7aba7c71e3ade9d18f57c755ec5c189cdc78f0a3b6960eb4828` |
| `demand_pool_v2.jsonl` | `ea17f72788632595bfa1fdf5a5c85f9a07cc45d8e2fd6d63c00c34141ebb3656` |

**Le contenu :**

- **Cinq forfaits, de quatre fournisseurs fictifs :**
  - Lyon → Alger aller-retour direct (Brisolis) ;
  - Lyon → Alger aller-retour avec escale au retour (Calanqua) ;
  - Lyon → Alger aller-retour, retour le 27 février (Orvalis) ;
  - Lyon → Alger aller simple (Veltrane) ;
  - Marseille → Alger aller-retour (Orvalis).
- **Le référentiel :** trois lieux (Alger, Lyon, Marseille) avec leurs alias (Algiers,
  ALG, Argel, LYS, Lyons, Marseilles, MRS).
- **Le carnet :** six demandes, soit quatre Lyon → Alger aller-retour sur les fenêtres
  de référence, une Lyon → Alger aller simple et une Marseille → Alger.

### 4.3 Tests

`tests/test_i4_catalog_admissibility.py` contient 50 tests.

| Groupe | Contenu |
|---|---|
| Données figées | chargement, accord avec le référentiel, carnet ; empreinte du catalogue v1 inchangée |
| C1 à C6 et H-forfait au chargement | 10 refus pour un aller-retour et 6 pour un aller simple, dont : bloc `return` partiel ou `null`, `leg_ref` en minuscules, avec un espace ou un autre séparateur, suffixe de date faux, `leg_ref` partagé entre deux forfaits ou dans un forfait, champ `direct` redondant. Clé `format` inconnue ou absente. Escale à l'aller lue comme non directe (C3) |
| Référentiel | alias ; collision, lieu du catalogue absent, empreinte fausse : refusés ; catalogue qui nomme un lieu par un alias : refusé |
| `NON_FINANCIAL_V2`, un test par règle et par motif | `destination_mismatch` et `origin_mismatch` seuls (court-circuit) ; `trip_type_mismatch` dans les deux sens ; les deux bornes du départ et du retour ; arrivée de l'aller ; offre avant la date de référence ; vol direct exigé (escale sur le retour) et note de préférence ; exclusion de fournisseur ; capacité ; fenêtres par profil |
| Politique et K9 | politique déduite v1 et v2 ; lot mixte, unité v2 face au catalogue v1 et l'inverse, politique contradictoire : refusés ; une seule route par lot |
| Validation v2 | champs obligatoires dans l'ordre ; fenêtre de retour exigée pour un aller-retour ; chaque message v2 au niveau de la demande et des profils ; une fenêtre fixée sur chaque profil suffit ; demandes du carnet valides et aux noms canoniques |

**Deux tests d'I4-A corrigés en I4-B.** La validation v2 rendait incomplets certains
brouillons de K4 et de K10, qui omettaient une borne de retour d'un aller-retour.

- **K4** utilise maintenant un aller simple, dont les champs de retour sont réellement
  facultatifs.
- **K10** ne tire plus de borne de retour nulle.

En corrigeant K5, j'ai trouvé un vrai défaut de règle. Une fenêtre donnée sur chaque
profil, sans fenêtre au niveau de la demande, était déclarée manquante. La règle est
corrigée (§6, point 2).

---

## 5. I4-C : workflow, présentation et commande

### 5.1 Fichiers

| Fichier | Changement |
|---|---|
| `application/trip_proposal.py` | `trip-proposal-v2` : champs v2 facultatifs (`LegView`, origine et type de trajet de l'unité, origine, type et jambes des offres). Un document v1 n'en montre aucun. `request.draft` vient de `draft_document`. `contract_field_names(schema)` |
| `infrastructure/presentation/json_renderer.py` | rendu par `public_fields` ; `trip-request-status-v2`, statut `unknown_place`, domaine E étendu aux messages v2 ; validateur v2 à part, le v1 étant inchangé |
| `infrastructure/presentation/explanations_fr.py` | motifs, champs et questions v2 ; message de lieu inconnu qui liste les lieux connus sans citer la valeur |
| `infrastructure/presentation/text_renderer.py` | résumé v2 (départ, type de trajet, fenêtres) ; offres avec leurs jambes ; message `unknown_place`. Le rendu v1 est identique |
| `infrastructure/presentation/vocabulary.py` | `origin` soumis au contrôle de D-I3-17 |
| `infrastructure/llm/ollama.py` | prompt `travel-request-extraction-v2` (D-I4-12) |
| `Multi-Agent/plan_trip.py` | version de la demande ; résolution des lieux ; lieu inconnu par clarification ou code 2 ; catalogue et carnet choisis après avoir obtenu la demande (D-I4-2) ; documents de statut v2 |
| `data/eval/request_extraction_v3.jsonl` et son manifeste | nouveaux : 8 cas |
| `tests/test_i4_route_cli.py` | nouveau : 15 tests |
| `tests/test_ollama_adapter.py`, `tests/test_trip_proposal.py`, `tests/test_presentation.py` | **modifiés,** une ou deux lignes chacun (§6, point 6) |

### 5.2 Tests

| Groupe | Contenu |
|---|---|
| K1 sur les sorties | E3 par la commande : sortie standard et sortie d'erreur, en JSON et en texte, égales aux empreintes d'I3 ; documents de statut v1 toujours `trip-request-status-v1` |
| Lyon-Alger de bout en bout | proposition v2 complète ; alias résolu ; motifs d'exclusion attendus ; clés fermées ; ni empreinte, ni mot interdit, ni chemin ; sortie identique sur deux exécutions ; résumé v2 |
| Lieu inconnu | par `--draft-json` : code 2, document `unknown_place`, la valeur jamais citée ; par clarification : le lieu est demandé de nouveau, puis résolu ; fin d'entrée : code 2 |
| Documents v2 | champs manquants, fenêtre vide, erreur de pydantic, motif de budget, mot interdit dans `origin`, refus de validation ; 9 documents refusés par le validateur v2 |
| T-CONF en v2 | T-CONF-1 : le budget d'un membre du bloc varie et la proposition, son JSON et son texte restent identiques, alors que les empreintes privées diffèrent ; T-CONF-3 : les noms de champs v2 étendent exactement ceux de v1 |
| Jeu v3 et prompt | `--validate-only` sur le jeu v3 (8 exemples) ; chaque étiquette égale le statut de la validation déterministe ; prompt versionné v2 |

---

## 6. Précisions et écarts à trancher

Chacun de ces points a reçu la solution la plus étroite possible.

1. **`trip_planning.py` est modifié,** alors que le §6 du périmètre le donnait comme
   inchangé. `route_key` ne sélectionnait les demandes du carnet que par destination :
   une demande Marseille → Alger serait entrée dans un lot Lyon → Alger. La docstring
   d'I1 prévoyait déjà qu'I4 y ajoute l'origine et le type de trajet. Pour une unité v1,
   la clé est inchangée.
2. **Une borne de fenêtre fixée sur chaque profil satisfait l'exigence de D-I4-3,**
   même sans valeur au niveau de la demande. Sans cela, une fenêtre propre à un profil
   serait impossible (K5).
3. **Le rendu JSON passe par `public_fields`.** C'est ainsi qu'un document v1 omet les
   champs v2 et que `return_leg` s'écrit `return`.
4. **La version d'un document de statut, quand le brouillon JSON est invalide,** se lit
   sur ses clés : v2 s'il contient un champ de trajet, sinon v1.
5. **Le marché est ouvert juste après l'obtention de la demande,** avant le résumé et
   la question de validation. Cet ordre respecte D-I4-2 et le test I3-A13, qui compte
   les sessions ouvertes avant la validation.
6. **Trois tests existants sont modifiés,** une ou deux lignes chacun ; leur intention
   est conservée :
   - **`test_ollama_adapter.py`** : la version épinglée du prompt passe de v1 à v2,
     conséquence directe de D-I4-12 ;
   - **`test_trip_proposal.py`** : la fonction d'aide `frozen_dump` compare
     `request.draft` à `draft_document` au lieu de `model_dump`. `model_dump` contient
     maintenant les clés de trajet à `null`, que la proposition v1 omet justement pour
     garder ses octets d'I3 ;
   - **`test_presentation.py`** : le cas « schéma inconnu » utilisait
     `trip-request-status-v2`, qui existe désormais ; il utilise
     `trip-request-status-v9`.
7. **Le message d'erreur du DTO** pour un schéma v2 sans route nomme « the v2 schema »,
   ce qui garde intact le test d'I3 qui attend le mot « schema ».
8. **`invalid_request_id` et `route_incomplete`** sont des motifs de `TravelUnitError`
   qu'on ne peut pas atteindre par `plan_lot` : les contrôles d'entrée ou la validation
   les précèdent. Ils restent hors des domaines publics.

---

## 7. Preuves communes

### 7.1 Suite complète et qualité

Environnement : Python 3.14.2 du `.venv`, macOS, arm64. `/opt/homebrew/bin` est dans le
`PATH`, pour que les tests Python 3.10 s'exécutent avec un vrai Python 3.10.

| Exécution | Résultat |
|---|---|
| Base : `PYTHONHASHSEED=0 python -m pytest -q` | **882 passed** |
| Après I4-A | 911 passed |
| Après I4-B | 961 passed |
| `PYTHONHASHSEED=0 python -m pytest -q`, livraison | **976 passed** : 882 tests de la base et 94 nouveaux (29 + 50 + 15), aucun saut |
| `PYTHONHASHSEED=2 python -m pytest -q`, livraison | **976 passed** |
| Python 3.10, grammaire | le contrôle de grammaire 3.10 couvre les fichiers nouveaux et modifiés ; il passe. Ce contrôle est **syntaxique** : il ne vaut pas exécution de la suite sous 3.10 |
| Python 3.10, suite complète (ajout du 2026-11-20) | **anomalie ouverte, non validée :** 972 passed et 4 failed. Voir `docs/FINAL_PROJECT_AUDIT.md`, §5 |
| `ruff check` et `ruff format --check` sur les 27 fichiers Python créés ou modifiés | All checks passed ; 27 already formatted |
| `git diff --check` | propre |
| Mutants d'I3 rejoués contre le code d'I4 | I3-A : 16 sur 16 tués ; I3-B et I3-C : 15 sur 15. La ligne visée par le mutant 8 a dû être mise à jour, parce que `not_validated_document` reçoit maintenant le paramètre `schema` |
| Golden master, tests de `process_travel_request` | inclus dans la suite, inchangés, verts |

### 7.2 Les empreintes P4

*Section réécrite le 2026-11-20. Le texte initial disait « En cours au moment de ce
commit ».*

**Le constat.** Régénérée avec le code d'I4, la strate exploratoire ne donne plus la
référence historique.

| Exécution (`evaluate_formation.py exploratory`, `PYTHONHASHSEED=0`) | SHA-256 de `results.json` |
|---|---|
| Référence historique (`docs/p4_results/README.md`) | `997109eee5a9ee4c6567410066730e2f8b5c8dd01bd46ff958b586f4c33eced4` |
| Code de la base d'I4 (copie vérifiée par le manifeste), régénéré le 2026-11-20 | `997109eee5a9ee4c6567410066730e2f8b5c8dd01bd46ff958b586f4c33eced4` : identique |
| Code d'I4, régénéré le 2026-11-20 | `8988a1be89bf22ec7d5ea34dee1181088f93df6d5a71f24c37dfc1e4dd6eae2a` |

**La cause est démontrée dans le code.** C'est une chaîne de dépendances voulue :

```
code_sha256  →  oracle_configuration_id  →  formation_run_id  →  result_sha256
```

- `code_sha256` (`simulated_oracle._agent_source_hashes`) hache les octets source de
  12 modules. Quatre d'entre eux sont modifiés par I4 : `domain/negotiation_request.py`,
  `domain/offer.py`, `domain/travel_unit.py` et
  `infrastructure/catalog/json_catalog.py`.
- `oracle_configuration_id` contient `code_sha256`.
- `formation_run_id` (`coalition_formation`) hache `oracle_configuration_id`.
- `result_sha256` hache `formation_run_id`.

Toute modification de l'un de ces 12 modules change donc l'empreinte, quels que soient
les résultats calculés. La demande du périmètre (K1 : « reproduire `997109ee…` ») ne
pouvait pas tenir une fois ces fichiers modifiés.

**La preuve d'équivalence.** Les deux `results.json` ont été comparés champ par champ :

- 1 740 enregistrements de chaque côté ;
- **seuls deux champs diffèrent, `formation_run_id` et `result_sha256`,** dans 1 720
  enregistrements. Les 20 autres sont au statut `capacity_model_violated` : sans
  formation, ils ne portent pas ces champs ;
- tous les autres champs sont identiques dans les 1 740 enregistrements : coûts,
  références, économies, décomposition, coalitions, tailles, compteurs d'oracle et de
  cache, statuts, baselines et tableaux ;
- `report.md` est identique octet pour octet entre les deux exécutions, et à
  `docs/p4_results/exploratory_report.md`.

**Le critère I4-A2 est reformulé.** La revue a accepté cette reformulation le
2026-11-20 :

> I4-A2 : sur la strate exploratoire, les résultats métier du code d'I4 sont identiques
> à ceux du code de la base. La comparaison porte sur tous les champs, sauf les deux
> champs de provenance `formation_run_id` et `result_sha256`. Le rapport Markdown est
> identique octet pour octet.

- `997109eee5a9ee4c6567410066730e2f8b5c8dd01bd46ff958b586f4c33eced4` reste la
  référence historique. Elle n'est pas modifiée.
- `8988a1be89bf22ec7d5ea34dee1181088f93df6d5a71f24c37dfc1e4dd6eae2a` est l'empreinte
  propre au code d'I4.
- Le code de P4 et le mécanisme d'empreinte ne sont pas modifiés.

**L'empreinte de performance, vérifiée séparément.** La décision n'a pas été transposée
d'office. La strate `performance` a été régénérée avec les deux codes :

| Exécution | SHA-256 de `results.json` |
|---|---|
| Référence historique | `3024fef1187ece03e97c4da3391b2bb9e7c458f8346fad007402dc29310b0b85` |
| Code de la base | `3024fef1187ece03e97c4da3391b2bb9e7c458f8346fad007402dc29310b0b85` |
| Code d'I4 | `3024fef1187ece03e97c4da3391b2bb9e7c458f8346fad007402dc29310b0b85` |

Cette strate est reproduite telle quelle, avec 0 champ différent sur 60 enregistrements.
Ses enregistrements ne contiennent ni `formation_run_id` ni `result_sha256`. La
reformulation ne s'y applique pas.

**Commandes.** Dans une copie de la base, puis à la racine du dépôt :

```
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=Multi-Agent \
  python Multi-Agent/evaluate_formation.py exploratory --output <répertoire temporaire>
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=Multi-Agent \
  python Multi-Agent/evaluate_formation.py performance --output <répertoire temporaire>
```

Les `results.json` ne sont pas versionnés : les catalogues générés contiennent des
termes vendeurs privés (voir `docs/p4_results/README.md`).

### 7.3 Mutants

Chaque mutant est réintroduit seul, dans une copie de travail hors du dépôt. Sont
exécutés, avec `-x` :

- les trois fichiers de tests d'I4 ;
- deux fichiers d'I3, `test_trip_proposal.py` et `test_presentation.py` ;
- trois fichiers de la base : clés de requête, unités, formation.

**20 mutants sur 20 sont tués.**

| # | Mutant | Premier test qui échoue |
|---|---|---|
| A1 | fenêtres de trajet dans toute unité (les clés v1 changent) | K1 différentiel (E3) |
| A2 | origine absente du document d'unité | K2 (origine) |
| A3 | clé de consolidation sans fenêtres | K2 (`departure_before`) |
| A4 | C2 non contrôlé | C1 à C5 |
| A5 | suffixe de date C5 non contrôlé | C1 à C5 |
| A6 | C6 non contrôlé dans le catalogue | C6 |
| A7 | pas de contrôle de route avant une négociation | K9 (clés) |
| A8 | collisions d'orthographes admises | référentiel invalide |
| B1 | pas de court-circuit sur un écart de route | écart de route seul |
| B2 | borne haute du départ ignorée | fenêtre de départ |
| B3 | fenêtre de retour jamais contrôlée | fenêtre de retour |
| B4 | lot mixte accepté (K9) | K9 |
| B5 | fenêtre de retour non exigée pour un aller-retour | champs obligatoires v2 |
| B6 | bloc `return` invalide lu comme un aller simple | bloc `return` nul |
| B7 | route du lot sans origine | une route par lot |
| C1 | brouillon v1 avec les clés de trajet | document v1 |
| C2 | lieux non résolus par la commande | Lyon-Alger de bout en bout |
| C3 | documents de statut v2 émis en v1 | documents v2 par la commande |
| C4 | catalogue v1 toujours ouvert | Lyon-Alger de bout en bout |
| C5 | lieux connus non triés acceptés | validateur v2, cas négatifs |

### 7.4 Base, diffs et manifeste

- **Manifeste.** 163 fichiers de la base sont OK sur 185. Les 22 fichiers modifiés sont
  ceux des §3 à §5 : 19 fichiers de code et 3 fichiers de tests existants.
- **Ce qui n'a pas changé :**
  - P4 (`coalition_*`, `partition_solver`, `formation_*`) ;
  - P5 (`savings_allocation`) ;
  - le simulateur P3 ;
  - `travel_workflow.py` ;
  - le catalogue v1 et le carnet v1 ;
  - les fichiers historiques et le golden master.
- **Fichiers nouveaux :** 14, soit 2 de code, 3 de tests, 8 de données et le manifeste.

| Diff | Fichiers | Lignes | SHA-256 |
|---|---:|---:|---|
| `docs/PHASE_I4_DIFF_FROM_BASELINE.patch`, cumulé depuis la base | 35 | 3 962 | `4aad07d4380be892535ca288bcc5af581c70a2b7cfbb17fd3e20804976e4e481` |
| `docs/PHASE_I4_A_DIFF.patch`, de la base à la fin d'I4-A | 9 | 1 087 | `3e59a0f2bc0acd544ea304c52ceb87d19cdc78c6472fe33d59e99593725c127f` |
| `docs/PHASE_I4_B_DIFF_FROM_A.patch`, de la fin d'I4-A à la fin d'I4-B | 14 | 1 580 | `736d46cbab49721592a1a6a9dbe66fb3f25b3b88154f29b09dd457b281754046` |
| `docs/PHASE_I4_C_DIFF_FROM_B.patch`, de la fin d'I4-B à la livraison | 13 | 1 327 | `55c3ff997f1e0ae27ca32d7ec053ccc4280d9a1dfa752432195f42d81c5eebb3` |

Les trois diffs par sous-étape partent de copies exactes, conservées à la fin de chaque
sous-étape. Aucun diff ne contient de chemin personnel. Les lignes retirées ne sont que
des remplacements dans les fichiers modifiés.

---

## 8. Critères d'acceptation (périmètre, §7.2)

| Critère | État |
|---|---|
| I4-A1 | **Atteint :** Lyon-Alger, sous forme structurée, produit une proposition v2 complète (§2) |
| I4-A2 | **Atteint, dans sa formulation reformulée (§7.2) :** résultats métier exploratoires identiques à ceux du code de la base, hors `formation_run_id` et `result_sha256` ; empreinte de performance `3024fef1…` reproduite telle quelle ; autres empreintes figées et sorties d'I3 identiques |
| I4-A3 | **Atteint :** K2 à K10 |
| I4-A4 | **Atteint :** C1 à C6 et H-forfait au chargement, avec les refus listés |
| I4-A5 | **Atteint :** un test par règle et par motif v2 |
| I4-A6 | **Atteint :** alias, lieu inconnu, référentiel invalide |
| I4-A7 | **Atteint :** P4, P5, le simulateur P3 et `process_travel_request` sont inchangés (manifeste) |
| I4-A8 | **Atteint :** documents v2 fermés ; T-CONF-1 et T-CONF-3 en v2 |
| I4-A9 | **Atteint :** `--validate-only` sur le jeu v3 |
| I4-A10 | **Atteint :** données figées avant toute planification, jamais retouchées |
| I4-A11 | voir le §7.1 ; mutants : 20 sur 20 |

**I4 est clôturée** (2026-11-20) : ses critères I4-A1 à I4-A11 sont atteints. Les
huit points du §6 n'ont pas reçu de décision explicite en revue ; aucun ne change un
critère. Reste une anomalie, ouverte hors du périmètre d'I4 : l'exécution de la
suite complète sous Python 3.10 (§7.1).

**Revérification du 2026-11-20 (mission finale) :**

- 976 passed avec `PYTHONHASHSEED=0` et `2` ;
- les 20 mutants d'I4 rejoués, 20 tués ;
- Lyon-Alger exécuté de bout en bout avec la commande installée : code 0, statut
  `served_in_coalition`, économie de 46,17 €.
