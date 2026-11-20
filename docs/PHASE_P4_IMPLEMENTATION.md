# Phase P4 — Implémentation : formation et optimisation de coalitions

Ce rapport décrit le code P4 réellement présent dans le dépôt. La spécification
normative reste `docs/PHASE_P4_SPECIFICATION.md` : chaque section ci-dessous renvoie à
la section de la spécification qu'elle applique, et les écarts sont listés au §10.

Le rapport explique chaque concept avant de décrire le code qui le réalise. Les
résultats chiffrés du §9 proviennent tous d'exécutions enregistrées ; aucun n'est
estimé ni recopié à la main.

## 0. Ce qui a été livré

| Sous-phase | Contenu livré |
|---|---|
| P4.1 | modèle du jeu : `v`, `v*`, `w`, K = n, P = 1, décodage, garde numérique |
| P4.2 | candidats, faisabilité structurelle, cache économique, coûts collectifs |
| P4.3 | adaptateur des solveurs historiques, orchestration par composante, provenance |
| P4.4 | baselines B1 (glouton) et B0 (Broker historique), re-notation, écart ; adaptateur MILP (P4.4-bis) |
| P4.5 | décomposition des économies, métriques, générateur de scénarios, rapport, lanceur du protocole |

Décisions appliquées : D1 à D9 telles que recommandées dans la spécification ; D10
est un fait (note de nomenclature) ; D11 (implémenter l'IDP et l'IP du cours) reste
hors P4. La répartition des gains (Shapley, projection, arrondi) est P5 et **n'est pas
implémentée**.

Aucun fichier historique (`Multi-Agent/*.py` existant), aucun algorithme historique,
ni le catalogue, ni le golden master n'ont été modifiés. Une seule modification d'un
fichier non historique existant : l'alias public `validate_negotiation_outcome` dans
`application/reference_costs.py` (décision D7), sans changement de comportement.

## 1. Vue d'ensemble

```text
TravelUnit[] + OfferCatalog + date de référence
  │
  ├─ P2  lot_admissibility ──► relation unités × offres, composantes, contrôle H2
  │        └─ H2 violée ──► statut capacity_model_violated, aucun appel d'oracle
  │
  ├─ P2  compute_reference_costs(lot, CachingNegotiationOracle(oracle P3))
  │        └─ ref_u pour chaque unité ; unités sans référence = non servies
  │
  └─ P4  pour chaque composante effective K (ordre des component_id) :
           M1 enumerate_candidates ──► C ⊆ K avec offre commune
           M2 check_structural_feasibility (recalcul indépendant)
           M3 negotiate_candidate (une requête par offre commune, cache)
           M4 build_game ──► jeu (F, v), v({u}) = 0 vérifié
           M5 solve_component ──► idp_search, contrôlé par dp_search et la force brute
         M9 assemble FormationResult (blocs, totaux, statuts, provenance)
```

Modules ajoutés (chemins relatifs à `Multi-Agent/coalition_travel/`) :

| Module | Couche | Rôle |
|---|---|---|
| `domain/coalition_game.py` | domaine | jeu, `v`, `v*`, `w`, décodage, garde numérique (bibliothèque standard seulement) |
| `application/coalition_candidates.py` | application | `FormationLimits`, `CoalitionCandidate`, énumération (M1) |
| `application/coalition_feasibility.py` | application | faisabilité structurelle (M2) |
| `application/negotiation_cache.py` | application | cache (`request_key`, `oracle_configuration_id`) (M3) |
| `application/coalition_costs.py` | application | `c(C)` par l'oracle P3 (M3) |
| `application/partition_solver.py` | application | adaptateur des solveurs historiques (M5) |
| `application/coalition_formation.py` | application | orchestration, résultat, provenance (M9) |
| `application/formation_baselines.py` | application | B1, re-notation, écart à l'optimum (M6) |
| `application/formation_evaluation.py` | application | décomposition des économies, métriques (M7) |
| `infrastructure/optimization/exact_milp.py` | infrastructure | MILP optionnel avec libellés de confiance |
| `infrastructure/baselines/legacy_broker.py` | infrastructure | B0 : Broker historique inchangé |
| `infrastructure/evaluation/formation_scenarios.py` | infrastructure | scénarios synthétiques (seul module P4 qui construit des termes privés, D8) |
| `infrastructure/evaluation/formation_report.py` | infrastructure | `results.json`, `environment.json`, `report.md` (M8) |
| `Multi-Agent/evaluate_formation.py` | script | lanceur des strates performance et exploratoire |

Règles de dépendance (§8.1 de la spécification), vérifiées par
`tests/test_p4_module_boundaries.py` :

- `domain/coalition_game.py` n'importe que la bibliothèque standard ;
- aucun module du domaine ou de l'application n'importe l'infrastructure, les agents
  historiques, Ollama, SQLite, Pydantic ou SciPy ;
- les agents historiques ne sont importés que par `legacy_broker.py` (et par l'oracle
  P3, existant) ; SciPy seulement par `exact_milp.py`.

Le moteur de formation est donc déterministe et totalement indépendant du LLM et du
RAG : ni l'un ni l'autre ne peut influencer une partition.

## 2. Concepts et leur réalisation

### 2.1 Unités, joueurs, coalitions, structures

- Une **unité** (`TravelUnit`, P1) est une demande indivisible : ses profils voyagent
  ensemble ou pas du tout. P4 ne sépare jamais une unité et ne fusionne jamais deux
  unités parce que leurs profils se ressemblent.
- Les **joueurs** N d'une exécution sont les unités qui ont une référence
  individuelle `ref_u` (P2). Les autres sont « non servies », avec leur raison P2
  (`no_admissible_offer`, `no_solo_reference`), et n'entrent pas dans le jeu.
- Une **coalition** C est un ensemble non vide de joueurs ; P4 la représente par le
  tuple trié de ses identifiants (`canonical_coalition`).
- Une **structure** est une partition des joueurs en coalitions disjointes, dont
  l'union est N. Chaque bloc d'une structure correspond à un accord distinct, négocié
  pour `seats(C)` places sur une offre.

### 2.2 Offres communes, anti-monotonie et composantes

`O(C) = common_offers(C)` est l'intersection exacte des offres admissibles de tous les
membres (P2). Elle est **anti-monotone** : ajouter un membre ne peut que retirer des
offres, `O(C ∪ {u}) ⊆ O(C)`. Deux conséquences :

1. **énumération** (M1) : `enumerate_candidates` parcourt les unités triées en
   profondeur et coupe une branche dès que l'intersection est vide, car aucun
   sur-ensemble ne peut plus avoir d'offre commune. Le résultat est exactement
   `{C ⊆ K : C ≠ ∅, O(C) ≠ ∅}`, trié par (taille, identifiants) ; c'est vérifié contre
   une énumération naïve de tous les sous-ensembles ;
2. **composantes** : une coalition qui a une offre commune relie tous ses membres à
   cette offre, donc elle est contenue dans une seule composante connexe du graphe
   P2. Les composantes sont les sous-problèmes indépendants (§2.7).

Une composante n'est pas une clique : dans la chaîne u1–o1–u2–o2–u3, `{u1, u3}` n'a
aucune offre commune et n'est pas candidate (test dédié).

### 2.3 Coût collectif, fonction caractéristique et exclusion

Pour un candidat C (M3, `negotiate_candidate`) :

1. pour chaque offre `o` de `O(C)`, la requête est construite par la seule fabrique P2
   `negotiation_request_for(C, o)` : `seats(C)` places, réservation additive
   `R(C) = Σ B_u`, clé économique `request_key` ;
2. l'oracle P3 négocie ; la réponse est contrôlée par le contrat P2
   (`validate_negotiation_outcome`) ;
3. `c(C)` est le plus petit montant d'accord, départagé par `offer_id`.

`C` est **réalisable** (C ∈ F) si au moins une offre commune aboutit à un accord. La
**fonction directe** est `v(C) = Σ_{u∈C} ref_u − c(C)`, en centimes entiers, définie
seulement sur F : une coalition sans accord **n'a pas de valeur** (représentation par
exclusion, D1). `v(C)` peut être négatif, par exemple quand l'offre commune est moins
bonne pour un membre ou quand la trajectoire de négociation P3, qui dépend de `R(C)`,
est défavorable.

### 2.4 Singletons : `v({u}) = 0` garanti et vérifié

Pour un joueur u, `O({u})` est exactement l'ensemble des offres négociées en P2, la
requête est construite par la même fabrique, et le départage est le même. Avec la
même configuration d'oracle, `c({u}) = ref_u` et donc `v({u}) = 0`. Trois mécanismes le
garantissent :

