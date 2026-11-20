# Phase P2 / P2-bis — admissibilité, graphe unités-offres et références individuelles

Ce rapport décrit le code P2 tel qu'il existe après les corrections P2-bis et la
décision sur `request_key`. Il remplace la première version du document, qui
décrivait un comportement antérieur (voir §20).

## 1. Objectifs et périmètre

P2 relie les fondations P1 (unités de voyage indivisibles, montants en centimes,
catalogue public et termes vendeurs privés) à la future formation de coalitions.
P2 :

1. décide, pour chaque couple unité × offre, si l'offre respecte les contraintes
   dures non financières de l'unité (politique versionnée et fermée) ;
2. construit le graphe biparti des couples admissibles, ses composantes connexes et
   les diagnostics des sommets isolés ;
3. vérifie l'hypothèse de capacité H2 (`uncoupled_v1`) sur tout le lot ;
4. définit la seule fabrique de requête de négociation, son identité économique
   (`request_key`) et le contrat abstrait de l'oracle ;
5. calcule le coût de référence individuel `ref_u` de chaque unité en négociant
   seule avec chacune de ses offres admissibles.

Hors périmètre : aucun prix, budget ou plancher n'intervient dans l'admissibilité ;
P2 ne fournit pas de simulateur de vendeur (c'est P3) et ne forme aucune coalition
(c'est P4). Le code historique (agents, Broker, DP/IDP/IP) n'est pas modifié.

## 2. Architecture des modules

| Module | Couche | Rôle |
|---|---|---|
| `coalition_travel/domain/admissibility.py` | domaine | politique `NON_FINANCIAL_V1`, règles, violations, notes, `evaluate_unit_offer` |
| `coalition_travel/domain/offer_graph.py` | domaine | `AdmissibilityRelation`, `OfferComponent`, `connected_components`, `common_offers` |
| `coalition_travel/domain/negotiation_request.py` | domaine | `NegotiationRequest`, `negotiation_request_for`, `request_key`, `NegotiationOutcome`, protocole `NegotiationOracle` |
| `coalition_travel/application/lot_admissibility.py` | application | évaluation d'un lot, contrôle H2, diagnostics, `admissibility_id` |
| `coalition_travel/application/reference_costs.py` | application | validation des réponses d'oracle, références `ref_u`, relation effective |

Les modules du domaine ne dépendent que de la bibliothèque standard et du
domaine P1. Ils s'importent sous Python 3.10 sans dépendance externe
(`tests/test_python310_compatibility.py`). Aucun module P2 ne référence l'API des
planchers vendeurs privés (garde AST de `tests/test_offer_catalog.py` et
`test_p2_modules_do_not_reference_private_seller_floor_api`).

Flux :

```text
TravelUnit[] + OfferCatalog + reference_date
   └─ lot_admissibility ──► LotAdmissibilityResult (relation, composantes, H2, diagnostics)
                                └─ compute_reference_costs(lot, oracle)
                                      ├─ negotiation_request_for((u,), o) pour chaque arête
                                      ├─ oracle.negotiate(request) ──► NegotiationOutcome (validé)
                                      └─ ReferenceCostsResult (ref_u, exclusions, relation effective)
```

## 3. Règles d'admissibilité

`evaluate_unit_offer(unit, offer, reference_date, policy)` renvoie un
`PairAdmissibility(unit_id, offer_id, policy, admissible, violations, notes)`.

**Politique fermée.** `AdmissibilityPolicy` est une énumération qui ne contient que
`NON_FINANCIAL_V1`. Une chaîne ou une liste de règles est refusée (`TypeError`).
Les règles sont lues dans `RULE_REGISTRY`, un `MappingProxyType` en lecture seule ;
toute politique enregistrée doit contenir toutes les règles de `MANDATORY_RULES`.
L'évaluation refuse un registre incohérent (`RuntimeError`). Changer les règles
exige donc une nouvelle version de politique.

**Les sept règles, dans cet ordre (`RULE_ORDER`) :**

| Règle | Niveau | Violation si | Raison |
|---|---|---|---|
| `destination` | unité | destination normalisée de l'unité ≠ celle de l'offre | `destination_mismatch` |
| `offer_not_before_reference` | unité | `offer.departure_date < reference_date` | `offer_departs_before_reference_date` |
| `departure_window` | profil | `offer.departure_date < profile.departure_after` | `departure_before_window` |
| `arrival_window` | profil | `offer.arrival_date > profile.arrival_before` | `arrival_after_window` |
| `direct_flight` | profil | `direct_flight == "required"` et offre non directe | `direct_flight_required` |
| `supplier_exclusion` | profil | fournisseur de l'offre exclu par le profil | `excluded_supplier` |
| `unit_capacity` | unité | `unit.seats > offer.capacity_seats` | `unit_exceeds_offer_capacity` |

- Les deux destinations sont renormalisées au moment de l'évaluation
  (`normalize_destination_key` : NFC, `strip`, `casefold`, puis NFC), sans alias
  linguistique (« Lisbonne » n'est pas « Lisbon »).
- Un désaccord de destination est la **seule** violation rapportée pour ce couple.
  Sinon, toutes les violations sont collectées, triées par règle, puis niveau unité
  avant niveau profil, puis `profile_id`.
- `AdmissibilityViolation` vérifie que la raison appartient à la règle, qu'une règle
  de niveau profil porte un `profile_id` et qu'une règle de niveau unité n'en porte pas.
- `PairAdmissibility` vérifie : `admissible` ⇔ aucune violation, violations et notes
  triées, types exacts.
- `reference_date` doit être une `datetime.date` (un `datetime` est refusé).
- Aucun prix, budget ou plancher n'est lu : une offre chère reste admissible. Le
  filtrage économique est fait par la négociation, pas par l'admissibilité.

## 4. Fenêtres temporelles

- Les bornes sont **inclusives** : un départ le jour de `departure_after` et une
  arrivée le jour de `arrival_before` sont admis.
- Un profil sans fenêtre (`None`) n'impose aucune contrainte de date.
- Une offre qui part avant la date de référence du lot est refusée même si aucun
  profil n'a de fenêtre.
- Chaque profil d'une unité est vérifié séparément ; une violation est attribuée au
  profil concerné. Une unité dont les profils ont des fenêtres disjointes n'est
  admissible à aucune offre (`test_family_with_non_overlapping_windows_is_admissible_to_no_offer`).

## 5. Préférences de vol direct

- `required` : une offre non directe est une violation dure (`direct_flight_required`).
- `preferred` : une offre non directe reste admissible et produit uniquement la note
  qualitative `AdmissibilityNote("direct_preference_not_met", profile_id)`.
- `any` : aucun effet.

Il n'existe **aucun score de préférence** : la note ne change ni l'admissibilité, ni
une valeur économique, ni un ordre de priorité (`test_pair_result_carries_no_preference_score`).
Une paire refusée pour destination ne porte aucune note.

## 6. Exclusions fournisseurs

- Les noms sont comparés après `normalize_supplier_key` : NFC, `strip`, `casefold`,
  puis NFC à nouveau (« RyanAir » = « ryanair »). Un nom vide après normalisation
  est refusé.
- Une exclusion est attribuée au seul profil qui l'a déclarée.
- Une exclusion qui ne correspond à aucun fournisseur du catalogue n'est pas une
  erreur : elle apparaît dans `LotAdmissibilityResult.unmatched_exclusions`
  (`unit_id`, `profile_id`, nom) et ne change aucune arête. Il n'y a pas d'alias.

## 7. Capacité et hypothèse H2

Deux contrôles distincts :

1. **Par couple** (`unit_capacity`) : une unité indivisible plus grande que l'offre
   n'y est pas admissible.
2. **Par offre, sur le lot** (H2, `CAPACITY_MODEL = "uncoupled_v1"`) :

   `capacity(o) ≥ Σ seats(u)` pour toutes les unités `u` individuellement admissibles à `o`.

Chaque offre du catalogue reçoit un `CapacityCheck(offer_id, capacity_seats,
admissible_unit_seats, unit_ids, valid)`, y compris les offres sans unité (demande
nulle). H2 est vérifiée **avant toute négociation**. Si une offre la viole, le lot
garde sa relation, ses composantes et ses diagnostics (`status =
"capacity_model_violated"`), mais `require_optimizable()` lève
`CapacityModelViolated` et `compute_reference_costs` refuse de démarrer sans appeler
l'oracle.

**Pourquoi H2.** Si chaque offre peut accueillir toutes ses unités admissibles à la
fois, aucune coalition ne prive une autre de places : la capacité ne couple pas les
coalitions, et les composantes connexes peuvent être traitées indépendamment (P4).

**Restriction assumée.** H2 est conservatrice : elle refuse un lot même si une
répartition des unités sur plusieurs offres, ou un service partiel, aurait été
possible (`test_h2_refuses_a_lot_that_a_split_over_two_offers_could_have_served`,
`test_h2_refuses_the_whole_lot_even_when_partial_service_was_possible`, cas
70/60/60 contre 100). Une capacité partagée demanderait un modèle d'optimisation
avec ressources communes, hors P2.

## 8. Graphe biparti unités / offres

`AdmissibilityRelation(units, offers, pair_results)` contient un résultat pour
**chaque** couple du produit unités × offres :

- unités triées par `unit_id`, offres triées par `offer_id`, identifiants uniques ;
- résultats exactement dans l'ordre du produit trié, tous issus de la même politique.

Une arête existe exactement lorsque le couple est admissible (`edges`). Accès :
`decision(unit_id, offer_id)`, `offers_for(unit_id)`, `units_for(offer_id)` (erreur
`KeyError` pour un identifiant inconnu), `with_units(retained)` (sous-relation).

## 9. Union-find et composantes connexes

`connected_components(relation)` applique un union-find aux seules arêtes
admissibles, parcourues dans l'ordre trié. Les sommets sont typés (`("unit", id)`,
`("offer", id)`), la racine retenue est toujours le plus petit sommet et la
compression de chemin est déterministe.

Chaque `OfferComponent(component_id, units, offers)` contient au moins une unité et
une offre, triées. `component_id` est le SHA-256 des listes triées d'identifiants
d'unités et d'offres ; l'objet refuse un identifiant qui ne correspond pas à ses
sommets. Les composantes sont renvoyées triées par `component_id`.

Un test compare l'union-find à un parcours en profondeur de référence sur 60
relations aléatoires et vérifie que chaque arête est dans une seule composante, que
les composantes partitionnent exactement les sommets reliés, et qu'une coalition qui
partage une offre est toujours contenue dans une seule composante.

## 10. Sommets isolés

Les composantes **n'incluent jamais** de sommet isolé :

- une unité sans aucune offre admissible est listée par `units_without_offers()` et
  devient une `UnitExclusion(unit_id, "no_admissible_offer", details)` du lot, avec
  une ligne par offre : `offer_id: raison[@profil], …` ;
- une offre admissible pour aucune unité est listée par `offers_without_units()` et
  apparaît dans `unused_offers`.

`LotAdmissibilityResult` vérifie que ses exclusions sont exactement les unités
isolées. Un lot sans aucune arête n'a aucune composante.

## 11. Offres communes à une coalition

`relation.common_offers(unit_ids)` (et la fonction `common_offers`) renvoie
l'**intersection exacte** des offres admissibles de toutes les unités demandées. Une
composante n'est pas une clique : dans une chaîne u1–o1–u2–o2–u3, les trois unités
sont dans la même composante mais u1 et u3 ne partagent aucune offre
(`test_chain_is_one_component_whose_ends_share_no_offer`). Une coalition candidate
doit donc toujours être vérifiée par `common_offers`, jamais par l'appartenance à une
composante. Une liste vide, dupliquée ou contenant une unité inconnue est refusée.

## 12. Construction et validation de `NegotiationRequest`

`negotiation_request_for(units, offer)` est la **seule** façon de construire une
requête : le constructeur direct lève `TypeError` sans le jeton privé. La fabrique :

1. exige une `OfferQuote` et au moins une `TravelUnit` ;
2. trie les unités par `unit_id` et refuse les doublons d'identifiant ;
3. refuse une unité dont la destination normalisée diffère de celle de l'offre ;
4. calcule `seats = Σ seats(u)` et refuse une requête qui dépasse `capacity_seats` ;
5. calcule la réservation additive `R = Σ budget_total_cents(u)` en centimes entiers ;
6. calcule `request_key` (§13).

La même fabrique sert pour une unité seule (référence) et pour une coalition, ce qui
rend `R({u}) = B_u` et `R(C) = Σ B_u` strictement comparables. Aucun plancher vendeur
n'est représenté dans la requête.

Limite : la fabrique ne réévalue pas toute la politique d'admissibilité (fenêtres,
vol direct, exclusions). C'est à l'appelant de ne construire une requête que pour
une offre admissible : `compute_reference_costs` le fait pour les arêtes du graphe,
et P4 devra le faire avec `common_offers`.

## 13. Identité économique du mandat : `request_key`

**Décision.** `request_key` est l'identité économique canonique d'un mandat de
négociation. C'est le SHA-256 d'un document JSON canonique (`request_key_content`),
**recalculé à partir des données de la requête**, jamais lu dans une empreinte
stockée.

**Contenu du document** (schéma `REQUEST_KEY_SCHEMA = "negotiation-request-key-v2"`) :

| Partie | Champs |
|---|---|
| `offer` | `offer_id`, `catalog_version`, `supplier_id`, `destination_key`, `departure_date`, `arrival_date`, `direct`, `capacity_seats`, `price_tiers` (`[min_seats, list_per_seat]`) |
| `units` | multiset trié d'unités ; chaque unité = `destination_key` normalisée + profils économiques |
| profil économique | `seats`, `budget_per_seat_cents`, `departure_after`, `arrival_before`, `direct_flight`, `excluded_suppliers` (normalisés par `normalize_supplier_key`, triés, sans doublon) |
| totaux | `seats`, `reservation_cents` |

`offer_id` reste dans la clé : c'est l'identifiant métier du produit dans le
catalogue, et il sélectionne les termes privés du vendeur.

**Exclu de la clé** : `unit_id`, `profile_id`, l'empreinte P1 `fingerprint`,
`rounded_budget_profiles` (provenance de l'arrondi), le drapeau `synthetic` du
catalogue (toujours vrai), tout horodatage, identifiant de session ou paramètre de
l'oracle.

**Invariances garanties et testées** (`tests/test_negotiation_request_key.py`) :

- permuter les unités, permuter ou renommer les profils, changer `unit_id`,
  `profile_id`, l'empreinte stockée ou `rounded_budget_profiles` : clé identique ;
- découper un profil en profils identiques (2 + 1 places contre 3 places, mêmes
  contraintes) : clé identique, les profils de mêmes contraintes étant fusionnés en
  additionnant leurs places ;
- orthographes d'exclusion équivalentes (« RyanAir », «  ryanair  », NFC/NFD) : clé identique.

**Sensibilité garantie et testée** : chaque champ économique d'un profil (places,
budget à un centime près, chaque borne de fenêtre, exigence de vol direct, exclusion)
et chaque champ public de l'offre (identifiant, version, fournisseur, dates, vol
direct, capacité, prix et seuils de palier) change la clé.

