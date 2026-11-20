# I2 : répartition des économies (P5)

**Statut :** **acceptée** à la revue finale du 2026-11-20. Les critères A1 à A11 sont
atteints (§6).

La revue a accepté I2 sur la base des résultats transmis, sans réexécuter les tests ni
recalculer les empreintes. Cette acceptation lève le prérequis de la conception d'I3. Elle
n'autorise ni l'implémentation d'I3, ni aucune opération Git.

**Autorisation :** I2 autorisée, option A (2026-11-19). Ce que cela n'autorise pas :

- aucune opération Git n'a été faite ;
- I3 n'est pas commencée ;
- les 18 fichiers personnels n'ont pas été touchés.

**Référence normative :** `docs/PHASE_I2_SCOPE_REVIEW.md`, révision 3, validée. On s'y
réfère sous le nom de « périmètre ». Elle s'appuie sur :

- `docs/PHASE_P4_SPECIFICATION.md`, §9.2 à §9.7 ;
- `docs/PHASE_3H_P5_INTEGRATION_PLAN.md`, §6.1 ;
- `docs/PHASE_P5_ADDENDUM_ID6.md`, qui fixe θ = 0.

---

## 1. Base de référence (option A)

La base a été figée avant la première modification.

- **Manifeste :** `docs/PHASE_I2_BASELINE_MANIFEST.sha256`, soit les SHA-256 des
  157 fichiers du projet. Il ne contient aucun fichier personnel. Son empreinte est
  `ff2a3d1fafbaa63a5f058a5f7df64f30180286354db14ae79fda9c4125d4d5b7`.
- **Copie complète :** `Multi-Agent/`, `tests/`, `data/`, `docs/` et `pyproject.toml`,
  dans le répertoire temporaire de la session.
- **Diff complet :** `docs/PHASE_I2_DIFF_FROM_BASELINE.patch`. Il compare `Multi-Agent/`,
  `tests/`, `data/` et le document de périmètre corrigé ; il contient les nouveaux
  fichiers et aucun chemin personnel.

**Première modification après le gel.** La revue de démarrage a demandé de corriger une
formulation du §1 du périmètre : l'addendum ID-6 y était encore « à valider ». Il est
maintenant décrit comme une décision validée. Cette correction figure dans le diff.

### 1.1 Incident : redémarrage de la machine pendant la mesure

La machine a redémarré à 21 h 53, pendant M2. Le répertoire temporaire de la session a
été vidé : la copie de la base, les scripts de mutants et la mesure en cours ont disparu.
Le dépôt n'a pas été touché.

**Le dépôt est intact.** `shasum -a 256 -c` sur le manifeste donne 154 fichiers OK.
Les 3 fichiers en échec sont exactement les 3 fichiers modifiés d'I2 (§2.1).

**La copie de la base a été reconstruite, puis vérifiée par le manifeste :**

- **154 fichiers inchangés.** Le manifeste prouve qu'ils sont identiques à la base ; ils
  ont été recopiés depuis le dépôt.
- **`trip_planning.py` et `demand_pool.py`.** Ces deux fichiers ont été créés par I1, et
  leur contenu complet figure dans `docs/PHASE_I1_DIFF_FROM_BASELINE.patch`, qui en a été
  extrait.
- **Le document de périmètre.** La correction du §1 a été inversée. Il s'agissait d'un
  seul remplacement de chaîne, relevé dans le journal de la session.

**Résultat :** la copie reconstruite donne **157 fichiers OK sur 157**. Elle est donc
identique, octet pour octet, à la copie d'origine. Dans `Multi-Agent/`, `tests/` et
`data/`, les seuls fichiers absents du manifeste sont les 7 fichiers créés par I2 (§2.2).

**Conséquence pour la mesure.** Le premier lancement avait produit M0 et M1 avant
l'interruption :

- M0 : `T_P4_total(14)` = 6,72 s ;
- M1 : k = 14, 0,38 s.

**Ces valeurs ne sont pas retenues.** Le périmètre exige les trois mesures dans la même
session, et M2 n'a pas pu s'y achever. La mesure complète a donc été relancée de zéro, avec
les mêmes paramètres et les mêmes seuils (§5).

---

## 2. Ce qui a été réalisé

### 2.1 Fichiers de la base modifiés (3)

**Aucun fichier de P2, P3 ou P4 ne figure parmi eux (critère A9, §6).**

| Fichier | Modification |
|---|---|
| `Multi-Agent/coalition_travel/application/trip_planning.py` (I1) | Trois changements : 1) `TripPlan.allocation`, avec une valeur par défaut, et le contrôle qu'une allocation appartient à la formation de son plan ; 2) dans `plan_lot`, l'appel à `allocate_formation` après les invariants des journaux, puis le contrôle à l'exécution que P5 n'a fait aucun appel à l'oracle ; 3) le durcissement 1 : le SHA-256 de `DemandPoolSnapshot` doit compter 64 caractères hexadécimaux en minuscules |
| `Multi-Agent/coalition_travel/infrastructure/demand/demand_pool.py` (I1) | Durcissement 2 : le décodage UTF-8 du manifeste est enveloppé dans `DemandPoolError` |
| `docs/PHASE_I2_SCOPE_REVIEW.md` | Correction du §1 demandée par la revue de démarrage |

