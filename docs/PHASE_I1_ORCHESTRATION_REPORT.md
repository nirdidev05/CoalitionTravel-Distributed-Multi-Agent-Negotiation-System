# I1 : orchestration 3H sur le catalogue v1

**Statut :** implémentée ; tous les critères d'acceptation du plan sont vérifiés (§6). En attente de revue.

**Autorisation :** « I1 autorisée, option A » (2026-11-19).

**Ce qui n'a pas été fait :**

- aucune opération Git ;
- I2 n'est pas commencée ;
- aucun fichier personnel n'a été touché.

**Référence normative :** `docs/PHASE_3H_P5_INTEGRATION_PLAN.md`, révision 4 : §4.3,
§4.4 (y compris §4.4.1 à §4.4.3), §6.3 et §7 (I1).

---

## 1. Base de référence (option A)

Avant la première modification, la base a été figée sans aucune opération Git.

- **Manifeste :** `docs/PHASE_I1_BASELINE_MANIFEST.sha256`, soit les SHA-256 des
  141 fichiers du projet :
  - les fichiers suivis par Git ;
  - les fichiers non suivis de `Multi-Agent/`, `tests/`, `docs/` et `data/`.

  Il ne contient aucun fichier personnel. Son empreinte est
  `dd91c39746896979097fd5fd5a3e28b68b0a508b29ec083cfa182ca560f5d74e`.
- **Copie complète :** `Multi-Agent/`, `tests/`, `data/`, `docs/` et `pyproject.toml`,
  dans le répertoire temporaire de la session.
- **Écart avec la base :** vérifié par `shasum -a 256 -c` sur le manifeste et par
  `diff -ruN` sur la copie (§7). Le diff complet est dans
  `docs/PHASE_I1_DIFF_FROM_BASELINE.patch`.

---

## 2. Ce qui a été réalisé

### 2.1 Fichiers de la base modifiés (2)

| Fichier | Modification |
|---|---|
| `Multi-Agent/coalition_travel/application/coalition_formation.py` | ajout de `FormationStages` et de `run_formation_stages`. `run_formation_pipeline` devient une enveloppe qui renvoie `.formation`. Le corps du pipeline est inchangé ; seules les deux instructions `return` construisent maintenant un `FormationStages` (plan §4.3) |
| `tests/test_offer_catalog.py` | entrée `infrastructure/negotiation/market.py` dans `FLOOR_ALLOW_LIST`, et la même entrée dans le test d'égalité exacte de la liste. C'est la seule exception prévue par le critère d'I1 |

### 2.2 Fichiers nouveaux (12)

| Fichier | Rôle |
|---|---|
| `Multi-Agent/coalition_travel/infrastructure/negotiation/journaling_oracle.py` | `JournalingNegotiationOracle`, placé sous le cache (§4.4) ; `check_journal_concordance` (J2) ; `JournalConsistencyError` ; `NonDeterministicJournalError` (§4.4.2) |
| `Multi-Agent/coalition_travel/infrastructure/negotiation/market.py` | racine de composition (§4.5) : `open_simulated_market` et `SimulatedMarket`, qui donnent accès au catalogue public et à `open_session()` |
| `Multi-Agent/coalition_travel/infrastructure/demand/__init__.py` | paquet |
| `Multi-Agent/coalition_travel/infrastructure/demand/demand_pool.py` | lecteur strict du carnet synthétique (ID-1) |
| `Multi-Agent/coalition_travel/application/trip_planning.py` | `plan_lot`, les DTO `PlanningRequest`, `DemandPoolSnapshot`, `PlanningInput` et `TripPlan`, les ports `NegotiationMarket` et `JournalingSession`, et `verify_journal_invariants` (J3 à J5) |
| `data/demand/demand_pool_v1.jsonl` | carnet v1 : 6 demandes structurées, synthétiques |
| `data/demand/demand_pool_v1.manifest.json` | manifeste : SHA-256 `ef9513a0…d476`, version, catalogue visé, nombre de demandes |
| `tests/test_journaling_oracle.py` | 16 tests |
| `tests/test_trip_planning.py` | 20 tests |
| `tests/test_demand_pool.py` | 25 tests |
| `tests/test_i1_python310_compatibility.py` | 1 test (import réel sous Python 3.10) |
| `docs/PHASE_I1_BASELINE_MANIFEST.sha256` | manifeste de la base (§1) |