**Frontières d'unité conservées.** Deux unités (2 places + 1 place) et une unité de
3 places ont les mêmes places, la même réservation et la même offre, mais des clés
différentes : l'indivisibilité des unités fait partie du mandat et comptera pour la
répartition des gains (P5). Deux unités identiques restent deux éléments du
multiset.

**Empreinte stockée non fiable.** Une `TravelUnit` construite à la main peut porter
une `fingerprint` incohérente avec ses profils. La clé ne la lit plus : une
différence économique change la clé même si l'empreinte est identique, et deux
empreintes différentes ne changent pas la clé si le contenu est identique. L'empreinte
P1 reste un artefact de consolidation P1 ; elle normalise les exclusions par
`casefold` seul, alors que la clé utilise la normalisation de l'admissibilité.

**Valeur figée.** Un mandat fixe a une clé figée dans le test
`test_request_key_is_pinned_for_a_fixed_mandate`, vérifiée par une dérivation
indépendante du document. Toute modification du format doit changer
`REQUEST_KEY_SCHEMA` et cette valeur.

**Séparation des identités :**

| Identifiant | Identifie | Dépend de |
|---|---|---|
| `request_key` | le mandat économique | offre publique, unités (contenu), places, réservation |
| `oracle_configuration_id` (P3) | la configuration de l'oracle | stratégies et paramètres, protocole, limite d'itérations, date de référence, empreintes du catalogue et des termes privés, empreintes du code |
| `admissibility_id` | une évaluation de lot | politique, modèle de capacité, empreinte du catalogue, date de référence, `(unit_id, empreinte économique de l'unité)` |
| `component_id` | une composante | identifiants triés de ses unités et offres |
| `run_id`, `journal_sha256` (P3) | une exécution simulée | configuration, requête, offre, palier ; contenu du journal |

