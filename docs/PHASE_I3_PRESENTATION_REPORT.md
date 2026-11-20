# I3 : présentation, explications et CLI — rapport de livraison

**Statut :**

- **I3-A** est acceptée depuis la revue technique finale du 2026-11-20. Sa revue a validé
  les sept précisions du §3.2. Elle a relevé un durcissement non bloquant, appliqué depuis
  (§10).
- **I3-B** est acceptée et clôturée depuis sa revue du 2026-11-20.
- **I3-C** est acceptée avec une réserve d'intégration : un essai de la commande
  installée. Cet essai a été fait et il passe (§16).
- **Les dix précisions du §14 sont acceptées.**

**Historique de l'autorisation :**

- **I3-A.** Le 2026-11-20, la personne responsable du projet a demandé de commencer le
  codage d'I3. Le périmètre (révision 4, §10 et §14) prévoit que chaque sous-étape soit
  autorisée et revue séparément : j'ai donc livré I3-A seule, puis je me suis arrêté
  pour sa revue.
- **I3-B et I3-C.** Après l'acceptation d'I3-A, la revue recommandait une autorisation
  distincte pour I3-B, et de ne pas commencer I3-C par anticipation. La personne
  responsable a ensuite demandé de faire « le reste ». J'ai pris cette demande pour
  l'autorisation des deux sous-étapes. Chacune a sa propre section, ses propres tests et
  ses propres mutants, pour être revue séparément.
- **La dernière revue de la révision 4 du périmètre** n'avait pas été transmise quand le
  codage a commencé. Le code suit la révision 4 telle quelle. Les précisions trouvées en
  codant sont listées au §3.2 (I3-A, acceptées) et au §14 (I3-B et I3-C, à trancher).

**Aucune opération Git** n'a été faite. Les 18 fichiers personnels n'ont pas été
touchés.

**Textes de référence :**

- `docs/PHASE_I3_SCOPE_REVIEW.md`, révision 4 (« le périmètre ») ;
- la spécification technique d'I3 et le plan `docs/PHASE_3H_P5_INTEGRATION_PLAN.md`,
  révision 4.

---

## 1. Base de référence (option A, I3-A16)

La base a été figée avant la première modification.

- **Manifeste :** `docs/PHASE_I3_BASELINE_MANIFEST.sha256`. Il contient les SHA-256 des
  169 fichiers du projet, avec la même règle de sélection qu'en I2 :
  - `Multi-Agent/`, `tests/`, `data/` et `docs/` ;
  - les fichiers de la racine du projet : `.gitignore`, les `README`, `SCENARIOS.md`,
    `pyproject.toml` et les deux `requirements`.

  Sont exclus les caches, `.DS_Store` et les 18 fichiers personnels. L'empreinte du
  manifeste est `80194aa5c5a9aae5bdeeb7cde7978fa4b918478539982782d0fdcb6c1d7d7768`.