- le **cache partagé** : `run_formation_pipeline` enveloppe l'oracle dans un unique
  `CachingNegotiationOracle` utilisé pour les références **et** pour les coalitions.
  Les singletons de P4 sont donc des succès de cache (10 sur 10 dans l'exemple du
  catalogue v1) ;
- la **configuration** : `form_coalitions` refuse un oracle dont
  `oracle_configuration_id` diffère de celui des références
  (`OracleConfigurationMismatch`) ;
- la **vérification** : `build_game` lève `GameConsistencyError` si un singleton n'est
  pas évalué ou si `c({u}) ≠ ref_u`. Un test le provoque avec un oracle qui porte la
  même configuration mais donne d'autres prix.

Aucune économie artificielle ne peut donc venir d'une différence de paramètres entre
référence et coalition.

### 2.5 Couverture superadditive `v*`

`v*(S)` est la meilleure valeur d'une partition de S en blocs de F
(`CoalitionGame.cover_values`). Elle est définie parce que tous les singletons sont
dans F. Le calcul est un DP sur les sous-ensembles codés en masques de bits : pour
chaque masque T, on part de `v(T)` si T est réalisable, puis on essaie toutes les
découpes dont le premier bloc contient le plus petit membre de T (règle du pivot), en
parcourant les sous-masques du reste. Coût Θ(3^m), arithmétique entière exacte.

Propriétés vérifiées par les tests sur des jeux aléatoires, et égalité avec la
définition par énumération de toutes les partitions :

1. `v*({u}) = 0` ;
2. `v* ≥ 0` ;
3. superadditivité : `v*(S ∪ T) ≥ v*(S) + v*(T)` si S ∩ T = ∅ ;
4. monotonie ;
5. `v*(C) ≥ v(C)` sur F ;
6. `v*(C) = v(C)` pour tout bloc d'une partition optimale.

En P4, `v*` sert aux propositions et préparera P5 ; aucune répartition n'est calculée.

### 2.6 Poids du solveur, K = n, P = 1

Les solveurs historiques exigent une valeur finie pour **tout** sous-ensemble. P4 leur
fournit `w(C) = K·v(C) − (|C| − 1)` si C ∈ F, et `w(C) = −P` sinon, avec `K = n`
(nombre de joueurs de la composante) et `P = 1` (`CoalitionGame.weight`). Pour une
partition π en blocs de F : `W(π) = K·V(π) − (n − |π|)`.

- **Proposition 1** (K ≥ n) : W ordonne les partitions d'abord par économie `V` en
  centimes, puis par nombre de blocs. Si `V(π) ≥ V(π') + 1`, l'écart de W est au
  moins `K − (n − 1) ≥ 1`. Conséquences : aucune coalition d'économie nulle n'est
  formée, et aucun bloc n'est formé s'il peut être scindé sans perte (test
  `v(abcd) = v(ab) + v(cd)`, où la structure retenue est `{ab}{cd}`).
- **Proposition 2** (K = n est minimal) : sur l'instance « grande coalition = 1 centime
  contre singletons », K = n − 1 donne une égalité et K < n − 1 perd le centime. C'est
  testé pour n = 2 à 8.
- **Proposition 3** (décodage) : `V = ⌈W / K⌉` pour toute partition en blocs de F
  (`decode`, calcul entier `−((−W) // K)`). C'est vérifié sur toutes les partitions
  réalisables de jeux aléatoires.
- **Proposition 4** (pénalité) : un bloc pénalisé n'est jamais dans un maximiseur, car
  le remplacer par ses singletons gagne P. Le résultat ne dépend pas de P : c'est
  testé pour P ∈ {1, 7, 10⁶}, en remplaçant la constante du module.

**Exactitude numérique.** Les solveurs historiques convertissent chaque valeur en
`float` (`_v_idx`) et additionnent des `float`. On note `M = max |w(C)|`, le maximum
étant pris sur F et sur la pénalité (`M ≥ P = 1`).

**Fait utilisé.** Tout entier de valeur absolue au plus 2⁵³ est représentable
exactement en `float` (double précision, mantisse de 53 bits). La somme de deux tels
entiers est calculée exactement dès que la somme exacte reste dans cette plage, et la
comparaison de deux tels entiers est exacte.

**Garde.** `require_numeric_domain` refuse le jeu, **avant** tout appel de solveur,
si `n · M ≥ 2⁵³` (`NumericDomainExceeded`).

**Invariant.** Sous la garde, toute valeur manipulée par un solveur est un entier de
valeur absolue au plus `n · M < 2⁵³` :

- valeur transmise : `|w(C)| ≤ M` ;
- `dp_search` : par récurrence sur la taille, `f[T]` est soit `w(T)`, soit
  `f[T₁] + f[T∖T₁]`, donc toujours la somme des poids des blocs d'une partition de T,
  avec au plus `|T|` blocs : `|f[T]| ≤ |T| · M ≤ n · M`. Chaque somme candidate
  `f[T₁] + f[T₂]` est elle-même une telle somme pour T ;
- `idp_search` : en plus, `0 ≤ UB[k] ≤ max(0, max_{|T|=k} f[T]) ≤ k · M`, donc
  `UB[k₁] + UB[k₂] ≤ (k₁ + k₂) · M ≤ n · M` ;
- force brute : chaque somme partielle porte sur une partie des blocs d'une
  partition, donc `|somme| ≤ n · M`.

Toutes les opérations sont donc exactes : les solveurs calculent les mêmes valeurs
qu'en arithmétique entière.

**Contrôle a posteriori.** L'adaptateur recalcule W en entiers Python à partir de la
structure renvoyée, et exige `float(W_exact) == W_solveur` (`SolverDisagreement`
sinon).

**Test au plus près de la borne.** `test_float_exactness_close_to_two_to_the_53` :
- des poids de `2⁵¹ − 13` (`n · M = 2⁵³ − 52`) donnent des sommes partielles proches
  de 2⁵³, et IDP, DP et la force brute restent exacts ;
- avec des poids de `2⁵¹ + 3`, le jeu est refusé et le solveur n'est jamais appelé.

**Ordre de grandeur réel.** Les montants du projet sont de l'ordre de 10⁵ à 10⁷
centimes : `n · M` y est inférieur à 10¹⁰, très loin de 2⁵³ ≈ 9·10¹⁵.

### 2.7 Décomposition par composante

**Théorème** (spécification §5). Sous H2 (capacité de chaque offre suffisante pour
toutes ses unités admissibles), I1 (indépendance des mandats côté vendeur) et I2 (une
seule configuration d'oracle), l'union des partitions optimales des composantes est
optimale pour le lot.

**Réalisation.** `form_coalitions` résout chaque composante séparément, dans l'ordre
des `component_id`. Avec K = n par composante, le départage global (économie, puis
nombre de blocs) est respecté, car les deux critères s'additionnent sur les
composantes.

**Vérification.** `test_component_decomposition_equals_a_whole_lot_optimum` calcule,
sur 12 lots générés, l'optimum du lot **entier** par énumération de toutes ses
partitions (sans utiliser les composantes), et le compare au résultat P4 : économie
et nombre de blocs identiques.

**Ce qui l'invalide** (rappel) : H2 fausse, vendeur couplé, oracle avec état,
contraintes entre unités ou par offre, disponibilité dans le temps. H2 fausse est
refusée explicitement (`capacity_model_violated`, aucun appel d'oracle, testé).

### 2.8 Solveurs, exactitude et nomenclature

- **`dp_search`** : DP de Yeh (1986) présenté au cours. `f(T)` est le maximum entre
  `w(T)` et les découpes « bloc du pivot + reste ». Il est exact pour toute fonction
  pure ; l'adaptateur garantit cette pureté (consultation d'une table, sans oracle).
- **`idp_search`** : nom historique conservé. C'est un DP **avec élagage par bornes de
  taille**, exact, et non l'IDP de Rahwan et Jennings (2008) présenté au cours
  (chapitre C3b). Il suit la même trajectoire que DP : P4 exige la même valeur **et**
  la même structure à chaque appel (`SolverDisagreement` sinon).
- **Force brute** : énumération des partitions ; contrôle pour n ≤ 9
  (`brute_force_max_units`, configurable jusqu'à 10).
- **MILP** (`exact_milp.py`, optionnel) : partitionnement en nombres entiers résolu par
  HiGHS avec `mip_rel_gap = 0`. Il est distinct de l'« IP » du cours (Rahwan et al.,
  2009). Procédure d'acceptation en 6 étapes (spécification §6.3). Libellés :
  `milp_certified_exact` seulement si W est égal exactement au W d'`idp_search`,
  `milp_solver_optimal` (optimal aux tolérances de HiGHS), `milp_feasible_unverified`
  sinon. La structure officielle vient toujours d'`idp_search`.

**Solveur et contrôles par défaut** : `idp_search`, contrôlé par `dp_search` (même
valeur et même structure) et par la force brute (même valeur) si n ≤ 9. Une composante
d'une seule unité donne directement son singleton, sans appel de solveur.

### 2.9 Cache économique

`CachingNegotiationOracle` mémorise les réponses par (`request_key`,
`oracle_configuration_id`). Comme `request_key` est l'identité **économique** du
mandat (P2-bis : contenu de l'offre, des unités, places, réservation, sans
identifiant technique), deux coalitions formées d'unités différentes mais
économiquement identiques partagent légitimement un même résultat. C'est correct
parce que l'oracle P3 est déterministe et sans état (I1). Une réponse qui viole le
contrat P2 n'est jamais mise en cache. Les statistiques (requêtes, succès, appels
réels) sont informatives et restent hors de tout identifiant.