### 2.2 Fichiers nouveaux

| Fichier | Rôle |
|---|---|
| `Multi-Agent/coalition_travel/domain/savings_allocation.py` | **Mathématiques pures en rationnels**, bibliothèque standard seulement, sans aucun flottant : `values_by_mask`, `shapley_exact`, `project_onto_bounds`, `round_largest_remainder`, `constrained_equal_awards`, `max_core_excess` et les distances |
| `Multi-Agent/coalition_travel/application/savings_allocation.py` | **Allocation applicative.** `ALLOCATION_VERSION = "p5-allocation-v1"`, `THETA_CENTS = 0`, `CoverCache`, `allocate_block`, `split_unit_payment`, `allocate_formation`, les DTO `BlockAllocation`, `TravelerShare`, `UnallocatedUnit`, `AllocationCounters` et `AllocationResult` (avec `theta_cents`), les préconditions, les invariants à l'exécution et l'empreinte |
| `Multi-Agent/evaluate_allocation.py` | banc de mesure M0, M1 et M2 (§5) |
| `tests/test_savings_allocation_math.py` | 21 tests |
| `tests/test_savings_allocation.py` | 17 tests |
| `tests/test_i1_hardening.py` | 7 tests |
| `tests/test_i2_python310_compatibility.py` | 1 test |
| `docs/PHASE_I2_BASELINE_MANIFEST.sha256`, ce rapport, `docs/PHASE_I2_DIFF_FROM_BASELINE.patch` | traçabilité |

### 2.3 Hors périmètre, conformément à celui-ci

- **Côté P2 à P4 :** aucune modification de P2, P3 ou P4.
- **Côté autres étapes :** ni le `TripProposal`, ni le rendu, ni la CLI, ni les
  explications (I3) ; ni l'origine, ni l'aller-retour (I4) ; ni Ollama (I5).
- **Pas de LLM ni de RAG** dans P5.

---

## 3. Contrats et calcul

Le calcul suit le périmètre, §3.

### 3.1 Calcul d'un bloc

| Étape | Mise en œuvre |
|---|---|
| Préconditions (§3.2) | Pour un bloc C qui n'est pas un singleton : le jeu de la composante existe, C ∈ F, et **chaque** sous-coalition non vide de C figure dans `FormationResult.evaluations`. On vérifie aussi que les références et le coût sont cohérents avec le `FormedBlock`. En cas d'échec : `AllocationPreconditionError` |
| 1. v\*\|C | `CoverCache.block_cover`. On lit la restriction d'une couverture de composante déjà en mémoire, si elle existe (lemme de restriction), sinon on appelle `cover_values(C)`. Le cache refuse d'être réutilisé pour un autre jeu. Contrôle : `v*(C) = v(C)` |
| 2. φ | `shapley_exact`. Le numérateur est un entier exact sur `n!`, avec une seule `Fraction` par unité. Contrôles : `φ ≥ 0` et `Σ φ = v(C)` |
| 3. y | `project_onto_bounds(φ, v(C), 0, ref − θ)`. λ* est la racine de g la plus proche de 0, calculée exactement en rationnels |
| 4. y', x' | `round_largest_remainder`, départage par `unit_id`, puis `x'_u = ref_u − y'_u` |
| 5. q' | `split_unit_payment` : gains égaux sous plafonds par siège (`constrained_equal_awards`), puis plus fort reste, départage par (`profile_id`, rang) |
| 6. Diagnostics | `projection_active`, unités saturées, `‖y − φ‖²`, `max |y − φ|`, écart d'arrondi, excès maximal du cœur (seulement mesuré) |

**Singletons :** φ = 0 et `x' = ref`. L'étape 5 s'applique quand même : chaque voyageur
paie sa part du prix solo de son unité.

**Unités hors bloc :** elles figurent dans `unallocated` avec leur raison
(`no_admissible_offer`, `no_solo_reference`, `component_too_large` ou
`capacity_model_violated`), sans aucun montant fictif.

### 3.2 Invariants contrôlés à chaque exécution (§3.5)

| Niveau | Invariant |
|---|---|
| Bloc, contrôlé **avant** la répartition entre voyageurs | `Σ x' = c(C)` ; `0 ≤ x'_u ≤ ref_u ≤ B_u` |
| Voyageur | `0 ≤ q'_s ≤ b_s` ; `Σ q'_s = x'_u` |

Une violation lève `AllocationConsistencyError`.

### 3.3 Empreinte

`allocation_sha256` est calculée sur le JSON canonique, avec les rationnels écrits
`"p/q"`. Elle contient :

- `allocation_version` et `theta_cents` (= 0, ID-6) ;
- `formation_run_id` ;
- les blocs, les parts et les unités non allouées.