Un même mandat garde sa clé sous plusieurs configurations d'oracle ; deux mandats
différents ont des clés différentes sous la même configuration (tous deux testés
avec l'oracle P3 réel). Le couple (`request_key`, `oracle_configuration_id`)
identifie donc un résultat de négociation reproductible.

## 14. Contrat de l'oracle

Le protocole `NegotiationOracle` ne contient que `negotiate(request) ->
NegotiationOutcome`. `NegotiationOutcome(request_key, status, agreed_total_cents,
turns, oracle_configuration_id)` ne contient aucun champ de plancher.

| Statut | Sens | Montant |
|---|---|---|
| `agreement` | message final ACCEPT | entier, `0 < montant ≤ reservation_cents` |
| `rejected` | message final REJECT d'un participant | `None` |
| `turn_limit` | limite d'itérations atteinte sans message final | `None` |

`compute_reference_costs` valide chaque réponse et lève
`NegotiationOracleContractError` si : le type n'est pas `NegotiationOutcome`, la clé
diffère de celle de la requête, le statut est inconnu, `turns` n'est pas un entier
positif ou nul, l'identifiant de configuration est vide ou change au cours du lot, ou
le montant ne respecte pas la règle de son statut. L'oracle P3 ajoute dans son propre
journal une raison de fin typée (`terminal_reason`) ; elle ne fait pas partie du
contrat P2.

## 15. Coûts de référence individuels

`compute_reference_costs(lot, oracle)` :

1. appelle `lot.require_optimizable()` (H2) avant tout appel d'oracle ;
2. parcourt les unités triées ; pour chaque offre admissible de l'unité (triées par
   `offer_id`), négocie la requête `negotiation_request_for((u,), o)` et conserve une
   `ReferenceAttempt(offer_id, request_key, status, agreed_total_cents, turns)` ;