Ce rapport et `docs/PHASE_I1_DIFF_FROM_BASELINE.patch` s'y ajoutent ensuite.

### 2.3 Hors périmètre, conformément au plan

- **P5 :** non commencée.
- **CLI, `TripProposal`, explications, avertissement de simulation :** relèvent d'I3.
- **Origine, aller-retour, catalogue v2, référentiel des lieux :** relèvent d'I4.
- **Inchangés :** `process_travel_request`, `BrokerAgent`, `Entry.py` et tous les
  fichiers historiques.

---

## 3. Contrats

### 3.1 Adaptateur des journaux (§4.4)

À chaque appel réel, dans cet ordre :

1. `negotiate_detailed` ;
2. `validate_negotiation_outcome`, la même fonction que celle du cache. Un résultat
   refusé ne laisse donc aucun journal ;
3. `check_journal_concordance` (J2) : `request_key`, configuration, statut, montant et
   `router_iterations = turns` ;
4. mémorisation du journal canonique (J1), ou déduplication ;
5. renvoi du résultat.

**Déduplication (§4.4.2).** Une même clé présentée deux fois sans cache est traitée
ainsi :

- **même `journal_sha256` et même résultat :** le journal canonique reste en place, et
  c'est le même objet ;
- **sinon :** `NonDeterministicJournalError`, le magasin n'est pas modifié et aucun
  résultat n'est renvoyé.

**Autres garanties :**

- `journals` est une vue en lecture seule ;
- `oracle_calls` compte les appels réels ;
- une session sert un seul lot.

### 3.2 Marché simulé (§4.5)

`open_simulated_market(catalog_path, reference_date, config=None)` :

- charge le catalogue et ses termes privés ;
- remet les termes au seul `SimulatedNegotiationOracle` ;
- ne renvoie que des objets publics.

L'objet renvoyé ne contient que deux attributs, de types `OfferCatalog` et
`SimulatedNegotiationOracle` (vérifié par un test). Une configuration dont la date de
référence diffère de celle du marché est refusée. Chaque appel à `open_session()`
renvoie un `JournalingNegotiationOracle` neuf.

### 3.3 Planification d'un lot

`plan_lot(PlanningInput, NegotiationMarket) -> TripPlan`.

**Entrée `PlanningInput` :**

- `focus` : un tuple non vide de `PlanningRequest`, prêt pour le mode session (§6.3) ;
- `pool` : un `DemandPoolSnapshot` ou `None` ;
- `reference_date` ;
- `limits`.

Les identifiants doivent être uniques, et disjoints entre premier plan et carnet.

**Règles :**

- **Une demande au premier plan qui ne devient pas une unité.** Le plan prend le statut
  `request_rejected`, avec la raison, le statut, les champs manquants et les erreurs.
  Rien n'est négocié : la règle est « tout ou rien », pour que la composition d'un lot
  ne change jamais en silence.
- **Une demande du carnet qui ne devient pas une unité.** Elle lève `PoolRequestError` :
  c'est une erreur de données, jamais une erreur du voyageur.
- **Sélection du lot :** les unités au premier plan, plus les unités du carnet sur le
  même trajet. En v1, `route_key(unit) = destination_key` ; I4 y ajoutera l'origine et
  le type de trajet.
- **Une session neuve par lot.** Une session qui a déjà des journaux ou des appels est
  refusée, et une configuration différente de celle du marché aussi.
- **Exécution :** `run_formation_stages` est appelé avec un seul
  `CachingNegotiationOracle` au-dessus de la session. Ensuite,
  `verify_journal_invariants` vérifie :
  - **J3 :** chaque tentative retrouve son journal canonique, qui concorde avec elle
    (statut, montant, tours) ;
  - **J4 :** aucun journal n'est sans tentative ;
  - **J5 :** journaux = appels réels = clés distinctes = appels de la session, et
    tentatives = requêtes au cache.