- **Le décompte est cohérent avec I2 :** 157 fichiers de la base d'I2, plus les 7
  fichiers créés par I2, plus 5 documents (le rapport d'I2, son manifeste, son diff, le
  périmètre d'I3 et la mesure brute M2).
- **Copie complète :** dans le répertoire temporaire de la session. Elle est vérifiée par
  le manifeste : 169 fichiers OK sur 169.
- **Aucun fichier de code n'avait changé depuis la clôture d'I2.** Les fichiers les plus
  récents étaient des documents.
- **La suite était verte sur la base :** `PYTHONHASHSEED=0 python -m pytest -q` donne
  **770 passed**.

---

## 2. I3-A : fichiers

| Fichier | Nature |
|---|---|
| `Multi-Agent/coalition_travel/application/trip_proposal.py` | nouveau : DTO du contrat `trip-proposal-v1`, ensembles fermés des 13 codes, `ExtractionProvenance`, constructeur `build_trip_proposal`, invariants |
| `tests/test_trip_proposal.py` | nouveau : 37 tests |
| `docs/PHASE_I3_BASELINE_MANIFEST.sha256` | nouveau : manifeste de la base |
| `docs/PHASE_I3_DIFF_FROM_BASELINE.patch` | nouveau : diff cumulé depuis la base |

**Aucun fichier de la base n'est modifié.** Le manifeste le confirme : 169 fichiers OK
sur 169. `travel_workflow.py` et `pyproject.toml` ne seront modifiés qu'en I3-C.

**Le module n'importe aucune infrastructure.** Il lit les journaux par un protocole,
`PublicJournal`, qui ne déclare que les champs publiés. Le test existant des frontières
entre modules passe.

---

## 3. Contrat implémenté

### 3.1 Conformité au périmètre

| Point du périmètre | Implémentation |
|---|---|
| §4.1 à §4.10, champs et sources | une dataclass gelée par objet. Les collections sont des tuples, et le brouillon validé est une copie en lecture seule |
| §4.10, provenance | versions, date de référence et `extraction`. **Aucune empreinte, aucun chemin** |
| §4.10, `extraction` | `ExtractionProvenance` n'accepte que les trois formes du tableau ; toute autre combinaison lève `ValueError` |
| §5.1, un statut unique | les quatre règles sont évaluées indépendamment. `ProposalConsistencyError` est levée si aucune ou plusieurs s'appliquent |
| §5.1, « évaluée par P4 » | coalitions de `FormationResult.evaluations` qui contiennent l'unité et comptent au moins 2 unités ; « bénéfique » veut dire réalisable et v(C) > 0 |
| §5.2, modificateurs | `projection_active` seulement dans un bloc d'au moins 2 unités ; `budget_cap_active` dès qu'une part de l'unité est saturée |
| §5.3, annotations | `offer_rejected`, une par offre non admissible ; `direct_preference_not_met` sur l'offre retenue seulement (D-I3-14) |
| §5.4, `alone_social_optimum` | `cover_values()` calculé une fois. V\* doit égaler `ComponentSolution.value_cents`, et chaque écart être positif ou nul : les deux sont contrôlés à chaque construction. On retient les trois alternatives de plus grand total, à égalité dans l'ordre canonique, sans leurs membres |
| B8, autres membres | `autre demande k`, places, paiement ; la personne d'abord, sous le libellé `vous` |
| B11, journaux | côté leader masqué dans un journal de bloc (offre initiale et messages) ; deux côtés dans les journaux solo de la personne |
| §7.1, ordre | offres par `offer_id`, notes par (code, profil), messages par index, parts par (profil, rang), explications par niveau, code, puis `offer_id` |
| Invariants du DTO | `TripProposal` les vérifie à sa construction : schéma, statut connu, bloc et allocation présents ensemble, un seul statut dans les explications, modificateurs cohérents, ordres canoniques, la personne en tête du bloc, somme des paiements égale au coût du bloc |
| Cohérence avec la demande | le brouillon passé au constructeur doit reconstruire la même unité (même empreinte d'unité), sinon `ProposalConsistencyError` |

### 3.2 Précisions et écarts à trancher à la revue

Le codage a fait apparaître sept points que la révision 4 ne fixait pas, ou fixait d'une
façon que le code ne permet pas. Chacun a reçu la solution la plus étroite possible ;
aucun ne change une décision validée.

1. **`solo` vaut `null` quand H2 échoue.** Le §4.1 donne `solo` comme toujours présent.
   Or, quand le modèle de capacité est violé, rien n'est négocié et il n'existe aucune
   `UnitReferenceCost`. `solo` est donc absent exactement pour le statut
   `capacity_model_violated`, et l'invariant du DTO le vérifie.
2. **Les `params` de cinq statuts.** Le §5.4 ne les fixe que pour les deux statuts
   `alone_*`. J'ai défini les autres au plus juste, chacun par une classe fermée :

   | Code | `params` |
   |---|---|
   | `no_admissible_offer` | `rejected_offers` : le nombre d'offres rejetées, détaillées dans `offers` |
   | `no_solo_reference` | `failed_attempts` : le nombre de négociations solo sans accord |
   | `component_too_large` | `component_units`, `max_component_units` |
   | `capacity_model_violated` | `offer_ids` : les offres dont le contrôle de capacité échoue pour l'unité |
   | `served_in_coalition` | `offer_id`, `other_requests` (le nombre d'autres demandes du bloc), `saving_cents` |

3. **Les rationnels restent des `Fraction` dans le DTO.** Le §4 les décrit sous la forme
   `"p/q"` : c'est la forme du JSON, que produira l'afficheur d'I3-B.
4. **`REPLAY_FORMAT_VERSION` est défini dans `trip_proposal.py`, et non dans
   `replay.py`.** La couche application ne peut pas importer l'infrastructure, ce que
   vérifie le test des frontières. L'extracteur de rejeu d'I3-C importera la constante.
5. **`best_direct` ne retient que les offres directes dont la capacité couvre les places
   du bloc.** Au-delà de la capacité, `OfferQuote.list_total` n'a pas de valeur et lève
   une erreur. Une offre trop petite n'est donc pas candidate.
6. **T-CONF-3 et les champs de `SellerTerms`.** La règle littérale, « aucune clé n'est un
   nom de champ de `SellerTerms` ou de `SellerFloorTier` », refuserait des clés publiques
   que ces classes partagent avec `OfferQuote` et `PriceTier` : `offer_id`,
   `catalog_version`, `capacity_seats` et `min_seats`. Le test porte donc sur les champs
   propres aux conditions privées, `floor_tiers` et `floor_per_seat`. **À signaler pour
   I3-B :** au niveau du JSON, les clés de `request.draft` contiennent `budget_per_person`.
   C'est la demande de la personne, publiée par le §4.3 : l'exception « budget » de
   T-CONF-3 devra la couvrir.
7. **L'ensemble d'exclusions de T-CONF-2 (e) compte 10 entrées.** Pour `pool-tyo-03`, le
   « y » nul du périmètre comprend aussi son arrondi, `saving`. Le reste est exactement
   l'ensemble documenté (§5.2).

---

## 4. Tests

### 4.1 Le fichier `tests/test_trip_proposal.py` : 37 tests

| Groupe | Tests |
|---|---|
| I3-A1, les neuf éléments | E3 : les 9 éléments, la provenance, le brouillon tel quel ; le lot figé (`a` et `e`) ; deux constructions identiques |
| I3-A2 et I3-A4, un statut par code | les 7 statuts, plus le cas Rome ; un cas construit de coalition de valeur nulle ; le refus de deux règles à la fois |
| Modificateurs et annotations | `budget_cap_active` ; `projection_active`, construit ; l'absence de modificateur pour une unité seule ; `offer_rejected` ; `direct_preference_not_met`, et une note sur une autre offre qui ne crée pas d'annotation |
| Codes et invariants | les 13 codes par niveau ; les paramètres fermés ; les invariants du DTO ; les entrées refusées par le constructeur |
| T-REPLAY, niveau contrat | les trois formes d'`extraction`, et huit combinaisons refusées, dont un `model` de 64 chiffres hexadécimaux |
| T-CONF, niveau DTO | précondition, T-CONF-1, T-CONF-2 (a) à (e), T-CONF-3 |

### 4.2 Voie utilisée, code par code (I3-A4)

Tous les scénarios utilisent le catalogue v1, à la date du 2026-11-19.

| Code | Voie | Scénario |
|---|---|---|
| `served_in_coalition` | pipeline réel | E3 : Tokyo, 8 voyageurs, 500 €, carnet v1 |
| `alone_social_optimum` | pipeline réel | Tokyo, 2 voyageurs, 500 €, carnet v1 : V\* = 2 520, et la meilleure alternative a un écart nul (égalité de valeur, départagée par P4). Aussi Rome, 3 voyageurs, 450 € |
| `alone_no_beneficial_coalition` | pipeline réel | Tokyo, 2 voyageurs, 500 €, carnet vide : composante singleton |
| `alone_no_beneficial_coalition`, avec une coalition de valeur nulle | **construit** | le jeu de la composante est modifié pour qu'une coalition réalisable vaille exactement 0. Le catalogue v1 n'offre pas ce cas : j'ai parcouru 100 demandes, et toute unité seule y avait au moins une coalition de valeur positive |
| `no_admissible_offer` | pipeline réel | Alger : les trois offres sont rejetées (`destination_mismatch`) |
| `no_solo_reference` | pipeline réel | Tokyo, 1 voyageur, 100 € |
| `component_too_large` | pipeline réel | Tokyo, 1 voyageur, 520 €, avec `max_component_units = 4` |
| `capacity_model_violated` | pipeline réel | deux demandes Rome de 20 voyageurs |
| `budget_cap_active` | pipeline réel | Tokyo, deux profils : 1 voyageur à 300 € et 3 à 700 € |
| `projection_active` | **construit** | l'allocation du bloc d'E3 est forcée à « projection active ». Le catalogue v1 ne l'active jamais (rapport d'I2, §5.4) |
| `offer_rejected` | pipeline réel | E3 (Rome rejetée) et Alger |
| `direct_preference_not_met` | pipeline réel | Tokyo, 1 voyageur, 700 €, vol direct préféré, Northstar exclu : bloc sur SkyWays, `best_direct` nul |
| `needs_clarification`, `unknown_place` | — | codes de niveau demande, jamais dans une proposition. Leurs messages relèvent d'I3-B |

---

## 5. Confidentialité, au niveau du DTO

T-CONF s'exécute ici sur l'arbre de la `TripProposal`. I3-B le refera sur le JSON et la
sortie texte.

| Test | Résultat |
|---|---|
| Précondition | entre A (520,00 €) et B (521,37 €) : mêmes références, mêmes coûts de coalition, mêmes blocs, mêmes paiements |
| T-CONF-1 | `TripProposal(A)` égale `TripProposal(B)`. Les données privées diffèrent bien : `pool_sha256`, la `request_key` et le `journal_sha256` du bloc, `formation_run_id`, `allocation_sha256`, et l'offre initiale du leader, qui passe de 339 600 à 339 682 |
| T-CONF-2 (a) | les seuls types de l'arbre sont les dataclasses du contrat et des types simples (`str`, `int`, `bool`, `None`, `date`, `Fraction`, tuple, mapping en lecture seule). Aucun `SellerTerms`, `TravelUnit` ni `NegotiationJournal` |
| T-CONF-2 (b) | aucune chaîne de 64 chiffres hexadécimaux, et aucune des empreintes réelles du plan, journal par journal |
| T-CONF-2 (c) | dans B, ni 52 137, ni 566 137, ni 166 137, ni 339 682. Leur absence du catalogue est vérifiée d'abord |
| T-CONF-2 (d) | les messages du vendeur, dans le journal du bloc et dans les journaux solo, égalent les montants internes |
| T-CONF-2 (e) | le carnet marqué M donne le même bloc qu'E3. Structure vérifiée sur E3 et sur M. Sur M, les exclusions calculées égalent l'ensemble attendu, et aucune autre donnée privée des autres demandes n'apparaît : identifiants, `profile_id`, dates, fournisseur, budgets, références, φ, y, τ, parts |
| T-CONF-3 | les 106 noms de champs du contrat égalent l'ensemble figé. Aucun ne contient `floor`, `seller_terms`, `request_key`, `sha256`, `run_id` ni `configuration`. Seuls `budget_total_cents` et `budget_cents` contiennent `budget` |

---

## 6. Mutants

Chaque mutant est réintroduit seul dans une copie de travail, hors du dépôt, puis
`tests/test_trip_proposal.py` est exécuté. **15 mutants sur 15 sont tués.**

| # | Mutant | Tests qui échouent |
|---|---|---|
| 1 | `pool_sha256` dans la provenance | T-CONF-1, T-CONF-2 (b), T-CONF-3, provenance d'E3 |
| 2 | `oracle_configuration_id` dans la provenance | T-CONF-2 (b), T-CONF-3, provenance d'E3 |
| 3 | montants du leader visibles dans un journal de bloc | T-CONF-1, T-CONF-2 (c), les neuf éléments d'E3 |
| 4 | `request_key` exposée dans un essai solo | T-CONF-2 (b), T-CONF-3 |
| 9 | `alone_social_optimum` dès que v(C) ≥ 0 | coalition de valeur nulle, construite |
| 11 | `catalog_sha256` dans la provenance | T-CONF-2 (b), T-CONF-3, provenance d'E3 |
| 14 | contre-offres du vendeur masquées dans le journal du bloc | T-CONF-2 (d) |
| 16 | libellé d'un autre membre remplacé par son `unit_id` | T-CONF-2 (e1), T-CONF-2 (e2), les neuf éléments d'E3 |
| 17 | parts de tous les membres du bloc dans `travellers` | 24 tests, dont T-CONF-2 (e1) et (e2). La plupart échouent parce que le constructeur refuse des τ différents dans une même unité |
| A1 | contrôle « exactement un statut » retiré | refus de deux règles à la fois |
| A2 | alternatives triées par total croissant | `alone_social_optimum`, cas Tokyo et cas Rome |
| A3 | annotation de préférence directe tirée de n'importe quelle offre | note sur une autre offre |
| A4 | rejeu accepté avec n'importe quel `model` | trois formes d'`extraction` |
| A5 | offres rejetées non annotées | `offer_rejected`, invariants, les neuf éléments d'E3 |
| A6 | plafond de budget jamais signalé | `budget_cap_active` |

Les mutants 5 à 8, 10, 12, 13 et 15 du §9.2 portent sur le vocabulaire, l'interruption,
les documents de statut, la validation et le rejeu en ligne de commande. Ils relèvent
d'I3-B et d'I3-C.

---

## 7. Suite complète et qualité

Environnement : Python 3.14.2 du `.venv`, macOS, arm64. `/opt/homebrew/bin` est placé
dans le `PATH`, pour que les tests Python 3.10 s'exécutent avec un vrai Python 3.10.

| Exécution | Résultat |
|---|---|
| Base, avant toute modification : `PYTHONHASHSEED=0 python -m pytest -q` | **770 passed** |
| `PYTHONHASHSEED=0 python -m pytest -q` | **807 passed** : 770 tests de la base et 37 nouveaux, aucun saut |
| `PYTHONHASHSEED=2 python -m pytest -q` | **807 passed** |
| `tests/test_trip_proposal.py` avec `-W error` | 37 passed, aucun avertissement |
| Python 3.10 (I3-A17) | le contrôle de grammaire 3.10 de `tests/test_python310_compatibility.py` parcourt tous les fichiers de `Multi-Agent/` et de `tests/`, donc les deux nouveaux. Il passe avec un vrai Python 3.10. Comme pour le module applicatif d'I2, l'import complet sous 3.10 n'est pas testé : il demande pydantic |
| Frontières entre modules | `tests/test_p4_module_boundaries.py` passe : la couche application n'importe pas l'infrastructure |
| `ruff check`, `ruff format --check` sur les 2 fichiers Python | All checks passed ; 2 already formatted |
| `git diff --check`, et recherche d'espaces en fin de ligne dans les fichiers nouveaux | propre |
| Golden master | inclus dans la suite complète ; il passe |

**Les tests de la base ne sont pas modifiés.** Le manifeste le prouve : 169 fichiers OK
sur 169.

**Le diff cumulé,** `docs/PHASE_I3_DIFF_FROM_BASELINE.patch`, compare `Multi-Agent/`,
`tests/` et `data/` à la copie de la base. Il contient 2 fichiers, tous deux nouveaux,
sur 2 074 lignes. Il ne contient aucun chemin personnel. Son SHA-256 est
`4aef0d17752405ab83a1c643f20d5eb714487d78f4bfa3a39ecf3ae3d094a3fa`. Comme en I2, ni le
manifeste ni ce rapport n'y figurent.

---

## 8. Critères d'acceptation : état après I3-A

| Critère | État |
|---|---|
| I3-A1 | **Au niveau du constructeur :** les neuf éléments sur E3 et sur le lot figé. Le parcours E3 de bout en bout, par la CLI, relève d'I3-C |
| I3-A2 | **Atteint** : exactement un statut, contrôlé par règles indépendantes |
| I3-A3 | **Atteint** : chaque montant est lu dans un champ typé ; les trois dérivations sont recalculées indépendamment dans les tests |
| I3-A4 | **Atteint pour les 11 codes d'une proposition** (§4.2). `needs_clarification` et `unknown_place` relèvent d'I3-B |
| I3-A7 | **Au niveau du DTO** (§5). Le JSON relève d'I3-B |
| I3-A8 | **Atteint au niveau du DTO**, par T-CONF-2 (e) |
| I3-A16 | **Atteint** : manifeste, copie, diff ; aucun fichier de la base modifié |
| I3-A17 | **Atteint pour I3-A** : grammaire 3.10, ruff, `git diff --check`, golden master, suite complète verte avec deux graines (§7) |
| I3-A18 | **Atteint pour I3-A** : commandes, version de Python et graines au §7. Tout ce qui est écrit ici a été exécuté ; rien n'est seulement déclaré |
| I3-A20 | **Atteint pour les mutants d'I3-A** (§6) |
| I3-A6, A10 à A15, A19 | relèvent d'I3-B ou d'I3-C |

---

## 9. Après I3-A

Les sections 1 à 8 décrivent I3-A telle qu'elle a été acceptée. La suite du rapport
couvre le durcissement d'I3-A demandé par sa revue (§10), I3-B (§11) et I3-C (§12).
Viennent ensuite les preuves communes (§13), les précisions à trancher (§14) et l'état
des critères (§15).

---

## 10. I3-A : durcissement après la revue

La revue d'I3-A a relevé un point non bloquant : `TripProposal.__post_init__` ne
refusait pas explicitement les doublons de modificateurs ni d'explications. Le
constructeur n'en produit pas, mais un DTO construit à la main le pouvait.

**Ajout, dans `trip_proposal.py` :**

- les modificateurs doivent être des codes distincts de l'ensemble fermé ;
- un même code d'explication ne peut apparaître deux fois pour la même offre.

**Test ajouté :** `test_duplicate_modifiers_and_annotations_are_refused`, dans
`tests/test_trip_proposal.py`. **Mutant ajouté :** A7, contrôle retiré, tué (§13.2).

Aucune autre ligne d'I3-A n'a changé. Le fichier de tests d'I3-A n'a reçu que ce
nouveau test.

---

## 11. I3-B : messages, rendus et vocabulaire

### 11.1 Fichiers

Tous sont nouveaux, dans `Multi-Agent/coalition_travel/infrastructure/presentation/`.

| Fichier | Rôle |
|---|---|
| `__init__.py` | paquet |
| `vocabulary.py` | règle du vocabulaire (§7.2) ; chemins des chaînes fournies par la personne (D-I3-17) |
| `explanations_fr.py` | messages français des 13 codes, montants en euros, questions de clarification, messages de rejet |
| `json_renderer.py` | JSON canonique de la proposition ; documents `trip-request-status-v1` et leur validateur fermé ; domaine E des erreurs ; réduction des erreurs de pydantic |
| `text_renderer.py` | rendu texte de la proposition ; résumé de la demande comprise ; messages de statut sur la sortie d'erreur |

Tests : `tests/test_presentation.py`, 31 tests.

### 11.2 Ce qui est implémenté

- **Vocabulaire (§7.2).** NFC, puis `casefold`, puis découpage par `\w+`, puis
  comparaison des mots entiers aux 13 formes interdites du plan.
  - Un mot qui contient seulement un mot interdit passe : « réservation », « émission »,
    « confirmation », « billetterie ».
  - Chaque rendu (texte, JSON, documents de statut) passe ce contrôle avant d'être
    renvoyé. Un échec lève `PresentationError` : c'est un défaut du système, donc le
    code 1.
- **Messages (§5.4).**
  - Ils sont déterministes : ils ne dépendent que du code et de ses paramètres.
  - `alone_social_optimum` décrit la structure retenue et les alternatives. Il traite à
    part l'écart nul (« même valeur totale… règle de départage documentée de P4 »).
    Aucun des mots « meilleur », « optimal » ou « avantageux » n'y figure : un test le
    vérifie.
  - `alone_no_beneficial_coalition` ne parle que des coalitions évaluées par P4.
- **JSON (§7.1).**
  - Forme : `json.dumps(sort_keys=True, ensure_ascii=False, indent=2)`, plus un saut de
    ligne final.
  - Les rationnels s'écrivent `"p/q"`, comme dans l'empreinte d'I2 : `"3900/1"` pour un
    entier.
  - Les dates sont des chaînes ISO.
  - Chaque explication porte `code`, `level`, `params` et `message`.
  - Le rendu n'accepte qu'une `TripProposal`.
- **Texte (§9.1 de la spécification).** Dans l'ordre :
  - l'avertissement, en première ligne, puis la date de référence ;
  - la demande validée ;
  - le résultat ;
  - les offres, admissibles ou écartées avec leurs motifs ;
  - les négociations individuelles ;
  - le groupe constitué : offre commune, prix catalogue, prix négocié (simulation),
    valeur créée, membres anonymisés ;
  - la répartition calculée ;
  - les paiements par voyageur ;
  - les explications ;
  - la provenance.

  Dans un journal de bloc, les montants du mandataire apparaissent comme « montant non
  publié ».
- **Documents de statut (§6.4).**
  - Il y a un constructeur par statut.
  - Le validateur contrôle les clés, les valeurs, le domaine E (9 formes, par
    expressions régulières ancrées) et les cinq lignes de `request_rejected`. Il renvoie
    le code de sortie du document.
  - Les erreurs de pydantic sont réduites à `chemin: type`. La racine s'écrit `$`, et un
    nom inconnu `?`.

### 11.3 Tests (31)

| Groupe | Contenu |
|---|---|
| T-LEX | les deux faces de la règle, en majuscules et en NFD ; les chaînes du fichier du catalogue ; toutes les sorties de dix scénarios réels ; les chemins des chaînes interdites ; un rendu empoisonné refusé |
| Messages, un test par code | les 11 codes d'une proposition, à partir de scénarios réels, plus `projection_active` construit ; `needs_clarification` et `unknown_place` ; format des montants |
| JSON | forme canonique et identité octet pour octet ; types et unités ; rendu limité à une `TripProposal` ; T-CONF-3 sur les clés réelles du JSON |
| Texte | les neuf éléments et l'avertissement ; identité octet pour octet ; résumé construit à partir des seuls champs validés |
| T-CONF, sur le JSON et le texte | T-CONF-1 : sorties de A et de B identiques octet pour octet. T-CONF-2 (b) : aucune empreinte. (c) : aucune valeur privée de B, ni en centimes dans le JSON ni en euros dans le texte. (d) : messages du vendeur. (e) : carnet marqué, mêmes exclusions qu'au niveau du DTO, aucune fuite |
| T-STATUS | 11 documents valides ; les cinq lignes de `request_rejected` produites par le vrai planificateur ; 21 documents refusés ; réduction des erreurs de pydantic sans valeur reçue ; messages sans la valeur interdite |

---

## 12. I3-C : `plan_travel_request`, rejeu et commande

### 12.1 Fichiers

| Fichier | Nature |
|---|---|
| `Multi-Agent/coalition_travel/application/travel_workflow.py` | **modifié, ajouts seulement** : `TravelPlanningResult` et `plan_travel_request`. `process_travel_request` ne change pas : aucune ligne de la base n'est supprimée ni modifiée |
| `Multi-Agent/coalition_travel/infrastructure/llm/replay.py` | nouveau : `ReplayStructuredRequestExtractor` |
| `Multi-Agent/plan_trip.py` | nouveau : la commande |
| `pyproject.toml` | **modifié, deux lignes :** le script `coalition-travel-plan = "plan_trip:main"`, et `plan_trip` dans `py-modules` (§14) |
| `tests/test_plan_trip_cli.py` | nouveau : 43 tests |

### 12.2 Ce qui est implémenté

- **`plan_travel_request` (§6.1).**
  - Elle reçoit une demande déjà validée par la personne, appelle `plan_lot`, puis
    `build_trip_proposal` si le plan est `planned`.
  - Elle est synchrone et n'ajoute aucun statut.
  - `TravelPlanningResult` vérifie qu'une proposition existe exactement pour un plan
    `planned`.
- **Extracteur de rejeu (D-I3-10).**
  - Le fichier est lu une fois, à la construction. Un fichier illisible est donc signalé
    dès la lecture des options.
  - Le n-ième appel renvoie le n-ième brouillon, validé. Au-delà, ou pour une entrée
    invalide, l'extracteur lève `ExtractorContractError`. Aucun message ne cite le
    chemin ni le contenu.
  - Sa provenance est `replay` / `replay-v1`.
- **La commande (§6.2).**
  - Les fichiers d'entrée sont lus avec les options.
  - Le catalogue v1 et le carnet v1 sont ouverts avant la demande.
  - La demande est obtenue par `--draft-json`, par `--prompt` ou par saisie. Avec
    `--prompt` ou la saisie, il y a au plus 3 tours de clarification, d'une question par
    tour (« Précision k/3 : … »). Une fin d'entrée pendant un tour donne le code 2.
  - Le contrôle de D-I3-17 porte sur chaque brouillon, avant tout affichage qui en
    dérive.
  - Le résumé de la demande et la question de validation vont sur la sortie d'erreur.
    Seuls « o » et « oui » valent validation.
  - `plan_travel_request` est appelée ensuite, puis la sortie est rendue en texte ou en
    JSON.
- **Sorties.**
  - La sortie standard ne reçoit que le document final, écrit en une fois à la fin.
  - En mode texte, pour les codes 2, 3 et 4, elle reste vide ; avec `--json`, elle
    reçoit le document de statut validé.
  - Pour les codes 1, 64 et 130, elle est toujours vide.
- **Codes de sortie (§6.3).**
  - 0 : proposition produite.
  - 1 : erreur technique, affichée sous la forme « Erreur technique : Classe: message »,
    sans trace de pile.
  - 2 : clarification requise.
  - 3 : demande invalide, ou demande rejetée par le planificateur.
  - 4 : demande non validée.
  - 64 : usage incorrect.
  - 130 : interruption.
- **Aucun chemin dans les messages (B10).**
  - Un fichier d'entrée devient le nom de son option, et un fichier versionné son nom
    de base.
  - Un chemin absolu inattendu devient `<chemin>`.
  - Pour une `OSError`, seul `strerror` est affiché.

### 12.3 Tests (43)

Les scénarios passent par un sous-processus : `python -B Multi-Agent/plan_trip.py`, dans
un répertoire temporaire, avec un environnement sans variable `OLLAMA_*`.

| Groupe | Contenu |
|---|---|
| `plan_travel_request` | E3 : la proposition égale celle du constructeur, paiement 380 100 ; demande rejetée : pas de proposition ; invariant de `TravelPlanningResult` |
| I3-A11, scénarios | `--draft-json` d'E3 de bout en bout ; sortie identique octet pour octet sur deux exécutions, en JSON et en texte ; validation acceptée (« o », « oui », «  OUI  ») ; refus, réponse vide, fin d'entrée (code 4) ; `--prompt` avec rejeu, même proposition qu'avec `--draft-json`, sauf la provenance ; saisie interactive ; clarification scriptée ; limite de 3 tours ; fin d'entrée pendant un tour ; date de référence |
| I3-A12 | le carnet de rejeu contient un cinquième brouillon complet, qui serait lu s'il y avait un quatrième tour. Résultat : code 2, `rounds = 3`, exactement 3 questions |
| Codes de sortie | les trois motifs de budget par `--draft-json` (code 3) ; erreurs de pydantic, JSON malformé et date passée (code 3) ; clarification par `--draft-json` (code 2) ; saisie vide (code 3) ; 8 usages incorrects (code 64) ; rejeu épuisé et Ollama injoignable (code 1) |
| T-REPLAY | R1 et R2 donnent des sorties identiques, en JSON et en texte ; `extraction` exacte ; ni empreinte ni chemin dans les sorties ; R0 vide : code 1, sans chemin ; fichier illisible (répertoire, et `chmod 000` hors `root`) : code 64, avant toute question, sans chemin, sans marque, sans texte système |
| T-SIGINT | un vrai `SIGINT`, à la question de validation et pendant la saisie : code 130, sortie standard vide, aucune trace de pile |
| T-LEX | mot interdit dans `destination`, un `profile_id` ou `excluded_suppliers` : code 3, `forbidden_term: chemin`, le mot absent des deux sorties, aucune question de validation ; même refus pour un brouillon venu de l'extracteur, avant toute question de clarification |
| I3-A13 | au niveau de la fonction, avec un marché qui compte les sessions : un refus (code 4) et une interruption (code 130) n'ouvrent aucune session ; une validation en ouvre une, qui négocie |

---

## 13. Preuves communes

### 13.1 Suite complète et qualité

Environnement : Python 3.14.2 du `.venv`, macOS, arm64. `/opt/homebrew/bin` est dans le
`PATH`, pour que les tests Python 3.10 s'exécutent avec un vrai Python 3.10.

| Exécution | Résultat |
|---|---|
| `PYTHONHASHSEED=0 python -m pytest -q` | **882 passed** : 770 tests de la base et 112 nouveaux (38 + 31 + 43), aucun saut |
| `PYTHONHASHSEED=2 python -m pytest -q` | **882 passed**, aucun saut |
| `-W error` sur les trois fichiers de tests d'I3 | aucun avertissement |
| Python 3.10 | le contrôle de grammaire 3.10 parcourt tous les fichiers de `Multi-Agent/` et de `tests/`, donc les nouveaux ; il passe |
| Frontières entre modules | la couche application n'importe pas l'infrastructure : le test existant passe |
| `ruff check` et `ruff format --check` sur les 12 fichiers Python créés ou modifiés | All checks passed ; 12 already formatted |
| `git diff --check`, espaces en fin de ligne | propre |
| Golden master et tests de `process_travel_request` | inclus dans la suite, inchangés, verts (I3-A15) |
| `coalition-travel-plan --help` | aucun mot interdit |

### 13.2 Mutants

Chaque mutant est réintroduit seul, dans une copie de travail hors du dépôt.

- **I3-A : 16 mutants sur 16 tués.** Ce sont les 15 du §6, plus A7, le durcissement
  retiré. `tests/test_trip_proposal.py` est exécuté en entier.
- **I3-B et I3-C : 15 mutants sur 15 tués.** Les trois fichiers de tests d'I3 sont
  exécutés avec `-x` : le tableau donne le premier test qui échoue.

| # | Mutant | Premier test qui échoue |
|---|---|---|
| 5 | vocabulaire contrôlé par sous-chaîne | `test_words_that_only_contain_a_forbidden_word_pass` |
| 6 | contrôle des chaînes de la personne retiré | T-LEX, mot interdit dans `destination` |
| 7 | interruption convertie en code 1 | T-SIGINT, question de validation |
| 8 | une clé en trop dans un document de statut | T-STATUS, cas positifs |
| 10 | validation acceptée sur une réponse vide | validation non donnée, réponse vide |
| 12 | provenance du rejeu égale au SHA-256 du fichier | `--prompt` avec rejeu (provenance) |
| 13 | chemin dans un message d'erreur | T-REPLAY, fichier illisible |
| 15 | validateur de statut limité aux clés | T-STATUS, cas négatifs |
| B1 | JSON avec échappements ASCII | JSON canonique |
| B2 | clés JSON non triées | JSON canonique |
| B3 | rationnels écrits en nombres flottants | types et unités du JSON |
| B4 | `message` absent des explications JSON | types et unités du JSON |
| B5 | forme E8 qui accepte n'importe quel texte | T-STATUS, cas négatifs |
| C1 | quatre tours de clarification | clarification scriptée (« Précision 1/3 ») |
| C2 | résumé écrit sur la sortie standard | E3 de bout en bout (sortie standard purement JSON) |

Avec les mutants 1 à 4, 9, 11, 14, 16 et 17 tués en I3-A, **les 17 mutants du §9.2 du
périmètre sont tous tués** (I3-A20).

### 13.3 Base, diff et manifeste

- **Manifeste.** La comparaison donne 167 fichiers de la base OK sur 169. Les deux
  fichiers modifiés sont exactement ceux prévus par le §2.1 du périmètre :
  `travel_workflow.py` et `pyproject.toml`.
- **Fichiers nouveaux :**
  - dans `Multi-Agent/` : 8, soit `trip_proposal.py`, les 5 fichiers de `presentation/`,
    `replay.py` et `plan_trip.py` ;
  - dans `tests/` : 3 ;
  - dans `docs/` : le manifeste, le diff et ce rapport.
- **Diff cumulé,** `docs/PHASE_I3_DIFF_FROM_BASELINE.patch`. Il compare `Multi-Agent/`,
  `tests/`, `data/` et `pyproject.toml` à la copie de la base. Il ne contient aucun chemin
  personnel. Ses chiffres sont donnés au §13.4.
- **Le diff de `travel_workflow.py` ne contient que des ajouts.** Aucune ligne de la base
  n'est retirée.

### 13.4 Les deux diffs

| Diff | Contenu | Lignes | SHA-256 |
|---|---|---:|---|
| `docs/PHASE_I3_DIFF_FROM_BASELINE.patch`, cumulé depuis la base | 13 fichiers : `travel_workflow.py` et `pyproject.toml` modifiés, 11 fichiers nouveaux | 4 840 | `9a7d05e10a052498947e06f9e16f86e7f5be464f2312df655d7a4bb9d1996c52` |
| `docs/PHASE_I3_BC_DIFF_FROM_I3A.patch`, depuis l'état accepté d'I3-A | les mêmes 13 fichiers. Pour `trip_proposal.py`, les 5 lignes du durcissement ; pour `test_trip_proposal.py`, son nouveau test | 2 786 | `4f8220ec16eab34de08b90692385fbf56372b782db2e7c71ea67e76275ab9872` |

**Aucun des deux ne retire de ligne.** Ils ne contiennent que des ajouts, et aucun
chemin personnel.

**Le diff cumulé remplace celui qu'a vérifié la revue d'I3-A** (empreinte `4aef0d…`).

**Le diff incrémental part d'une reconstruction de l'état accepté d'I3-A.**
- **Méthode :** la copie de la base, plus les deux fichiers d'I3-A, dont on retire
  exactement le durcissement et le nouveau test.
- **Vérification :** les deux fichiers reconstruits ont les tailles du diff accepté
  (995 et 1 071 lignes), et leurs 37 tests passent.
- **Limite :** l'empreinte `4aef0d…` ne peut pas être reproduite. `diff` écrit dans
  l'en-tête de chaque fichier sa date de modification, et ces dates ont changé.

---

## 14. Précisions d'I3-B et d'I3-C à trancher

Comme pour I3-A, chaque point a reçu la solution la plus étroite. Aucun ne change une
décision validée.

1. **Un module de plus dans `presentation/` : `vocabulary.py`.** Le périmètre (§2.1)
   parlait d'un « module d'aide au contrôle du vocabulaire », rangé avec les tests. Mais
   D-I3-17 exige le contrôle pendant l'exécution de la commande. Le module est donc dans
   le code produit, et les tests l'importent.
2. **Les rendus vérifient leur propre vocabulaire.** Un texte ou un JSON qui contiendrait
   un mot interdit lève `PresentationError`, donc le code 1. Le périmètre ne demandait
   ce contrôle qu'en test ; il s'ajoute ici comme garde-fou.
3. **`pyproject.toml` : deux lignes, et non une.** En plus du script, `plan_trip` doit
   figurer dans `py-modules`, sinon le point d'entrée n'est pas installé.
   L'environnement virtuel n'a pas été réinstallé. Les tests lancent donc
   `python Multi-Agent/plan_trip.py`, et la commande `coalition-travel-plan` ne sera
   disponible qu'après `pip install -e .`.
4. **Le modèle du chemin `--prompt` vient de `OLLAMA_MODEL`, et l'adresse de
   `OLLAMA_BASE_URL`.** C'est la convention existante de `evaluate_requests.py`. Sans
   `OLLAMA_MODEL` ni `--extractor-replay`, `--prompt` et la saisie donnent le code 64,
   avec un message qui l'explique.
5. **`--extractor-replay` avec `--draft-json` donne le code 64.** Le rejeu remplace le
   modèle de langage, que `--draft-json` n'utilise pas. Le périmètre ne fixait pas ce
   cas.
6. **Messages d'usage fixes.** Les messages d'`argparse` peuvent recopier un argument
   inconnu, donc une valeur fournie par la personne. Ils sont remplacés par trois
   messages français fixes, suivis de la ligne d'usage.
7. **Une ligne d'information, « Demande validée : simulation en cours. »**, va sur la
   sortie d'erreur après la validation. Rien n'est écrit pendant `plan_travel_request`.
8. **Une saisie interactive vide donne le code 3**, avec l'erreur E6 de
   `understand_request`. C'est la règle existante : un texte vide est une demande
   invalide, pas une erreur technique.
9. **T-CONF-3 au niveau du JSON** admet trois clés contenant « budget » :
   `budget_total_cents`, `budget_cents`, et `budget_per_person`. Cette dernière est une
   clé de la demande validée de la personne, publiée par le §4.3. C'est le point
   annoncé au §3.2, n° 6.
10. **T-CONF-1 au niveau de la commande n'est pas possible.** La commande n'utilise que
    le carnet versionné. T-CONF-1 est donc fait sur les rendus JSON et texte de A et de
    B (§11.3), construits par les mêmes fonctions que la commande.

---

## 15. Critères d'acceptation : état final

| Critère | État |
|---|---|
| I3-A1 | **Atteint** : les neuf éléments, au niveau du constructeur (lot figé et E3), du texte et du JSON, et E3 de bout en bout par sous-processus (paiement 380 100 ; 4 × 47 513 + 4 × 47 512) |
| I3-A2, A3, A4 | **Atteints** (§8) ; les deux codes de niveau demande ont leur message (§11.3) |
| I3-A6 | **Atteint** : sortie identique octet pour octet, en texte et en JSON, sur deux exécutions de la commande |
| I3-A7, A8 | **Atteints** au niveau du DTO, du JSON et du texte (T-CONF-1 à 3, T-REPLAY) |
| I3-A10 | **Atteint** : T-LEX sur les rendus, les messages et la commande, et sur les chaînes du catalogue |
| I3-A11 | **Atteint** : tous les scénarios par sous-processus, y compris le code 130 avec sortie standard vide |
| I3-A12 | **Atteint** : la quatrième réponse n'est jamais lue |
| I3-A13 | **Atteint** : aucune session ouverte avant la validation, au niveau de la fonction |
| I3-A14 | **Atteint** : les codes 0, 1, 2, 3, 4, 64 et 130 sont tous testés |
| I3-A15 | **Atteint** : `process_travel_request` et ses tests sont inchangés et verts ; `travel_workflow.py` ne reçoit que des ajouts |
| I3-A16 | **Atteint** : seuls `travel_workflow.py` et `pyproject.toml` diffèrent de la base, plus les fichiers nouveaux |
| I3-A17 | **Atteint** : §13.1 |
| I3-A18 | **Atteint** : commandes, Python et graines au §13.1. Tout ce qui est écrit ici a été exécuté |
| I3-A19 | **Atteint** : T-STATUS, clés et valeurs, cas positifs et négatifs |
| I3-A20 | **Atteint** : les 17 mutants du §9.2, et 14 mutants supplémentaires, tous tués |

---

## 16. Revue d'I3-B et d'I3-C, et vérification d'installation

### 16.1 Décisions de la revue (2026-11-20)

- **I3-B est acceptée et clôturée.**
- **I3-C est acceptée**, sous réserve d'un essai de la commande installée.
- **Les dix précisions du §14 sont acceptées.** La dixième l'est avec une observation :
  T-CONF-1 est testé au niveau des rendus, puisque la commande n'utilise que le carnet
  v1.
- **La revue est statique :** elle n'a pas exécuté les tests. Les résultats du §13 restent
  des résultats rapportés par l'équipe.
- **Limite à garder dans l'historique.** Le diff incrémental part d'une reconstruction de
  l'état accepté d'I3-A (§13.4), et non d'une copie conservée octet pour octet. Les
  tailles identiques et les 37 tests verts ne prouvent pas, à eux seuls, l'identité
  octet pour octet.

### 16.2 Essai de la commande installée

**Installation.** `python -m pip install -e .`, dans l'environnement virtuel du projet,
le 2026-11-20. L'opération a eu trois effets :

- `setuptools` n'étant pas dans l'environnement, pip l'a téléchargé dans un
  environnement de construction isolé. Les dépendances déjà installées (numpy, scipy,
  pydantic) n'ont pas changé ;
- le paquet `coalition-travel` 0.2.0 a été réinstallé en mode éditable, par le même
  mécanisme qu'avant : un fichier `.pth` qui pointe vers `Multi-Agent/` ;
- deux scripts sont apparus dans `.venv/bin` : `coalition-travel-plan`, et
  `coalition-travel-eval-rag`, déjà déclaré dans `pyproject.toml` mais absent de
  l'ancienne installation.

**Ce que l'installation n'a pas touché dans le dépôt.** Aucun répertoire `build/` ni
`dist/` n'a été créé. Les seuls fichiers de la base qui diffèrent du manifeste restent
`travel_workflow.py` et `pyproject.toml`. Le répertoire `coalition_travel.egg-info`,
ignoré par Git et exclu du manifeste, a été régénéré.

**Essai,** depuis un répertoire temporaire hors du dépôt, sans `PYTHONPATH` ni variable
`OLLAMA_*`, en lançant le script installé `.venv/bin/coalition-travel-plan` :

| Commande | Résultat |
|---|---|
| `coalition-travel-plan --help` | code 0 ; l'usage s'affiche ; rien sur la sortie d'erreur ; aucun mot interdit |
| `coalition-travel-plan --draft-json e3.json --reference-date 2026-11-19 --yes --json` | code 0 ; `served_in_coalition` ; paiement 380 100 ; parts 4 × 47 512 + 4 × 47 513 ; `extraction` = `draft-json`. La sortie est **identique octet pour octet** à celle de `python Multi-Agent/plan_trip.py` avec les mêmes options (SHA-256 `8ea8538128440e92de89ca5ac48fb01a04d68637180018d86d4c30316d53ff5c`) |
| la même commande, sans `--yes` ni `--json`, réponse « o » | code 0 ; l'avertissement en première ligne ; prix négocié (simulation) 5 280,00 € ; paiement de la demande 3 801,00 € ; « autre demande 3 » |
| la même commande, réponse « non » | code 4 ; sortie standard vide (0 octet) ; « Demande non validée : aucune simulation n'a été lancée. » |

Le module chargé par la commande installée est bien `Multi-Agent/plan_trip.py` du
dépôt. Après la réinstallation, les 112 tests d'I3 passent de nouveau.

**La réserve d'intégration d'I3-C est donc levée.**

### 16.3 Deux améliorations non bloquantes, laissées ouvertes

La revue les a relevées sans rouvrir I3-B. Elles ne sont pas appliquées :

1. **`validate_status_document` et une valeur non hachable.** Le validateur teste
   l'appartenance de `status` à un dictionnaire. Avec une liste, Python lèverait
   `TypeError` au lieu de `StatusDocumentError`. C'est sans effet dans le flux normal,
   où les documents sont construits en interne. Il faut le durcir si le validateur
   devient une frontière publique.
2. **T-CONF-2 (e) et les montants en chaînes décimales.** Le test reconnaît les entiers,
   les `"p/q"` et les montants en euros du texte. Il devrait reconnaître aussi un montant
   privé écrit en chaîne décimale, par exemple `"521.37"`.

**État de clôture proposé :**

- I3-A, I3-B et I3-C sont acceptées ;
- I3 est techniquement close ;
- aucune autorisation Git n'est accordée, et les 18 fichiers personnels restent
  exclus.