3. retient `ref_u = c({u})`, le plus bas montant d'accord, départagé par `offer_id`.

`UnitReferenceCost` vérifie ses invariants : tentatives uniques et triées, référence
égale au minimum des accords, pas de montant hors statut `referenced`.
`ReferenceCostsResult.reference(unit_id)` renvoie `ref_u` en centimes ou lève
`KeyError`.

Comme la référence et une négociation de coalition passent par la même fabrique et
le même oracle, `v({u}) = ref_u − c({u}) = 0` sera garanti par construction en P4, à
condition d'utiliser la même configuration d'oracle.

## 16. Absences d'accord

- `no_admissible_offer` : l'unité n'a aucune arête ; elle n'est **jamais** envoyée à
  l'oracle. L'exclusion est portée par le lot.
- `no_solo_reference` : l'unité a des offres admissibles, mais aucune négociation
  seule n'aboutit. Toutes les tentatives sont conservées et les statuts `rejected` et
  `turn_limit` restent distincts ; l'exclusion détaille
  `offer_id: statut (n turns)`.

Les unités sans référence sont retirées : `effective_relation = relation.with_units(retenues)`
et les composantes sont recalculées (`effective_components`). Retirer une unité
« pont » peut scinder une composante (`test_removing_a_bridge_unit_splits_the_effective_component`).

