# I2 : périmètre et critères d'acceptation de P5 (répartition des économies)

**Statut :** périmètre validé, révision 3. La validation finale a demandé deux harmonisations, intégrées au §9. Le démarrage d'I2 n'est pas autorisé.

- I2 **n'est pas démarrée** et aucun code n'a été écrit pour elle.
- Aucune opération Git n'a été faite.

**Rôle de ce document :** préciser le périmètre et les critères d'acceptation d'I2 avant
que son démarrage soit demandé.

**Textes de référence :**

- `docs/PHASE_P4_SPECIFICATION.md`, §9.1 à §9.7 (mathématiques de P5) ;
- `docs/PHASE_3H_P5_INTEGRATION_PLAN.md`, révision 4 : §6.1 (répartition entre les
  voyageurs d'une unité, ID-5) et §7, I2 (performance, CoverCache, M0 à M2).

**Ce qui a déjà été accepté :**

- I0 est clôturée ;
- I1 est acceptée (`docs/PHASE_I1_ORCHESTRATION_REPORT.md`, §9).

---

## 0. Résumé

1. **Ce que fait I2.** I2 implémente la répartition P5, bloc par bloc :
   - Shapley exact sur `v*|C` ;
   - projection dans `[0, ref_u]` ;
   - arrondi au plus fort reste ;
   - répartition entre les voyageurs d'une unité, par gains égaux sous plafonds.

   Elle s'appuie sur les jeux déjà construits par P4, **sans aucun appel à l'oracle**.
2. **Ce qu'I2 ne fait pas :** ni la présentation, ni la CLI, ni les explications (I3) ;
   ni l'origine ou l'aller-retour (I4). Elle ne modifie aucun algorithme de P2 à P4.
3. **Six exemples de référence (§4) seront figés comme tests.** E6 protège contre l'erreur qui consiste à exiger l'axiome du joueur nul après la projection. L'exemple E3 a été
   calculé pendant la préparation de ce document, à titre d'analyse et hors du dépôt. Il
   confirme l'observation de la revue d'I1 sur le cas Tokyo : la grande demande, qui
   donne accès au palier sans voir baisser son propre prix, reçoit la plus grande part
   de l'économie (39 € sur 90 €).
4. **Six décisions sont demandées** avec l'autorisation d'I2 (§7).

---

## 1. Préalables

| Préalable | État |
|---|---|
| I1 acceptée | fait |
| ID-6 (θ_u = 0, paiement minimal nul) confirmée par un addendum à la spécification | **addendum rédigé :** `docs/PHASE_P5_ADDENDUM_ID6.md`, à valider avec ce périmètre. C'est un fichier séparé : la spécification P4 n'est pas modifiée, ce qui préserve la preuve A9. L'addendum explicite une conséquence, qu'il faut valider en connaissance de cause : avec θ = 0, une unité peut payer 0 (exemple E2) |
| Base de référence | option A reconduite, sauf décision Git contraire (§7, D-I2-6) : manifeste SHA-256 et copie complète avant la première modification |

---

## 2. Périmètre

### 2.1 Inclus

| Élément | Module proposé |
|---|---|
| Mathématiques pures en rationnels : Shapley exact (somme entière sur le dénominateur `n!`), projection par les conditions KKT avec λ*, plus fort reste, gains égaux sous plafonds | `domain/savings_allocation.py` (bibliothèque standard seulement : `fractions`, `math`) |
| Allocation d'une formation, bloc par bloc, et répartition par voyageur ; version `p5-allocation-v1` ; compteurs et durées | `application/savings_allocation.py` |
| `CoverCache` : mémoire des couvertures `v*`, propre à une exécution, fondée sur le lemme de restriction (plan §7, I2) | idem |
| Diagnostic de stabilité : excès maximal du cœur par bloc, `max_{S⊊C} (v*(S) − Σ_{u∈S} y_u)`. Il est seulement mesuré, jamais garanti (spécification §9.4 et métrique « Projection (P5) » du §11) | idem |
| Intégration dans `plan_lot` : `TripPlan.allocation` | `application/trip_planning.py` (selon D-I2-2) |
| Banc de mesure M0 à M2 | script séparé `Multi-Agent/evaluate_allocation.py` |
| Rapport, manifeste de la base et diff | `docs/` |

### 2.2 Exclu

- **Côté P2 à P4 :** aucune modification de P2, P3 ou P4. En particulier,
  `coalition_formation.py`, les solveurs et le cache sont inchangés.
- **Côté autres étapes :**
  - le `TripProposal`, le rendu, la CLI et les explications relèvent d'I3 ;
  - l'avertissement de simulation est mis en œuvre en I3 ;
  - l'origine, l'aller-retour, le catalogue v2 et les lieux relèvent d'I4 ;
  - Ollama relève d'I5.
- **Aucun rôle pour le LLM ni le RAG** dans P5.
- **Le Shapley historique** (`shapley_value`, en flottants) ne sert que d'oracle
  différentiel dans les tests (spécification §9.7). Il n'est jamais le calcul officiel.

### 2.3 Durcissement d'I1 (selon D-I2-3)

Les deux réserves de la revue d'I1 (rapport I1, §9) pourraient être traitées en I2,
puisque `trip_planning.py` y est de toute façon modifié :

1. **Contrôler le SHA-256 de `DemandPoolSnapshot`** : 64 caractères hexadécimaux en
   minuscules.
2. **Envelopper le décodage du manifeste** du carnet dans `DemandPoolError`.

Chacune s'accompagne d'un test qui échoue avant la correction.

---

## 3. Spécification opérationnelle

### 3.1 Entrées et sorties

**Entrées :**

- le `FormationResult` de P4 : blocs et composantes, avec leur `CoalitionGame` ;
- les `TravelUnit` du lot : budgets par siège en centimes ;
- θ = 0.

**Unités hors allocation :**

- les unités `unserved` (`no_admissible_offer`, `no_solo_reference`) ;
- les unités non résolues (`component_too_large`, `capacity_model_violated`).

Elles n'ont aucune allocation et apparaissent dans `AllocationResult.unallocated`, avec
leur raison. Elles ne reçoivent jamais de montant fictif.

### 3.2 Préconditions vérifiées à l'exécution

Pour chaque bloc C qui n'est pas un singleton :

1. **Le jeu existe.** La composante qui contient C a un `CoalitionGame`, et C en fait
   partie (`C ∈ F`).
2. **Toutes les sous-coalitions ont été évaluées.** Toute sous-coalition non vide `S ⊆ C`
   apparaît parmi les coalitions évaluées par P4 (`FormationResult.evaluations`),
   réalisable ou non.
   - **Pourquoi c'est attendu.** Toutes les sous-coalitions de C partagent au moins
     l'offre de C. Ce sont donc des candidates de M1 (spécification §9.2).
   - **Pourquoi on le vérifie.** C'est cette précondition qui garantit que `v*|C` ne
     dépend d'aucune hypothèse cachée.
   - **En cas d'échec :** `AllocationPreconditionError`.
3. **Les montants sont cohérents.** `v(C) = Σ ref_u − c(C) ≥ 0` et `c(C)` égale le coût
   du `FormedBlock`.

### 3.3 Calcul par bloc

| Étape | Calcul | Contrôle exact |
|---|---|---|
| 1 | `v*|C` : couverture du bloc, prise dans `CoverCache` si la couverture de la composante y est déjà ; sinon `cover_values(C)` en Θ(3^k) | `v*(C) = v(C)` (spécification, propriété 6) |
| 2 | `φ_u = N_u / n!`, avec `N_u = Σ_{S⊆C∖{u}} |S|!(n−|S|−1)! (v*(S∪{u}) − v*(S))`. Le numérateur est un entier exact, et il y a une seule `Fraction` par unité | `φ ≥ 0` ; `Σ φ = v(C)` |
| 3 | projection de φ dans `[0, ref_u]` (spécification §9.5), avec λ* = point de Λ le plus proche de 0, calculé en rationnels | `Σ y = v(C)` ; conditions KKT ; `λ* ≤ 0` |
| 4 | arrondi au plus fort reste (spécification §9.6), départage par `unit_id` ; `x'_u = ref_u − y'_u` | `Σ x' = c(C)` en entiers ; `0 ≤ x'_u ≤ ref_u ≤ B_u` |
| 5 | répartition entre les voyageurs de chaque unité : gains égaux sous plafonds, puis plus fort reste par siège (plan §6.1) | `Σ q' = x'_u` ; `0 ≤ q'_s ≤ b_s` |
| 6 | diagnostic : excès maximal du cœur et projection active ou non | seulement mesuré |

**Singletons :** `φ = 0`, `x' = ref_u`, pas de projection. L'étape 5 s'applique tout de
même, puisque le voyageur paie sa part du prix solo de son unité.

### 3.4 Contrats

**`BlockAllocation`**

- identification : `unit_ids`, `offer_id`, `cost_cents`, `value_cents` ;
- calcul : `phi` (rationnels), `y` (rationnels), `y_rounded` (centimes),
  `payments_cents` ;
- projection : `projection_active`, `saturated_unit_ids`, `lambda_star` ;
- écarts : `distance_squared` et `distance_max`, entre φ et y ;
- diagnostic : `rounding_gap`, `max_core_excess`.

**`TravelerShare`**

- `unit_id`, `profile_id`, rang du siège, `amount_cents` ;
- saturation du profil ;
- τ de l'unité.

**`AllocationResult`**

- `allocation_version`, `formation_run_id` ;
- `theta_cents` : paiement minimal θ appliqué à toutes les unités ; il vaut 0 en `p5-allocation-v1` (ID-6, `docs/PHASE_P5_ADDENDUM_ID6.md`). C'est un champ du contrat métier, et il entre aussi dans le contenu canonique de `allocation_sha256` ;
- `blocks`, `shares`, `unallocated` ;
- compteurs : couvertures calculées, masques visités, contributions marginales ;
- durées par sous-étape (volatiles, hors empreinte) ;
- `allocation_sha256` : JSON canonique, les rationnels écrits `"p/q"`.

### 3.5 Invariants contrôlés à chaque exécution

Ils reprennent le plan, §8, point 4. Une violation lève `AllocationConsistencyError`.

- `Σ x'_u = c(C)` pour chaque bloc ;
- `0 ≤ x'_u ≤ ref_u ≤ B_u` pour chaque unité ;
- `Σ q'_s = x'_u` et `0 ≤ q'_s ≤ b_s` pour chaque voyageur ;
- aucun appel à l'oracle pendant P5 (§5, A5).

---

## 4. Exemples de référence à figer

| # | Cas | Données | Résultat attendu |
|---|---|---|---|
| E1 | v* et non v (spécification §3.5) | C = {a, b, c} ; F : singletons, v({a,b}) = 6, v({a,b,c}) = 9 ; références assez grandes (10 000) | φ = (4, 4, 1) ; projection inactive. Le Shapley historique sur v* redonne (4, 4, 1) |
| E2 | paiement négatif évité par la projection (spécification §9.4) | seule la grande coalition est réalisable, v = 900 ; ref = (100, 1 000, 1 000) | φ = (300, 300, 300) ; y = (100, 400, 400) ; λ* = −100 ; unité saturée : la première ; x = (0, 600, 600) |
| E3 | cas Tokyo (carnet v1 et demande de 8 voyageurs à 500 €, rapport I1 §5.3) | bloc (pool-tyo-01, pool-tyo-02, pool-tyo-04, user) ; v(C) = 9 000 | φ = (600, 1 500, 3 000, 3 900) ; projection inactive ; paiements (48 000, 48 900, 51 000, 380 100) ; pour `user`, τ = 47 512,5, quatre sièges à 47 513 et quatre à 47 512 |
| E4 | budgets individuels (contre-exemple de la revue, plan §6.1) | budgets (1 000, 10 000), X = 5 000 | (1 000, 4 000) |
| E5 | renommage (plan §6.1, R7c) | profils `a` (1 siège, budget 10 000) et `b` (1 siège, budget 20 000), X = 3 001 | τ = 1 500,5 ; `a` paie 1 501 ; après échange des noms, le siège au budget de 20 000 paie 1 501 |
| E6 | joueur nul après projection (§5.1) | φ = (450, 450, 0), où c est un joueur nul de v\* ; références (100, 1 000, 1 000) ; V = 900 | λ* = −175 ; y = (100, 625, 175) ; c reçoit 175 > 0 ; unité saturée : la première ; x = (0, 375, 825) |

### 4.1 Comment E3 a été obtenu

Le calcul a été fait pendant la préparation de ce document, avec un script jetable, hors
du dépôt :

1. `plan_lot` sur le carnet v1 avec la demande de test ;
2. lecture du `CoalitionGame` de la composante et de `cover_values(C)` ;
3. Shapley exact en `Fraction`.

Le Shapley historique en flottants donne les mêmes valeurs : 600,0 ; 1 500,0 ; 3 000,0 ;
3 900,0.

Comme E3 a été calculé avant d'écrire le code d'I2, il sert de véritable oracle pour le
code à venir.

### 4.2 Ce que montre E3

**v* diffère de v** sur trois sous-coalitions :

| Sous-coalition | v | v* |
|---|---|---|
| {01, 04} | −5 400 | 0 |
| {02, 04} | −3 600 | 0 |
| {01, 02, 04} | −3 000 | 1 800 |

Calculer Shapley sur v donnerait donc un autre résultat.

**Économie de chaque demande** par rapport à sa référence solo :

| Demande | Économie |
|---|---|
| 01 | 6 € |
| 02 | 15 € |
| 04 | 30 € |
| user | 39 € |

La grande demande reçoit la plus grande part alors que son prix négocié ne baisse pas.
Shapley récompense sa contribution marginale, c'est-à-dire l'accès au palier qu'elle
apporte aux autres.

Les explications d'I3 devront distinguer trois montants, comme l'a demandé la revue
d'I1 :

- la valeur créée par la coalition (90 €) ;
- la contribution calculée par P5 (φ) ;
- le montant finalement payé (x').

---

## 5. Critères d'acceptation

| Id | Critère |
|---|---|
| A1 | Les 724 tests existants passent sans modification, avec `PYTHONHASHSEED` 0 et 2. Toute exception doit être nommée ici avant le démarrage ; aucune n'est prévue si `TripPlan.allocation` reçoit une valeur par défaut |
| A2 | Les propriétés sont vérifiées **objet par objet**, en exact. Les quatre objets (φ, y, y', q) sont détaillés au §5.1. Les trois premiers sont vérifiés sur au moins 300 jeux aléatoires, le quatrième sur au moins 1 000 unités aléatoires. Les axiomes de Shapley ne sont **jamais** exigés de y, de y' ou de q |
| A3 | Les exemples E1 à E6 sont reproduits exactement, comme tests obligatoires. E6 vérifie qu'un joueur nul peut recevoir `y_u > 0` après la projection |
| A4 | **Oracle différentiel, appliqué au même jeu v\*.** On compare φ_exact(v\*) avec `shapley_value(u, C, v*)`, où la fonction caractéristique passée au Shapley historique est **la couverture v\*\|C** (lue dans la table de couverture), **jamais v**. Tolérance : `|φ_exact − φ_historique| ≤ 1e-6 × max(1, |V|)` pour chaque unité, sur les jeux de A2 et sur E1 et E3. Cette comparaison n'existe que dans les tests. Un test AST vérifie que les modules officiels d'I2 n'importent ni `CoalitionStructureSearch`, ni `cooperative_game`, ni aucun module qui exporte `shapley_value`. Comparer avec Shapley(v) serait une erreur de protocole : l'écart y est attendu mathématiquement (spécification §9.3), et ce n'est pas une erreur numérique |
| A5 | Zéro appel à l'oracle pendant P5. On le vérifie de deux façons : le compteur de la session reste inchangé, et un faux oracle qui lève une exception s'il est appelé est substitué après la formation |
| A6 | Les invariants du §3.5 sont contrôlés à chaque exécution, et chacun a un test de violation |
| A7 | Les mutants sont tués : Shapley sur v au lieu de v* ; signe de λ inversé ; projection omise ; arrondi à l'entier inférieur sans reste ; poids de Shapley décalé de un ; partage égal sans plafond ; prorata ; départage inversé ; mauvais effectif dans τ ; précondition du §3.2 supprimée ; `CoverCache` qui renvoie la couverture d'un autre sous-ensemble |
| A8 | Les mesures M0, M1 et M2 sont faites dans la même session, et les seuils pré-enregistrés (§6) sont atteints |
| A9 | P4 n'est pas modifié. On le prouve par le manifeste de la base : les fichiers de P2 à P4 sont identiques. Dans ce cas, l'empreinte exploratoire `997109ee…` n'a pas à être régénérée. Si un fichier de P4 devait changer, la régénération deviendrait obligatoire |
| A10 | Les nouveaux modules qui n'utilisent que la bibliothèque standard s'importent sous un vrai Python 3.10. Golden master, ruff et `git diff --check` sont propres |
| A11 | Le rapport I2, le manifeste de la base et le diff complet sont produits, sans chemin personnel |

### 5.1 Propriétés vérifiées, objet par objet (détail de A2)

Chaque propriété porte sur un objet précis. Les axiomes de Shapley ne s'appliquent qu'à
φ.

| Objet | Propriétés testées | À ne pas exiger |
|---|---|---|
| **φ**, Shapley exact sur `v*\|C` | efficacité (`Σ φ = v*(C) = v(C)`) ; non-négativité (`φ ≥ 0`, par la superadditivité de v\*, spécification §9.4) ; symétrie (deux joueurs interchangeables dans v\* reçoivent le même φ) ; joueur nul (si `v*(S∪{u}) = v*(S)` pour tout S, alors `φ_u = 0`) ; additivité, sur des paires de jeux construites pour cela | – |
| **y**, projection dans `[0, ref_u]` | somme conservée (`Σ y = v(C)`) ; bornes (`0 ≤ y_u ≤ ref_u`) ; conditions KKT exactes (`y_u = clip(φ_u − λ*, 0, ref_u)`) ; convention λ* (`λ* = min(max(0, λ_lo), λ_hi)`) et `λ* ≤ 0` ; si aucune borne n'est active, `y = φ` et `λ* = 0` ; **symétrie conditionnelle** : deux unités de même φ **et** de mêmes bornes reçoivent le même y ; plancher `y_u ≥ min(φ_u, ref_u)` pour toute unité, qui découle de `λ* ≤ 0` | l'axiome du joueur nul. Un joueur nul (`φ_u = 0`) peut recevoir `y_u > 0` quand un autre joueur est saturé, car l'excédent est reporté. C'est une conséquence voulue de la projection, testée par un cas construit (E6) : φ = (450, 450, 0) avec c joueur nul, références (100, 1 000, 1 000) et V = 900. On obtient y = (100, 625, 175) et λ* = −175 : c reçoit 175 > 0. Pas non plus la symétrie entre unités de bornes différentes |
| **y'**, allocation arrondie en centimes | `Σ y' = v(C)` en entiers ; `y'_u ∈ {⌊y_u⌋, ⌊y_u⌋ + 1}` ; aucun centime ajouté à une unité dont la partie fractionnaire est nulle ; départage par `unit_id` ; `0 ≤ y'_u ≤ ref_u` ; puis `Σ x' = c(C)` et `0 ≤ x'_u ≤ ref_u ≤ B_u` | l'invariance par renommage de l'attribution des centimes, pour la même raison que R7c |
| **q**, répartition entre les voyageurs (plan §6.1) | R1 à R7c et le certificat d'optimalité exact ; sur au moins 1 000 unités aléatoires | l'invariance par renommage de l'attribution des centimes (R7c) |

---

## 6. Mesures de performance

Le protocole est celui de la révision 4 du plan, §7, I2 : un échauffement, puis
5 répétitions, médiane et intervalle. Les trois mesures sont faites dans la même session.

| Mesure | Objet |
|---|---|
| M0 | `T_P4_total(14)` : pipeline P4 complet sur les 10 instances de 14 unités de la strate de performance, mêmes graines |
| M1 | `T_P5` sur des blocs denses (toutes les sous-coalitions réalisables, grande coalition optimale), k = 2 à 14. Les jeux sont construits directement, et les durées sont séparées par sous-étape (couverture, Shapley, projection, arrondi, répartition par voyageur, excès du cœur) |
| M2 | Les 1 616 instances à blocs de la strate exploratoire, régénérées avec les mêmes graines. Pour chaque instance, `T_P4_total` et `T_P5` sont mesurés dans la même exécution. On rapporte la médiane, le 95e centile et le maximum de `T_P5` et du rapport `T_P5 / T_P4_total`, ainsi que la taille des blocs |

**Seuils, enregistrés avant la mesure :**

- M1 : la médiane de `T_P5` pour le bloc dense k = 14 est inférieure à la médiane de
  `T_P4_total(14)` mesurée en M0 ;
- M2 : la médiane du rapport `T_P5 / T_P4_total` est au plus de 0,25.

**Si un seuil n'est pas atteint,** on optimise P5 avant l'acceptation. On peut par
exemple calculer la couverture par masques de bits, avec un test différentiel contre
`cover_values`. On ne relâche jamais une limite sans le dire.

**Durée prévue.** M2 régénère P4 sur 1 740 instances, soit environ 25 minutes, comme
lors des vérifications d'I0 et d'I1.

---

## 7. Décisions demandées avec l'autorisation d'I2

| Id | Question | Recommandation |
|---|---|---|
| D-I2-1 | Confirmer ID-6 (θ_u = 0) | **Oui.** Recommandation confirmée par la revue. L'addendum est rédigé avant tout code d'I2 : `docs/PHASE_P5_ADDENDUM_ID6.md`. Personne n'est payé pour voyager, la projection est toujours faisable (c(C) > 0), et un paiement nul reste possible |
| D-I2-2 | Brancher l'allocation dans `plan_lot` (`TripPlan.allocation`) dès I2 | **Oui.** M2 et I3 en ont besoin. Le champ reçoit une valeur par défaut, et il est présent si et seulement si la formation a eu lieu |
| D-I2-3 | Traiter en I2 les deux réserves de durcissement d'I1 (§2.3) | **Oui.** Ce sont deux petites corrections, chacune avec un test |
| D-I2-4 | Calculer l'excès maximal du cœur en I2 | **Oui.** C'est une métrique de la spécification (§11), seulement mesurée |
| D-I2-5 | Valider les seuils M1 et M2 du §6 avant la mesure | **Oui**, avec les valeurs ci-dessus |
| D-I2-6 | Base de référence | **Option A reconduite** (manifeste et copie), sauf décision Git préalable |

---

## 8. Risques

| Risque | Mesure prévue |
|---|---|
| Coût de `cover_values` en Θ(3^k) à k = 14, et de l'excès du cœur en Θ(2^k) | `CoverCache` ; compteurs ; M1 ; optimisation par masques de bits si un seuil échoue |
| Utiliser par erreur les flottants (Shapley historique) | test qui vérifie le type rationnel des sorties ; module de domaine sans `float` |
| Confondre « valeur créée », « contribution » et « montant payé » | exemple E3 figé ; vocabulaire fixé pour I3 |
| Dépendance cachée aux limites de P4 (`FormationLimits`) | précondition du §3.2 vérifiée à l'exécution |
| Volume du diff | tout le calcul est dans deux nouveaux modules ; `trip_planning.py` est seulement étendu |

---

## 9. Révision 2 : réponse à la revue du périmètre

La revue valide l'architecture, les méthodes, les cinq exemples, les critères A1 à A11
dans leur principe, les six décisions et les seuils. Elle demande deux précisions et
l'addendum ID-6.

| Point de la revue | Traitement |
|---|---|
| A2 : séparer les propriétés de φ de celles de y | **Accepté.** A2 renvoie au nouveau §5.1, qui associe chaque propriété à son objet : φ, y, y' ou q. Les axiomes de Shapley ne portent que sur φ. Pour y : symétrie seulement entre unités de même φ et de mêmes bornes, et pas d'axiome du joueur nul. Un cas construit montre un joueur nul qui reçoit `y_u > 0` après le report de l'excédent. J'ajoute aussi une propriété de y qui découle de `λ* ≤ 0` : le plancher `y_u ≥ min(φ_u, ref_u)` |
| A4 : comparer sur le même jeu v\* | **Accepté.** `shapley_value` reçoit la couverture v\*\|C, jamais v. La comparaison n'existe que dans les tests. Un test AST interdit aux modules officiels d'importer le Shapley historique. Comparer avec Shapley(v) est explicitement qualifié d'erreur de protocole |
| Addendum ID-6 avant tout code | **Fait :** `docs/PHASE_P5_ADDENDUM_ID6.md`. C'est un fichier séparé, la spécification P4 n'est pas modifiée. Il démontre la faisabilité (c(C) > 0), explique pourquoi θ > 0 serait arbitraire et explicite la possibilité d'un paiement nul (E2) |
| Seuils M1 et M2, 95e centile et maximum | Déjà prévus au §6 ; les seuils restent enregistrés avant la mesure |

I2 n'est toujours pas démarrée, et aucune opération Git n'a été faite.

### 9.1 Révision 3 : harmonisations de la validation finale

La validation finale accepte le périmètre technique et mathématique, ainsi que ID-6. Les
trois décisions restent séparées :

- la revue du périmètre est validée ;
- le démarrage d'I2 n'est pas autorisé ;
- aucune opération Git n'est autorisée.

| Point | Traitement |
|---|---|
| E6 absent du résumé et de A3 | E6 est ajouté au tableau du §4. Le résumé annonce maintenant six exemples, et A3 exige E1 à E6 |
| `theta_cents` absent du contrat `AllocationResult` | Ajouté au §3.4, comme champ du contrat métier qui entre aussi dans l'empreinte |
| Statut de l'addendum | `docs/PHASE_P5_ADDENDUM_ID6.md` passe au statut « décision validée » |