### 2.10 Baselines

- **B1** (`greedy_b1`) : prend répétitivement le bloc disjoint de F de plus grande
  `v > 0` (départage : moins d'unités, puis identifiants triés). Même F, même v :
  l'écart à l'optimum isole l'effet du solveur exact. Un test construit une instance
  où B1 est sous-optimal (bc = 15 bloque ab + cd = 20).
- **B0** (`run_b0`) : le `BrokerAgent` historique, inchangé :
  - un acheteur par unité, budget = `B_u`, places = `seats(u)` ;
  - seuil de 3, ordre d'arrivée, un Broker par destination ;
  - `negotiate_on_formation=False` ; pas de `finalize_pending` ;
  - 20 ordres d'arrivée par instance ; sortie console capturée.

  Sa structure est **re-notée** dans le jeu P4 (`rescore_structure`) : un bloc de
  plusieurs unités non réalisable, ou qui couvre deux composantes, est compté comme
  non réalisable et ses membres comme singletons. B0 n'est jamais présenté comme
  équivalent à P4.
- **Écart** (`optimality_gap`) : manque absolu `V* − V` toujours défini, écart relatif
  seulement si `V* > 0`. Une baseline qui dépasserait l'optimum est une anomalie
  (`BaselineError`).

### 2.11 Décomposition des économies

Pour un bloc C sur l'offre `o_C`, chaque membre u ayant sa référence sur `o_u`, et
`L(o, s) = list_total(s)` le prix catalogue public, on définit cinq états :

| État | Définition |
|---|---|
| A | `Σ L(o_u, s_u)` |
| B | `Σ ref_u` |
| C₁ | `Σ L(o_C, s_u)` |
| C₂ | `L(o_C, s_C)` |
| D | `c(C)` |

Les termes (`decompose_block`, `SavingsDecomposition`) :

- `savings_individual_negotiation = A − B` ;
- `savings_offer_switch = A − C₁` ;
- `savings_public_tier_pooling = C₁ − C₂` ;
- `residual_collective_negotiation = (C₂ − D) − (A − B)`.

Les identités `v(C) = B − D = offer_switch + tier_pooling + residual` et
`A − D = individual + offer_switch + tier_pooling + residual` sont **vérifiées à la
construction** de chaque objet (`DecompositionMismatch` sinon), en entiers.

`savings_public_tier_pooling ≥ 0` sous les préconditions T1 à T5 : le prix par siège
ne croît pas avec le nombre de places, donc
`Σ s_u·p(s_u) ≥ Σ s_u·p(s_C) = s_C·p(s_C)`. Le prix **total** n'est pas monotone
(contre-exemple testé : `L(2) = 20 000 > L(3) = 18 000`). Tests aux frontières :
t − 1, t, t + 1 ; membres qui franchissent ensemble un seuil ; membre déjà au palier
supérieur ; grille à un seul palier ; capacité atteinte exactement ; test de propriété
sur 500 grilles aléatoires.

Le résidu est un **résidu comptable non identifiable causalement** (`RESIDUAL_LABEL`) :
il mêle le plancher privé du palier collectif, l'avantage de négociation et
l'artefact budgétaire de la stratégie historique. Le rapport impose cette mention.

### 2.12 Protocole expérimental et générateur

Le générateur (`build_scenario`) dérive une graine de SHA-256(cellule | indice). Il
construit les offres (grilles plate, modérée ou forte, planchers de 65 % à 80 % du prix
catalogue), puis les unités :

- **densité** : chaque couple unité–offre est admissible avec la probabilité donnée,
  par exclusion de fournisseur sur le premier profil ; les fenêtres de dates ne
  restreignent jamais ;
- **taux d'accord solo visé** : avec la stratégie P3 par défaut, rejet ⇔ plancher >
  réservation ; le budget par siège est tiré au-dessus du plus petit plancher
  admissible avec la probabilité visée, et strictement en dessous sinon ;
- **hétérogénéité des budgets** : multiplicateur 1,15 × lognormal(σ = cv) ;
- **H2** : capacité = max(⌈demande × (1 + marge)⌉, plus grand seuil de palier) ; la
  famille `h2_violation` force capacité = demande − 1.

Le catalogue est écrit au format P1 puis **rechargé par le chargeur strict P1** : tout
scénario passe donc la validation P1. L'oracle est construit dans le module même, et
seuls des objets publics en sortent (D8).

Strates (spécification §11.3) :

| Strate | Où | Nature |
|---|---|---|
| correction | suite de tests | exhaustive, exigence de 100 % |
| performance | `evaluate_formation.py performance` | durées : médiane et écart interquartile de 5 répétitions après une chauffe ; hors `results.json` |
| exploratoire | `evaluate_formation.py exploratory` | descriptive : 22 cellules en faisant varier un facteur à la fois, 60 cellules tirées au hasard, 5 familles, 20 graines par cellule |
| confirmatoire | non exécutée | exige des hypothèses préenregistrées après l'exploration |

## 3. Fiches des modules

### 3.1 `domain/coalition_game.py` (P4.1)
- `CoalitionGame(component_id, players, references, values, oracle_configuration_id)`.
  Invariants : joueurs triés et uniques ; références = joueurs, entières et positives ;
  `values` = exactement F, triées par (taille, identifiants) ; tout singleton présent
  avec v = 0.
- Méthodes : `value` (KeyError hors de F), `weight`, `decode`, `check_structure`,
  `structure_value`, `structure_score`, `cover_values`, `require_numeric_domain`.
- `build_game(component_id, references, coalition_costs, configuration)` : calcule v,
  ignore les coûts `None` (non réalisables), vérifie les singletons.
- Erreurs : `GameConsistencyError`, `NumericDomainExceeded`.
- Tests : `tests/test_coalition_game.py` (propositions 1 à 4, propriétés 1 à 6 de
  `v*`, validations, dépendances).

### 3.2 `application/coalition_candidates.py`
- `FormationLimits(max_component_units=14, max_offer_neighbourhood=14,
  brute_force_max_units=9)` : limites opérationnelles provisoires (D4).
- `enumerate_candidates(relation, component, limits)` : lève `ComponentTooLarge`
  **avant** toute négociation si la composante, ou le voisinage d'une offre, dépasse
  la limite.
- Tests : `tests/test_coalition_candidates.py`.

### 3.3 `application/coalition_feasibility.py`
- `check_structural_feasibility(candidate, lot, references)` recalcule, sans faire
  confiance à M1 :
  - le lot respecte H2 ;
  - les deux objets viennent du même lot ;
  - tous les membres ont une référence ;
  - le candidat est dans une seule composante effective ;
  - ses offres communes sont exactes ;
  - ses places tiennent dans la capacité.
- Toute contradiction est une anomalie (`CandidateInfeasible`), jamais un statut.

### 3.4 `application/negotiation_cache.py` et `coalition_costs.py`
- `CachingNegotiationOracle(oracle)` exige `oracle_configuration_id` (protocole
  `ConfiguredNegotiationOracle`) et implémente le protocole P2 `NegotiationOracle`.
- `negotiate_candidate(candidate, relation, oracle) -> CoalitionCost`, qui contient
  une tentative par offre commune, triée par `offer_id`. Invariant : coût = plus petit
  accord, départagé par `offer_id` ; sans accord, offre et coût sont `None`.

### 3.5 `application/partition_solver.py`
- `solve_component(game, method="idp", cross_checks=("dp", "brute_force"), limits)`
  renvoie `ComponentSolution` (structure canonique, `value_cents`, `block_count`,
  `tie_break_score`, contrôles exécutés, compteurs, statut).
- Statuts : `optimized`, `no_beneficial_coalition`, `singleton_component`.
- Erreurs : `SolverDisagreement`, `PartitionInvalid`, `NumericDomainExceeded`.

### 3.6 `application/coalition_formation.py`
- `form_coalitions(lot, references, caching_oracle, ...)` et
  `run_formation_pipeline(units, catalog, reference_date, oracle, ...)`.
- `FormationResult` contient :
  - les composantes (avec leur jeu et leur solution), les blocs (`FormedBlock` : unités,
    offre, places, références, coût, valeur) et toutes les évaluations ;
  - les totaux, les unités non servies et les unités non résolues ;
  - le statut, `formation_run_id`, `result_sha256` et les statistiques du cache.
- Statuts globaux : `optimized`, `incomplete`, `capacity_model_violated`,
  `no_eligible_units`.
- Contrôles internes (`FormationConsistencyError`) :
  - Σ références − Σ coûts = Σ valeurs ;
  - somme des valeurs des blocs = somme des optimums des composantes ;
  - un singleton utilise son offre de référence.

### 3.7 Baselines, MILP, évaluation, rapport
- `formation_baselines.py` : `greedy_b1`, `rescore_structure`, `optimality_gap`.
- `legacy_broker.py` : `run_b0`, `arrival_orders` (permutations dérivées de SHA-256).
- `exact_milp.py` : `solve_component_milp(game, certify_with=None) -> MilpSolution`.
  Erreurs : `SolverAnomaly` (statuts 2 et 3), `SolverNotOptimal`,
  `IntegralityViolation`, `PartitionInvalid`, `CertificateFailure`.
- `formation_evaluation.py` : `decompose_block`, `block_decomposition`,
  `structure_decomposition`, `formation_metrics`.
- `formation_scenarios.py` : `ScenarioParameters`, `build_scenario`, `derived_seed`.
- `formation_report.py` : `write_report(document, environment, output_dir,
  volatile_tables)`. Il refuse toute clé contenant « floor », un schéma ou une strate
  inconnus, et un tableau mal formé. Il impose les mentions obligatoires.

## 4. Statuts et erreurs

| Situation | Résultat |
|---|---|
| H2 violée | statut `capacity_model_violated`, aucun appel d'oracle, unités listées comme non résolues |
| composante au-delà des limites | statut de composante `component_too_large` ; statut global `incomplete` ; unités non résolues ; aucune négociation de cette composante |
| aucune unité référencée | `no_eligible_units` (unités non servies listées) |
| aucune coalition profitable | composante `no_beneficial_coalition` (structure en singletons) |
| configuration différente entre références et coalitions | `OracleConfigurationMismatch` |
| `c({u}) ≠ ref_u` | `GameConsistencyError` |
| réponse d'oracle hors contrat | `NegotiationOracleContractError` (P2), non mise en cache |
| désaccord entre solveurs, partition invalide | `SolverDisagreement`, `PartitionInvalid` |

Une exception n'est jamais transformée en statut, et un statut n'est jamais présenté
comme un optimum quand il ne l'est pas.

## 5. Déterminisme et provenance

- Tous les ensembles sont triés par identifiant. L'énumération, les solveurs et les
  départages sont déterministes, et aucune graine n'est cachée. L'invariance par
  permutation des unités en entrée est testée.
- `formation_run_id` = SHA-256 du JSON canonique de : version de l'adaptateur
  (`p4-formation-v1`), `admissibility_id`, `oracle_configuration_id`, références
  (`unit_id`, `ref_u`, offre), méthode, contrôles, règle de départage (K = taille de la
  composante, P = 1), limites, `component_id`.
- `result_sha256` = SHA-256 du JSON canonique du résultat : composantes, structures,
  valeurs, scores, blocs, évaluations avec chaque tentative et sa `request_key`, unités
  non servies et non résolues.
- Aucune durée, aucun horodatage et aucune statistique de cache n'entre dans ces
  empreintes. Deux exécutions et deux `PYTHONHASHSEED` donnent les mêmes empreintes
  (testé).

## 6. Tests

### 6.1 Décompte : fonctions de test et cas exécutés

Une **fonction** de test paramétrée produit plusieurs **cas** exécutés. Le décompte de
pytest (« passed ») compte les cas.

| Fichier | Fonctions | Cas | Ce qu'ils établissent |
|---|---|---|---|
| `tests/test_coalition_game.py` | 17 | 29 | définition de v, exclusion, singletons, propositions 1 à 4, propriétés de `v*`, garde numérique, dépendances |
| `tests/test_coalition_candidates.py` | 10 | 12 | égalité avec l'énumération naïve, chaîne, anti-monotonie, limites, invariance ; faisabilité structurelle |
| `tests/test_negotiation_cache.py` | 8 | 8 | partage économique du cache, contrat, départage, identité avec et sans cache sur l'oracle P3 |
| `tests/test_partition_solver.py` | 10 | 12 | 500 jeux : IDP = DP = force brute = énumération indépendante ; indépendance vis-à-vis de P ; défaillances injectées ; borne 2⁵³ ; deux optimums de même score |
| `tests/test_coalition_formation.py` | 10 | 10 | ancre de régression (catalogue v1), décomposition = optimum du lot entier, refus H2, invariance, configuration, `incomplete`, générateur défaillant |
| `tests/test_formation_baselines.py` | 8 | 8 | B1 ≤ optimum, B1 sous-optimal construit, re-notation, écart, B0 = regroupement historique |
| `tests/test_exact_milp.py` | 5 | 7 | certification exacte, libellés, statuts, intégralité, échec de certificat |
| `tests/test_formation_evaluation.py` | 11 | 18 | frontières de paliers, propriété `E_tier ≥ 0`, identités, métriques à la main, générateur, D8 |
| `tests/test_formation_report.py` | 4 | 8 | déterminisme, mentions, tableaux volatils, règles |
| `tests/test_p4_module_boundaries.py` | 4 | 4 | règles de dépendance, garde D8 |
| **Total des fichiers P4** | **87** | **116** | |
| `tests/test_offer_catalog.py` (modifié) | +1 | +1 | liste blanche figée à 4 entrées (D8) |
| `tests/test_python310_compatibility.py` (modifié) | 0 | 0 | 7 modules P4 ajoutés à la liste importée sous Python 3.10 (même test) |

**Réconciliation des totaux** (cas collectés par pytest) :

| État | Cas | Écart |
|---|---|---|
| HEAD `f2cef07` | 376 | |
| après P2/P2-bis | 461 | +85 |
| après P3/P3-bis | 515 | +54 |
| après la décision `request_key` | 545 | +30 |
| après P4 | **662** | **+117** = 116 (fichiers P4) + 1 (`test_offer_catalog`) |

Le chiffre « 114 » annoncé dans un message intermédiaire était exact à ce moment-là
(659 − 545). Trois tests ont été ajoutés ensuite : deux à la demande de la revue (la
borne 2⁵³ et le générateur de candidats défaillant), et un pour tuer le seul mutant
survivant (§7 : deux optimums de même score). La première version de ce tableau
contenait deux erreurs (baselines 9 au lieu de 8, MILP 8 au lieu de 7). Le total de
116 calculé à partir de ce tableau ne correspondait donc à aucun état réel (il y avait
alors 114 nouveaux cas). Son égalité avec le total actuel des fichiers P4 (116) est
une coïncidence. Le tableau ci-dessus est issu de `pytest --collect-only`, fichier par
fichier, sur l'état final.

### 6.2 Nature des tests

- **Tests unitaires déterministes** (jeux, lots ou offres construits à la main) :
  - singletons, exclusion, statuts, erreurs ;
  - frontières de paliers ;
  - B1 sous-optimal, B0 sur un ordre connu ;
  - instance limite de la proposition 2 ;
  - borne 2⁵³ ;
  - procédure MILP par injection ;
  - règles du rapport ;
  - frontières de modules.
- **Tests de régression** : `test_catalogue_v1_lot_is_pinned` fixe la structure, les
  coûts et les économies du lot du catalogue v1 calculés avec l'oracle P3 réel. Toute
  évolution de P2, P3 ou P4 qui les change doit être expliquée.
- **Tests randomisés à graine fixe** (différentiels ou de propriété ; graines écrites
  dans le code, donc reproductibles) :

  | Test | Instances | Graine |
  |---|---|---|
  | propositions 1, 3, 4 | 60, 80, 50 × 3 pénalités | 7, 31, P |
  | propriétés de `v*` | 80 jeux | 2026 |
  | blocs optimaux, `v* = v` | 40 jeux | 77 |
  | énumération = énumération naïve | 60 relations | 4 |
  | anti-monotonie | 30 relations | 9 |
  | **solveurs** : IDP = DP = force brute = énumération indépendante | **500 jeux**, n de 2 à 9 | 20261119 |
  | indépendance vis-à-vis de P | 40 jeux × 3 pénalités | 55 |
  | B1 ≤ optimum | 200 jeux | 8 |
  | MILP certifié | 60 jeux | 12 |
  | `E_tier ≥ 0` | 500 grilles | 11 |
  | décomposition par composante = optimum du lot | 12 scénarios | 0 à 11 |
  | identités de blocs | 5 + 6 scénarios | 0 à 5 |

- **Déterminisme** : la suite entière est exécutée avec `PYTHONHASHSEED=0` et `=2` ;
  l'invariance par permutation des entrées et la répétition (mêmes empreintes) sont
  testées.

### 6.3 Exécution

Exécutions de la suite finale, sur la machine décrite au §9.1 :

| Commande | Résultat |
|---|---|
| `PYTHONHASHSEED=0 python -m pytest -q` | **662 passed** (39,6 s) |
| `PYTHONHASHSEED=2 python -m pytest -q` | **662 passed** (39,5 s) |
| les 10 fichiers P4 seuls | 116 passed |
| `tests/test_python310_compatibility.py` (interpréteur 3.10 réel, 7 modules P4 importés) | 3 passed |
| golden master + contrats historiques + agents | 48 passed |
| `ruff check Multi-Agent/coalition_travel tests Multi-Agent/evaluate_formation.py` | All checks passed |
| `ruff format --check` (même périmètre) | 93 files already formatted |
| `git diff --check` | aucune sortie |
| `git diff --stat -- Multi-Agent/*.py data/` (fichiers historiques et données) | vide |

Le test le plus coûteux est la comparaison des solveurs sur 500 jeux (environ 25 s),
dont le coût vient surtout de la force brute sur les jeux de 9 unités.


## 7. Contrôle par mutants

**Méthode.** Le dépôt est copié dans un répertoire temporaire, hors du dépôt. Pour
chaque mutant, un seul défaut est réintroduit dans la copie, puis les 9 fichiers de
tests P4 fonctionnels sont exécutés (`pytest -x`, arrêt au premier échec). La copie
est supprimée à la fin ; le dépôt lui-même n'est jamais modifié.

**Premier passage : 16 mutants, 15 tués, 1 survivant.**

| # | Mutant | Résultat | Premier test qui échoue |
|---|---|---|---|
| 1 | K = n − 1 au lieu de K = n | tué | `test_weight_uses_k_equal_n_and_penalty_one` |
| 2 | pénalité P = 0 | tué | `test_weight_uses_k_equal_n_and_penalty_one` |
| 3 | décodage par plancher au lieu du plafond | tué | `test_weight_uses_k_equal_n_and_penalty_one` |
| 4 | contrôle `c({u}) = ref_u` supprimé | tué | `test_singleton_cost_must_equal_the_reference` |
| 5 | élagage qui coupe toute la branche | tué | `test_enumeration_equals_naive_enumeration_on_random_relations` |
| 6 | cache indexé par identifiants d'unités | tué | `test_economically_identical_requests_share_one_oracle_call` |
| 7 | coût collectif = plus grand accord | tué | `test_collective_cost_is_the_lowest_agreement_with_offer_id_tie_break` |
| 8 | aucun contrôle croisé par défaut | tué | `test_exact_solvers_match_an_independent_enumeration_on_500_games` |
| 9 | faisabilité structurelle (défensive) supprimée | tué | `test_a_defective_candidate_generator_is_caught_before_negotiation` |
| 10 | signe des paliers publics inversé | tué | `test_public_tier_pooling_at_tier_boundaries[seats1-12000]` |
| 11 | B0 ignore l'ordre d'arrivée | tué | `test_b0_reproduces_the_historical_fifo_threshold_grouping` |
| 12 | contrôle d'intégralité MILP supprimé | tué | `test_fractional_or_non_partition_solutions_are_rejected` |
| 13 | rapport accepte des clés « floor » | tué | `test_reporting_rules_are_enforced[changes2]` |
| 14 | garde numérique 2⁵³ supprimée | tué | `test_float_exactness_close_to_two_to_the_53` |
| 15 | contrôle « même structure IDP = DP » supprimé | **survivant** | — |
| 16 | mention du résidu absente du rapport | tué | `test_mandatory_notes_are_rendered` |

**Analyse du survivant.** Le mutant 15 n'est **pas équivalent** : sans le contrôle, si
`dp_search` renvoyait une autre structure de même score, P4 l'accepterait. Il survivait
parce qu'aucun test ne créait cette situation. Le test d'injection existant renvoyait
une structure de score différent, déjà rejetée en amont par le recalcul exact. Ajout de
`test_dp_returning_another_structure_with_the_same_score_is_refused` : un jeu à deux
optimums de même score (`{ab}{cd}` et `{ac}{bd}`), avec un `dp_search` injecté qui
renvoie l'autre optimum.

**Second passage (mutant 15 seul) : tué** par ce nouveau test.

**Bilan : 16 mutants, 16 tués après ajout d'un test ; aucun mutant équivalent
identifié.** Les mutants 9 et 15 portent sur des contrôles défensifs, inactifs si les
composants amont sont corrects. Ils sont désormais exercés par injection de
défaillances. Cette campagne ne prouve pas l'absence d'autres défauts. Elle montre que
les invariants principaux (K, P, décodage, singletons, énumération, cache, coût,
contrôles croisés, garde numérique, décomposition, B0, MILP, règles du rapport) sont
chacun protégés par au moins un test qui échoue s'ils sont cassés.


## 8. Exemple commenté (catalogue v1)

Six unités : quatre pour Tokyo (a : 1 place, 520 € ; b : 1, 540 € ; c : 2, 500 € ;
d : 1, 600 €) et deux pour Rome (e : 2, 450 € ; f : 1, 330 €). Résultat, fixé dans
`test_catalogue_v1_lot_is_pinned` :

| Bloc | Offre | Références | Coût | Économie |
|---|---|---|---|---|
| a, b, c (4 places) | tyo-northstar | 1 897,20 € | 1 872,00 € | 25,20 € |
| d | tyo-skyways | 540,00 € | 540,00 € | 0 |
| e, f (3 places) | rom-cloudwing | 900,00 € | 810,00 € | 90,00 € |

Économie totale : 115,20 € sur 3 337,20 € de références. Les deux composantes (Tokyo,
Rome) sont résolues séparément. Chaque solution est contrôlée par DP et par la force
brute. Les 10 négociations solo de P2 sont réutilisées par le cache (10 succès).

## 9. Résultats expérimentaux

Tous les chiffres de cette section proviennent des fichiers `results.json` et
`environment.json` produits par `Multi-Agent/evaluate_formation.py`. Les répertoires
de sortie sont hors du dépôt (§9.4).

### 9.1 Strate performance

**Plan.**
- Tailles n ∈ {6, 8, 10, 12, 14, 16}, 10 instances par taille.
- Cellule : 1 profil par unité, **1 offre**, densité 100, **taux d'accord 100 %**,
  grille modérée. Chaque lot forme une seule composante de n unités ; le voisinage de
  l'offre vaut n, donc le nombre de candidats est maximal, `2ⁿ − 1`.
- Par instance : une exécution de chauffe (durée conservée à part), une exécution de
  contrôle non chronométrée qui vérifie que le résultat instrumenté est identique à
  celui de `form_coalitions`, puis 5 répétitions chronométrées, qui doivent toutes
  donner le même résultat.
- Machine : Apple arm64, macOS 27.0, Python 3.14.2, NumPy 2.4.1, SciPy 1.17.1.
- Empreinte de `results.json` :
  `3024fef1187ece03e97c4da3391b2bb9e7c458f8346fad007402dc29310b0b85`.

**Charge déterministe** (moyennes sur les 10 instances ; partie hachée) :

| n | Statut | Composante | Candidats | Requêtes au cache | Appels réels à l'oracle | Succès du cache |
|---|---|---|---|---|---|---|
| 6 | optimized | 6 | 63 | 69 | 28,3 | 40,7 |
| 8 | optimized | 8 | 255 | 263 | 62,7 | 200,3 |
| 10 | optimized | 10 | 1 023 | 1 033 | 102,6 | 930,4 |
| 12 | optimized | 12 | 4 095 | 4 107 | 164,3 | 3 942,7 |
| 14 | optimized | 14 | 16 383 | 16 397 | 274,5 | 16 122,5 |
| 16 | **incomplete** | 16 | 0 | 16 | 4 | 12 |

**Durée totale** (secondes ; 50 mesures par taille = 10 instances × 5 répétitions) :

| n | Chauffe (médiane) | Médiane | [Q1, Q3] | Maximum |
|---|---|---|---|---|
| 6 | 0,0144 | 0,0143 | [0,0124 ; 0,0154] | 0,0208 |
| 8 | 0,0716 | 0,0710 | [0,0687 ; 0,0723] | 0,0815 |
| 10 | 0,2014 | 0,2009 | [0,1862 ; 0,2117] | 0,2257 |
| 12 | 1,0492 | 1,0450 | [1,0283 ; 1,0525] | 1,0731 |
| 14 | 6,5979 | 6,6323 | [6,5690 ; 6,7045] | 8,3138 |
| 16 | 0,0018 | 0,0017 | [0,0016 ; 0,0018] | 0,0019 |

**Médiane par phase** (secondes ; médiane, sur les instances, des médianes de leurs 5
répétitions ; `oracle_inside` est le temps passé dans l'oracle P3 lui-même, déjà
compté dans `references` et `negotiation`) :

| n | admissibilité | références | énumération | faisabilité | négociation | jeu | `idp_search` | contrôle DP | contrôle force brute | dans l'oracle |
|---|---|---|---|---|---|---|---|---|---|---|
| 6 | 0,0002 | 0,0010 | 0,0002 | 0,0008 | 0,0101 | 0,0002 | 0,0003 | 0,0003 | 0,0010 | 0,0069 |
| 8 | 0,0002 | 0,0011 | 0,0006 | 0,0046 | 0,0350 | 0,0010 | 0,0022 | 0,0025 | 0,0236 | 0,0152 |
| 10 | 0,0003 | 0,0012 | 0,0024 | 0,0244 | 0,1245 | 0,0046 | 0,0212 | 0,0215 | — (n > 9) | 0,0287 |
| 12 | 0,0003 | 0,0013 | 0,0100 | 0,1253 | 0,4925 | 0,0211 | 0,1941 | 0,1992 | — | 0,0490 |
| 14 | 0,0004 | 0,0014 | 0,0416 | 0,6286 | 2,1242 | 0,0946 | 1,8342 | 1,8847 | — | 0,0882 |

**Détail à 14 unités** (médiane des 5 répétitions par instance, en secondes) :
6,58 ; 6,59 ; 6,64 ; 6,65 ; 6,57 ; 4,92 ; 6,89 ; 6,71 ; 6,79 ; 6,53. Les chauffes vont
de 5,00 s à 7,16 s ; la durée maximale mesurée est 8,31 s. Les appels réels à l'oracle
vont de 174 à 359 selon l'instance.

**Lecture des mesures** (constats, sans extrapolation sauf mention contraire) :

1. **D'où vient la croissance.** À 14 unités, sur 6,63 s :
   - environ 3,7 s sont de l'**optimisation** (`idp_search` 1,83 s et contrôle DP
     1,88 s, soit Θ(3ⁿ)) ;
   - environ 2,1 s sont de la **négociation** ;
   - 0,63 s de la **faisabilité structurelle** (recalcul indépendant) ;
   - l'énumération est négligeable (0,04 s).

   Entre 12 et 14 unités, la durée totale est multipliée par 6,3 : le solveur par 9,4
   (3² = 9 attendu) et la négociation par 4,3 (2² = 4 attendu).