Les durées n'y entrent pas.

### 3.4 Intégration dans `plan_lot` (D-I2-2)

Après les invariants J3 à J5, `plan_lot` calcule l'allocation. Il vérifie ensuite que le
compteur d'appels de la session n'a pas bougé, sinon `PlanConsistencyError`.
`TripPlan.allocation` vaut `None` pour un plan rejeté.

---

## 4. Tests

### 4.1 Suite complète

| Exécution | Résultat |
|---|---|
| `PYTHONHASHSEED=0 python -m pytest -q` | **770 passed**, 0 skipped (724 existants + 46 nouveaux) |
| `PYTHONHASHSEED=2 python -m pytest -q` | **770 passed**, 0 skipped |
| **A1.** Les 724 tests de la base, copiés depuis la copie de la base, exécutés contre le code et les données d'I2 dans un répertoire temporaire | **724 passed** avec `PYTHONHASHSEED=0` et **724 passed** avec `PYTHONHASHSEED=2`. Aucune exception |
| Python 3.10 : 3 tests existants, 1 d'I1 et 1 d'I2. Ils s'exécutent dans la suite complète, avec un vrai Python 3.10.21 | exécutés, aucun saut (voir la note) |
| `ruff check` et `ruff format --check` sur les 9 fichiers Python créés ou modifiés | All checks passed ; 9 already formatted |
| `git diff --check` | propre |

**Note sur Python 3.10.** Après le redémarrage (§1.1), le `PATH` du shell ne contenait
plus `/opt/homebrew/bin`. Une première exécution a donc sauté les 5 tests Python 3.10
(765 passed, 5 skipped). Le code n'y est pour rien. Les exécutions retenues ci-dessus
remettent ce répertoire dans le `PATH` ; elles donnent 0 skipped.

### 4.2 Exemples de référence E1 à E6 (A3)

| # | Test | Résultat exact |
|---|---|---|
| E1 | `test_e1_shapley_of_the_cover_game_is_4_4_1` | φ = (4, 4, 1) ; projection inactive |
| E2 | `test_e2_projection_avoids_a_negative_payment` et `test_e2_and_e6_through_allocate_block` | y = (100, 400, 400) ; λ* = −100 ; unité saturée : a ; x = (0, 600, 600) |
| E3 | `test_e3_tokyo_block_is_reproduced_exactly` | φ = (600, 1 500, 3 000, 3 900) ; x = (48 000, 48 900, 51 000, 380 100) ; voyageurs de `user` : 4 × 47 513 et 4 × 47 512, τ = 95 025/2 ; excès du cœur = 0 |
| E4 | `test_e4_individual_budgets_are_respected` et `test_e4_and_e5_through_split_unit_payment` | (1 000, 4 000) ; a est saturé |
| E5 | `test_e5_renaming_moves_the_cent_but_not_the_amounts` et le même test applicatif | τ = 1 500,5 ; le centime suit le nom (R7c) ; montants et τ invariants (R7a, R7b) |
| E6 | `test_e6_a_null_player_can_receive_savings_after_projection` et `test_e2_and_e6_through_allocate_block` | φ = (450, 450, 0) ; λ* = −175 ; y = (100, 625, 175) ; x = (0, 375, 825) |

### 4.3 Propriétés objet par objet (A2, §5.1 du périmètre)

