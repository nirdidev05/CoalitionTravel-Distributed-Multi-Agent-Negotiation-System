# Phase P1.1 — monnaie en centimes et compatibilité Python 3.10

## Fichiers

- Créé : `Multi-Agent/coalition_travel/domain/money.py`
- Créé : `tests/test_money.py` (88 tests)
- Créé : `tests/test_python310_compatibility.py` (3 tests, ignorés si `python3.10` est absent)
- Modifié, deux lignes : `Multi-Agent/coalition_travel/infrastructure/evaluation/provenance.py` (`datetime.UTC` → `timezone.utc`, lignes 7 et 59)

## Contenu

`Cents = int`, `MAX_CENTS = 10^11` (10^9 €), `MAX_EUROS = Decimal("1000000000.00")`, `MONEY_CONTEXT` (précision 34, demi-pair, pièges `InvalidOperation`, `DivisionByZero`, `Overflow`).

| Fonction | Règle |
|---|---|
| `require_cents(value, minimum=0)` | `type(value) is int`, borne `[minimum, MAX_CENTS]` |
| `cents_from_budget(Decimal)` | fini, > 0, ≤ `MAX_EUROS` (comparaison exacte), `quantize(0.01, ROUND_FLOOR)` puis `scaleb(2)` dans `MONEY_CONTEXT`, résultat ≥ 1 centime |
| `decimal_from_cents(int)` | `Decimal(value).scaleb(-2)` dans `MONEY_CONTEXT` |
| `to_agent_amount(int)` | `value / 100` (division d'entiers correctement arrondie) |
| `from_agent_amount(float ou int)` | `bool`, `Decimal`, `str` refusés; fini, ≥ 0, préfiltre ≤ 10^9 € + 0,01; `Decimal(x)` exact, `quantize(0.01, ROUND_HALF_EVEN)` dans `MONEY_CONTEXT`; résultat ≤ `MAX_CENTS` |

Règle du module : toute opération `Decimal` sensible au contexte s'exécute dans `localcontext(MONEY_CONTEXT)`; seuls les constructeurs et les comparaisons, exacts, sont faits hors contexte.

## Correction d'une affirmation de la spécification

La spécification affirmait qu'aucun `float` ne tombe exactement sur un demi-centime. C'est faux. Un demi-centime vaut (2k+1)/200 €; lorsque 2k+1 est multiple de 25, il se réduit à m/8 €, exactement représentable : 0,125 €, 0,375 €, 0,625 €, 0,875 €, 1814,125 €… Ces montants sont des égalités exactes; l'arrondi demi-pair les tranche de façon déterministe (0,125 → 12 centimes, 0,375 → 38, 0,625 → 62, 0,875 → 88). Le test aléatoire l'a révélé; la docstring et les tests ont été corrigés.

Les démonstrations qui comptent sont intactes : l'aller-retour `c → c/100 → c` ne passe jamais par un demi-centime, et le respect des bornes (plancher ≤ accord ≤ réservation) repose sur la monotonie de l'arrondi et sur des bornes en centimes entiers.

## Tests principaux

- bornes : `MAX`, `MAX−1`, `MAX+1`, `0`, `−0.0`, `nextafter(0, −1)`, `nextafter(1e9, ±inf)`, `999999999.995`, `1000000000.01`;
- budgets : `0.0099…` (31 chiffres) refusé, `1234567.0199…9` (38 chiffres) → 123 456 701, `333.335` → 33 333, `MAX_EUROS + 0.01` refusé;
- caractérisation du piège « multiplier puis arrondir » (donne 1 centime au lieu de 0 sous la précision 28);
- types refusés, NaN, ±inf, sNaN;
- aller-retour sur 10 000 valeurs aléatoires et sur `[MAX−1000, MAX]`; monotonie sur 5 000 paires;
- égalités exactes uniquement pour les multiples impairs de 1/8 €, tranchées demi-pair;
- précision globale réduite à 5 : tous les résultats identiques.

## Compatibilité Python 3.10

`python3.10 -c "from datetime import UTC"` échouait (ImportError). Après correction, le test importe sous un vrai Python 3.10 (`-I -B`) tous les modules qui n'utilisent que la bibliothèque standard, et analyse tous les fichiers du projet avec la grammaire 3.10 (aucune erreur de syntaxe). La suite complète n'est pas exécutée sous 3.10 : NumPy, SciPy et Pydantic n'y sont pas installés.

Annotation : `from_agent_amount(amount: float)` (Ruff PYI041 : `int` est implicitement accepté par `float`); le comportement accepte bien `int` et `float`.