**Sortie `TripPlan` :**

- le statut et les rejets éventuels ;
- les unités du lot et les identifiants des unités du carnet retenues ;
- `stages` (lot, références, formation) ;
- les journaux, en lecture seule, et les compteurs des invariants ;
- la provenance : date, version et SHA du catalogue, `oracle_configuration_id`, version
  et SHA du carnet, `planning_version = "3h-planning-v1"`.

### 3.4 Carnet de demandes (ID-1)

**Format :** JSON Lines. Chaque ligne contient exactement trois clés : `request_id`,
`synthetic` (vrai) et `draft` (les champs de `TravelRequestDraft`).

**Règles :**

- les budgets sont des chaînes ; les nombres décimaux, NaN et Infinity sont refusés ;
- les clés en double sont refusées ;
- les identifiants doivent respecter `pool-[a-z0-9]+(-[a-z0-9]+)*` et être uniques ;
- le manifeste fixe le SHA-256, la version, le catalogue visé et le nombre de demandes.

**Contenu du carnet v1 :** il a été fixé **avant** toute exécution. Les six demandes sont
économiquement identiques au lot figé de `tests/test_coalition_formation.py` :

| Identifiant | Destination | Voyageurs | Budget par personne |
|---|---|---|---|
| `pool-tyo-01` | Tokyo | 1 | 520 € |
| `pool-tyo-02` | Tokyo | 1 | 540 € |
| `pool-tyo-03` | Tokyo | 2 | 500 € |
| `pool-tyo-04` | Tokyo | 1 | 600 € |
| `pool-rom-01` | Rome | 2 | 450 € |
| `pool-rom-02` | Rome | 1 | 330 € |

Le carnet est ainsi rattaché à une ancre de régression qui existe déjà. Un test vérifie
deux bornes :

- au plus 13 demandes par trajet ;
- H2 tenu sur chaque offre du catalogue v1 avec la plus grande demande admise
  (20 voyageurs).

---

## 4. Décisions d'implémentation à valider

1. **Rejet « tout ou rien ».** Si une demande au premier plan est rejetée, rien n'est
   négocié. L'alternative, négocier sans elle, modifierait la composition du lot sans
   le dire.
2. **La route v1 est la destination.** C'est aujourd'hui la seule dimension de trajet
   du modèle.
3. **Python 3.10 dans un fichier séparé.** L'import sous 3.10 des deux nouveaux modules
   n'utilisant que la bibliothèque standard (`journaling_oracle`, `market`) est testé
   dans un nouveau fichier. Ajouter ces modules à la liste de
   `tests/test_python310_compatibility.py` aurait modifié un second test existant.
   Ce n'est pas nécessaire pour la grammaire : le test existant analyse déjà tout
   l'arbre, nouveaux fichiers compris.
4. **Les journaux comme port.** L'application ne voit les journaux qu'à travers un port
   typé (`NegotiationJournalView`), puisqu'elle ne peut pas importer l'infrastructure
   (test de frontières P4).
5. **Invariant de `FormationStages`.** Les références sont absentes **si et seulement
   si** H2 est violée.

---

## 5. Tests

**Suite complète : 724 tests** (662 existants + 62 nouveaux).

| Exécution | Résultat |
|---|---|
| `PYTHONHASHSEED=0 python -m pytest -q` | **724 passed** |
| `PYTHONHASHSEED=2 python -m pytest -q` | **724 passed** |
| Python 3.10 (existant + I1), golden master, contrats historiques, agents | **52 passed** |
| `ruff check` et `ruff format --check` sur les 11 fichiers Python créés ou modifiés | All checks passed ; 11 already formatted |
| `git diff --check` | propre |

### 5.1 Correspondance avec les cas du plan (§7, I1)