| Objet | Test | Volume |
|---|---|---|
| φ | efficacité, non-négativité et type `Fraction` sur des jeux de couverture aléatoires ; symétrie, joueur nul et additivité sur des jeux arbitraires | 300 + 300 |
| y | somme, bornes, forme KKT, `g(λ*) = 0`, convention (aucune racine entre 0 et λ*), y = φ sans borne active, `λ* ≤ 0` et plancher `y ≥ min(φ, ref)` quand `V = Σ φ`, symétrie conditionnelle. Testé dans deux régimes : V = Σφ, et V quelconque pour exercer λ* > 0. S'y ajoutent deux paliers construits (V = Σh, et V = Σl = 0) | 2 × 300 + 2 |
| y' | somme exacte, `y' ∈ {⌊y⌋, ⌊y⌋+1}`, aucun centime à une valeur entière, borne haute ; départage par clé croissante | 300 + 1 |
| q | R1 à R7c et le certificat d'optimalité ; renommage aléatoire pour R7a et R7b ; cas limites (X = 0, X = Σb, un seul siège, X > Σb refusé) | 1 000 + 4 |

### 4.4 Autres critères

- **A4, oracle différentiel.** Le Shapley historique `shapley_value` reçoit toujours la
  couverture `v*|C`, jamais v. La tolérance de 1e-6 × max(1, |V|) est respectée par
  unité sur tous les jeux. La revue provisoire a relevé que la première version ne
  couvrait ni E3 ni, à la lettre, les jeux de A2. Les tests couvrent désormais :

  | Jeux | Test |
  |---|---|
  | Les 300 jeux de couverture de A2 : même générateur, même graine 7 ; plus 300 jeux (graine 19), plus E1 | `test_differential_oracle_uses_the_same_cover_game` |
  | Les 300 jeux arbitraires de A2 (graine 11), avec leurs 4 fonctions chacun : symétrique, joueur nul, première et seconde de la paire d'additivité. Ici v\* = v par construction | `test_differential_oracle_on_the_arbitrary_games_of_a2` |
  | **E3**, sur le bloc réellement produit par `plan_lot`, avec la couverture lue dans le jeu de la composante | `test_e3_differential_oracle_on_the_cover_game` |

  Deux tests vérifient aussi le code des modules :
  - **Pas de Shapley historique.** Un test AST vérifie que ni le module de domaine ni le
    module applicatif n'importent `CoalitionStructureSearch` ou `cooperative_game`, et
    qu'ils n'utilisent pas `shapley_value`.
  - **Pas de flottant.** Un autre vérifie que le module de domaine ne contient ni
    littéral flottant ni `float`.
- **A5, aucun appel à l'oracle :** vérifié de deux façons.
  - **Faux oracle armé.** Après la formation, un oracle qui lève une exception s'il est
    appelé est substitué ; l'allocation se termine sans l'appeler, et le compteur de la
    session reste inchangé (`test_allocation_makes_no_oracle_call`).
  - **Contrôle de `plan_lot` à l'exécution.** Une allocation truquée qui négocie est
    refusée (`test_plan_lot_refuses_an_allocation_that_negotiates`).
- **A6, invariants à l'exécution :** un test de violation par invariant, par
  substitution de la fonction concernée :
  - `Σ x' ≠ c(C)` ;
  - `x' > ref`, avec une somme conservée ;
  - `q' > b` ;
  - `Σ q' ≠ x'` ;
  - `Σ φ ≠ v(C)`.

  Les préconditions sont testées aussi : une sous-coalition manquante, une unité absente
  du lot.
- **Lot figé** (`test_pinned_lot_allocation_is_pinned`) : calculé une fois au début d'I2,
  puis figé ; expliqué au §4.5.
- **Unités non allouées :** `no_solo_reference`, `capacity_model_violated` et
  `component_too_large`, avec la limite à 4 unités.
- **Cache et empreinte.** La restriction depuis une couverture de composante déjà en
  mémoire donne la même empreinte, avec 0 calcul supplémentaire. Le cache refuse d'être
  réutilisé pour un autre jeu. L'empreinte est déterministe, contient `theta_cents: 0`
  et la version, et change si une part change.
- **Durcissement d'I1 (A1 et D-I2-3).** 6 SHA invalides sont refusés et un manifeste en
  UTF-8 invalide lève `DemandPoolError`. Exécutés contre le code de la base, ces
  7 tests **échouent tous**, ce qui prouve qu'ils échouaient avant la correction.

### 4.5 Allocation du lot figé, expliquée

Le lot est celui de `tests/test_coalition_formation.py`, passé par `plan_lot`.

| Bloc | Valeur v(C) | φ | Références | Paiements x' |
|---|---|---|---|---|
| (a, b, c), `tyo-northstar` | 2 520 | (900, 1 260, 360) | (48 600, 50 400, 90 720) | (47 700, 49 140, 90 360) |
| (d), `tyo-skyways` | 0 | (0) | (54 000) | (54 000) |
| (e, f), `rom-cloudwing` | 9 000 | (4 500, 4 500) | (60 000, 30 000) | (55 500, 25 500) |

**Lecture des résultats :**

- **Bloc (e, f).** C'est un jeu à deux joueurs dont la seule coalition non triviale est
  le bloc : chacun reçoit la moitié de la valeur, quelle que soit sa référence. f, la
  plus petite référence, voit donc son prix baisser de 15 %.
- **Bloc (a, b, c).** b reçoit la plus grande part (12,60 €), parce que sa contribution
  marginale moyenne dans v\* est la plus élevée.
- **Projection.** Elle est inactive partout, et aucun paiement n'est nul.
- **Répartition entre voyageurs.**
  - les deux voyageurs de c paient chacun 451,80 € ;
  - ceux de e paient chacun 277,50 € ;
  - les montants sont entiers, donc aucun centime n'est à départager.

### 4.6 Mutants d'I2 (A7)

Le script est `i2_mutants.py`, exécuté sur une copie de travail dans le répertoire
temporaire.

**Résultat final : 19 tués sur 19.** Le script a disparu avec le répertoire temporaire
(§1.1). Il a été recréé à l'identique, puis rejoué sur la version finale des tests, avec
les tests A4 ajoutés : 19 tués sur 19 de nouveau.

