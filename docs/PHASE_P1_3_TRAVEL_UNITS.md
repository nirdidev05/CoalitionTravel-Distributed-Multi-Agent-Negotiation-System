# Phase P1.3 — unités de voyage (`TravelUnit`)

## Fichiers

- Créé : `Multi-Agent/coalition_travel/domain/destination.py`
- Créé : `Multi-Agent/coalition_travel/domain/travel_unit.py`
- Créé : `Multi-Agent/coalition_travel/application/travel_units.py`
- Créé : `tests/test_travel_units.py` (58 tests)

## `normalize_destination_key`

NFC, `strip`, `casefold`, puis une dernière passe NFC. Cette passe finale garantit l'idempotence (`normalize(clé) == clé`) : le `casefold` peut décomposer quelques caractères. Aucun alias : « Lisbonne » ≠ « Lisbon » jusqu'à P7.

## `build_travel_unit(request_id, draft, reference_date)`

1. Types vérifiés : `request_id` est une `str` (nettoyée, 1 à 120 caractères), `draft` un `TravelRequestDraft`, `reference_date` une `date` et pas un `datetime`.
2. `validate_request_draft` doit renvoyer `ready`; sinon `TravelUnitError("request_not_ready")` avec le statut, les champs manquants et les erreurs.
3. `build_profiles(draft)` : union des exclusions et première consolidation. Chaque profil porte son budget **effectif**.
4. Chaque budget effectif est ramené au centime inférieur (`cents_from_budget`), puis le profil est reconstruit avec `dataclasses.replace`, qui revalide l'objet. `model_copy` n'est jamais utilisé : il ne valide pas.
5. Seconde consolidation (`consolidate_profiles`) : des budgets devenus égaux une fois arrondis décrivent le même groupe.
6. `rounded_budget_profiles` liste les profils finaux dont au moins un contributeur avait un budget au sous-centime.
7. Empreinte SHA-256 (`unit_fingerprint`) d'un JSON canonique contenant `destination_key` et les profils triés (effectif, budget en centimes, dates, vol direct, exclusions normalisées), **sans** `profile_id` ni `unit_id`.

Motifs d'erreur : `request_not_ready`, `budget_below_one_cent`, `budget_out_of_range`, `budget_total_out_of_range`, `invalid_request_id`.

Un budget de demande remplacé par tous les profils n'est ni arrondi, ni signalé, ni vérifié : 0,004 € entièrement remplacé ne provoque aucune erreur.

## `TravelUnit` : invariants vérifiés à la construction

`unit_id` et `destination_key` déjà normalisés; `profiles` est un `tuple` non vide de `TravelerProfile` triés et uniques. Pour chaque profil :

- `excluded_suppliers` est un `tuple` de chaînes non vides;
- les dates sont des `date` (et pas des `datetime`) ou `None`;
- `direct_flight` vaut `required`, `preferred` ou `any`;
- l'effectif est un entier ≥ 1;
- le budget est un nombre exact de centimes, ≥ 1 centime;
- la destination normalisée est celle de l'unité.

Également : total ≤ `MAX_CENTS`; empreinte de 64 caractères hexadécimaux minuscules; `rounded_budget_profiles` est un `tuple` trié, sans doublon et inclus dans les profils.

`budget_total_cents` est calculé **en entiers** (Σ effectif × centimes), jamais avec `TravelerProfile.total_budget`. Test : 7 voyageurs × 123 456,78 € donnent 86 419 746 centimes même avec une précision globale de 5, là où `total_budget` donnerait `8.6420E+5`.

Immutabilité profonde testée : `FrozenInstanceError` sur l'unité et sur les profils contenus, collections en `tuple`, `hash(unit)` qui réussit. Limite : Python ne peut pas interdire `object.__setattr__`; l'immutabilité est une garantie de contrat.

## Tests des budgets arrondis

R1 budget hérité 333,335 → signalé · R2 budget remplacé → non signalé · R2b 0,004 remplacé → aucune erreur · R3 seul le profil héritier est signalé · R4 333,335 et 333,33 fusionnés et signalés · R5 0,004 utilisé → `budget_below_one_cent` · R6 aucun arrondi → tuple vide.