2. **Le cache est presque parfait dans cette cellule, et seulement dans cette
   cellule.**
   - À 14 unités, l'oracle n'est réellement appelé que 274,5 fois en moyenne pour
     16 397 requêtes (98,3 % de succès), et le temps passé dans l'oracle n'est que de
     0,088 s.
   - Cette cellule est **homogène par construction** : un profil par unité, de 1 à 4
     places, budgets proportionnels au plancher (cv = 0), une seule offre. Elle ne
     contient donc que quelques contenus d'unité distincts, et beaucoup de coalitions
     sont le même mandat économique.
   - **Ce chiffre n'est pas une performance générale.** Dans la strate exploratoire
     (§9.2), le taux de succès médian du cache est de 24,1 % (quartiles 13,7 % et
     37,5 %). Sur les 234 instances de 1 000 candidats ou plus, il n'est que de
     **1,6 %** en médiane (minimum 0,1 %). Quand les unités sont hétérogènes, l'oracle
     est appelé pour presque chaque couple (C, o).
   - Ici, la phase « négociation » mesure surtout la construction des requêtes
     (JSON canonique et SHA-256 de `request_key`).
3. **Le contrôle DP double le coût de l'optimisation.** Il est conservé par défaut
   (D3) ; le rendre optionnel au-delà d'une taille serait une décision à prendre, pas
   une conclusion de ces mesures.