| # | Défaut réintroduit | Tué par |
|---|---|---|
| 1 | Shapley sur v au lieu de v\* | E3 |
| 2 | signe de λ inversé | E2 |
| 3 | projection omise | E2 et E6 (application) |
| 4 | arrondi à l'entier inférieur, sans reste | E5 |
| 5 | poids de Shapley décalé de un | E1 |
| 6 | partage égal sans plafond | E4 |
| 7 | prorata des budgets | E4 |
| 8 | départage inversé | E5 |
| 9 | mauvais effectif dans τ | E4 |
| 10 | convention λ\* : racine la plus éloignée de 0 sur un palier | test des paliers (*a survécu au premier passage, voir ci-dessous*) |
| 11 | précondition sur les sous-coalitions supprimée | `test_a_missing_sub_coalition…` |
| 12 | `CoverCache` qui renvoie la couverture d'un autre sous-ensemble | `test_cover_cache…` |
| 13 | θ absent de l'empreinte | `test_digest…` |
| 14 | invariants de bloc non contrôlés | `test_each_runtime_invariant…` |
| 15 | invariants des voyageurs non contrôlés | idem |
| 16 | `plan_lot` accepte une allocation qui négocie | `test_plan_lot_refuses…` |
| 17 | allocation d'une autre formation acceptée | `test_trip_plan_allocation…` |
| 18 | durcissement 1 supprimé | `test_a_snapshot_needs…` |
| 19 | durcissement 2 supprimé | `test_an_invalid_manifest_encoding…` |

**Corrections faites pendant l'étape :**

1. **Le mutant 10 a survécu au premier passage.** La convention λ* n'était exercée sur
   aucun palier de g, un cas qui ne se produit jamais dans P5, puisque V < Σ ref
   strictement. J'ai ajouté deux paliers construits à partir de la spécification §9.5 :
   - V = Σh, où Λ = (−∞, −2] et λ* = −2 ;
   - V = Σl = 0, où Λ = [3, +∞) et λ* = 3.
2. **Un défaut de conception, révélé par un test d'invariant avant la livraison.**
   - **Le défaut.** Les invariants de bloc étaient contrôlés après la répartition entre
     voyageurs. Un paiement supérieur à la référence était donc d'abord rejeté par
     `constrained_equal_awards`, avec une erreur mathématique, et non par l'invariant
     prévu.
   - **La correction.** Les invariants de bloc sont maintenant contrôlés **avant** la
     répartition (§3.2).

---

## 5. Mesures M0, M1 et M2 (A8)

**Verdict : les deux seuils sont atteints, avec une large marge.** Les seuils sont ceux du
§6 du périmètre, enregistrés avant la mesure ; aucun paramètre n'a été modifié.

| Seuil | Règle | Mesuré | Verdict |
|---|---|---|---|
| M1 | médiane `T_P5`(dense, k = 14) < médiane `T_P4_total(14)` | 0,385 s < 6,727 s, soit 17 fois moins | **Atteint** |
| M2 | médiane `T_P5 / T_P4_total` ≤ 0,25 | 0,0307, soit 8 fois sous le seuil | **Atteint** |

### 5.1 Session et protocole

- **Une seule session.** M0, puis M1, puis M2, dans le même processus :
  `Multi-Agent/evaluate_allocation.py`, paramètres par défaut. Début le 19 novembre à
  23 h 05, fin le 20 novembre à 1 h 29, soit 8 605 s. C'est la session relancée de zéro
  après l'incident du §1.1.
- **Protocole.** Un échauffement, puis 5 répétitions, médiane. En M2, chaque répétition
  exécute P4, puis P5 sur la formation obtenue. L'empreinte de chaque répétition de P5 est
  comparée à celle de l'échauffement : elles sont toutes identiques.
- **Environnement.** Python 3.14.2, macOS 27.0, arm64, `PYTHONHASHSEED=0`, veille
  empêchée par `caffeinate -i`, mode économie d'énergie désactivé.
- **Alimentation.** Le Mac a fonctionné sur batterie pendant au moins une partie de M2 :
  une alerte de batterie faible a été émise à 1 h 01, et le secteur était rebranché à
  1 h 05. L'heure du débranchement n'est pas connue. Le rapport de M2 n'en dépend pas,
  puisque `T_P4_total` et `T_P5` sont mesurés dans la même exécution. M0 et M1 étaient
  terminés à 23 h 12.
- **Résultat brut.** `docs/p5_results/allocation_measurements.json`, schéma
  `p5-allocation-measurements-v1`, SHA-256
  `1816453b364a4cbb9fe4ccc871cbe4a0960dcf86a9c1ffdfa75c784303cbec37`.
  - **Origine.** Le fichier a été copié tel quel depuis la sortie de la session, après
    l'acceptation d'I2. La copie a été vérifiée par son empreinte et par une comparaison
    octet par octet.
  - **Contenu.** Les mesures de M0 et de M1, puis une ligne par instance de M2 (1 740) :
    paramètres de la cellule, graine, statut de la formation, nombre de blocs, taille du
    plus grand bloc, blocs à projection active, `T_P4_total`, `T_P5` et empreinte de
    l'allocation. Il ne contient ni plancher de vendeur ni chemin de fichier.
  - **Statut.** C'est un artefact de mesure, pas une source de données métier.
  - **Ce qui n'est pas conservé.** Les catalogues générés pendant la mesure restent hors
    du dépôt, car ils contiennent les planchers privés des vendeurs. Ils se régénèrent à
    partir des paramètres de cellule et des graines.