| Cas du plan | Test |
|---|---|
| Absence dans le cache | `test_cache_miss_stores_one_canonical_journal_matching_the_outcome` |
| Présence dans le cache | `test_cache_hit_reuses_the_canonical_journal_without_calling_the_oracle` : un seul appel ; même objet journal ; J2 avec le résultat en cache |
| Même clé sans cache, journaux identiques | `test_same_key_twice_without_cache_is_deduplicated` : 2 appels, 1 journal, même objet |
| Même clé sans cache, journaux différents | `test_same_key_twice_with_a_different_result_raises`, dans deux variantes : un autre `journal_sha256`, ou un autre résultat concordant |
| Journal incohérent | `test_an_inconsistent_journal_is_refused_and_nothing_is_stored`, en 5 variantes : clé, statut, montant, configuration, tours. Ni journal ni entrée de cache : l'oracle est rappelé |
| Résultat contraire au contrat | `test_an_outcome_violating_the_contract_leaves_no_orphan_journal` |
| Exception de l'oracle | `test_an_oracle_exception_leaves_no_journal_and_no_cache_entry` |
| Invariants J1 à J5 | lot figé (`test_pinned_lot_satisfies_the_journal_invariants`) ; 4 lots exploratoires, dont une violation de H2 (`test_journal_invariants_hold_on_exploratory_lots`) ; détection de chaque violation (`test_verify_journal_invariants_detects_each_violation` : J3 manquant, J3 discordant, J4, J5 sur les journaux, J5 sur les tentatives, statistiques absentes) |

### 5.2 Non-régression champ par champ

`test_pinned_lot_through_plan_lot_matches_the_pipeline_field_by_field`.

**Montage :** le lot figé couvre deux trajets. On met donc une demande par trajet au
premier plan (`a` pour Tokyo, `e` pour Rome), et les quatre autres dans le carnet.

**Comparaison avec `run_formation_pipeline`,** calculé sur les mêmes unités avec un
oracle neuf :

- chaque champ de `FormationResult`, un par un : blocs, composantes (jeu, solution,
  décomptes), `evaluations`, `unserved`, `unresolved_unit_ids`, totaux,
  `cache_statistics`, `formation_run_id`, `result_sha256` ;
- puis l'égalité complète.

`stages.lot` et `stages.references` sont aussi comparés à un calcul direct.

**Valeurs figées retrouvées :**

- blocs (a, b, c), (d) et (e, f) ;
- totaux 333 720, 322 200 et 11 520 ;
- 10 succès du cache.

### 5.3 Ancre de régression du carnet v1

`test_versioned_pool_plan_is_pinned`. Elle a été calculée une seule fois, avec le carnet
déjà figé, puis fixée.

**Demande de test :** 8 voyageurs pour Tokyo, 500 € par personne. Le lot contient la
demande et les 4 demandes Tokyo du carnet.

| Bloc | Offre | Sièges | Références | Coût négocié | Valeur |
|---|---|---|---|---|---|
| `pool-tyo-01`, `pool-tyo-02`, `pool-tyo-04`, `user` | `tyo-northstar-20270310` | 11 | 5 370,00 € | 5 280,00 € | 90,00 € |
| `pool-tyo-03` | `tyo-northstar-20270310` | 2 | 907,20 € | 907,20 € | 0 |

**Cache :** 72 requêtes, 10 succès, 62 appels réels.

**Observation utile pour I2 et I3, sans défaut ni modification.** Seule, la demande de
test obtient déjà 3 840,00 €, c'est-à-dire 480 € par siège, le prix du palier 6+ du
catalogue. Les 90 € d'économie de la coalition viennent donc de ce que les trois petites
demandes accèdent à ce palier :

| Demande | Référence solo | Prix par siège dans la coalition |
|---|---|---|
| `pool-tyo-01` | 486,00 € (SkyWays) | 480 € |
| `pool-tyo-02` | 504,00 € (Northstar) | 480 € |
| `pool-tyo-04` | 540,00 € (SkyWays) | 480 € |

C'est P5 qui dira quelle part de ces 90 € revient à chacun. Les explications d'I3
devront le rendre lisible, car la grande demande apporte le palier sans gagner elle-même
sur son prix solo.

### 5.4 Statuts et validation