## 17. Déterminisme, provenance et identifiants

- Toutes les collections sont triées par identifiant avant calcul ; l'ordre d'entrée
  ne change ni les arêtes, ni les composantes, ni `admissibility_id`.
- Aucun horodatage, aléa ou identifiant de session n'entre dans un identifiant.
- Les montants sont des centimes entiers ; aucun `Decimal` dépendant du contexte
  global n'est utilisé.
- Les identifiants sont des SHA-256 de JSON canonique (clés triées, séparateurs
  fixes) ; voir le tableau du §13.
- `admissibility_id` recalcule l'empreinte économique de chaque unité
  (`unit_economic_digest`) au lieu de lire `fingerprint`.
- La suite complète est exécutée avec deux valeurs de `PYTHONHASHSEED`.

## 18. Tests

| Fichier | Tests | Couverture principale |
|---|---|---|
| `tests/test_admissibility.py` | 27 | règles et ordre, bornes inclusives, NFC, absence d'alias, note sans score, exclusions par profil, registre fermé, invariants, équivalence T-EQ, garde de confidentialité |
| `tests/test_offer_graph.py` | 11 | intersection exacte, chaîne, sommets isolés, composantes non vides, invariance à l'ordre, union-find contre parcours de référence |
| `tests/test_lot_admissibility.py` | 20 | bornes H2, refus des répartitions et du service partiel, 70/60/60, exclusions détaillées, offres inutilisées, exclusions sans correspondance, provenance |
| `tests/test_reference_costs.py` | 27 | fabrique, réservation additive, choix et départage de la référence, statuts distincts, contrat d'oracle, H2 avant tout appel, stabilité de configuration |
| `tests/test_negotiation_request_key.py` | 30 | invariances, sensibilité champ par champ, frontières d'unité, empreinte stockée, valeur figée, séparation avec `oracle_configuration_id`, provenance du lot |