**Durée.** Le §6 du périmètre prévoyait environ 25 minutes pour M2. Cette estimation
comptait une seule exécution de P4 par instance. Le protocole en exige 6 (échauffement et
5 répétitions), plus autant d'exécutions de P5. M2 a pris 2 h 17. Le temps est concentré
sur quelques cellules de 14 unités très denses : la plus lente a pris à elle seule
51 minutes pour ses 20 graines.

### 5.2 M0 : `T_P4_total(14)`

Strate de performance : 14 unités, 1 profil, 1 offre, densité 100, accord 100, graines 0
à 9. **Médiane des 50 échantillons : 6,727 s.**

| Graine | Médiane (s) | Graine | Médiane (s) |
|---|---|---|---|
| 0 | 6,926 | 5 | 5,114 |
| 1 | 6,925 | 6 | 6,580 |
| 2 | 6,783 | 7 | 6,744 |
| 3 | 6,687 | 8 | 6,806 |
| 4 | 6,679 | 9 | 6,641 |

Les médianes par instance vont de 5,114 s à 6,926 s.

### 5.3 M1 : `T_P5` sur des blocs denses

Toutes les sous-coalitions sont réalisables, et la grande coalition est optimale. Durées
en millisecondes : médiane, quartiles, et médiane par sous-étape.

| k | Médiane | Q1 | Q3 | Couverture | Excès du cœur | Shapley | Projection | Arrondi | Voyageurs |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 0,112 | 0,111 | 0,120 | 0,011 | 0,005 | 0,003 | 0,035 | 0,005 | 0,030 |
| 3 | 0,165 | 0,165 | 0,168 | 0,018 | 0,012 | 0,005 | 0,048 | 0,011 | 0,042 |
| 4 | 0,226 | 0,225 | 0,226 | 0,037 | 0,025 | 0,008 | 0,060 | 0,006 | 0,055 |
| 5 | 0,334 | 0,333 | 0,334 | 0,078 | 0,051 | 0,013 | 0,074 | 0,008 | 0,068 |
| 6 | 0,535 | 0,534 | 0,537 | 0,170 | 0,107 | 0,025 | 0,087 | 0,018 | 0,081 |
| 7 | 0,925 | 0,925 | 0,928 | 0,393 | 0,215 | 0,052 | 0,099 | 0,021 | 0,093 |
| 8 | 1,758 | 1,747 | 1,762 | 0,938 | 0,413 | 0,110 | 0,113 | 0,011 | 0,107 |
| 9 | 3,853 | 3,852 | 3,863 | 2,374 | 0,873 | 0,263 | 0,127 | 0,026 | 0,119 |
| 10 | 8,805 | 8,799 | 8,806 | 6,132 | 1,660 | 0,631 | 0,140 | 0,013 | 0,135 |
| 11 | 21,509 | 21,495 | 21,514 | 16,143 | 3,477 | 1,458 | 0,155 | 0,032 | 0,148 |
| 12 | 54,650 | 54,486 | 54,765 | 43,879 | 6,942 | 3,192 | 0,180 | 0,036 | 0,174 |
| 13 | 143,343 | 143,236 | 143,560 | 121,310 | 14,002 | 7,374 | 0,200 | 0,041 | 0,197 |
| 14 | 384,942 | 384,288 | 385,270 | 340,427 | 27,852 | 14,932 | 0,216 | 0,043 | 0,216 |

**Lecture :**

- **La couverture domine.** À k = 14, elle représente 88 % du temps. De k = 10 à k = 14,
  elle est multipliée par 2,6 à 2,8 à chaque pas. C'est cohérent avec le coût prévu en
  Θ(3^k).
- **L'excès du cœur et Shapley doublent environ à chaque pas** aux grands k, ce qui
  correspond à Θ(2^k).
- **Projection, arrondi et répartition par voyageur restent sous 0,25 ms.**
- **L'optimisation par masques de bits n'est pas nécessaire.** Le périmètre la prévoyait
  seulement en cas d'échec d'un seuil.

### 5.4 M2 : strate exploratoire

- **1 740 instances** : 87 cellules de 20 graines. Les cellules sont 22 variations d'un
  facteur à la fois, 60 cellules tirées au hasard et 5 familles.
- **1 616 instances à blocs.** C'est exactement le nombre prévu par le périmètre.
- **Les 124 instances sans bloc** se répartissent ainsi :
  - 100 en `no_eligible_units` ;
  - 20 en `capacity_model_violated` ;
  - 4 en `incomplete`.

**Statistiques sur les 1 616 instances à blocs :**

| Grandeur | Médiane | 95e centile | Maximum |
|---|---|---|---|
| `T_P5` | 0,41 ms | 1,86 ms | 24,0 ms |
| `T_P5 / T_P4_total` | 0,0307 | 0,124 | 0,236 |
| Taille du plus grand bloc | 2 | 6 | 11 |

