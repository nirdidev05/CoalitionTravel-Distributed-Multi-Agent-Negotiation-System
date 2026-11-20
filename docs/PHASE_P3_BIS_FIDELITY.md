# Phase P3-bis — fidélité de l'oracle simulé à la stratégie historique

Rapport à l'attention de Codex. Il décrit les corrections apportées par Claude au
P3 que tu as implémenté, les preuves qui les justifient et les règles à respecter
dans les phases suivantes. P3-bis ne lance pas P4.

## 1. Pourquoi une correction

Une revue en lecture seule de P3 a comparé l'oracle réel aux agents historiques
réels (`CoalitionLeaderAgent.receive_message` et `SellerAgent`), en leur donnant
la même réservation R, le même plancher F et le même prix initial vendeur I.

- Sur 4 scénarios courants (1 voyageur, 4 voyageurs, plancher > réservation,
  prix catalogue = réservation) et 3 000 tirages aléatoires, P3 était identique.
- Sur deux scénarios construits à une borne d'arrondi, P3 divergeait :

| Scénario (R / F / I en centimes) | Historique | P3 initial |
|---|---|---|
| Borne côté vendeur (242424 / 160000 / 400000) | accord 176000, 5 itérations | accord 160000, 3 itérations |
| Borne côté leader (90008 / 70000 / 100009) | accord 81007, 6 itérations | accord 90008, 4 itérations |

**Cause.** Les deux agents P3 convertissaient le prix reçu en centimes **avant**
de comparer :

- `MandateLeader` : `from_agent_amount(price) <= reservation_cents`. Le vendeur
  propose 1000,09 × 0,9 = 900,081 €, arrondi à 90008 = R, donc le leader
  acceptait. L'historique compare `900.081 <= 900.08` (faux) et fait une
  contre-offre.
- `_ConfiguredSellerAgent` : `from_agent_amount(offre) >= plancher_cents`. Le
  leader offre 2424,24 × 0,6 × 1,1 = 1599,9984 €, arrondi à 160000 = F, donc le
  vendeur acceptait. L'historique compare `1599.9984 >= 1600.0` (faux) et fait
  une contre-offre.

Le statut ne changeait jamais et les montants restaient dans [F, R] : le contrat
P2 n'était pas violé. Mais la suite des offres, le montant (−160,00 € et
+90,01 €) et le nombre d'itérations changeaient, alors que P3 affirmait
reproduire la stratégie historique.

## 2. Corrections, fichier par fichier

La version P3 initiale n'a jamais été versionnée ; les tableaux « avant / après »
ci-dessous suffisent à la reconstituer. Seuls `mandate_leader.py`,
`simulated_oracle.py` et le document P3 ont été modifiés ; ton fichier
`tests/test_simulated_negotiation_oracle.py` est inchangé et ses 31 tests passent.

### 2.1 `Multi-Agent/coalition_travel/infrastructure/negotiation/mandate_leader.py`

| Avant | Après |
|---|---|
| `if from_agent_amount(price) <= self.reservation_cents:` | `if price <= self.reservation_amount:` (ligne 110), avec `self.reservation_amount = to_agent_amount(self.reservation_cents)` (ligne 88), soit le flottant historique `self.budget` |
| `self.current_offer * (1.0 + float(self.strategy.concession_rate))` | `self.current_offer * self._concession_factor` (ligne 95) |
| — | `MandateLeaderStrategy.concession_factor` = `float(Decimal(1) + concession_rate)`, arrondi une seule fois ; vaut exactement `1.10` pour le taux par défaut (ligne 46) |
| — | propriété `counteroffers_exhausted` = `bid_count > max_counteroffers` (ligne 124), utilisée par l'oracle pour vérifier un REJECT du leader |

`from_agent_amount(price)` reste appelé, mais **seulement pour valider** le prix
(domaine monétaire, au moins un centime). Il ne sert plus à décider.

### 2.2 `Multi-Agent/coalition_travel/infrastructure/negotiation/simulated_oracle.py`

**Vendeur** (`_ConfiguredSellerAgent`, ligne 585) :

