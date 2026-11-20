# Phase P4 — Spécification : formation et optimisation de coalitions

**Statut : spécification normative, implémentée** (P4.1 à P4.5, et P4.4-bis).
L'implémentation, ses tests, ses écarts et ses résultats sont décrits dans
`docs/PHASE_P4_IMPLEMENTATION.md`. Ce document fixe le modèle mathématique,
l'architecture, le protocole d'évaluation et le découpage ; il fait foi en cas de
divergence. La répartition des gains (§9) relève de P5 et n'est pas implémentée.

Il part du code réel après P1, P2/P2-bis et P3/P3-bis (545 tests verts). Les
mesures ont été faites sur la machine de développement avec le catalogue
synthétique v1 : ce sont des ordres de grandeur, pas des résultats expérimentaux.

**Légende.** Chaque affirmation importante porte une étiquette :

- **[Fait]** : vérifié dans le code ou par une exécution, et reproductible ;
- **[Décision]** : choix d'architecture recommandé ;
- **[Hypothèse]** : à valider par l'équipe ou par l'expérience ;
- **[Hors périmètre]** : exclu de P4.

## Sommaire

0. Résumé des décisions
1. Audit de l'existant (B1)
2. Objectif fonctionnel (B2)
3. Définition formelle du jeu (B3)
4. Départage, choix de K et exactitude numérique
5. Hypothèse H2 et décomposition par composante (B4)
6. Formation, solveurs et limites de taille (B5)
7. Baselines (B6)
8. Architecture applicative (B8)
9. Répartition des gains et Shapley (B9)
10. Cache, déterminisme et provenance (B7)
11. Évaluation scientifique et démonstration AI Engineering (B10)
12. Sous-phases et dépendances (B11)
13. Préservation de l'historique scientifique (B12)
14. Cohérence avec P2/P3 et contradictions relevées
15. Décisions ouvertes, hypothèses et hors périmètre

## 0. Résumé des décisions

1. **[Décision]** Joueurs = unités ayant une référence P2 `ref_u`.
2. **[Décision]** Représentation par **exclusion**. Une coalition est réalisable si
   elle a une offre commune admissible et au moins un accord P3 sur l'une d'elles ;
   seules les coalitions réalisables ont une valeur `v(C) = Σ ref_u − c(C)`, en
   centimes entiers.
3. **[Décision]** L'optimiseur travaille sur `w(C) = K·v(C) − (|C| − 1)` avec `K ≥ n`
   (recommandé : `K = n`). Une coalition non réalisable reçoit une pénalité
   technique `−1`, qui reste interne à l'adaptateur.
4. **[Décision]** L'optimisation est faite composante par composante. C'est valide
   sous H2 et sous l'indépendance des mandats côté vendeur (§5).
5. **[Décision]** Solveur par défaut : `idp_search` historique, inchangé. C'est un
   DP avec élagage par bornes, et non l'IDP du cours (§6.3). `dp_search` et la force
   brute servent de contrôles exacts. Le MILP est optionnel : il n'est qualifié
   d'optimum exact que s'il est certifié par égalité avec `idp_search`.
6. **[Décision]** La répartition est faite par Shapley sur la couverture
   superadditive `v*` restreinte au bloc retenu, en arithmétique rationnelle. Les
   paiements négatifs sont évités par projection (vecteur unique, convention
   déterministe pour λ), et l'arrondi au centime se fait par la méthode du plus
   fort reste. Implémentation : P5, hors P4.
7. **[Décision]** Toute négociation passe par un cache indexé par
   (`request_key`, `oracle_configuration_id`), partagé avec les références P2.
8. **[Hypothèse]** Limite opérationnelle provisoire et configurable : 14 unités par
   composante et par voisinage d'offre (§6.4).
9. **[Décision]** Décomposition des économies en quatre termes exacts. Le dernier,
   `E_residual_collective`, est un **résidu comptable non identifiable causalement**
   (§11.5).

## 1. Audit de l'existant (B1)

### 1.1 Matrice de réutilisation

| Élément | Où | Constat **[Fait]** | Décision P4 |
|---|---|---|---|
| Monnaie en centimes | `domain/money.py` (P1) | entiers ; conversions exactes et monotones | direct |
| `TravelUnit`, consolidation | `domain/travel_unit.py`, `application/profiles.py` (P1) | unité indivisible ; consolidation interne à l'unité | direct |
| Catalogue public / termes privés | `domain/offer.py`, `infrastructure/catalog/json_catalog.py` (P1) | paliers par siège dont le prix ne croît pas avec le nombre de places (`_validate_tier_sequence`) ; planchers privés protégés par une garde AST | direct |
| Admissibilité, graphe, H2 | `domain/admissibility.py`, `domain/offer_graph.py`, `application/lot_admissibility.py` (P2) | politique fermée ; `common_offers` exact ; composantes sans sommet isolé ; H2 vérifiée avant toute négociation | direct |
| Fabrique de requête, `request_key` | `domain/negotiation_request.py` (P2-bis) | seule fabrique ; réservation additive ; clé économique canonique v2 | direct, obligatoire |
| Références individuelles | `application/reference_costs.py` (P2) | `ref_u` = plus bas accord solo ; la validation du contrat d'oracle est la fonction **privée** `_validate_outcome` | direct (voir décision ouverte D7) |
| Oracle simulé | `infrastructure/negotiation/` (P3/P3-bis) | fidèle à l'historique ; déterministe ; expose l'attribut `oracle_configuration_id`, que le protocole P2 ne déclare pas | direct, derrière le cache |
| `dp_search` | `domain/partition_optimization.py` | exact ; appelle `v` sur les 2ⁿ−1 sous-ensembles ; exige des valeurs finies ; départage par `>` strict selon l'ordre d'énumération ; renvoie (valeur, structure, compteur), pas sa table interne | adaptateur |
| `idp_search` | idem | DP avec élagage par bornes de taille ; renvoie la même valeur **et** la même structure que DP (1 000 jeux aléatoires, valeurs négatives comprises) | adaptateur ; défaut |
| `brute_force_search` | idem | énumère toutes les partitions ; limité à 10 agents par défaut | adaptateur ; oracle de validation |
| `ip_search` (MILP) | `infrastructure/optimization/scipy_ip.py` | programme linéaire en nombres entiers, pas l'IP anytime du cours ; une colonne par sous-ensemble ; ne fixe aucune option ; HiGHS : `mip_rel_gap` = 1e-4 par défaut | conservé pour l'existant ; nouvel adaptateur IP |
| `CoalitionOptimizationService` | `application/optimization.py` | IDP + force brute ; tolérance flottante 1e-9 | conservé pour l'existant |
| `validate_partition` | `domain/partition.py` | couverture exacte et blocs disjoints | direct |
| `shapley_value` | `domain/cooperative_game.py` | formule exacte, poids en flottants ; `v` doit être défini sur tous les sous-ensembles | oracle de test différentiel en P5 |
| `allocate_shapley_payments` | idem | paiement = part égale − (φ − moyenne φ) ; écrêtage par budget itératif en flottants | remplacé |
| `CoalitionProblem.value` | `domain/coalition_problem.py` | économie = budget total × remise par taille | baseline historique (démos) |
| `BrokerAgent` | `BrokerAgent.py` | file par destination ; coalition dès que `coalition_size` (3) est atteint, dans l'ordre d'arrivée | baseline B0 |
| `CoalitionLeaderAgent.negotiate_for_group` | `Leader.py` | voir §1.2 | remplacé |
| Golden master d'`Entry.py` | `tests/test_entry_golden_master.py` | fige la sortie historique | intouchable |

### 1.2 Ce qui ne doit pas être réutilisé, et pourquoi

- **`negotiate_for_group()`** :
  - la remise est une **entrée** fixée avant la négociation
    (`group_min_fare × q × (1 − discount)`), alors qu'elle devrait en être le
    résultat : c'est circulaire ;
  - le plancher vient d'un tarif global, pas des termes de l'offre ;
  - le plafond `min(budget total, plus petit plafond × q)` mélange budget
    individuel et collectif ;
  - le prix initial vaut 1,4 × plancher ;
  - la méthode affiche et modifie `payment_due` ;
  - Shapley y est calculé sur budget × remise.

  Sa règle de décision `receive_message` est reproduite exactement par
  `MandateLeader` (P3-bis).
- **`CoalitionProblem.value`** : une coalition plus riche « économise » plus sans
  aucune négociation, ce qui est contraire à B3.
- **Le Broker comme optimiseur** : formation selon l'ordre d'arrivée, taille fixe,
  seule la destination est contrôlée à l'inscription simple, aucune optimisation, et
  des valeurs qui ne viennent pas d'une négociation.
- **`allocate_shapley_payments`** : règle non reliée à `ref_u`, sans garantie
  `paiement ≤ ref_u`, et en flottants.

### 1.3 Ce qui manque

Énumération des candidats ; contrôle de faisabilité structurelle ; cache ; coûts
collectifs ; modèle du jeu ; adaptateur de solveur ; orchestration et provenance ;
baselines ; scénarios, métriques et rapport. Le détail est au §8.

## 2. Objectif fonctionnel (B2)

```text
TravelUnit[] ─► P2 lot_admissibility ─► H2 ─► P2 compute_reference_costs (oracle P3 + cache)
                                               │  joueurs N = unités référencées
                                               ▼
               P4, par composante effective K :
                 candidats C ⊆ K tels que common_offers(C) ≠ ∅
                 faisabilité structurelle (recalcul indépendant)
                 négociation de chaque (C, o) par negotiation_request_for (cache)
                 jeu (F_K, v) ─► partition optimale de K
                                               ▼
               structure + offre et coût de chaque bloc + provenance ─► (P5) répartition
```

Invariants métier **[Décision]** :

- une unité reste indivisible et n'est jamais fusionnée avec une autre parce que
  leurs profils se ressemblent ;
- une coalition négocie une offre commune admissible, pour `seats(C)` places, avec
  `R(C) = Σ B_u`, et uniquement via `negotiation_request_for` ;
- aucune valeur ne provient d'une offre seulement admissible.

## 3. Définition formelle du jeu (B3)

### 3.1 Fonction directe sur les coalitions réalisables

- `N` : unités référencées de la relation effective P2.
- `O(C) = common_offers(C)`.
- `A(C) = { o ∈ O(C) : la négociation de (C, o) aboutit à un accord }`.
- `F = { C ⊆ N, C ≠ ∅ : A(C) ≠ ∅ }`.
- `c(C) = min_{o ∈ A(C)} montant(C, o)`, départage par `offer_id`.
- **Fonction directe** : `v : F → ℤ`, `v(C) = Σ_{u∈C} ref_u − c(C)`.

**[Fait]** `v` peut être négatif : l'offre commune peut être moins bonne pour un
membre, et la trajectoire de négociation de P3 dépend de `R(C)`. Le jeu n'est donc
ni superadditif ni monotone en général.

### 3.2 Singletons

`O({u}) = offers_for(u)` contient exactement les offres négociées en P2, avec la
même fabrique et le même oracle. Donc `c({u}) = ref_u` et `v({u}) = 0`.

**[Décision]** P4 vérifie que la configuration d'oracle est la même et que
`v({u}) = 0`. Sinon il lève `GameConsistencyError` ; il ne produit jamais
d'économie artificielle.

### 3.3 Couverture superadditive `v*`

**Définition.** Pour `S ⊆ N` :
`v*(S) = max { Σ_{B∈π} v(B) : π partition de S en blocs de F }`, et `v*(∅) = 0`.