- **Aucune instance ne dépasse 0,25.** Même au cas par cas, le rapport reste sous le
  seuil fixé pour la médiane.
- **Le maximum du rapport (0,236) est atteint sur une très petite instance :** un bloc
  d'une seule unité, avec `T_P4_total` = 0,60 ms et `T_P5` = 0,14 ms. Les rapports élevés
  viennent donc des instances où P4 est presque instantané, pas d'un P5 coûteux.
- **Le `T_P5` le plus long (24,0 ms)** correspond au bloc de 11 unités, pour un
  `T_P4_total` de 11,0 s sur la même instance.

**Par taille du plus grand bloc :**

| Taille | Instances | Médiane du rapport | Médiane de `T_P5` | Maximum de `T_P5` |
|---|---|---|---|---|
| 1 | 510 | 0,0451 | 0,16 ms | 0,85 ms |
| 2 à 3 | 763 | 0,0356 | 0,44 ms | 2,78 ms |
| 4 à 6 | 297 | 0,0020 | 1,07 ms | 3,45 ms |
| 7 à 11 | 46 | 0,0025 | 4,66 ms | 24,0 ms |

Plus les blocs sont grands, plus le rapport baisse : le coût de P4 croît bien plus vite que
celui de P5.

**Projection jamais active (0 bloc sur la strate).** Il s'agit d'une observation, et non
d'un défaut.

- **La borne inférieure ne peut pas être active.** v\* est superadditif par construction,
  puisque la réunion de deux couvertures disjointes est une couverture. Chaque contribution
  marginale est donc au moins égale à v\*({u}) = 0, d'où φ ≥ 0.
- **La borne supérieure** n'est active que si φ(u) dépasse la référence de l'unité. Cela
  n'arrive sur aucune instance de la strate.

M2 ne mesure donc pas le chemin où la projection agit. Sa justesse est établie par les
tests : E2, E6, les paliers construits et A2 sur y (§4.2 et §4.3). Son coût est mesuré
par M1, où la projection est calculée à chaque exécution.

---

## 6. Critères d'acceptation A1 à A11

| Critère | Verdict | Preuve |
|---|---|---|
| A1, les 724 tests existants passent sans modification | **Atteint** | Copiés depuis la copie de la base et exécutés contre le code d'I2 : 724 passed avec `PYTHONHASHSEED=0`, 724 passed avec `PYTHONHASHSEED=2`. Aucune exception n'est nécessaire, puisque `TripPlan.allocation` a une valeur par défaut. Le diff ne modifie aucun test existant (§7.2) |
| A2, propriétés objet par objet | **Atteint** | §4.3. φ : 300 jeux de couverture et 300 jeux arbitraires. y : 2 × 300 jeux et 2 paliers. y' : 300 jeux. q : 1 000 unités. Les axiomes de Shapley ne sont exigés que de φ |
| A3, E1 à E6 exacts | **Atteint** | §4.2. E6 vérifie que le joueur nul reçoit y = 175 > 0 après la projection |
| A4, oracle différentiel sur v\* | **Atteint** | §4.4. Jeux de A2 (de couverture et arbitraires), 300 jeux de plus, E1 et E3. Test AST : aucun import du Shapley historique dans les modules officiels |
| A5, zéro appel à l'oracle | **Atteint** | Deux mécanismes (§4.4) : le faux oracle armé, et le compteur de session contrôlé par `plan_lot` |
| A6, invariants à l'exécution | **Atteint** | §3.2 et §4.4. Chaque invariant a un test de violation ; les préconditions sont testées aussi |
| A7, mutants | **Atteint** | 19 tués sur 19 (§4.6). Les 11 mutants exigés sont les n° 1 à 9, 11 et 12. Les 8 autres couvrent la convention λ\*, l'empreinte, les invariants, `plan_lot` et les deux durcissements |
| A8, M0, M1 et M2 dans la même session, seuils atteints | **Atteint** | §5. Une seule session de 8 605 s. M1 : 0,385 s < 6,727 s. M2 : médiane du rapport 0,0307 ≤ 0,25, sur 1 616 instances à blocs. Les seuils ont été enregistrés avant la mesure, et aucun paramètre n'a été modifié |
| A9, P2 à P4 inchangés | **Atteint** | `shasum -a 256 -c docs/PHASE_I2_BASELINE_MANIFEST.sha256` donne 154 OK et 3 échecs. Les 3 échecs sont `trip_planning.py` (I1), `demand_pool.py` (I1) et `docs/PHASE_I2_SCOPE_REVIEW.md`. Aucun fichier de P2, P3 ou P4 n'y figure. L'empreinte exploratoire `997109ee…` n'a donc pas à être régénérée |
| A10, Python 3.10, golden master, ruff, `diff --check` | **Atteint** | Le test `test_p5_domain_module_imports_and_computes_under_python_3_10` passe sous un vrai Python 3.10.21. Le module applicatif est couvert par le contrôle de grammaire existant. Le golden master passe dans la suite complète. ruff est propre sur les 9 fichiers, et `git diff --check` aussi |
| A11, rapport, manifeste, diff, sans chemin personnel | **Atteint** | Ce rapport, `docs/PHASE_I2_BASELINE_MANIFEST.sha256` et `docs/PHASE_I2_DIFF_FROM_BASELINE.patch`. Aucun chemin personnel n'y figure (§7.1) |