| Avant | Après |
|---|---|
| `if from_agent_amount(offre) >= self._private_floor_total_cents:` | `if buyer_price >= self.min_price:` (ligne 611), la règle historique `buyer_offer >= self.min_price` |
| ACCEPT renvoyait `to_agent_amount(buyer_total_cents)` (prix arrondi) | ACCEPT renvoie `buyer_price`, le flottant brut, comme l'historique |
| `previous_total * (1.0 - self._concession_rate)` | `self.current_offer * self._concession_factor`, avec `seller_concession_factor(rate) = float(Decimal(1) - rate)` (ligne 577) ; vaut exactement `0.90` par défaut |
| paramètre `private_floor_total_cents` | supprimé : le vendeur décide sur `self.min_price` (= `to_agent_amount(F)`, posé par le constructeur historique). Le plancher privé traverse une frontière de moins |

Note honnête : renvoyer le prix arrondi dans le ACCEPT n'avait aucun effet
observable, car `from_agent_amount` est idempotent et le montant final est le
même en centimes. La correction sert la fidélité au niveau des messages, testée
flottant par flottant (§4).

**Raison de fin typée** (lignes 96-108, 449-485, 566-574) :

- `TerminalReason = Literal["leader_counteroffers_exhausted", "seller_rejected",
  "router_iteration_limit"]` remplace la chaîne libre `"participant_rejected"`.
- `REASONS_BY_STATUS` (en lecture seule) fixe les raisons permises pour chaque
  statut P2.
- La raison d'un REJECT est déduite de `terminal.sender`
  (`_rejection_reason`), jamais devinée :
  - leader : vérifie `leader.counteroffers_exhausted`, sinon `AgentExecutionError` ;
  - vendeur : `seller_rejected` ;
  - autre expéditeur : `AgentExecutionError`.
- `terminal is None` n'est accepté comme `turn_limit` que si
  `router_iterations == max_router_iterations`. Sinon `AgentExecutionError`.
  Aujourd'hui l'observateur lève déjà une erreur sur un agent muet ; c'est une
  garde de plus, pas une hypothèse.
- Un ACCEPT d'un expéditeur inconnu lève `AgentExecutionError`.
- Un accord sous le plancher privé lève `AgentExecutionError` (ligne 483).
  C'est impossible avec les règles actuelles, mais vérifié.

**Journal** (`NegotiationJournal.__post_init__`, ligne 234) : il refuse un
statut inconnu, une raison incompatible avec le statut, un montant présent hors
accord ou absent dans un accord, et un nombre d'événements différent de
`router_iterations`.

### 2.3 `docs/PHASE_P3_SIMULATED_NEGOTIATION.md`

- §3 : décrit la règle de décision en flottants et les facteurs.
- §6 : tableau des différences de paramètres (choix de spécification),
  tableau statut / raison de fin, caractérisation du rejet, accessibilité de
  `turn_limit`.
- §7 : mentionne les tests de fidélité.
- §8 : marqué comme résultats du P3 initial.
- §9 : ajouté pour P3-bis.

## 3. Garanties et preuves

1. **Contrat P2 conservé.** `from_agent_amount` arrondit au centime de façon
   monotone et `from_agent_amount(to_agent_amount(c)) == c` (aller-retour P1).
   - Le leader accepte seulement si `prix <= R/100`, donc montant ≤ R.
   - Le vendeur accepte seulement si `offre >= F/100`, et le leader n'offre
     jamais plus que R/100, donc F ≤ montant ≤ R.
2. **Statut inchangé par rapport au P3 initial.** c ↦ c/100 est strictement
   croissant sur le domaine P1, donc « F > R » donne le même résultat en
   flottants et en centimes. Seuls le montant et la trajectoire pouvaient
   différer.
3. **`rejected` ⇔ F > R avec la stratégie par défaut.** La première proposition
   du leader vaut 0,66 R ; la sixième vaut min(R, 0,6 × 1,1⁶ R) = R, car
   0,6 × 1,1⁶ ≈ 1,063 ≥ 1.
   - Si F ≤ R, le vendeur accepte au plus tard cette offre, ou le leader a déjà
     accepté un prix ≤ R.
   - Si F > R, aucun prix du vendeur (toujours ≥ F) n'est ≤ R et aucune offre
     du leader (toujours ≤ R) n'est ≥ F : la septième proposition du vendeur
     au-dessus de R déclenche le REJECT.
4. **Au plus 14 itérations du routeur** (7 propositions vendeur + 7 réponses
   leader). `turn_limit` ne peut donc pas arriver avec la limite par défaut
   de 30.
5. **Refus explicite du vendeur impossible** avec le `SellerAgent` historique
   (`SellerAgent.py:38-45` : ACCEPT ou PROPOSE seulement). `seller_rejected`
   est réservé à un futur vendeur et testé avec un vendeur simulé.