4. **La garde fonctionne** : à 16 unités, la composante est déclarée
   `component_too_large` en 1,7 ms, sans aucun candidat négocié ; seules les 16
   références solo sont calculées.
5. **La limite de 14 unités est un garde-fou opérationnel**, pas une propriété
   mathématique ni une performance garantie.
   - **Ce qui a été mesuré** : environ 6,6 s par composante de 14 unités, sur une seule
     machine (Apple arm64, Python 3.14.2), dans une seule cellule (une offre,
     densité 100, unités homogènes). C'est le pire cas pour l'énumération et le
     solveur, mais un cas **favorable pour l'oracle** (98,3 % de succès du cache).
   - **Ce qui n'a pas été mesuré** : une composante de 14 unités hétérogènes, dont le
     cache serait presque vide. Estimation, et non mesure : avec le coût d'environ
     0,13 ms par négociation P3 mesuré lors de la préparation de la spécification
     (§6.4), 16 383 appels ajouteraient environ 2,1 s, soit environ 8,7 s par
     composante. Les durées dépendent aussi du nombre d'offres communes par candidat
     et de la machine.
   - **Ce que fait la garde** : `FormationLimits(max_component_units=14,
     max_offer_neighbourhood=14)` est configurable. Au-delà, la composante est déclarée
     `component_too_large`, ses unités sont listées comme non résolues et le lot passe
     en `incomplete`. Rien n'est optimisé en silence (mesuré à 16 unités : 1,7 ms).
   - **Avant tout déploiement**, la limite doit être recalibrée sur la machine et la
     charge cibles. Une mesure complémentaire sur une cellule hétérogène (budgets
     cv = 30, plusieurs profils) est **recommandée et non exécutée** ; elle ne modifie
     pas le banc d'essai déjà réalisé.
   - Par extrapolation seulement (croissance Θ(3ⁿ) du solveur), 15 unités coûteraient
     environ 3 fois plus pour l'optimisation.