**T-EQ.** Sur 2 000 cas aléatoires du domaine commun (au moins deux profils, offre
complète, prix neutralisé, noms ASCII, capacité suffisante, offre non antérieure à
la date de référence), `NON_FINANCIAL_V1` donne le même verdict final que l'ancienne
fonction `evaluate_compatibility`. Seul le verdict est comparé : l'ancienne politique
s'arrête à la première raison, la nouvelle les collecte toutes.

## 19. Limites connues

- H2 est conservatrice : elle refuse des lots que des répartitions ou un service
  partiel auraient pu servir ; aucune capacité partagée n'est modélisée.
- La fabrique de requête ne réévalue pas toute la politique : l'appelant doit
  n'utiliser que des offres admissibles (§12).
- Pas d'alias de destination ou de fournisseur.
- L'admissibilité ignore volontairement les prix : une offre trop chère n'est
  éliminée que par la négociation.
- Les références coûtent un appel d'oracle par arête du graphe.
- L'empreinte P1 et la clé de requête normalisent les exclusions différemment (§13) ;
  seule la clé est utilisée pour l'identité des mandats.

## 20. Historique du document

La première version décrivait un état antérieur à P2-bis. Corrections :

1. elle décrivait un `preference_score` ; le code ne produit que la note
   `direct_preference_not_met`, sans score (§5) ;
2. elle incluait les sommets isolés dans les composantes ; ils en sont exclus et
   signalés comme diagnostics (§9, §10) ;
3. elle citait les statuts `agreed` / `no_agreement` ; les statuts sont
   `agreement`, `rejected`, `turn_limit` (§14) ;
4. elle ne précisait pas la sémantique de la clé ; `request_key` est l'identité
   économique du mandat (§13). Avec cette décision, la clé est passée au schéma
   `negotiation-request-key-v2` : elle ne lit plus l'empreinte stockée, inclut le
   contenu public de l'offre et normalise les exclusions comme l'admissibilité ;
   `admissibility_id` ne lit plus non plus l'empreinte stockée.