## 4. Tests ajoutés : `tests/test_simulated_negotiation_fidelity.py`

17 fonctions, 23 cas.

La référence est l'agent historique réel, non modifié, réglé comme
`negotiate_for_group` le fait avant de router (`budget`,
`current_offer = budget * 0.6`, `bid_count = 0`). Deux niveaux de comparaison :

- **oracle** : statut, montant, itérations et suite `(acteur, type, centimes)`
  issue du journal ;
- **agents** : `MandateLeader` et `_ConfiguredSellerAgent` routés comme dans
  l'oracle ; la suite des **flottants bruts** doit être identique bit à bit.

| Test | Ce qu'il fixe |
|---|---|
| `test_fixed_scenarios_match_historical_agents_exactly` (×6) | les 6 scénarios (dont 1 voyageur, 4 voyageurs, plancher > réservation, 2 bornes) aux deux niveaux, plus les valeurs historiques attendues |
| `test_seller_boundary_…` / `test_leader_boundary_…` | que ces scénarios sont réellement sur une borne (le flottant est du mauvais côté mais s'arrondit sur la borne) |
| `test_generated_rounding_boundaries_match_historical_agents` (×2) | 60 bornes générées côté leader et 60 côté vendeur, aux deux niveaux |
| `test_seeded_random_scenarios_match_historical_agents` | 300 scénarios aléatoires (1-6 sièges), aux deux niveaux ; les deux statuts apparaissent |
| `test_seller_accept_returns_the_raw_buyer_float_…` | ACCEPT du vendeur identique message par message (prix brut) |
| `test_concession_factors_are_exactly_the_historical_literals` | facteurs `1.10` et `0.90`, fraction `0.6`, inégalité 0,6 × 1,1⁶ ≥ 1 |
| `test_default_strategy_rejects_exactly_when_floor_exceeds_reservation` | `rejected` ⇔ F > R (cas F = R et F = R + 1 compris), F ≤ montant ≤ R, au plus 14 itérations, raisons de fin |
| `test_floor_above_reservation_is_leader_exhaustion_after_fourteen_iterations` | 14 itérations, `leader_counteroffers_exhausted`, dernier événement = REJECT du leader |
| `test_initial_leader_amount_is_internal_…` | `initial_leader_total_cents` (0,6 R) n'est jamais envoyé ; la première proposition vaut 0,66 R |
| `test_router_limit_is_the_only_source_of_turn_limit` | `turn_limit` / `router_iteration_limit` avec une limite de 3 |
| `test_seller_rejection_is_reported_as_seller_rejected` | `rejected` / `seller_rejected` avec un vendeur qui refuse |
| `test_leader_rejection_before_exhaustion_…`, `…unknown_sender…`, `…below_the_seller_floor…`, `…router_stop_without_terminal…` | les quatre gardes lèvent `AgentExecutionError` |
| `test_journal_rejects_inconsistent_status_reason_amount_or_events` | 7 combinaisons de journal invalides refusées |

**Contrôle par mutants**, exécuté sur une copie hors dépôt : chaque défaut est
réintroduit seul, puis les tests P3 et P3-bis sont lancés.

| Mutant | Résultat |
|---|---|
| M1 leader compare en centimes (règle P3 initiale) | 3 échecs |
| M2 vendeur compare en centimes (règle P3 initiale) | 4 échecs |
| M3 ACCEPT vendeur renvoie le prix arrondi | 4 échecs |
| M4 mauvaise raison de fin pour le leader | 2 échecs |
| M5 facteur leader décalé de 1e-15 | 9 échecs |
| M6 facteur vendeur décalé de 1e-16 | 10 échecs |
| M7 pas de contrôle de la limite du routeur | 1 échec |
| M8 pas de contrôle d'épuisement du leader | 1 échec |
| M9 pas de contrôle du plancher | survivait (garde inatteignable) ; tué depuis par `test_agreement_below_the_seller_floor_is_an_agent_error` |

## 5. Ce qui n'a pas changé

- Contrat P2 : `NegotiationOutcome`, les statuts `agreement` / `rejected` /
  `turn_limit`, `negotiation_request_for`, `reference_costs`. Aucun 4ᵉ statut.
- Champs de `SimulatedOracleConfig` et chaînes de version (`mandate-leader-total-v1`,
  `legacy-seller-agent-configurable-concession-v1`). `oracle_configuration_id`
  change quand même, car il inclut l'empreinte des sources modifiées. Aucun
  résultat P3 n'avait été enregistré ni commité.
- Fichiers historiques (`Leader.py`, `SellerAgent.py`, `Negotiation.py`…),
  catalogue, Golden Master, liste blanche de `tests/test_offer_catalog.py`.
- Le module `mandate_leader.py` ne contient toujours aucun nom lié au plancher.

## 6. Règles à respecter pour la suite (P4 et au-delà)

1. **Ne jamais arrondir un prix d'agent avant une décision de négociation.**
   Comparer les flottants bruts comme l'historique ; convertir en centimes une
   seule fois, sur le prix accepté final.
2. **Toute nouvelle stratégie ou tout changement de paramètre** doit garder les
   tests de fidélité verts pour la configuration par défaut. S'il modifie
   volontairement le comportement, il faut une nouvelle version de stratégie et
   un test qui documente l'écart.
3. **Ne pas ajouter de statut P2.** Le diagnostic va dans `terminal_reason`,
   une liste fermée. Une nouvelle raison exige d'étendre `TerminalReason`,
   `REASONS_BY_STATUS` et les tests.
4. **Pour P4**, `rejected` et `turn_limit` signifient qu'il n'y a pas d'accord sur
   cette offre. Si aucune offre commune n'aboutit, la coalition n'est pas
   réalisable : elle n'a pas de valeur (représentation par exclusion, voir
   `docs/PHASE_P4_SPECIFICATION.md` §3). Ne pas lire `terminal_reason` dans le
   calcul de valeur. Avec les paramètres
   par défaut, un rejet veut dire F > R : aucun accord n'est possible, ce n'est
   pas un échec stratégique.