6. **Aucun effet de chauffe notable** : la médiane des chauffes est proche de celle
   des mesures (6,60 s contre 6,63 s à 14 unités).

### 9.2 Strate exploratoire (descriptive)

**Statut de ces résultats.** Statistiques **descriptives** d'une exploration. Elles ne
sont ni une validation statistique, ni une confirmation d'hypothèse. Aucune p-valeur
n'est calculée. Les distributions sont synthétiques et ne valent pas pour un marché
réel.

**Plan exécuté.**
- 87 cellules : 22 cellules faisant varier un facteur à la fois autour de la cellule
  de référence (8 unités, 2 profils, 2 offres, marge 50 %, grille modérée, cv 0,
  accord 80 %, densité 60 %), 60 cellules tirées au hasard dans le plan complet
  (graine `p4-exploratory-random-cells-v1`), et 5 familles (null, mutualisation,
  isolated, h2_violation, large).
- 20 graines par cellule (indices 0 à 19), soit **1 740 instances**.
- Pour chaque instance : formation exacte (contrôlée par DP, et par la force brute si
  n ≤ 9), B1, et B0 sur 20 ordres d'arrivée.
- Empreinte de `results.json` :
  `997109eee5a9ee4c6567410066730e2f8b5c8dd01bd46ff958b586f4c33eced4`.

**Populations.** Chaque chiffre de cette section porte sur l'une des populations
suivantes, toutes disjointes ou emboîtées comme indiqué :

| Population | Définition | Instances |
|---|---|---|
| P_all | toutes les instances générées | 1 740 |
| P_ref | lot conforme à H2, références calculées (P_all moins les 20 `capacity_model_violated`) | 1 720 |
| P_block | au moins un bloc formé, donc un taux d'économie défini | 1 616 |
| P_game | au moins une composante résolue, donc un jeu, B1, B0 et une décomposition | 1 616 (**même ensemble** que P_block, vérifié) |
| P_pos | P_game avec `V* > 0` | 1 106 |
| P_zero | P_game avec `V* = 0` | 510 |

Les 124 instances hors de P_block sont :
- 100 `no_eligible_units` : aucune unité référencée, donc ni bloc ni jeu ;
- 20 `capacity_model_violated` : aucun appel d'oracle ;
- 4 `incomplete` : leur seule composante dépasse la limite, et elles ne forment aucun
  bloc.

