# Phase P1.4 — offres, catalogue et confidentialité des planchers

## Fichiers

- Créé : `Multi-Agent/coalition_travel/domain/offer.py`
- Créé : `Multi-Agent/coalition_travel/infrastructure/catalog/__init__.py`, `json_catalog.py`
- Créé : `data/catalog/catalog_v1.json`, `data/catalog/catalog_v1.manifest.json`
- Créé : `tests/test_offer_catalog.py` (75 tests)

## Frontière de confidentialité des planchers

**`SellerTermsBook` et ses planchers sont transmis uniquement au simulateur vendeur (P3 et suivants). Ils ne sont jamais transmis au composant de compatibilité, ni exposés par le catalogue public `OfferCatalog`, ni inclus dans un rapport destiné aux voyageurs.**

Mise en œuvre :

- **Séparation par les types.** Publics, sans aucun plancher : `PriceTier(min_seats, list_per_seat)`, `OfferQuote`, `OfferCatalog`. Privés : `SellerFloorTier(min_seats, floor_per_seat)`, `SellerTerms`, `SellerTermsBook`. `load_offer_catalog(path)` renvoie le couple `(OfferCatalog, SellerTermsBook)`; le point d'assemblage de P6 ne donnera le second qu'au simulateur.
- **Tests de structure.** Aucun champ des types publics ne contient « floor ». Un parcours complet du catalogue public ne rencontre aucun objet privé.
- **Test d'architecture.** Il analyse par `ast` tous les fichiers `.py` de `Multi-Agent/` et échoue si un module hors liste blanche référence `SellerTerms`, `SellerTermsBook`, `SellerFloorTier`, `load_offer_catalog`, `validate_seller_terms_against_catalog`, `floor_total`, `floor_tier_for`, `floor_tiers` ou `floor_per_seat`. Liste blanche : `domain/offer.py` et `infrastructure/catalog/json_catalog.py`. Deux tests de sensibilité prouvent que le détecteur repère un import, un alias et un accès d'attribut, et qu'il ignore `ROUND_FLOOR` et `math.floor`. En P3, ajouter le simulateur à la liste blanche devra être une modification explicite et relue.

## Validation

- `PriceTier` / `SellerFloorTier` : entiers stricts; `min_seats` ≥ 1; montants ≥ 1 centime et ≤ `MAX_CENTS`.
- `OfferQuote` : identifiants non vides et sans espaces en bordure; départ ≤ arrivée; `direct` booléen; capacité entre 1 et 10 000; `synthetic is True`; paliers en `tuple`, premier palier à 1 siège, `min_seats` strictement croissants, dernier palier ≤ capacité, prix non croissants, totaux ≤ `MAX_CENTS`.
- `SellerTerms` : mêmes règles pour les planchers, plus `capacity_seats`, dupliquée depuis l'offre pour borner `floor_total`.
- Registres : `offer_id` uniques et triés, version et SHA-256 communs.
- `validate_seller_terms_against_catalog(catalog, book)` : même version, même SHA-256, mêmes `offer_id`, même capacité, même suite de `min_seats`, et plancher ≤ prix catalogue à chaque palier.

**Écart avec la spécification :** cette validation croisée est une fonction du domaine, appelée par le chargeur, et non un `__post_init__` des registres. Chaque registre ne voit pas l'autre, et y ajouter une référence casserait la séparation public / privé.

## Lecture stricte et cohérence avec le manifeste

1. Une seule lecture des octets du catalogue; SHA-256 calculé sur ces octets; UTF-8 strict; lecture des mêmes octets.
2. JSON strict : nombres décimaux, `NaN` / `Infinity` et clés dupliquées refusés; clés exactes à chaque niveau; dates `AAAA-MM-JJ` valides; `currency == "EUR"`; `synthetic: true`.
3. Manifeste à `path.with_suffix(".manifest.json")`, lu avec le même lecteur strict. `provenance.load_manifest` n'est pas utilisé : il renvoie une sentinelle silencieuse quand le fichier est absent. Un manifeste absent est une erreur.
4. Contrôles : `version`, `catalog_file`, `catalog_sha256` (égal au SHA-256 calculé), `offers`, `synthetic`, `currency`, `purpose` non vide, `limitations` non vide.

## Données

Version `catalog-v1`, SHA-256 `4b145ecbdbd662d49015ef199bcd60b03b63b2e131e2cdcb3c14d8b182dc3071`, trois offres fictives.

| offer_id | Fournisseur | Destination | Dates | Direct | Capacité | Paliers (sièges : catalogue / plancher, en centimes par siège) |
|---|---|---|---|---|---|---|
| `rom-cloudwing-20270405` | CloudWing | Rome | 05/04 → 05/04/2027 | oui | 40 | 1 : 30000/20000 · 3 : 27000/18000 |
| `tyo-northstar-20270310` | Northstar | Tokyo | 10/03 → 11/03/2027 | oui | 60 | 1 : 56000/40000 · 3 : 52000/37000 · 6 : 48000/34000 |
| `tyo-skyways-20270312` | SkyWays | Tokyo | 12/03 → 13/03/2027 | non | 60 | 1 : 54000/39000 · 4 : 50000/36000 |

Toute modification de `catalog_v1.json` exige de mettre à jour `catalog_sha256` dans le manifeste; le chargeur refuse sinon (test : un octet modifié est rejeté).

## Reste ouvert pour P2

`evaluate_compatibility` compare un prix de `CommonOffer` au budget. Les planchers étant privés, l'admissibilité de P2 devra porter sur les contraintes dures hors prix. Deux options : un paramètre optionnel dans `compatibility.py`, dont la valeur par défaut conserve le comportement actuel, ou une vérification hors prix qui réutilise les mêmes codes de motif.