**Existence.** `v*` est défini pour tout `S` **si et seulement si** tous les
singletons de `S` sont dans F. C'est garanti pour les joueurs de N (§3.2).

**Propriétés** (preuves directes) :

1. `v*({u}) = 0`, car la seule partition est `{u}`.
2. `v*(S) ≥ 0`, car la partition en singletons vaut 0.
3. **Superadditivité** : pour `S ∩ T = ∅`, `v*(S ∪ T) ≥ v*(S) + v*(T)`. La
   concaténation d'une partition optimale de S et d'une partition optimale de T est
   une partition de `S ∪ T` en blocs de F.
4. **Monotonie** : si `S ⊆ T`, alors `v*(T) ≥ v*(S) + v*(T∖S) ≥ v*(S)`, par 3 puis 2.
5. `v*(C) ≥ v(C)` pour `C ∈ F`, en prenant `π = {C}`.
6. Si C est un bloc d'une partition optimale, `v*(C) = v(C)`. Sinon, remplacer C par
   sa meilleure partition augmenterait la valeur totale.

### 3.4 Fonctions utilisées par chaque composant

| Composant | Fonction | Domaine |
|---|---|---|
| Définition métier, rapports | `v` | F seulement |
| Optimiseur (adaptateur) | `w(C) = K·v(C) − (|C|−1)` si `C ∈ F`, `−1` sinon | tous les sous-ensembles de la composante |
| Valeur optimale | `V*(K) = v*(K)` | composante |
| Répartition (P5) | `v*` restreinte aux sous-ensembles du bloc retenu | `2^C` |

### 3.5 Exclusion ou pénalité : conséquences et décision

- **Pénalité** (`v = −P` hors de F) :
  - sans effet sur l'optimum pour tout `P > 0` (§4, proposition 4) ;
  - mais elle fausse la répartition. Exemple **[Fait]** (calcul exact) :
    C = {a, b, c}, F contient les singletons, `{a, b}` avec `v = 6` et `{a, b, c}`
    avec `v = 9`. Shapley sur la fonction complétée par la pénalité donne
    (9/2, 9/2, 0) pour P = 3, et (9, 9, −9) pour P = 30. L'allocation dépend donc
    d'un paramètre arbitraire.
- **Exclusion** :
  - sémantiquement exacte ;
  - `v*` complète le jeu sans paramètre : une sous-coalition non réalisable vaut ce
    qu'elle obtient en se réorganisant en coalitions réalisables, au minimum 0.
    Sur l'exemple, Shapley de `v*` donne (4, 4, 1), quel que soit P.

**[Décision]** Exclusion. La pénalité n'existe que dans l'adaptateur des solveurs,
et aucune valeur pénalisée n'en sort.

### 3.6 Rationalité et cas limites

- **Blocs formés.** Une partition optimale n'a aucun bloc avec `v < 0`. Avec le
  départage du §4, aucun bloc non singleton n'a `v = 0`. Tout bloc formé vérifie
  donc `c(C) < Σ ref_u`.
- **Pas d'accord collectif** : `C ∉ F`. La coalition compte dans les taux d'accord et
  de réalisabilité, mais n'a pas de valeur.
- **Aucune coalition profitable** : structure en singletons, statut
  `no_beneficial_coalition`. C'est un résultat valide.
- **Unités sans référence** : hors du jeu, rapportées avec leur raison P2.
- **Arrondis** : tous les montants sont des centimes entiers, issus de la conversion
  unique de P3.

## 4. Départage, choix de K et exactitude numérique

Notations, pour une composante de `n` unités :

- π est une partition en blocs de F ;
- `V(π) = Σ_{C∈π} v(C) ∈ ℤ` ;
- `b(π) = |π|`, le nombre de blocs ;
- `d(π) = n − b(π) ∈ [0, n − 1]`.

Avec `w(C) = K·v(C) − (|C| − 1)`, on a `W(π) = Σ w(C) = K·V(π) − d(π)`.

**Proposition 1 (ordre lexicographique).** Si `K ≥ n`, alors pour toutes
partitions π, π' :
`W(π) > W(π')` ⇔ `V(π) > V(π')`, ou `V(π) = V(π')` et `b(π) > b(π')`.

*Preuve.*

- Si `V(π) ≥ V(π') + 1` (valeurs entières), alors
  `W(π) − W(π') ≥ K − (d(π) − d(π')) ≥ K − (n − 1) ≥ 1`.
- Si `V(π) = V(π')`, alors `W(π) − W(π') = b(π) − b(π')`.
- Le sens inverse se déduit par symétrie. ∎

Conséquences : on maximise d'abord l'économie en centimes, puis le nombre de blocs.
Aucun bloc d'économie nulle n'est formé, et aucun bloc qui pourrait être scindé sans
perte.

**Proposition 2 (borne minimale).** Pour `n ≥ 2` et `K ≤ n − 1`, la propriété peut
échouer.

*Instance :* F = singletons + la grande coalition, avec `v = 1` centime. Alors
`W(grande) = K − (n − 1)` et `W(singletons) = 0`.

- Si `K < n − 1`, les singletons sont strictement préférés : on perd 1 centime.
- Si `K = n − 1`, il y a égalité, et le résultat dépend du traitement des égalités
  par le solveur. **[Fait]** DP et la force brute historiques choisissent ici la
  grande coalition, parce qu'ils l'évaluent en premier ; l'objectif, lui, ne le
  garantit pas (un MILP pourrait renvoyer les singletons). ∎

**La borne minimale est donc `K = n`.** **[Décision]** `K = n`, calculé par
composante.

**Proposition 3 (décodage).** Pour toute partition π telle que `d(π) < K` :
`V(π) = ⌈W(π) / K⌉`.

*Preuve :* `W/K = V − d/K` avec `0 ≤ d/K < 1`. ∎

Conditions de validité :

- π ne contient que des blocs de F ;
- `K ≥ n`, ce qui donne `d(π) ≤ n − 1 < K` pour toute partition.

Pour la valeur optimale d'un sous-ensemble T de la composante, la partition
W-optimale de T est en blocs de F (proposition 4) et V-optimale (proposition 1
appliquée à T, avec `|T| ≤ n ≤ K`). Donc `v*(T) = ⌈W*(T) / K⌉`. La formule est
fausse pour une partition qui contient un bloc pénalisé.

**Proposition 4 (pénalité).** Si tous les singletons sont dans F et que
`w(C) = −P` (avec `P > 0`) pour `C ∉ F`, aucun maximiseur de W ne contient de bloc
hors de F, et `max W` ne dépend pas de P.

*Preuve :* remplacer un bloc hors de F par ses singletons augmente W de `P > 0`. ∎

**[Décision]** `P = 1`, le plus petit entier positif.

**Exactitude numérique.** Les solveurs additionnent des `float`. Des entiers de valeur
absolue inférieure ou égale à 2⁵³, et leurs sommes partielles dans cette plage, sont
exacts. Bornes :

- `v(C) ∈ [−Σ_{u∈C} B_u, Σ_{u∈C} ref_u]`, car `c(C) ≤ R(C)` ;
- donc `|W| ≤ K·Σ_u B_u + n·P`.

Avec `K ≤ 14`, `n ≤ 14` et `B_u ≤ MAX_CENTS = 10¹¹`, on obtient moins de
`2·10¹³ ≪ 9·10¹⁵`. **[Décision]** L'adaptateur vérifie quand même cette borne :
une violation lève une exception et ne peut pas arriver dans les limites fixées.

**[Fait]** Vérification hors dépôt sur 400 jeux aléatoires (n ≤ 7), avec les trois
solveurs historiques inchangés et `P ∈ {1, 7, 10⁶}` :

- même optimum ;
- aucun bloc non réalisable ni d'économie nulle ;
- `V = ⌈W/K⌉` ;
- nombre de blocs maximal parmi les partitions d'économie optimale.

Ce contrôle a été fait avec `K = n + 1`, ce qui satisfait aussi `K ≥ n`.

## 5. Hypothèse H2 et décomposition par composante (B4)

**Rappel [Fait].** `uncoupled_v1` : `capacity(o) ≥ Σ_{u ∈ N(o)} seats(u)` pour toute
offre `o`. Elle est vérifiée par `lot_admissibility`, et `require_optimizable()`
bloque toute négociation si elle échoue.

**Hypothèses de décomposition :**

- **(H2)** ci-dessus ;
- **(I1) Indépendance des mandats** : le résultat de la négociation de (C, o) ne
  dépend que de (C, o) et de la configuration d'oracle ; le vendeur n'a ni stock
  partagé, ni prix dépendant des autres mandats, ni mémoire. **[Fait]** pour la
  simulation P3 (agents neufs à chaque appel, double exécution vérifiée) ;
  **[Hypothèse]** pour un vendeur réel ;
- **(I2) Configuration unique** pour les références et les coalitions.

**Lemme 1 [Fait, testé en P2].** Toute coalition C de F est contenue dans une seule
composante. En effet, ses unités sont toutes reliées à une offre commune.

**Lemme 2.** Sous (H2) et (I1), une famille de blocs disjoints peut être réalisée
simultanément, chacun avec son offre optimale. Pour une offre `o`, les blocs qui la
choisissent sont des sous-ensembles disjoints de `N(o)`, donc
`Σ seats ≤ Σ_{u∈N(o)} seats(u) ≤ capacity(o)`. Par (I1), le coût de chaque bloc ne
dépend pas des autres.

**Théorème.** Si `π*_j` est optimale pour la composante `K_j`, alors `π* = ∪_j π*_j`
est optimale pour N, et `V*(N) = Σ_j V*(K_j)`.

*Preuve.*

1. Toute partition réalisable π de N se décompose en `π_j = {C ∈ π : C ⊆ K_j}`
   (lemme 1).
2. Donc `V(π) = Σ_j V(π_j) ≤ Σ_j V(π*_j) = V(π*)`.
3. `π*` est réalisable (lemme 2). ∎

Le départage se décompose aussi : l'économie totale est maximale si et seulement si
chaque `V_j` l'est. Parmi ces partitions, le nombre total de blocs est maximal si et
seulement si chaque `b(π_j)` l'est. On peut donc prendre `K_j = n_j` par composante.

**Ce qui invalide la décomposition :**

- **H2 fausse.** Deux blocs qui choisissent la même offre peuvent en dépasser la
  capacité. Ces blocs sont dans la même composante : la séparation entre composantes
  reste valide. En revanche, à l'intérieur d'une composante, `c(C) = min` n'est plus
  valide, et le choix d'offre devient une variable.
- **Vendeur couplé** : stock commun, prix fonction de la demande totale,
  négociations séquentielles qui s'influencent.
- **Oracle avec état** : apprentissage ou cache non économique.
- **Contraintes entre unités** : « voyager ensemble » ou « pas ensemble », budget
  partagé entre unités, alors que les unités sont indépendantes par définition.
- **Contraintes globales par offre** : taille minimale de groupe, quotas fournisseur.
- **Disponibilité dans le temps.**

**Comportement si H2 est fausse [Décision].** Refus `capacity_model_violated`, avec
les `CapacityCheck` en échec : aucune optimisation partielle, aucune capacité
ignorée. Retirer des unités non référencées ne peut pas casser H2, car la demande ne
fait que baisser.

**Modèle futur [Hors périmètre].** Partitionnement avec affectation :
`x_{C,o} ∈ {0,1}`, couverture exacte, et `Σ_C seats(C)·x_{C,o} ≤ capacity(o)`. Un MILP
est naturelle ; le DP par sous-ensembles ne s'applique plus. Si la valeur d'un bloc
dépend des autres, le jeu devient un **jeu à fonction de partition**, et
l'optimisation par composante avec `c(C) = min` n'est plus correcte.