Ces instances ne contribuent donc **à aucune médiane, aucun quartile, aucune
décomposition ni aucune baseline**. Elles sont seulement comptées dans les statuts.

**Les deux tableaux du `report.md` ne portent pas sur la même population** :
- le tableau par cellule compte toutes les instances (colonne « instances » : P_all de
  la cellule), mais ses médianes, quartiles et colonnes de baselines portent sur
  P_block ou P_game ;
- le tableau de décomposition ne compte que P_block (par exemple 16 au lieu de 20 dans
  la cellule « 2 unités » qui a 4 `no_eligible_units`) ;
- le tableau « grille, cv » ci-dessous ne porte que sur les instances factorielles de
  P_block : 1 540 sur 1 640.

**Statuts.**
- 1 616 `optimized`, 100 `no_eligible_units`, 20 `capacity_model_violated` (toute la
  famille h2_violation ; **0 requête d'oracle**), 4 `incomplete`.
- La colonne « statuts » du `report.md` liste seulement l'**ensemble** des statuts
  d'une cellule. Les 20 cellules mixtes sont détaillées ici :

  | Cellule (n, profils, offres, grille, cv, accord, densité) | optimized | no_eligible_units | incomplete |
  |---|---|---|---|
  | 2, 2, 2, modérée, 0, 80, 60 | 16 | 4 | 0 |
  | 8, 2, 2, modérée, 0, 20, 60 | 16 | 4 | 0 |
  | 4, 3, 2, forte, 30, 80, 30 | 18 | 2 | 0 |
  | 2, 1, 2, modérée, 30, 50, 90 | 15 | 5 | 0 |
  | 4, 1, 5, plate, 10, 50, 30 | 18 | 2 | 0 |
  | 4, 2, 3, plate, 10, 20, 30 | 9 | 11 | 0 |
  | 4, 1, 1, forte, 10, 50, 90 | 17 | 3 | 0 |
  | 2, 3, 3, forte, 30, 100, 30 | 19 | 1 | 0 |
  | 8, 1, 1, modérée, 30, 100, 30 | 18 | 2 | 0 |
  | 8, 1, 2, modérée, 0, 100, 30 | 19 | 1 | 0 |
  | 6, 2, 2, modérée, 0, 50, 30 | 16 | 4 | 0 |
  | 6, 3, 5, forte, 30, 20, 90 | 16 | 4 | 0 |
  | 10, 2, 5, plate, 30, 20, 90 | 19 | 1 | 0 |
  | 2, 3, 2, modérée, 30, 50, 60 | 12 | 8 | 0 |
  | 6, 1, 1, modérée, 30, 50, 60 | 14 | 6 | 0 |
  | 2, 1, 2, modérée, 0, 20, 60 | 5 | 15 | 0 |
  | 6, 1, 5, forte, 10, 20, 90 | 16 | 4 | 0 |
  | 2, 3, 1, forte, 10, 100, 60 | 15 | 5 | 0 |
  | 6, 2, 1, modérée, 0, 20, 30 | 2 | 18 | 0 |
  | famille large : 16, 2, 1, modérée, 0, 80, 100 | 16 | 0 | 4 |

- Les 4 instances `incomplete` (famille large, graines 0, 2, 13 et 14) ont 16, 15, 15
  et 15 joueurs, tous non résolus. La médiane d'économie de la famille large (2,47 %)
  porte donc sur ses **16 instances `optimized` seulement**.

Aucun contrôle croisé n'a échoué : une divergence entre solveurs aurait arrêté
l'exécution. Les 86 lignes de décomposition vérifient toutes l'identité exacte.

**Définitions des colonnes du tableau par cellule** (calculées par `summarize_cells`
de `evaluate_formation.py`) :

| Colonne | Définition exacte | Population |
|---|---|---|
| instances | nombre d'instances de la cellule | P_all |
| statuts | ensemble des statuts présents (effectifs ci-dessus) | P_all |
| taux d'économie médian, [Q1, Q3] | `V / Σ ref_u` (économie totale sur références des unités résolues) ; quartiles par la méthode « inclusive » | P_block |
| coalitions (médiane) | nombre de blocs d'au moins deux unités | P_block |
| B1 sous-optimal `k/m` | k = instances où `V* − V_B1 > 0` ; m = instances de P_game de la cellule | P_game |
| écart relatif B1 max | `max (V* − V_B1) / V*` sur les instances de P_pos de la cellule ; « — » s'il n'y en a aucune | P_pos |
| B0 / optimum (médiane) | médiane de `ρ = V̄_B0 / V*` (voir ci-dessous) | P_pos |
| blocs B0 non réalisables (moyenne) | moyenne, sur les instances, du nombre moyen (sur 20 ordres) de blocs B0 de plusieurs unités hors de F | P_game |
| taux d'accord (C, o) médian | accords / négociations (C, o) tentées ; seules les instances au taux indéfini (aucune négociation) sont omises, un taux nul est compté | P_block |

**Écart relatif de B1.** `g = (V* − V_B1) / V*`, défini seulement si `V* > 0`.

- B1 ne retient que des blocs de valeur strictement positive, donc `V_B1 ≥ 0`. Si
  `V* > 0`, B1 retient au moins un bloc positif, donc `V_B1 > 0` et `0 ≤ g < 1`.
- Si `V* = 0`, aucun bloc n'est positif, donc `V_B1 = 0` (vérifié sur les 510
  instances de P_zero) : l'écart absolu est nul et l'écart relatif n'est pas défini.
  Ces instances sont exclues des écarts relatifs, mais comptées dans le dénominateur
  m de « B1 sous-optimal ».
- Un maximum de 0,5 signifie que, dans au moins une instance, B1 n'obtient que la
  moitié de l'économie optimale.

**Ratio B0 / optimum.** Pour une instance de P_pos :
`ρ = V̄_B0 / V*`, où `V̄_B0` est la moyenne, sur les 20 ordres d'arrivée, de la valeur
de la structure B0 re-notée dans le jeu P4 :
- les blocs réalisables de plusieurs unités apportent leur v, **qui peut être
  négatif** ;
- les blocs non réalisables sont remplacés par des singletons, de valeur 0.

Propriétés et convention :
- **`ρ ≤ 1` toujours**, car la structure re-notée est une partition réalisable, donc
  sa valeur est au plus V* (vérifié par `optimality_gap` à chaque ordre) ;
- **`ρ < 0`** quand B0 forme en moyenne des coalitions qui coûtent plus cher que
  leurs membres séparés ; **`ρ < −1`** quand cette perte dépasse l'économie optimale
  (80 instances) ;
- exemple vérifié, cellule « grille plate » (8 unités, cv 0) : sur 20 instances,
  13 ont `V* > 0`. La médiane −1,0106 est celle d'une instance où V* = 118,26 € et
  V̄_B0 = −119,52 € : B0 y perd en moyenne autant que l'optimum gagne ;
- **instabilité aux très petits optimums** : dans cette même cellule, 6 instances ont
  V* = 0,01 € (artefact d'arrondi, réserve 1) et ρ y atteint −26 650. La médiane
  neutralise ces valeurs, mais une moyenne de ρ n'aurait pas de sens. ρ doit donc
  toujours être lu avec les valeurs absolues V* et V̄_B0, conservées dans
  `results.json` ;
- ρ n'est pas défini si `V* = 0` (P_zero exclue) ; la valeur absolue `V̄_B0` reste
  dans `results.json`.

**Effet d'un facteur à la fois** (taux d'économie médian `V / Σ ref` sur 20 graines ;
les autres facteurs à leur niveau de référence) :

| Facteur | Niveaux → médiane |
|---|---|
| unités | 2 → 0 ; 4 → 0,52 % ; 6 → 1,77 % ; 8 → 2,43 % ; 10 → 2,44 % ; 12 → 2,53 % ; 14 → 2,29 % |
| profils par unité | 1 → 1,71 % ; 2 → 2,43 % ; 3 → 1,03 % |
| offres | 1 → 1,61 % ; 2 → 2,43 % ; 3 → 2,35 % ; 5 → 1,80 % |
| marge H2 | 0 → 1,84 % ; 50 → 2,43 % |
| grille | plate → 0 ; modérée → 2,43 % ; forte → 2,34 % |
| cv des budgets | 0 → 2,43 % ; 10 → 3,69 % ; 30 → 3,20 % |
| accord solo visé | 20 → 0 ; 50 → 0,70 % ; 80 → 2,43 % ; 100 → 2,59 % |
| densité | 30 → 0,97 % ; 60 → 2,43 % ; 90 → 2,06 % |