---

## 7. Écart exact avec la base

### 7.1 Le diff

**Fichier :** `docs/PHASE_I2_DIFF_FROM_BASELINE.patch`, 10 fichiers, 2 067 lignes,
SHA-256 `245a16e40ef07e0ad34a613ef28611798f9623e3734a995cd008e43453e6a36a`.

**Construction.** Deux liens symboliques, `a/` vers la copie de la base et `b/` vers le
dépôt, évitent tout chemin absolu. Le diff assemble deux commandes :

- `diff -ruN -x __pycache__ -x '*.egg-info' -x .DS_Store` sur `Multi-Agent/`, `tests/` et
  `data/` ;
- `diff -u` sur `docs/PHASE_I2_SCOPE_REVIEW.md`.

**Contrôles :**

- **Réapplication.** Le diff appliqué par `patch -p1` à une copie de la base reproduit
  exactement le dépôt : `diff -rq` vide sur les trois arborescences, et `cmp` identique
  pour le document de périmètre.
- **Aucun chemin personnel.** Une recherche de `/Users/`, `/private/`, `/tmp/` et du
  répertoire de session ne trouve rien.
- **Fichiers exclus.** Ni ce rapport, ni le manifeste ne figurent dans le diff : ils
  n'existaient pas dans la base, et le diff ne couvre pas `docs/`, sauf le document de
  périmètre.

### 7.2 Contenu

| Fichier | Nature | Lignes |
|---|---|---|
| `Multi-Agent/coalition_travel/domain/savings_allocation.py` | nouveau | +301 |
| `Multi-Agent/coalition_travel/application/savings_allocation.py` | nouveau | +494 |
| `Multi-Agent/evaluate_allocation.py` | nouveau | +279 |
| `Multi-Agent/coalition_travel/application/trip_planning.py` | modifié (I1) | +20 −0 |
| `Multi-Agent/coalition_travel/infrastructure/demand/demand_pool.py` | modifié (I1) | +5 −3 |
| `tests/test_savings_allocation_math.py` | nouveau | +381 |
| `tests/test_savings_allocation.py` | nouveau | +404 |
| `tests/test_i1_hardening.py` | nouveau | +37 |
| `tests/test_i2_python310_compatibility.py` | nouveau | +36 |
| `docs/PHASE_I2_SCOPE_REVIEW.md` | §1 corrigé | +1 −1 |

**Aucun test existant n'est modifié.** Aucun fichier de `data/` ne l'est non plus.

**Les deux fichiers d'I1, en détail :**

- **`trip_planning.py`, 5 blocs, uniquement des ajouts :**
  - les imports `re`, `AllocationResult` et `allocate_formation` ;
  - `_SHA256_PATTERN`, puis son contrôle dans `DemandPoolSnapshot` (durcissement 1) ;
  - le champ `TripPlan.allocation`, avec sa valeur par défaut `None`, et son contrôle de
    cohérence ;
  - dans `plan_lot`, l'appel à `allocate_formation`, encadré par la lecture du compteur
    d'appels de la session ;
  - `allocation=allocation` dans le `TripPlan` retourné.
- **`demand_pool.py`, 1 bloc (durcissement 2) :** le décodage du manifeste est extrait
  dans un `try` qui convertit `UnicodeDecodeError` en `DemandPoolError`. L'appel
  `_object(...)` est reformaté sur une ligne, sans changement de logique.

---

## 8. Limites et points ouverts

- **Durées.** Les durées sont volatiles, mesurées sur une seule machine, et n'entrent
  dans aucune empreinte. Ce ne sont pas des constantes matérielles. M2 a été mesurée en
  partie sur batterie, puis sur secteur (§5.1). Le rapport `T_P5 / T_P4_total` reste
  valable comme comparaison interne, puisque P4 et P5 sont mesurés dans la même exécution.
  Les durées absolues, elles, ne valent que pour cette session.
- **Projection jamais active sur la strate exploratoire (§5.4).** Cela ne montre pas que
  la projection est inutile : les cas où elle agit sont construits et vérifiés par E2, E6
  et les tests A2 sur y.
- **Stabilité.** L'excès du cœur est mesuré, jamais garanti. Il vaut 0 sur E3 et il est
  négatif sur les deux blocs du lot figé : aucune sécession n'y est profitable.
- **Pour I3.** Les explications devront distinguer trois montants :
  - la valeur créée par la coalition (v(C)) ;
  - la contribution calculée (φ) ;
  - le montant payé (x').

  Un paiement nul (E2, E6) s'affichera comme une part entièrement couverte par
  l'économie collective (addendum ID-6, §3).
- **Réserves héritées, toujours ouvertes :** arrondis P3, durées variables.