- **Statuts couverts :**
  - violation de H2 (deux demandes de 20 voyageurs pour Rome) : aucune négociation,
    aucun journal ;
  - destination inconnue : `no_admissible_offer`, `no_eligible_units` ;
  - budget sous tous les planchers : `no_solo_reference`, avec ses négociations
    échouées journalisées ;
  - demande incomplète : `request_rejected`.
- **Sélection par trajet :** avec une ou deux demandes au premier plan.
- **Validation des entrées :**
  - identifiants en double ou partagés entre premier plan et carnet ;
  - date de référence différente de celle du marché ;
  - carnet visant un autre catalogue ;
  - demande du carnet invalide (`PoolRequestError`) ;
  - session réutilisée ;
  - cohérence de `TripPlan` et de `FormationStages`.
- **Lecteur du carnet :** 12 formes de ligne malformée, doublons, ligne vide, fichier
  vide, 8 incohérences de manifeste, manifeste absent, UTF-8 invalide, fichier absent.

### 5.5 Mutants d'I1

Le script est `i1_mutants.py`, exécuté sur une copie de travail dans le répertoire
temporaire.

**Résultat final : 17 tués sur 17.**

| # | Défaut réintroduit | Tué par |
|---|---|---|
| 1 | l'adaptateur omet le contrôle de contrat avant la mémorisation | `test_an_outcome_violating_the_contract…` |
| 2 | J2 ignore le nombre de tours | `test_an_inconsistent_journal…[turns]` |
| 3 | la déduplication remplace le journal canonique | `test_same_key_twice_without_cache_is_deduplicated` |
| 4 | la déduplication ignore un résultat différent | `test_same_key_twice_with_a_different_result_raises[outcome…]` |
| 5 | le lot ignore le trajet | `test_versioned_pool_plan_is_pinned` |
| 6 | le rejet n'est plus « tout ou rien » | `test_request_not_ready_is_rejected_without_negotiation` |
| 7 | J3 ignore le nombre de tours | `test_verify_journal_invariants_detects_each_violation` |
| 8 | contrôle J4 supprimé | idem |
| 9 | égalités J5 supprimées | idem |
| 10 | contrôle J5 « tentatives = requêtes » supprimé | idem (*a survécu au premier passage, voir ci-dessous*) |
| 11 | une session déjà utilisée est acceptée | `test_a_session_that_is_not_fresh_is_refused` |
| 12 | l'erreur sur une demande du carnet est ignorée | `test_a_pool_request_that_cannot_become_a_unit…` |
| 13 | le SHA du carnet n'est pas vérifié | `test_manifest_inconsistencies_are_refused` |
| 14 | le carnet accepte les nombres décimaux | `test_malformed_pool_lines_are_refused` |
| 15 | le format des identifiants du carnet n'est pas vérifié | idem |
| 16 | le marché accepte une autre date de référence | `test_market_refuses_an_inconsistent_configuration` |
| 17 | l'invariant de `FormationStages` est supprimé | `test_formation_stages_hold_references_exactly_outside_h2_violations` |

**Correction en cours d'étape (premier passage : 16 sur 17).** Le mutant 10 a survécu
au premier passage. Le cas « tentatives ≠ requêtes au cache » a donc été ajouté au test
de détection, avec le cas « statistiques absentes ». Les tests de l'invariant de
`FormationStages` et de la session neuve avaient été ajoutés avant le passage, après
une relecture des garde-fous non couverts.

---

## 6. Critères d'acceptation d'I1 (plan §7)