Le tableau par cellule (médianes, quartiles, B1, B0, taux d'accord) figure dans le
`report.md` de la strate ; il n'est pas recopié ici.

**Hypothèses E2 à E5 confrontées aux observations** (lecture descriptive) :

- **E2 (valeur de l'optimisation exacte)** : sur P_pos (1 106 instances), B1 est
  sous-optimal dans **317 cas (28,7 %)**. Parmi ces cas, l'écart relatif a pour
  médiane 8,1 %, pour troisième quartile 16,2 % et pour maximum 50 %. La fréquence
  augmente avec la taille et la densité : par exemple 18 sur 20 dans la cellule
  « 14 unités, 3 profils, 3 offres, grille forte, cv 10, accord 100, densité 90 ».
- **E3 (B0)** : sur P_game, B0 forme en moyenne **1,71 bloc non réalisable** par
  instance (moyenne sur ses 20 ordres). Sa valeur re-notée moyenne `V̄_B0` est
  **négative dans 470 instances sur 1 616**. Sur P_pos, ρ a pour médiane 0 et pour
  quartiles −0,10 et +0,10 ; ρ < −1 dans 80 instances. Le Broker historique forme des groupes de taille fixe sans
  contrôle d'offre commune ni d'économie : il produit souvent des groupes non
  réalisables ou coûteux. Ce n'est pas une comparaison à armes égales (§7) : B0 n'a
  jamais été conçu pour ce jeu.
- **E4 (paliers)** : sur toutes les instances factorielles, `savings_public_tier_pooling`
  vaut **exactement 0 pour les grilles plates**. Il est positif pour les grilles
  modérées (108 938 €, 39 160 € et 51 179 € pour cv 0, 10 et 30) et fortes
  (84 946 €, 46 179 € et 70 871 €), conformément à la preuve du §2.11.
- **E5 (famille null)** : 13 instances sur 20 ont une économie nulle, et 7 ont une
  économie de **1 à 5 centimes**, sur environ 13 000 € de références. L'hypothèse
  « économie de l'ordre de l'arrondi » est confirmée. Voir la réserve 1 ci-dessous.
- **E6** : relève de la strate performance (§9.1), **dans sa cellule homogène**. À
  14 unités, l'optimisation représente environ 56 % du temps, la tenue des requêtes
  environ 32 %, et l'oracle lui-même environ 1 %. Cette dernière part tient au cache
  presque parfait de cette cellule et n'est pas généralisable (§9.1, point 2).

**Décomposition des économies** (sommes sur les 1 540 instances factorielles de P_block, en
euros ; résidu comptable non identifiable causalement) :

| Grille, cv | Instances | v | changement d'offre | paliers publics | résidu |
|---|---|---|---|---|---|
| plate, 0 | 140 | 4 518 | −6 706 | 0 | 11 224 |
| plate, 10 | 107 | 33 673 | 16 744 | 0 | 16 929 |
| plate, 30 | 119 | 38 859 | −275 | 0 | 39 134 |
| modérée, 0 | 474 | 87 982 | −24 420 | 108 938 | 3 464 |
| modérée, 10 | 140 | 43 690 | −3 304 | 39 160 | 7 834 |
| modérée, 30 | 199 | 55 657 | −4 666 | 51 179 | 9 143 |
| forte, 0 | 80 | 21 760 | −9 368 | 84 946 | −53 818 |
| forte, 10 | 108 | 38 991 | 3 685 | 46 179 | −10 873 |
| forte, 30 | 173 | 72 418 | 876 | 70 871 | 671 |

Sur les 1 616 instances de P_block (toutes familles) : v = 414 430,35 €, paliers publics 441 807,00 €,
changement d'offre −27 747,20 €, résidu 370,55 € (identité exacte vérifiée).
Économie de négociation individuelle (A − B), hors v : 4 117 362,99 €.

**Réserves scientifiques tirées de l'exploration :**

1. **Coalitions à quelques centimes.** 45 instances ont un optimum compris entre
   1 et 10 centimes (38 factorielles, 7 null). Le modèle forme ces coalitions parce
   qu'il maximise l'économie au centime près. Ces centimes viennent de l'arrondi de la
   trajectoire de négociation P3 en flottants, pas d'un effet économique.
   L'optimisation est exacte **pour le jeu donné**, mais un seuil d'économie minimale
   pourrait être une décision métier future. Il n'est pas introduit ici.
2. **Économies sans paliers.** Sur les grilles plates, les économies (jusqu'à 3,2 % en
   médiane avec cv = 30) viennent du changement d'offre et du résidu, pas des paliers.
   Le résidu croît avec l'hétérogénéité des budgets, ce qui est compatible avec
   l'artefact connu : les offres du leader sont des fractions de `R(C)`. Les données ne
   permettent pas d'isoler causalement cet effet (§2.11).
3. **Résidu négatif sur les grilles fortes à budgets homogènes** (−53 818 €) : la
   négociation collective capte moins que l'avantage catalogue des paliers. C'est un
   constat descriptif, sans attribution causale.
4. **Généralisation.** Ces observations portent sur un générateur synthétique et un
   vendeur simulé historique. Elles ne valent pas pour des distributions de demandes
   ou de prix réelles, ni pour des vendeurs dont la stratégie diffère.

### 9.3 Strate confirmatoire

Non exécutée. Elle exige des hypothèses préenregistrées après cette exploration et des
graines disjointes (spécification §11.3).

### 9.4 Artefacts et confidentialité

- Les sorties des strates (catalogues générés, `results.json`, `environment.json`,
  `report.md`) sont écrites **hors du dépôt**. Aucune n'y est présente :
  - aucun `*.manifest.json` de scénario (les seuls manifestes sont ceux de
    `data/catalog/catalog_v1` et des jeux d'évaluation `data/eval/` antérieurs) ;
  - aucun `results.json`, `environment.json` ni `report.md`.
- Les catalogues générés contiennent des termes privés : ils ne doivent jamais être
  versionnés.
- Les fichiers suivis qui mentionnent la clé `seller_floor_per_seat_cents` sont le
  chargeur P1 (`json_catalog.py`), ses tests (`tests/test_offer_catalog.py`) et la
  fixture synthétique `data/catalog/catalog_v1.json`, versionnée depuis P1 par
  conception. Parmi les fichiers non suivis, seul le **code** du générateur
  (`formation_scenarios.py`) la mentionne ; il ne contient aucune donnée.
- `report.md` et `results.json` sont vérifiés par `write_report` : aucune clé
  contenant « floor » n'est acceptée.
- Les deux `report.md` sont copiés tels quels dans `docs/p4_results/`, avec les
  empreintes des `results.json` d'origine (`docs/p4_results/README.md`).



## 10. Écarts par rapport à la spécification

1. `infrastructure/optimization/exact_milp.py` au lieu de `exact_ip.py` : le nom suit
   la décision de nomenclature (MILP ≠ IP du cours).
2. Statut global supplémentaire `no_eligible_units` (aucune unité référencée), plus
   explicite qu'un `optimized` vide.
3. En cas de H2 violée, les unités sont listées dans `unresolved_unit_ids`.
4. Les durées de la strate performance sont des « tableaux volatils », écrits dans
   `environment.json` et dans `report.md`, jamais dans `results.json`, pour que
   l'empreinte des résultats reste un identifiant reproductible.
5. `decompose_block` (fonction pure) a été extraite pour tester la décomposition
   directement à partir d'offres construites.
6. Le taux d'accord piloté par le générateur est le taux d'accord **solo** (existence
   d'une référence). Le taux d'accord sur les couples (C, o) est mesuré, pas piloté.
7. `run_formation_pipeline` est une commodité ajoutée : elle enchaîne P2 et P4 avec un
   cache unique.

## 11. Limites et suites

- Données synthétiques ; vendeur simulé historique ; prix d'accord dépendant des
  budgets (artefact connu) ; aucune généralisation à un marché réel.
- Limites de 14 unités provisoires (D4), à confirmer par la strate performance.
- Coût exponentiel de l'énumération dans la taille des voisinages d'offre : c'est
  l'unique raison de la garde `component_too_large`.
- Strate confirmatoire non exécutée.
- P5 : répartition (Shapley rationnel sur `v*`, projection, arrondi au plus fort
  reste) ; D11 : IDP et IP du cours comme nouvelles fonctions.

## 12. Reproduire

```text
PYTHONHASHSEED=0 python -m pytest -q          # strate correction + tous les tests
PYTHONHASHSEED=2 python -m pytest -q
PYTHONPATH=Multi-Agent python Multi-Agent/evaluate_formation.py performance --output <répertoire>
PYTHONPATH=Multi-Agent python Multi-Agent/evaluate_formation.py exploratory --output <répertoire>
```

Le répertoire de sortie contient les catalogues générés : ils incluent des termes
privés et ne doivent pas être versionnés.