5. **`turn_limit` ne peut pas arriver avec la configuration par défaut.** Ne pas
   le présenter comme un résultat observé dans les rapports ou métriques.
6. **`initial_leader_total_cents`** est un point de départ interne, jamais
   envoyé. Ne pas le présenter comme la première offre du leader.
7. Les appels de l'oracle restent **séquentiels** (capture globale de `stdout`).

## 7. Vérifications exécutées

Résultats après P3-bis et la décision `request_key` (finalisation P2/P3) :

```text
PYTHONHASHSEED=0 python -m pytest -q
545 passed
PYTHONHASHSEED=2 python -m pytest -q
545 passed
python -m pytest -q tests/test_python310_compatibility.py
3 passed            (interpréteur python3.10 réel, modules P3 inclus)
python -m pytest -q tests/test_entry_golden_master.py tests/test_simulated_negotiation_fidelity.py \
    tests/test_simulated_negotiation_oracle.py tests/test_offer_catalog.py tests/test_negotiation_request_key.py
163 passed
ruff check Multi-Agent/coalition_travel tests
All checks passed!
ruff format --check Multi-Agent/coalition_travel tests
67 files already formatted
git diff --check
(aucune sortie)
```

545 = 492 avant P3-bis + 23 cas de fidélité P3-bis + 30 cas de
`tests/test_negotiation_request_key.py`. Aucun fichier historique suivi ni le
catalogue ne sont modifiés (`git diff --stat -- Multi-Agent/*.py data/` est vide).

## 8. Reproduire les vérifications

Depuis la racine du dépôt, avec l'environnement virtuel du projet :

- suite complète : `PYTHONHASHSEED=0 python -m pytest -q`, puis la même
  commande avec `PYTHONHASHSEED=2` ;
- fidélité seule : `python -m pytest -q tests/test_simulated_negotiation_fidelity.py` ;
- compatibilité Python 3.10 : `python -m pytest -q tests/test_python310_compatibility.py`
  (le test est ignoré si aucun exécutable `python3.10` n'est installé) ;
- qualité : `ruff check Multi-Agent/coalition_travel tests` et
  `ruff format --check Multi-Agent/coalition_travel tests`.

Méthode des mutants (§4) : copier le dépôt dans un répertoire temporaire,
réintroduire un seul défaut à la fois dans la copie, lancer
`tests/test_simulated_negotiation_fidelity.py` et
`tests/test_simulated_negotiation_oracle.py`, puis supprimer la copie. Le dépôt
lui-même n'est jamais modifié.

## 9. Suites

- La sémantique économique de `request_key`, décidée après P3-bis, est décrite
  dans `docs/PHASE_P2_ADMISSIBILITY.md` (§13) ; elle ne change pas le contrat de
  l'oracle P3.
- P4 est spécifiée, mais pas implémentée, dans `docs/PHASE_P4_SPECIFICATION.md`.