## 6. Formation, solveurs et limites de taille (B5)

### 6.1 Candidats

**[Fait]** `O` est anti-monotone : `O(C ∪ {u}) ⊆ O(C)`.

**[Décision]** Énumération en profondeur sur les unités triées de la composante,
avec coupure dès que l'intersection est vide. C'est équivalent à l'union, sur les
offres, des sous-ensembles non vides de `N(o) ∩ K`. Nombre de négociations :
au plus `Σ_o (2^{|N(o)∩K|} − 1)`.

### 6.2 Problème

- Maximiser W sur les partitions de K (couverture exacte, blocs disjoints).
- Décoder `V = ⌈W/K⌉`.
- Rapporter V et la structure.
- Une composante d'une seule unité donne directement son singleton.

### 6.3 Exactitude des solveurs

**DP (`dp_search`).**

- *Exactitude algorithmique* : récurrence
  `f(T) = max(w(T), max_{T₁ ∋ pivot(T), ∅ ≠ T₁ ⊊ T} f(T₁) + f(T∖T₁))`. Toute
  partition de T à au moins deux blocs s'écrit (bloc du pivot) + (partition du
  reste), ce qui rend la récurrence exacte pour des valeurs réelles quelconques.
- *Préconditions* :
  - vérifiées par le code : agents uniques et hachables ; valeurs finies et non
    booléennes ;
  - **non vérifiées** : la fonction doit être pure et déterministe. L'adaptateur le
    garantit en passant une table précalculée.
- *Exactitude numérique* : garantie dans la borne du §4.
- *Départage* : `>` strict, ordre d'énumération sur les agents triés.
- *Validation* : `validate_partition` est appelée par le code ; l'adaptateur
  revérifie aussi que chaque bloc est dans F et recalcule W en entiers.

**`idp_search` (nom historique conservé).**

- *Exactitude algorithmique* : DP + saut des paires de tailles (k₁, k₂) telles que
  `UB[k₁] + UB[k₂] ≤ meilleur courant`, avec `UB[k] = max(0, max_{|T|=k} f(T))`.
  Toutes les tailles inférieures sont complètes avant usage, donc `UB` majore toute
  valeur de sa taille. Une découpe sautée ne peut pas améliorer strictement, et les
  remplacements exigent une amélioration stricte. `idp_search` suit donc exactement
  la trajectoire de DP.
- **[Fait]** Même valeur et même structure que DP sur 1 000 jeux aléatoires, valeurs
  négatives comprises.
- Préconditions, exactitude numérique et validation : comme DP.

**Note académique sur la nomenclature [Fait].** Le support de cours *Coalition
Structure Generation in Multi-Agent Systems* (S. Aknine, chapitre C3b,
diapositives 18 à 25) présente :

- le **DP** de Yeh (1986) : essayer toutes les découpes en deux, puis résoudre
  chaque moitié. C'est ce que fait `dp_search` ;
- l'**IDP** de Rahwan et Jennings (2008) : il « supprime les arêtes rouges du graphe
  des structures de coalitions ». Sur l'exemple à 4 agents, les coalitions de taille
  3 ne sont pas découpées ; seules les découpes des tailles 2 et de la grande
  coalition sont évaluées (annotation « 2n/3 »).

L'algorithme historique `idp_search` ne suit pas cette règle. Il évalue toutes les
tailles, et saute seulement les paires de tailles dont la borne supérieure ne peut
pas améliorer le résultat. C'est un **DP avec élagage par bornes de taille**, exact,
qui n'est **pas** l'IDP du cours.

- Le nom `idp_search` est conservé pour ne pas casser l'historique ni ses tests.
- Les rapports et la soutenance doivent le décrire comme un DP avec élagage, et ne
  jamais affirmer son équivalence avec l'IDP de Rahwan et Jennings.
- Une implémentation fidèle de l'IDP du cours, dans une **nouvelle** fonction,
  serait un ajout scientifique possible (décision D11), hors P4.