| Critère | Résultat |
|---|---|
| Les 662 tests existants passent ; seule exception, l'entrée `market.py` de l'allow-list | **Vérifié directement.** Les 662 tests de la base, dans leur version d'origine, ont été exécutés contre le nouveau code : **661 passed, 1 failed**. Le seul échec est `test_only_allow_listed_modules_touch_private_seller_floors`, parce que `market.py` appelle `load_offer_catalog`. C'est l'exception prévue. Avec l'allow-list mise à jour, les 662 passent, ainsi que les 62 nouveaux |
| L'empreinte exploratoire P4 `997109ee…` est reproduite | **IDENTIQUE.** Le code final d'I1 a été régénéré avec `PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=Multi-Agent .venv/bin/python Multi-Agent/evaluate_formation.py exploratory --output <répertoire temporaire>/i1/exploratory` : code 0, 1 740 instances, 23 min 17 s. Le SHA-256 de `results.json` vaut `997109eee5a9ee4c6567410066730e2f8b5c8dd01bd46ff958b586f4c33eced4`, égal à la valeur publiée sur les 64 caractères. Le rapport Markdown régénéré est identique octet pour octet à `docs/p4_results/exploratory_report.md` (`diff` : code 0) |
| Aucun appel d'oracle en plus | **Vérifié.** `cache_statistics` (requêtes, succès, appels réels) est égal à celui de `run_formation_pipeline`, champ compris dans l'égalité complète de `FormationResult`. Il l'est sur le lot figé et sur les 4 lots exploratoires |
| Invariants J1 à J5, et les sept cas des journaux | **Vérifiés** (§5.1) |
| Non-régression champ par champ | **Vérifiée** (§5.2) |
| Mutants propres à l'étape | **17/17** (§5.5) |
| Golden master, Python 3.10, ruff, `diff --check` | **Vérifiés** (§5) |

---

## 7. Écart exact avec la base

`shasum -a 256 -c docs/PHASE_I1_BASELINE_MANIFEST.sha256` signale **2 fichiers** qui ont
changé :

- `Multi-Agent/coalition_travel/application/coalition_formation.py` (43 lignes changées) ;
- `tests/test_offer_catalog.py` (4 lignes).

Les 139 autres fichiers de la base sont identiques. Aucun fichier de la base n'a été
supprimé. Les fichiers nouveaux sont ceux du §2.2.

Le diff complet par rapport à la copie de la base, nouveaux fichiers compris (`diff -ruN`
sur `Multi-Agent/`, `tests/` et `data/`), est dans
`docs/PHASE_I1_DIFF_FROM_BASELINE.patch`.

---

## 8. Limites et points ouverts

- **Durée.** Une planification du carnet v1 avec une demande de 8 voyageurs prend environ
  16 ms. C'est une mesure indicative sur une seule machine, faite pendant qu'une
  régénération P4 tournait en parallèle ; elle n'entre dans aucun critère. Les
  négociations sont exécutées deux fois, par la vérification de reproductibilité de P3.
- **Contre-offres visibles.** Les journaux montrent les contre-offres du vendeur. C'est
  le risque résiduel accepté au §4.5 du plan : un journal ne contient aucun plancher, ni
  aucun terme privé.
- **Réserves héritées, toujours ouvertes :** arrondis P3, ID-6 (à confirmer au début
  d'I2), durées variables.
- **Aucune opération Git.** L'état de l'arbre est décrit au §7. L'arbre contient
  toujours P2 à P4 non commités, en plus d'I1.

---

## 9. Revue

**I1 est acceptée techniquement** par la revue de ChatGPT (2026-11-19).

- **Portée.** Il s'agit d'une revue statique : rapport, diff et manifeste. Le reviewer
  n'a pas exécuté les commandes lui-même.
- **Ce qui n'est pas autorisé :** démarrer I2 ; toute opération Git.

**Réserves de durcissement.** Elles ne bloquent pas I1 et sont conservées pour une étape
ultérieure. Les deux sont confirmées par lecture du code.

1. **`DemandPoolSnapshot` construit directement.** Son constructeur vérifie seulement
   que le SHA-256 n'est pas vide, pas qu'il compte 64 caractères hexadécimaux. De son
   côté, `plan_lot` vérifie la version du catalogue, pas l'authenticité de la
   provenance. Le parcours normal passe toujours par le lecteur strict.
2. **Décodage du manifeste du carnet.** Dans `load_demand_pool`, le manifeste est
   décodé (`.decode("utf-8")`) sans être enveloppé dans `DemandPoolError`. Un manifeste
   invalide est bien rejeté, mais par `UnicodeDecodeError`. Le fichier JSONL, lui, est
   correctement enveloppé.

**Observation économique transmise à I2 et I3 :** voir §5.3.