De même, l'« IP » du cours est l'algorithme anytime de Rahwan et al. (2009) : une
recherche arborescente par sous-espaces avec bornes supérieures. L'`ip_search`
historique et l'adaptateur IP ci-dessous sont des **programmes linéaires en nombres
entiers** (MILP, partitionnement d'ensemble). Les documents P4 les nomment
« MILP » pour éviter la confusion.

**Force brute (`brute_force_search`).** Elle énumère toutes les partitions (croissance
restreinte) : exacte, limitée par `max_agents`. Somme flottante par partition, exacte
dans la borne du §4.

**MILP (nouvel adaptateur ; « IP » dans l'historique du code).**

- *Exactitude algorithmique* : le partitionnement en nombres entiers est exact si le
  branch-and-bound prouve l'optimalité avec un écart nul, en arithmétique exacte.
- *Exactitude numérique* : HiGHS calcule en flottants. **[Fait]** Valeurs par défaut
  lues dans le binding SciPy 1.17.1 :
  - `mip_rel_gap = 1e-4` ;
  - `mip_abs_gap = 1e-6` ;
  - `mip_feasibility_tolerance = 1e-6` ;
  - `primal_feasibility_tolerance = 1e-7`.

  `scipy.optimize.milp` n'expose que `disp`, `presolve`, `time_limit`, `node_limit`
  et `mip_rel_gap`.
- *Statuts [Fait]* :
  - `0` « Optimal solution found », **y compris un arrêt par critère d'écart** ;
  - `1` limite atteinte ;
  - `2` infaisable ;
  - `3` non borné ;
  - `4` autre.

  Seul le statut 0 permet de revendiquer l'optimalité, et seulement **aux tolérances
  près**.
- **`mip_rel_gap = 0` n'est pas une preuve suffisante** : l'écart absolu et les
  tolérances de faisabilité restent actifs, et le calcul reste flottant.
- **Deux niveaux de confiance, à ne jamais confondre [Décision] :**
  - **« optimale aux tolérances HiGHS »** (`milp_solver_optimal`) : affirmation du
    solveur, contrôlée par les étapes 1 à 5 ci-dessous ; elle reste exposée aux
    tolérances et aux erreurs flottantes ;
  - **« optimum exact certifié »** (`milp_certified_exact`) : l'étape 6 a réussi,
    c'est-à-dire que W, recalculé en entiers, est égal exactement au W de
    `idp_search`.
- **Procédure** :
  1. statut 0 ;
  2. chaque `x_j` à moins de 1e-6 de 0 ou 1 ;
  3. arrondi, puis reconstruction des blocs ; vérification exacte en entiers :
     couverture une fois et une seule, blocs dans F ;
  4. recalcul exact de W en entiers à partir de la table ;
  5. borne duale `mip_dual_bound` finie, et cohérente : on minimise −W, l'objectif
     est entier, et on exige `−W − mip_dual_bound ≤ 0,5` ;
  6. égalité exacte de W avec `idp_search` sur la même table.
- **Issues** :

  | Situation | Libellé | Conséquence |
  |---|---|---|
  | étapes 1 à 6 réussies | `milp_certified_exact` | peut être rapportée comme optimum exact, mais la structure officielle reste celle d'`idp_search` |
  | étapes 1 à 5 réussies, étape 6 non exécutée (IDP non lancé) | `milp_solver_optimal` | jamais publiée comme optimum exact ; jamais utilisée comme `V*` dans un écart à l'optimum |
  | étape 6 échoue (W différent) | — | `CertificateFailure` ; solution MILP écartée ; incident enregistré ; la référence reste IDP |
  | statut 0 mais borne duale absente ou non finie (étape 5 impossible) | `milp_feasible_unverified` si les étapes 2 à 4 réussissent | jamais qualifiée d'optimale, même aux tolérances |
  | statut 1 (limite atteinte) avec une solution | `milp_feasible_unverified` si les étapes 2 à 4 réussissent | jamais optimale |
  | étape 2 ou 3 échoue | — | `IntegralityViolation` ou `PartitionInvalid` ; solution écartée |
  | statut 2 ou 3 | — | `SolverAnomaly` : impossible en théorie (la partition en singletons est réalisable, et les variables sont bornées) |
  | statut 4 | — | `SolverNotOptimal` |

- **Règle de publication** : la structure officielle de P4 vient **toujours**
  d'`idp_search`, contrôlé par `dp_search` et, si n ≤ 9, par la force brute. Le MILP
  ne sert que de contrôle ou d'objet d'étude. Au-delà de la limite de taille, IDP
  n'est pas exécuté : le MILP ne peut donc pas être certifié, et il ne remplace pas
  le statut `component_too_large`.

### 6.4 Limite de 14 unités : une limite opérationnelle, pas mathématique

**Mesures [Fait]** :

- une négociation P3 coûte environ 0,13 ms (moyenne sur 300 requêtes, unités à un
  profil, double exécution) ;
- DP / IDP sur table précalculée (30 % de sous-ensembles réalisables) : 0,21 / 0,20 s
  pour n = 12, et 0,62 / 0,63 s pour n = 13 ;
- force brute : 0,02 s pour n = 8, et 0,72 s pour n = 10.

**Croissance (extrapolations, non mesurées)** :

| n | DP / IDP, Θ(3ⁿ) | Négociations, une offre de voisinage n | Partitions (Bell) |
|---|---|---|---|
| 10 | ≈ 0,02 s | 1 023 ≈ 0,13 s | 115 975 (0,72 s mesuré) |
| 12 | 0,21 s (mesuré) | 4 095 ≈ 0,5 s | 4 213 597 (≈ 26 s) |
| 14 | ≈ 1,9 s | 16 383 ≈ 2,1 s | ≈ 1,9·10⁸ |
| 16 | ≈ 17 s | 65 535 ≈ 8,5 s | — |
| 18 | ≈ 150 s | 262 143 ≈ 34 s | — |

S'y ajoute la mémoire de DP : 2ⁿ entrées, chacune avec sa structure.

**[Hypothèse]**

- 14 est une limite opérationnelle provisoire et configurable, qui garde une
  composante sous quelques secondes dans le contexte mesuré ;
- la force brute est limitée à n ≤ 10 en validation (≤ 9 dans les tests rapides) ;
- les deux limites seront recalibrées par le banc d'essai de P4.3 (unités à
  plusieurs profils, plusieurs offres, vraies tables).

Au-delà de la limite : statut `component_too_large`, sans optimisation silencieuse.

### 6.5 Adaptateurs

Aucun algorithme historique n'est modifié.

- **Adaptateur de table** : précalcule `w` sur tous les sous-ensembles de la
  composante et fournit une fonction de consultation pure aux solveurs.
- **Adaptateur MILP** : colonnes = blocs de F (dont les singletons), procédure et libellés du §6.3.
  `ip_search` historique reste inchangé.

## 7. Baselines (B6)

| Code | Méthode | Même jeu que P4 ? | Usage |
|---|---|---|---|
| B0 | Broker historique : seuil de 3, ordre d'arrivée, par destination | **non** | ses blocs sont re-notés dans le jeu P4 ; les blocs non réalisables sont comptés et leurs membres traités en singletons |
| B1 | Glouton : bloc disjoint de F avec la plus grande `v > 0` ; départage par moins d'unités, puis identifiants triés | oui | isole l'effet du solveur |
| `idp_search` / `dp_search` | exacts historiques via l'adaptateur | oui | optimum officiel |
| MILP | exact alternatif, procédure et libellés du §6.3 | oui | contrôle |
| BF | force brute, n ≤ 10 | oui | validation |

**Protocole B0 [Décision].**

- Un `BuyerAgent` par unité : nom = `unit_id`, `budget = to_agent_amount(B_u)`,
  `traveller_count = seats(u)`, et une inscription `SUBSCRIBE` sur la destination
  de l'unité.
- Un `BrokerAgent` par destination, avec ses paramètres historiques
  (`coalition_size=3`, remises par défaut) et `negotiate_on_formation=False`.
- Les unités restées en attente deviennent des singletons, sans `finalize_pending`,
  comme `_simulate_broker_order` d'`Entry.py`.
- 20 ordres d'arrivée par instance, tirés d'une graine dérivée de l'instance (§11.3) ;
  on rapporte la moyenne, le minimum et le maximum.

La valeur native de B0 (budget × remise) est rapportée à part et n'est jamais
comparée aux économies P4.

## 8. Architecture applicative (B8)

### 8.1 Règles de dépendance [Décision]

| Couche | Peut importer | Ne doit jamais importer |
|---|---|---|
| `domain/coalition_game.py` | bibliothèque standard, `domain/money` | NumPy, SciPy, agents historiques, Ollama, SQLite, application, infrastructure |
| Modules `application/` P4 | domaine (y compris `partition_optimization`, `partition`), P2 | infrastructure, agents historiques, Ollama, SQLite, LLM, RAG |
| `infrastructure/optimization/exact_ip.py` | SciPy, domaine | agents |
| `infrastructure/baselines/legacy_broker.py` | `BrokerAgent`, `BuyerAgent`, `Message` (historiques) | application P4 |
| `infrastructure/evaluation/formation_*.py` | domaine, application, termes privés (scénarios seulement) | LLM, RAG |

Ces règles seront vérifiées par un test AST, sur le modèle de
`tests/test_coalition_module_boundaries.py`. Le moteur d'optimisation est
déterministe et n'utilise aucun LLM.

### 8.2 Types partagés (dataclasses gelées, montants en centimes `int`)

- `FormationLimits(max_component_units=14, max_offer_neighbourhood=14, brute_force_max_units=9)`
- `CoalitionCandidate(unit_ids: tuple[str, ...], common_offer_ids: tuple[str, ...])`
- `CoalitionAttempt(offer_id, request_key, status: NegotiationStatus, agreed_total_cents: int | None, turns: int)`
- `CoalitionCost(unit_ids, attempts: tuple[CoalitionAttempt, ...], offer_id: str | None, cost_cents: int | None)`,
  réalisable ⇔ `cost_cents is not None`
- `CoalitionGame(component_id, players: tuple[str, ...], references: tuple[tuple[str, int], ...], values: tuple[tuple[tuple[str, ...], int], ...], oracle_configuration_id)`
- `ComponentSolution(component_id, structure: tuple[tuple[str, ...], ...], value_cents: int, block_count: int, tie_break_score: int, method: str, checks: tuple[str, ...], status)`
- `FormationResult(formation_run_id, admissibility_id, oracle_configuration_id, limits, components, structure, total_value_cents, total_cost_cents, unserved_units, unresolved_units, evaluations, cache_stats, status)`

### 8.3 Fiches de modules

Les huit responsabilités demandées correspondent aux modules M1 à M8.
L'orchestration (M9) les enchaîne.

**M1 — Candidats** : `application/coalition_candidates.py`

- *Responsabilité* : énumérer `{C ⊆ K : C ≠ ∅, O(C) ≠ ∅}`.
- *Dépendances* : `domain/offer_graph`.
- *Entrées / sorties* : `enumerate_candidates(relation: AdmissibilityRelation, component: OfferComponent, limits: FormationLimits) -> tuple[CoalitionCandidate, ...]`.
- *Invariants* : ensemble complet et sans doublon ; tri par (taille, identifiants) ;
  offres triées ; déterministe.
- *Échecs* : `ComponentTooLarge` (statut `component_too_large`).
- *Tests* : égalité avec une énumération naïve sur des relations aléatoires ;
  chaîne ; anti-monotonie ; gardes ; invariance par permutation.

**M2 — Faisabilité structurelle** : `application/coalition_feasibility.py`

- *Responsabilité* : recalcul **indépendant**, avant toute négociation, de ce que M1
  affirme. Il vérifie :
  - le lot est optimisable (H2) ;
  - toutes les unités sont référencées ;
  - C est inclus dans une seule composante effective ;
  - `relation.common_offers(C)` est égal aux offres déclarées ;
  - `seats(C) ≤ capacity(o)` pour chaque offre.

  La faisabilité économique (accord) relève de M3. Justification d'un module
  séparé : défense en profondeur contre une erreur de M1, et point unique de
  préconditions avant l'oracle.
- *Dépendances* : `application/lot_admissibility`, `application/reference_costs`,
  `domain/offer_graph`.
- *Entrées / sorties* : `check_structural_feasibility(candidate, lot, references) -> None`.
- *Échecs* : `CandidateInfeasible` (anomalie, exception) ; `CapacityModelViolated`
  (P2).
- *Tests* : chaque violation est détectée ; accord avec M1 sur des instances
  aléatoires.

**M3 — Coûts négociés et cache** : `application/negotiation_cache.py`,
`application/coalition_costs.py`

- *Responsabilité* :
  - `CachingNegotiationOracle` implémente `NegotiationOracle`, avec une clé
    (`request_key`, `oracle_configuration_id`). Il exige un oracle qui expose
    `oracle_configuration_id` (protocole applicatif `ConfiguredNegotiationOracle`,
    justifié parce que la clé du cache en dépend). Il se branche **sans
    modification** sur `compute_reference_costs`, si bien que références et
    coalitions partagent le cache, ce qui garantit `c({u}) = ref_u` ;
  - `negotiate_candidate` construit une requête par offre commune avec
    `negotiation_request_for`, valide chaque réponse avec le contrat P2, et retient
    `c(C)`.
- *Dépendances* : `domain/negotiation_request`, `application/reference_costs`
  (validation). Aucun import d'infrastructure : l'oracle est injecté.
- *Entrées / sorties* : `negotiate_candidate(candidate, relation, oracle) -> CoalitionCost`.
- *Invariants* : une tentative par offre commune, triée par `offer_id` ;
  `c` = plus petit accord, départage par `offer_id` ; même configuration que les
  références.
- *Échecs* : `NegotiationOracleContractError` (P2) ; `OracleConfigurationMismatch`.
- *Tests* :
  - un seul appel d'oracle pour deux coalitions économiquement identiques ;
  - résultats identiques avec et sans cache ;
  - erreur si la configuration change ;
  - contrat d'oracle violé.

**M4 — Valeur caractéristique** : `domain/coalition_game.py`

- *Responsabilité* :
  - construire `CoalitionGame` à partir des `ref_u` et des `CoalitionCost` ;
  - calculer `v` ;
  - vérifier les singletons ;
  - fournir `weight(C)` (`w`, pénalité comprise), `tie_break_factor = n` et
    `decode(W) = ⌈W/K⌉` ;
  - calculer `cover(S)` (`v*`, par DP sur les sous-ensembles de S).
- *Dépendances* : bibliothèque standard, `domain/money`.
- *Invariants* : joueurs triés et uniques ; tout singleton dans F avec `v = 0` ;
  valeurs entières ; blocs de F inclus dans les joueurs.
- *Échecs* : `GameConsistencyError`.
- *Tests* :
  - propriétés 1 à 6 de `v*` (tests de propriétés) ;
  - propositions 1 à 4 du §4, dont l'instance limite `K = n − 1` ;
  - borne numérique.

**M5 — Optimisation** : `application/partition_solver.py` (+ option
`infrastructure/optimization/exact_ip.py`)

- *Responsabilité* : adaptateur de table, appel de `idp_search` / `dp_search` /
  `brute_force_search`, décodage, contrôles croisés.
- *Dépendances* : `domain/partition_optimization`, `domain/partition`, M4. SciPy
  seulement dans `exact_ip`.
- *Entrées / sorties* : `solve_component(game: CoalitionGame, method: Literal["idp", "dp", "brute_force"], cross_checks: tuple[str, ...]) -> ComponentSolution`.
- *Invariants* : partition exacte ; blocs dans F ; `V = Σ v` ; `W = K·V − d` ;
  contrôles égaux en entiers.
- *Échecs* : `SolverDisagreement` ; `PartitionInvalid` ; `NumericDomainExceeded`
  (garde) ; pour le MILP : `SolverNotOptimal`, `SolverAnomaly`, `IntegralityViolation`,
  `CertificateFailure`.
- *Tests* :
  - IDP = DP (valeur et structure) ;
  - égalité avec la force brute sur au moins 500 instances (n ≤ 9) ;
  - indépendance vis-à-vis de P ;
  - instances adversariales ;
  - procédure MILP et ses libellés (si SciPy est présente).

**M6 — Baselines** : `application/formation_baselines.py`,
`infrastructure/baselines/legacy_broker.py`

- *Responsabilité* : B1 glouton sur `CoalitionGame` ; re-notation d'une structure
  quelconque ; exécution du Broker historique (avec
  `negotiate_on_formation=False` et la sortie console capturée) sur des copies
  d'agents construites à partir des unités.
- *Dépendances* : M4. Les agents historiques ne sont importés qu'en infrastructure.
- *Entrées / sorties* :
  - `greedy_b1(game) -> tuple[tuple[str, ...], ...]` ;
  - `rescore(structure, game) -> RescoredStructure(feasible_blocks, infeasible_blocks, value_cents)` ;
  - `run_b0(units, arrival_orders) -> tuple[...]`, avec le protocole B0 du §7.
- *Invariants* : B1 et B0 re-noté restent inférieurs ou égaux à l'optimum ; B0 ne
  modifie aucun fichier historique.
- *Échecs* : `BaselineError`.
- *Tests* :
  - B1 inférieur ou égal à l'optimum, et égal sur des instances dont les blocs
    positifs sont disjoints ;
  - instance où B1 est sous-optimal ;
  - B0 reproduit le regroupement historique sur des ordres connus ;
  - test AST des dépendances.

**M7 — Évaluation expérimentale** : `application/formation_evaluation.py`,
`infrastructure/evaluation/formation_scenarios.py`

- *Responsabilité* :
  - `application/formation_evaluation.py` : métriques (§11.4) et décomposition des
    économies (§11.5), à partir de données publiques seulement ;
  - `infrastructure/evaluation/formation_scenarios.py` : génération de scénarios à
    graine fixe. C'est le **seul** module P4 qui construit des termes privés
    (décision D8) : il crée le `SellerTermsBook`, l'écrit au format P1 dans le
    répertoire de l'expérience et construit lui-même l'oracle simulé. Il ne renvoie
    que des objets publics.
- *Dépendances* : application P4 pour les métriques. Le générateur dépend du domaine
  P1 (termes), de l'oracle P3 et de la sérialisation P1.
- *Entrées / sorties* :
  - `formation_metrics(result, game, catalog) -> FormationMetrics` ;
  - `savings_decomposition(block, references, catalog) -> SavingsDecomposition`, avec
    les champs `savings_individual_negotiation`, `savings_offer_switch`,
    `savings_public_tier_pooling`, `residual_collective_negotiation` ;
  - `build_scenario(params, seed) -> Scenario(units, catalog, oracle, manifest)`. Le
    manifeste contient les paramètres, la graine, les empreintes SHA-256 du catalogue
    et des termes, et l'empreinte des unités, mais aucune valeur de plancher.
- *Invariants* : l'identité de décomposition est exacte en entiers ; un même
  manifeste donne les mêmes octets ; les objets renvoyés ne contiennent aucun type
  ni champ de plancher.
- *Échecs* : `DecompositionMismatch` ; `ScenarioError` ; un scénario qui viole les
  préconditions de sa cellule (par exemple H2 dans une cellule « H2 respectée ») est
  une anomalie du générateur, levée immédiatement et jamais régénérée en silence.
- *Tests* :
  - identités exactes et tests de paliers (§11.5) ;
  - reproductibilité des graines ;
  - métriques sur des cas calculés à la main ;
  - garde D8 (§15).

**M8 — Rapport de résultats** : `infrastructure/evaluation/formation_report.py`

- *Responsabilité* : écrire le JSON canonique des résultats et les tableaux Markdown.
  L'environnement (versions) est écrit à part, hors de la partie hachée.
- *Dépendances* : M7.
- *Entrées / sorties* : `write_report(results, path) -> ReportManifest`.
- *Invariants* :
  - octets identiques pour une même entrée ; schéma versionné ;
  - aucun chiffre qui ne provienne d'une exécution ;
  - toute colonne `residual_collective_negotiation` porte la mention « résidu
    comptable, non identifiable causalement » ;
  - une solution MILP n'est qualifiée d'« optimum exact » que si son libellé est
    `milp_certified_exact` ;
  - les analyses exploratoires et confirmatoires sont séparées (§11.3) ;
  - aucune valeur de plancher.
- *Échecs* : `ReportError`.
- *Tests* : déterminisme ; schéma ; régénération à partir du JSON ; présence des
  mentions obligatoires ; absence de champ de plancher.

**M9 — Orchestration** : `application/coalition_formation.py`

- *Responsabilité* : enchaîner M1 à M5 par composante, assembler `FormationResult`
  et calculer la provenance (§10).
- *Statuts* :
  - par composante : `optimized`, `singleton_component`, `no_beneficial_coalition`,
    `component_too_large` ;
  - global : `optimized`, `incomplete` (unités non résolues listées, jamais
    présentées comme optimales), `capacity_model_violated`.
- *Tests* :
  - égalité entre la résolution par composante et la résolution du lot entier ;
  - refus H2 sans appel d'oracle ;
  - invariance par permutation ;
  - même empreinte sur deux exécutions et deux `PYTHONHASHSEED`.

## 9. Répartition des gains et Shapley (B9)

**[Hors périmètre P4]** : implémentation en P5. Cette section en fixe les
mathématiques.

### 9.1 Quatre notions distinctes

| Notion | Question | Outil | Garantie |
|---|---|---|---|
| Optimisation sociale | quelle partition maximise `Σ v` ? | P4 (§4 à §6) | exacte |
| Allocation équitable | comment partager `v(C)` dans un bloc ? | Shapley sur `v*|C` | axiomes de Shapley sur `v*|C` |
| Rationalité individuelle | chacun paie-t-il au plus `ref_u` ? | propriété de l'allocation | garantie pour Shapley de `v*` (§9.4), pas pour Shapley en général |
| Stabilité | un sous-groupe a-t-il intérêt à faire sécession ? | cœur, excès | **non garantie** ; mesurée seulement |

### 9.2 Quand, et sur quelle fonction

- **Quand** : après l'optimisation, pour chaque bloc retenu non singleton ; un
  singleton paie `ref_u`. Jamais pendant l'optimisation, et jamais sur une
  composante entière : chaque bloc est un accord distinct.
- **Fonction** : le jeu `(C, v*|_{2^C})`. Les valeurs `v(S)` des sous-coalitions
  S ⊆ C sont déjà évaluées par M3, puisque toutes les coalitions candidates de la
  composante le sont. Aucun appel d'oracle supplémentaire n'est nécessaire.
- **Coalitions non réalisables** : elles valent `v*(S)`, c'est-à-dire leur meilleure
  réorganisation en coalitions réalisables, au minimum 0. Jamais −∞ ni −P (§3.5).
- **`v*` est nécessaire** parce que Shapley exige une valeur pour tout
  sous-ensemble, et que `v` n'est défini que sur F. Toute autre complétion introduit
  un paramètre arbitraire.

### 9.3 Pourquoi Shapley(`v*`) ≠ Shapley(`v`)

- Si un sous-ensemble S ⊆ C n'est pas dans F, Shapley(`v`) n'est pas défini.
- Même quand tout est dans F, `v*(S) > v(S)` dès qu'une scission de S vaut plus que
  S. Les contributions marginales changent, donc les valeurs de Shapley aussi.
- Pour le bloc lui-même, `v*(C) = v(C)` (propriété 6), et la somme est conservée.

Exemple **[Fait]** (§3.5) : Shapley de `v*` donne (4, 4, 1), alors que la complétion
par pénalité donne (9/2, 9/2, 0) ou (9, 9, −9). Le `shapley_value` historique
appliqué à `v*` redonne (4, 4, 1) en flottants.

### 9.4 Propriétés garanties et non garanties

- **Efficacité** : `Σ_{u∈C} φ_u = v*(C) = v(C) = Σ ref_u − c(C)`.
  Avec `x_u = ref_u − φ_u`, on obtient `Σ x_u = c(C)` exactement.
- **Rationalité individuelle** : `v*` est superadditif avec `v*({u}) = 0`, donc toute
  contribution marginale vérifie `v*(S ∪ {u}) − v*(S) ≥ v*({u}) = 0`, et `φ_u ≥ 0`.
  Donc `x_u ≤ ref_u ≤ B_u`, car la référence respecte la réservation (contrat P2).
  **[Fait]** `φ ≥ 0` et `Σφ = v*(C)` vérifiés exactement sur 300 jeux aléatoires.
  Cette garantie tient à la superadditivité de `v*` ; elle ne vaut pas pour Shapley
  sur une fonction quelconque (exemple : −9 ci-dessus).
- **Paiements négatifs : possibles.** Si `φ_u > ref_u`, alors `x_u < 0` : l'unité
  serait payée pour participer. Exemple **[Fait]** : trois unités dont seule la grande
  coalition est réalisable, avec `v = 900` ; alors `φ = (300, 300, 300)`, et une unité
  de référence 100 recevrait −200.
- **Stabilité : non garantie.** Le cœur de `(C, v*|C)` peut être vide, et Shapley
  n'est dans le cœur que pour un jeu convexe, ce que `v*` n'est pas en général. Elle
  est mesurée par l'excès maximal `max_{S⊊C} (v*(S) − Σ_{u∈S} y_u)` ; la stabilité
  entre blocs n'est pas garantie non plus.

### 9.5 Projection : paiements dans [θ_u, ref_u] [Décision, à valider en P5]

On travaille en économies `y_u = ref_u − x_u`. Données : `φ` (rationnel), `V = v(C)`,
et des bornes `l_u = 0` et `h_u = ref_u − θ_u`, où `θ_u ≥ 0` est le paiement minimal
(`θ_u = 0` recommandé : personne n'est payé).

**Problème** : `min Σ_u (y_u − φ_u)²` sous `Σ y_u = V` et `l ≤ y ≤ h`.

- **Faisabilité** ⇔ `Σ l ≤ V ≤ Σ h` ⇔ `c(C) ≥ Σ θ_u`, toujours vrai pour `θ = 0`.
- **Unicité du vecteur.** L'objectif est strictement convexe et l'ensemble admissible
  est convexe, compact et non vide : le **vecteur** `y` est unique.
- **Caractérisation (conditions KKT).** `y` est optimal si et seulement s'il existe λ
  tel que `y_u = clip(φ_u − λ, l_u, h_u)` pour tout u et `Σ y_u = V`. On pose
  `g(λ) = Σ_u clip(φ_u − λ, l_u, h_u) − V`. Cette fonction est continue, non
  croissante et linéaire par morceaux, avec `g(−∞) = Σh − V ≥ 0 ≥ Σl − V = g(+∞)`.
- **Le multiplicateur n'est pas toujours unique.** L'ensemble
  `Λ = {λ : g(λ) = 0}` est un intervalle fermé `[λ_lo, λ_hi]` non vide, éventuellement
  non borné d'un côté. Il n'est pas réduit à un point quand `g` est plate en zéro,
  c'est-à-dire quand toutes les unités sont saturées sur un intervalle. Exemple :
  si `V = Σ h`, alors `Λ = (−∞, min_u (φ_u − h_u)]`. Toutes les valeurs de Λ
  donnent le **même** vecteur `y`.
- **Convention déterministe pour λ.** On retient le point de Λ le plus proche de 0 :
  `λ* = min(max(0, λ_lo), λ_hi)`. Ce point existe toujours et il est rationnel,
  puisque les bornes de Λ sont des points de rupture `φ_u − h_u` ou `φ_u − l_u`, ou
  infinies. Calcul exact en rationnels : on trie les points de rupture, on évalue `g`
  à chacun d'eux, on localise le changement de signe ou le palier nul, puis on
  résout l'équation linéaire du segment. λ* sert seulement de diagnostic ; le
  résultat est le vecteur `y`.
- **Propriétés** :
  - si aucune borne n'est active, `y = φ` et `λ* = 0` ;
  - comme `φ ≥ 0 = l`, on a `g(0) = Σ min(φ_u, h_u) − V ≤ 0`, donc `λ* ≤ 0` :
    seules les bornes hautes peuvent être actives, et l'excédent est reporté sur les
    autres membres ;
  - deux unités qui ont le même φ et les mêmes bornes reçoivent le même `y`.
- **Contrôle exact** : `Σ y_u = V` et les conditions KKT sont vérifiées en
  rationnels.

  Quand la projection est active, les axiomes de Shapley ne tiennent plus
  exactement.

**Données conservées par P5 pour chaque bloc** [Décision] :

- la valeur de Shapley rationnelle initiale `φ` ;
- l'allocation projetée `y`, en rationnels, avant arrondi ;
- l'allocation arrondie `y'` et les paiements `x' = ref − y'`, en centimes ;
- la distance entre `φ` et `y` : carré de la distance euclidienne `Σ (y_u − φ_u)²`
  (rationnel exact), et distance maximale `max_u |y_u − φ_u|` ;
- l'indicateur `projection_active = (y ≠ φ)`, la liste des unités saturées et `λ*` ;
- l'écart d'arrondi, inférieur à un centime par unité.

### 9.6 Budgets et centimes

- **Budgets** : `x_u ≤ ref_u ≤ B_u` découle de `y_u ≥ 0` ; aucun écrêtage heuristique
  n'est nécessaire. La répartition entre profils d'une même unité est
  **[Hors périmètre]**.
- **Arrondi** (plus fort reste) :
  1. `y'_u = ⌊y_u⌋` en centimes ;
  2. `r = V − Σ ⌊y_u⌋`, entier compris entre 0 et `|C| − 1` ;
  3. +1 centime aux `r` unités de plus grande partie fractionnaire, départage par
     `unit_id`.
- **Preuve des bornes** :
  - `⌊y⌋ ≥ l`, car l est entier ;
  - une unité à fraction nulle ne reçoit jamais de centime, car `r` est strictement
    inférieur au nombre d'unités à fraction positive ;
  - si la fraction est positive, `y < h` avec `h` entier, donc `⌊y⌋ + 1 ≤ h`.
- **Résultat** : `Σ y' = V` et `Σ x = c(C)`, exactement, en entiers.

### 9.7 Réutilisation du Shapley historique

- `shapley_value` (formule exacte, poids en flottants) sert d'**oracle différentiel**.
  On l'appelle avec `v*` et on compare au calcul rationnel, avec une tolérance de
  1e-6 × max(1, |V|).
- Il ne peut pas être le calcul officiel. Ses poids `s!(n−s−1)!/n!` sont des
  flottants ; pour |C| = 14, `n! ≈ 8,7·10¹⁰` multiplié par des montants de l'ordre de
  10¹¹ dépasse 2⁵³, et il ne garantit pas une somme exacte au centime.
- `allocate_shapley_payments` est remplacée (§1.2).

## 10. Cache, déterminisme et provenance (B7)

- **Clé du cache** : (`request_key`, `oracle_configuration_id`). Deux coalitions
  économiquement identiques, formées d'unités différentes, partagent légitimement le
  même résultat, car l'oracle ne dépend que du mandat et de sa configuration (I1).
- **Valeur** : le `NegotiationOutcome` validé et l'empreinte du journal P3.
- **Portée** : en mémoire, pour une exécution, partagée avec les références P2.
  **[Hors périmètre]** : un cache persistant ; s'il existe un jour, il sera versionné
  par `REQUEST_KEY_SCHEMA` et la configuration.
- **Invalidation** : inutile, car tout changement modifie la clé.
- **Mesures** : succès, échecs, négociations exécutées.
- **Déterminisme** : tris par identifiant ; énumération et départages déterministes ;
  aucune graine cachée ; durées seulement dans les métriques ; suite exécutée avec
  deux `PYTHONHASHSEED`.
- **Provenance** :
  - `formation_run_id` = SHA-256 canonique de : `admissibility_id`,
    `oracle_configuration_id`, références (`unit_id`, `ref_u`, offre), méthode et
    version de l'adaptateur, K et P, limites, liste des `component_id` ;
  - pour chaque (C, o) : unités, offre, `request_key`, statut, montant, tours ;
  - empreinte du JSON canonique du résultat.

## 11. Évaluation scientifique et démonstration AI Engineering (B10)

### 11.1 Rôle de chaque composant d'IA

| Composant | Rôle | Déterministe | Évalué par | Influence la partition ? |
|---|---|---|---|---|
| LLM (Ollama) | extraction de `TravelRequestDraft` depuis le texte | non (modèle) | métriques d'extraction exactes (`evaluate_requests.py`) | seulement à travers des unités **validées** de façon déterministe ; ne choisit jamais la partition |
| RAG | assistance documentaire (règles, explications) | récupération déterministe | `evaluate_retrieval.py` | non : il ne fournit ni prix ni disponibilité |
| Négociation simulée P3 | coût d'un mandat | oui | tests de fidélité et de contrat | fournit `c(C)` |
| Optimisation P4 | partition optimale | oui | certificats DP / IDP / force brute | décide |
| Évaluation | protocole hors ligne | oui (graines) | reproductibilité | non |

**[Décision]** Les expériences P4 utilisent des unités synthétiques, sans LLM, pour
isoler l'optimisation. Une démonstration de bout en bout (texte → LLM → unités → P2
→ P3 → P4) reste possible, en mesurant à part les erreurs de l'étape LLM.

### 11.2 Questions de recherche

- **QR1 — Correction** : les méthodes exactes concordent-elles sur toutes les
  instances ?
- **QR2 — Valeur de l'optimisation** : quel écart sépare B1 et B0 re-noté de
  l'optimum, et comment varie-t-il selon les facteurs ?
- **QR3 — Origine des économies** : quelle part revient aux paliers, au changement
  d'offre et à la négociation (§11.5) ?
- **QR4 — Passage à l'échelle** : nombre de négociations et durée selon la taille
  des composantes et la densité du graphe.
- **QR5 — Robustesse** : statuts corrects sur les cas adversariaux, et
  reproductibilité.

### 11.3 Générateur et plan factoriel [Hypothèse : niveaux à valider]

| Facteur | Niveaux |
|---|---|
| unités par lot | 2, 4, 6, 8, 10, 12, 14 ; 16 à 20 pour tester la garde |
| profils par unité | 1, 2, 3 (fenêtres et exclusions qui se recoupent ou non) |
| places par profil | 1 à 4 |
| offres par destination | 1, 2, 3, 5 |
| capacités | H2 respectée (marges 0 % et 50 %) ; H2 violée (contrôle de refus) |
| grille de paliers | plate, modérée, forte |
| budgets | homogènes ; hétérogènes (coefficient de variation 0,1 et 0,3) |
| taux d'accord visé | 0,2 ; 0,5 ; 0,8 ; 1,0 |
| densité unité–offre | probabilité d'admissibilité 0,3 ; 0,6 ; 0,9 |

Le taux d'accord est piloté exactement, car **[Fait, P3-bis]** avec la stratégie par
défaut, `rejected` ⇔ `F(o, s_C) > R(C)`. Le générateur choisit planchers et budgets
en conséquence.

**Plan expérimental [Décision D9, à valider].** Quatre strates, jamais mélangées
dans un même tableau :

1. **Correction** (suite de tests, exhaustive, non statistique) :
   - au moins 500 instances aléatoires avec n ≤ 9 (graines 0 à 499), plus tous les
     cas S-ADV et les tests de paliers du §11.5 ;
   - égalité exacte entre force brute, `dp_search`, `idp_search`, et le MILP s'il est
     installé ; l'exigence est 100 %, et tout échec bloque ;
   - déterminisme : deux exécutions par instance et `PYTHONHASHSEED` ∈ {0, 2},
     avec une empreinte de résultat identique ;
   - aucune mesure de temps.
2. **Performance** (script de banc d'essai séparé, hors suite de tests, jamais dans
   un identifiant) :
   - tailles n ∈ {6, 8, 10, 12, 14}, plus 16 pour la garde ;
   - 10 instances par taille ;
   - une exécution de chauffe écartée, puis 5 répétitions chronométrées par
     instance ;
   - médiane, écart interquartile et maximum par taille ; machine et versions
     enregistrées ;
   - ces mesures servent à recalibrer D4.
3. **Analyse exploratoire** (descriptive uniquement) :
   - **sélection des instances** :
     - (a) variation d'un facteur à la fois autour d'une cellule de référence :
       8 unités, 2 profils par unité, 2 offres par destination, grille modérée,
       budgets homogènes, taux d'accord visé 0,8, densité 0,6, marge H2 de 50 %.
       Cela donne 22 cellules distinctes ;
     - (b) 60 cellules tirées uniformément dans le plan complet, avec une graine
       fixée, pour observer les interactions ;
     - (c) toutes les familles de scénarios ;
   - **graines** : 20 par cellule, dans la plage [0, 10 000). Ce minimum vise des
     médianes et quartiles descriptifs stables ; il **ne garantit aucune puissance
     statistique** ;
   - **sorties** : médianes, quartiles, proportions et intervalles bootstrap
     étiquetés « exploratoires », graphiques ; aucune p-valeur ; les hypothèses
     peuvent être reformulées à ce stade.
4. **Analyse confirmatoire** (optionnelle, une fois l'exploration figée) :
   - hypothèses préenregistrées, choisies parmi E2 à E6, avec leur métrique
     principale et leur sens, écrits avant l'exécution ;
   - graines neuves, disjointes de l'exploration, dans la plage [10 000, 20 000) ;
   - plan apparié : mêmes instances pour toutes les méthodes, et différences par
     instance (par exemple l'écart de B1) ;
   - taille d'échantillon calculée à partir de la variance observée en exploration,
     pour atteindre une précision fixée d'avance (par exemple, un intervalle
     bootstrap à 95 % de demi-largeur inférieure ou égale à 1 point de pourcentage
     sur un taux). Elle n'est **pas** fixée arbitrairement ;
   - tests non paramétriques appariés (Wilcoxon signé ou intervalle bootstrap),
     correction de Holm pour les hypothèses multiples, tailles d'effet avec leurs
     intervalles.

La puissance d'un test dépend de la taille de l'effet et de la variance, inconnues
avant l'exploration. Aucun nombre de graines ne la garantit à lui seul.

**Règles communes :**

- **Graines dérivées** : graine de l'instance = premiers 64 bits de
  SHA-256(`cell_id`, indice de graine). Les ordres d'arrivée de B0 sont dérivés de
  la même façon, avec un suffixe distinct.
- **Aucun filtrage a posteriori** : toute instance générée est conservée. Les
  instances dégénérées (aucun candidat, singletons seulement) sont comptées et
  rapportées. Une anomalie du générateur arrête l'expérience ; elle n'est jamais
  régénérée en silence.
- Les rapports indiquent la strate de chaque chiffre.

**Familles de scénarios :**

- **S-NULL**, sans coalition profitable : grilles plates, et planchers et budgets
  proportionnels aux places.
- **S-MUT**, forte mutualisation : grilles fortes, beaucoup de petites unités sur peu
  d'offres.
- **S-ISO** : unités isolées (`no_admissible_offer`, `no_solo_reference`).
- **S-ADV** :
  - jeu non superadditif ;
  - économies toutes nulles ;
  - égalités multiples ;
  - chaîne ;
  - unités identiques ;
  - permutations ;
  - budgets hétérogènes qui rendent `v` négatif ;
  - plancher supérieur à la réservation partout ;
  - unité pont non référencée ;
  - configuration d'oracle différente (doit échouer).
- **S-H2** et **S-LARGE** : refus explicites.

### 11.4 Métriques

| Métrique | Définition |
|---|---|
| Valeur sociale | `V(π) = Σ v(C)` en centimes ; taux `V / Σ ref_u` |
| Coût total | `Σ c(C)` |
| Coalitions | nombre, tailles, part des unités hors singleton |
| Demandes servies | unités référencées / unités du lot (exclusions P2 détaillées) |
| Taux d'accord | accords / négociations (C, o) |
| Taux de réalisabilité | `|F|` / candidats avec `O(C) ≠ ∅` |
| Effort | négociations, succès du cache, candidats, découpes et paires élaguées, durée |
| Écart à l'optimum | manque absolu `V* − V` en centimes, toujours défini ; écart relatif `(V* − V) / V*` seulement si `V* > 0`. `V*` doit venir d'`idp_search`, ou d'un MILP `milp_certified_exact` |
| Décomposition (§11.5) | `savings_individual_negotiation`, `savings_offer_switch`, `savings_public_tier_pooling`, `residual_collective_negotiation`, ce dernier étant un **résidu non identifiable causalement** ; la somme est contrôlée exactement |
| Projection (P5) | part des blocs où la projection est active ; excès maximal du cœur |
| Reproductibilité | même empreinte sur deux exécutions et deux `PYTHONHASHSEED` |

### 11.5 Décomposition des économies

Pour un bloc C négocié sur `o_C`, chaque membre u ayant sa référence sur `o_u`, avec
`L(o, s) = offer.list_total(s)` (prix catalogue public), on définit cinq états :

| État | Définition | Sens |
|---|---|---|
| A | `Σ_u L(o_u, s_u)` | prix catalogue individuels, offres de référence |
| B | `Σ_u ref_u` | négociations individuelles |
| C₁ | `Σ_u L(o_C, s_u)` | offre commune, paliers individuels |
| C₂ | `L(o_C, s_C)` | offre commune, palier collectif |
| D | `c(C)` | négociation collective |

Les termes :

| Terme | Définition | Nom dans les métriques | Interprétation |
|---|---|---|---|
| `E_ind` | `A − B` | `savings_individual_negotiation` | écart mesuré entre prix catalogue et négociation individuelle |
| `E_switch` | `A − C₁` | `savings_offer_switch` | effet catalogue du passage à l'offre commune, à paliers individuels ; signe quelconque |
| `E_tier` | `C₁ − C₂` | `savings_public_tier_pooling` | mutualisation des places sur la grille publique ; ≥ 0 sous les préconditions ci-dessous |
| `E_residual_collective` | `(C₂ − D) − (A − B)` | `residual_collective_negotiation` | **résidu non identifiable causalement** (voir plus bas) |

**Identités exactes** (somme télescopique, sans double compte, en centimes entiers) :

- `v(C) = B − D = E_switch + E_tier + E_residual_collective` ;
- économie totale par rapport au catalogue :
  `A − D = E_ind + E_switch + E_tier + E_residual_collective`.

Un singleton donne `E_switch = E_tier = E_residual_collective = 0`. Pour une
structure, on somme sur les blocs. Toutes les grandeurs sont publiques ou des
montants d'accord : aucun plancher n'est lu.

**Pourquoi « résidu » et non « effet de la négociation collective ».** Le terme
`E_residual_collective` est la remise négociée collective, moins les remises négociées
individuelles. Il mélange trois mécanismes que les données ne permettent pas de
séparer :

- la baisse du plancher privé au palier collectif ;
- l'avantage de négociation proprement dit ;
- un artefact de la stratégie historique : les offres du leader sont des fractions
  de `R(C)`, donc le prix d'accord dépend des budgets.

Ce n'est donc **pas** un effet causal. Les métriques et les rapports le nomment
`residual_collective_negotiation`, et chaque tableau qui le contient porte la mention
« résidu comptable, non identifiable causalement ». Le séparer exigerait des
négociations contrefactuelles, par exemple avec les planchers des paliers
individuels. **[Hors périmètre]** : il n'est pas décomposé ni estimé autrement.

Les autres termes sont aussi des différences comptables le long d'un chemin fixé
(catalogue → offre commune → palier collectif → négociation). Un autre ordre
donnerait une autre répartition. Seul `E_tier` a une interprétation structurelle
directe : c'est l'effet de la grille publique, à offre fixée.

#### Préconditions et preuve de `E_tier ≥ 0`

**[Fait]** dans le code P1 :

- `OfferQuote.list_total(s) = s × tier_for(s).list_per_seat`.
- `tier_for(s)` exige `1 ≤ s ≤ capacity_seats` (`_require_seat_count`), puis choisit
  le palier de plus grand seuil `min_seats ≤ s` (`_tier_index`).
- `_validate_tier_sequence` impose : premier seuil égal à 1, seuils strictement
  croissants, prix par siège non croissants.

Préconditions utilisées :

| Code | Précondition | Garantie par |
|---|---|---|
| T1 | `L(o, s) = s · p_o(s)`, où `p_o(s)` est le prix par siège du palier applicable | code de `list_total` |
| T2 | `p_o` est non croissant en s | `_validate_tier_sequence` + `_tier_index` (l'indice de palier ne décroît pas quand s augmente, et les prix ne croissent pas le long des indices) |
| T3 | C₁ et C₂ portent sur la **même** offre `o_C` | définition |
| T4 | `1 ≤ s_u ≤ s_C = Σ_u s_u ≤ capacity(o_C)` | H2 et la fabrique de requête ; `s_u ≤ s_C` puisque toutes les places sont positives |
| T5 | montants en centimes entiers | P1 |

**Preuve.** Par T4, `s_u ≤ s_C`, donc par T2 `p(s_u) ≥ p(s_C)`. Avec T1 et T3 :
`C₁ = Σ_u s_u·p(s_u) ≥ Σ_u s_u·p(s_C) = s_C·p(s_C) = C₂`. ∎

**Ce que la preuve n'utilise pas.** Le prix **total** `L(o, ·)` n'est **pas**
monotone. Contre-exemple avec les paliers `(1 : 10 000)` et `(3 : 6 000)` centimes
par siège : `L(2) = 20 000 > L(3) = 18 000`. La preuve repose seulement sur la
monotonie du prix **par siège**, qui donne la sous-additivité
`L(o, Σ s_u) ≤ Σ L(o, s_u)`. Si une version future autorisait des prix par siège
croissants, ou des paliers propres à l'offre de chaque membre, `E_tier` pourrait
devenir négatif : le test de propriété doit alors échouer.

**Tests obligatoires (P4.5, module M7) :**

- seuil t d'un palier : `s_C = t − 1`, `s_C = t` et `s_C = t + 1`, avec `E_tier`
  attendu calculé à la main ;
- membres aux nombres de places différents qui franchissent ensemble un seuil
  (1 + 2 = 3 avec un seuil à 3 ; 2 + 2 + 1 = 5 avec des seuils à 3 et 5), qui restent
  en dessous (1 + 1 = 2), et dont un seul membre est déjà au palier supérieur ;
- grille à un seul palier, donc `E_tier = 0` ;
- tous les membres au palier maximal, donc `E_tier = 0` ;
- cas où le prix total décroît (contre-exemple ci-dessus), où `E_tier ≥ 0` reste
  vrai ;
- capacité atteinte exactement (`s_C = capacity`) ;
- test de propriété : grilles aléatoires valides et découpages aléatoires des
  places, `E_tier ≥ 0` ;
- identités exactes en entiers sur des blocs aléatoires.

### 11.6 Hypothèses à tester (aucun résultat n'est annoncé)

- **E1** : `idp_search` = `dp_search` = force brute (= MILP `milp_certified_exact`) sur 100 % des instances. C'est une
  exigence de correction, et tout écart est une anomalie.
- **E2** : B1 est optimal quand les blocs positifs de F sont disjoints, et
  sous-optimal sur des instances construites. Son écart moyen est **mesuré**, pas
  prédit.
- **E3** : B0 re-noté a un taux de blocs non réalisables qui croît avec
  l'hétérogénéité des fenêtres et des exclusions.
- **E4** : `E_tier` croît avec la pente des grilles (et vaut 0 pour une grille
  plate).
- **E5** : en S-NULL, `|V|` reste de l'ordre de l'arrondi, parce que la trajectoire
  P3 est proportionnelle à R, F et I. À vérifier : le calcul flottant peut créer des
  écarts de quelques centimes.
- **E6** : au-delà d'environ 10 unités, la durée est dominée par l'énumération et la
  négociation plutôt que par le solveur.

**Limites de validité.**

- Données synthétiques.
- Vendeur simulé simple, fidèle à l'historique.
- Prix négociés dépendant des budgets (artefact).
- Aucune généralisation à un marché réel. Le RAG ne fournit aucun prix.

**Paquet de reproductibilité.**

- Manifeste par scénario : paramètres, graine, empreinte du catalogue et des termes,
  empreinte des unités.
- Identifiants de configuration et d'exécution.
- JSON canonique des résultats.
- Environnement (versions de Python, NumPy et SciPy) à part.
- Rapport régénérable à partir du JSON.

## 12. Sous-phases et dépendances (B11)

**Règle.** Une sous-phase ne démarre qu'après validation de la précédente (rapport,
diff, tests, revue). Elle ne démarre pas non plus tant que les décisions listées dans
sa rubrique « Décisions requises » ne sont pas validées. Chaque prompt Codex cite les
sections normatives de ce document. Codex ne choisit aucun paramètre mathématique :
K, P, l'ordre d'énumération, les départages, la clé du cache, les statuts, les
libellés MILP, le protocole B0, le chemin de décomposition et les graines sont tous
fixés ici.

**P4.1 — Modèle du jeu et contrats**

- *Objectifs* : M4 et les types partagés. Aucune allocation en P4 : `cover(S)` sert
  aux propositions du §4 et préparera P5.
- *Décisions requises* : D1, D2. *Sections normatives* : §3, §4, §8.2, §8.3 (M4).
- *Fichiers* : `domain/coalition_game.py` ; `tests/test_coalition_game.py`.
- *Fichiers existants concernés* : `tests/test_python310_compatibility.py` (ajout du
  module).
- *Dépendances* : aucune hors du domaine.
- *Tests* : propriétés de `v*` ; propositions 1 à 4 ; borne numérique ; singletons.
- *Acceptation* : tous les tests verts, sous Python 3.10 compris.
- *Risques* : confondre `v` et `v*` ; choisir K < n.
- *Livrables* : code, tests, `docs/PHASE_P4_1_GAME_MODEL.md`.

**P4.2 — Candidats, faisabilité, cache et coûts**

- *Objectifs* : M1, M2, M3.
- *Décisions requises* : D7. *Sections normatives* : §3.2, §6.1, §8.3 (M1 à M3), §10.
- *Fichiers* : `application/coalition_candidates.py`,
  `application/coalition_feasibility.py`, `application/negotiation_cache.py`,
  `application/coalition_costs.py`, et leurs tests.
- *Fichiers existants concernés* : `application/reference_costs.py`, seulement si la
  décision D7 (alias public de la validation) est acceptée.
- *Dépendances* : P4.1, P2, P3.
- *Tests* : énumération naïve ; violations ; cache ; `c({u}) = ref_u` ; erreur si la
  configuration change.
- *Acceptation* : `v({u}) = 0` sur tous les lots de test ; un seul appel pour deux
  mandats identiques.
- *Risques* : explosion combinatoire ; cache indexé par erreur sur des identifiants.
- *Livrables* : code, tests, rapport.

**P4.3 — Intégration DP/IDP et orchestration**

- *Objectifs* : M5 (sans MILP) et M9 ; banc d'essai pour recalibrer les limites
  (strate « performance » du §11.3).
- *Décisions requises* : D3, D4, D5. *Sections normatives* : §4, §5, §6.2 à §6.4,
  §8.3 (M5, M9), §10.
- *Fichiers* : `application/partition_solver.py`,
  `application/coalition_formation.py`, et leurs tests.
- *Fichiers existants concernés* : aucun (les solveurs historiques sont seulement
  importés).
- *Dépendances* : P4.2.
- *Tests* : IDP = DP ; force brute ; indépendance vis-à-vis de P ; décomposition ;
  refus H2 ; garde de taille ; reproductibilité.
- *Acceptation* : égalités exactes ; statuts conformes ; mesures de temps publiées
  avec leur contexte.
- *Risques* : temps de calcul ; mauvaise interprétation du départage.
- *Livrables* : code, tests, rapport, mesures.

**P4.4 — Baselines et comparaison avec la force brute**

- *Objectifs* : M6, et validation systématique par la force brute (n ≤ 9). En
  option, **P4.4-bis** : l'adaptateur MILP (§6.3).
- *Décisions requises* : D3 (libellés MILP). *Sections normatives* : §6.3, §7
  (protocole B0), §8.3 (M5, M6).
- *Fichiers* : `application/formation_baselines.py`,
  `infrastructure/baselines/legacy_broker.py`, en option
  `infrastructure/optimization/exact_ip.py`, et leurs tests.
- *Fichiers existants concernés* : aucun (le Broker est seulement utilisé).
- *Dépendances* : P4.3.
- *Tests* : B1 et B0 inférieurs ou égaux à l'optimum ; reproduction du Broker ;
  procédure MILP et ses libellés.
- *Acceptation* : aucun écart non expliqué ; B0 n'est jamais présenté comme
  équivalent.
- *Risques* : comparaison injuste B0 / P4 ; tolérances MILP prises pour une preuve.
- *Livrables* : code, tests, rapport.

**P4.5 — Évaluation expérimentale, rapport et provenance**

- *Objectifs* : M7 et M8 ; exécution du protocole du §11.
- *Décisions requises* : D8, D9. *Sections normatives* : §11.3 à §11.6, §8.3 (M7, M8),
  §15 (garde D8).
- *Fichiers* : `application/formation_evaluation.py`,
  `infrastructure/evaluation/formation_scenarios.py`,
  `infrastructure/evaluation/formation_report.py`, et leurs tests.
- *Fichiers existants concernés* : `tests/test_offer_catalog.py` (une entrée de liste
  blanche et les tests de garde de D8).
- *Dépendances* : P4.4.
- *Tests* : identités de décomposition ; tests aux frontières de paliers (§11.5) ;
  garde D8 ; reproductibilité des scénarios et du rapport ; mentions obligatoires
  dans le rapport.
- *Acceptation* : tous les chiffres proviennent d'exécutions enregistrées, avec leur
  manifeste.
- *Risques* : sur-interprétation ; artefact budgétaire.
- *Livrables* : résultats, rapport, `docs/PHASE_P4_5_EVALUATION.md`.

**P5 [Hors périmètre P4]** : répartition (§9), avec Shapley rationnel, projection
(unicité du vecteur, convention pour λ, données conservées), arrondi et
diagnostics du cœur. Décision requise : D6.

## 13. Préservation de l'historique scientifique (B12)

| Élément historique | 1. Conservé tel quel | 2. Réutilisé derrière un adaptateur | 3. Remplacé dans le nouveau workflow | 4. Baseline historique uniquement |
|---|---|---|---|---|
| `run_alternating_negotiation`, `Message`, `Agent` | ✔ (utilisés par P3) | | | |
| `SellerAgent` | ✔ (fichier inchangé) | ✔ `_ConfiguredSellerAgent` (P3) | | |
| `BuyerAgent` | ✔ (représentants P3, B0) | | | |
| `CoalitionLeaderAgent.receive_message` | ✔ (fichier inchangé) | règle reproduite par `MandateLeader`, tests différentiels (P3-bis) | | |
| `CoalitionLeaderAgent.negotiate_for_group` | ✔ (démos) | | ✔ par P3 + P4 | |
| `BrokerAgent` | ✔ | ✔ `legacy_broker` | ✔ comme mécanisme de formation | ✔ B0 |
| `dp_search` (DP de Yeh), `idp_search` (DP avec élagage, nom historique), `brute_force_search` | ✔ | ✔ `partition_solver` | | |
| `ip_search` (MILP, à ne pas confondre avec l'IP anytime du cours) | ✔ (démos) | formulation reprise par `exact_ip` | | |
| `validate_partition` | ✔ | | | |
| `shapley_value` | ✔ | ✔ oracle différentiel (P5) | | |
| `allocate_shapley_payments`, `_bounded_equal_allocation` | ✔ (démos) | | ✔ par l'allocation P5 | |
| `CoalitionProblem` (tables de remises) | ✔ | | ✔ par `CoalitionGame` | ✔ jeu de démonstration |
| `Entry.py` et son golden master | ✔ | | | ✔ |

L'IDP de Rahwan et Jennings (2008) et l'IP de Rahwan et al. (2009), présentés dans
le cours, **n'existent pas** dans le code. Les implémenter dans de nouvelles fonctions,
sans toucher à l'historique, serait un ajout scientifique possible (D11, hors P4).

**[Décision]** P4 ne prévoit **aucune** modification d'un algorithme historique.
Chaque réutilisation se fait par adaptateur, et les tests historiques restent verts.
La seule modification envisagée d'un code existant non historique est l'alias public
de la validation P2 (D7).

## 14. Cohérence avec P2/P3 et contradictions relevées

Vérifié :

- P2 §12 et §15 : P4 construit ses requêtes avec `common_offers`, et `v({u}) = 0`
  par construction. Cohérent avec §3.2.
- P2 §13 : (`request_key`, `oracle_configuration_id`) identifie un résultat
  reproductible. Cohérent avec §10.
- P2 §7 : H2 vérifiée avant toute négociation, avec refus. Cohérent avec §5.
- P3-bis : `rejected` ⇔ `F > R` avec la stratégie par défaut, ce qui permet de
  piloter le taux d'accord (§11.3) ; ACCEPT d'un expéditeur inconnu et accord hors
  [F, R] lèvent une exception. Cohérent avec M3.

Contradictions trouvées et traitées (documents seulement) :

1. **Rapport P3-bis, règle 4** : « `rejected` et `turn_limit` signifient
   c(C) = ∞, donc v(C) = −P ». C'est contraire à la décision d'exclusion. Règle
   réécrite.
2. **Rapport P3, §6** : « aucun accord n'existe (c(C) = ∞) » était ambigu (pour
   l'offre, ou pour la coalition ?). Précisé : pas d'accord **sur cette offre** ; une
   coalition sans accord sur aucune offre commune n'est pas réalisable.
3. **Rapport P2, §13** : « répartition des gains en P4 », alors que la répartition
   relève de P5. Corrigé.
4. **Version précédente de cette spécification** :
   - `K = n + 1` est remplacé par la borne démontrée `K ≥ n` (recommandé `K = n`) ;
   - l'extrapolation « environ 5 s pour DP à n = 14 » était fausse, puisque
     0,62 s × 3 ≈ 1,9 s ; corrigée ;
   - l'affirmation « P5 réutilise la table du solveur » est fausse, car les fonctions
     historiques ne l'exposent pas ; corrigée (§3.4, §9.2).

5. **Nomenclature (D10, résolue)** : la version précédente laissait ouverte la
   question de l'IDP. Le support de cours (chapitre C3b, diapositives 18 à 25, et
   non C3a) montre que l'IDP du cours ne découpe pas certaines tailles de coalitions.
   `idp_search` n'est donc pas cet IDP, et l'« IP » du cours n'est pas un MILP (§6.3).

**Vérification finale [Fait, sauf mention contraire]**

| Point | Constat | Preuve |
|---|---|---|
| `request_key` économique | contenu canonique recalculé (offre publique, unités, places, réservation), sans identifiant technique ni empreinte stockée | `domain/negotiation_request.py` (`request_key_content`, schéma v2) ; 30 tests dans `tests/test_negotiation_request_key.py` ; rapport P2 §13 |
| `oracle_configuration_id` séparé | sa charge utile ne contient aucune `request_key` ; un même mandat garde sa clé sous deux configurations | `_configuration_id` dans `simulated_oracle.py` ; tests `test_one_mandate_keeps_its_key_under_several_oracle_configurations` et `test_different_mandates_get_different_keys_under_one_oracle_configuration` |
| Singletons : même fabrique, même configuration | P2 négocie `negotiation_request_for((unit,), offer)` et refuse une configuration qui change dans un lot ; P4 utilise la même fabrique, le même cache et vérifie la configuration (§3.2, M3) | `reference_costs.py` (fabrique et erreur « oracle configuration changed within one lot ») ; pour P4 : **[Décision]** |
| H2 / I1 / I2 cohérents | H2 vérifiée avant toute négociation ; P3 crée des agents neufs à chaque appel et vérifie la reproductibilité ; I2 contrôlée par M3 | `lot_admissibility.py`, `require_optimizable()` ; `_execute_once` dans `simulated_oracle.py` ; §5 |
| Centimes entiers | P1 à P3 en entiers ; `CoalitionGame` en entiers ; l'optimiseur reçoit des entiers représentés exactement en `float` (borne du §4), qui sont reconvertis et vérifiés ; P5 travaille en rationnels, puis en centimes | §4, §8.2, §9.6 ; pour P4 et P5 : **[Décision]** |
| Shapley et projection en P5 | aucune sous-phase P4 ne les implémente | §9, §12 |
| Ni LLM ni RAG ne choisit la partition | règles de dépendance et test AST ; les expériences P4 n'utilisent pas de LLM | §8.1, §11.1 ; **[Décision]** |
| Aucune décision mathématique implicite pour Codex | chaque sous-phase indique ses décisions requises et ses sections normatives ; tous les paramètres sont fixés | §12 |

Écarts avec le code, à traiter pendant l'implémentation (pas des contradictions) :

- `_validate_outcome` est privée dans `reference_costs.py`, alors que M3 en a besoin
  (D7).
- Le protocole `NegotiationOracle` ne déclare pas `oracle_configuration_id`, alors que
  l'oracle P3 l'expose et que le cache en a besoin : protocole applicatif dédié (M3).

## 15. Décisions ouvertes, hypothèses et hors périmètre

**Décisions à valider :**

- **D1.** Exclusion, avec une pénalité `P = 1` interne à l'adaptateur (§3.5, §4).
- **D2.** Départage par `w` avec `K = n` (§4).
- **D3.** `idp_search` par défaut ; `dp_search` et la force brute en contrôles ;
  MILP optionnel, avec la procédure et les libellés du §6.3 (seul
  `milp_certified_exact` peut être qualifié d'optimum exact).
- **D4.** Limites provisoires 14 / 14, et force brute ≤ 9 dans les tests et ≤ 10 en
  validation, à recalibrer en P4.3 (§6.4).
- **D5.** Statut global `incomplete` plutôt qu'un échec total quand une composante
  dépasse la limite (§8.3, M9).
- **D6.** Paiement minimal `θ_u = 0` et projection euclidienne en P5 (§9.5).
- **D7.** Exposer un alias public de la validation du contrat d'oracle dans
  `reference_costs.py` : seule modification d'un fichier existant envisagée.
- **D8.** Termes privés dans le seul générateur expérimental. Garde proposée :
  - `FLOOR_ALLOW_LIST` reçoit **une seule** nouvelle entrée :
    `coalition_travel/infrastructure/evaluation/formation_scenarios.py` ;
  - un test vérifie que la liste blanche contient exactement ses quatre entrées
    connues, pour que tout ajout futur échoue explicitement ;
  - le test de garde existant interdit déjà les noms protégés partout ailleurs,
    `load_offer_catalog` compris. Les modules du domaine et de l'application
    reçoivent donc des objets et ne chargent jamais de catalogue ;
  - un nouveau test AST interdit à tout module `domain/` ou `application/` d'importer
    `coalition_travel.infrastructure` (dont le générateur) ;
  - un test vérifie que `Scenario`, son manifeste et le rapport ne contiennent aucun
    type ni champ de plancher ;
  - le générateur construit lui-même l'oracle, si bien que les termes ne sortent
    jamais du module ;
  - les fichiers de termes générés sont écrits dans le répertoire de l'expérience et
    ne sont pas versionnés **[à valider]**.
- **D9.** Plan expérimental du §11.3 : quatre strates (correction exhaustive,
  performance, exploration descriptive, confirmation optionnelle) ; 20 graines par
  cellule en exploration, comme minimum descriptif sans garantie de puissance ;
  5 répétitions chronométrées après une chauffe ; taille confirmatoire calculée à
  partir de la variance observée ; graines disjointes ; aucun filtrage a posteriori.
- **D10 — résolue [Fait].** `idp_search` est un DP avec élagage par bornes de taille.
  Il n'est pas l'IDP de Rahwan et Jennings (2008) présenté au chapitre C3b ; son nom
  historique est conservé, accompagné de la note du §6.3.
- **D11 [Hors P4].** Implémenter l'IDP et l'IP du cours dans de nouvelles fonctions,
  pour leur valeur pédagogique et comparative, sans modifier l'historique.

**Hypothèses** : indépendance des mandats pour un vendeur réel (I1) ; E1 à E6
(§11.6) ; limite de 14 unités.

**Hors périmètre P4** :

- implémentation de la répartition (P5) ;
- capacité partagée et jeu à fonction de partition ;
- cache persistant ;
- négociations contrefactuelles pour séparer les effets dans `E_residual_collective` ;
- répartition interne aux unités ;
- toute utilisation du LLM ou du RAG dans une décision de formation.
