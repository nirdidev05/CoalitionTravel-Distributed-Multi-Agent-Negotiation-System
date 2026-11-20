# I4 : périmètre et contrats figés (Lyon-Alger, catalogue v2, référentiel des lieux)

**Statut :** proposition de périmètre, **révision 1**, en attente de revue. I4 n'est pas
autorisée : aucun code n'a été écrit pour elle, et aucune opération Git n'a été faite.

**Rôle de ce document.** Le plan (`docs/PHASE_3H_P5_INTEGRATION_PLAN.md`, révision 4)
décrit I4 au §7 et en fixe les règles aux §6.2 (forfait aller-retour), §6.4 (clés v3) et
§6.5 (référentiel des lieux). Ce document :

- relève, dans le code actuel, les points qu'il faut trancher avant d'implémenter (§2) ;
- fige les contrats ajoutés (§3 à §6) ;
- propose un découpage en trois sous-étapes, chacune autorisée et revue séparément (§8) ;
- numérote chaque décision (D-I4-n, récapitulées au §9).

**Ce qui a déjà été accepté :** I0 à I2 sont clôturées. I3 est acceptée, sous-étapes
A, B et C ; la réserve d'installation d'I3-C a été levée.

**Les règles qui ne changent pas :**

- les contrats existants ne s'étendent que par ajout ;
- le chemin v1 n'est pas touché ;
- la non-régression v1 est prouvée par K1, en reproduisant toutes les empreintes figées,
  y compris l'empreinte exploratoire P4 `997109ee…`.

---

## 0. Résumé

- **Le plan est précis sur les données et les règles,** mais il laisse ouverts plusieurs
  points dont le code dépend. **Douze sont relevés au §2.** Les plus structurants :
  1. **la version d'une demande.** Il faut une règle qui dise quand une demande suit le
     chemin v2. Sans elle, ajouter « origine » aux champs obligatoires casserait toutes
     les demandes v1 ;
  2. **le choix du catalogue par la commande,** puisqu'un lot mixte v1 et v2 est refusé
     (K9) ;
  3. **les deux contrats publics d'I3,** proposition et document de statut, qui sont des
     schémas fermés : ajouter l'origine, les jambes ou le statut `unknown_place` les
     change ;
  4. **la résolution des lieux :** où elle a lieu, et si elle réécrit la valeur saisie.
- **La proposition générale :** tout ce qui est v2 est étiqueté v2, et tout ce qui est
  v1 reste identique octet pour octet. C'est la règle que le plan fixe déjà pour les
  clés (ID-4, K1, K8). Je propose de l'appliquer aussi :
  - aux documents publics, avec `trip-proposal-v2` et `trip-request-status-v2` pour les
    seules demandes v2 ;
  - aux champs obligatoires ;
  - à la politique d'admissibilité.
- **P4 et P5 ne changent pas.** La politique d'admissibilité est déduite des unités dans
  `lot_admissibility`. `run_formation_stages` l'appelle sans politique : il n'a donc pas
  à être modifié.
- **Ce qui change dans la base :** les contrats de P1 à P3, l'admissibilité, le lecteur
  du catalogue, le prompt et quatre fichiers d'I3. Comme les entrées de P4 changent de
  code, l'empreinte exploratoire `997109ee…` doit être régénérée (K1) : environ 23
  minutes.

---

## 1. Ce que le plan fixe

| Sujet | Où | Contenu |
|---|---|---|
| Exemple de référence | §3.2 | « Lyon-Alger, départ le 15 février 2027, retour le 25 février 2027 » |
| Aller-retour forfaitaire (ID-2) | §6.2 | une offre = un forfait ; jambes `outbound` et `return` ; type déduit de la présence du bloc `return` ; règles C1 à C6 ; hypothèse H-forfait |
| Politique `NON_FINANCIAL_V2` | §6.2 | `origin_mismatch`, `trip_type_mismatch`, `departure_after_window`, `return_before_window`, `return_after_window` ; le registre v1 n'est pas modifié |
| Clés v3 (ID-4) | §6.4 | `request_key`, `unit_economic_digest` et `unit_fingerprint` reçoivent les champs de trajet, sous condition ; tests K1 à K10 |
| Champs obligatoires (ID-8) | §5 | origine, destination, voyageurs, budget, fenêtre de départ, type de trajet ; « liste complète au §6.4 », qui ne la donne pas en fait (§2, B3) |
| Référentiel des lieux (ID-11) | §6.5 | `places_v1.json` avec alias, résolution avant `build_travel_unit`, clarification qui liste les lieux disponibles ; le chemin v1 n'est pas touché |
| Données | §7, I4 | `catalog_v2.json` (fournisseurs fictifs), `places_v1.json`, carnet v2, prompt `travel-request-extraction-v2`, jeu `request_extraction_v3.jsonl` |
| Calibration | §7, I4 | catalogue v2 et carnet v2 figés par leur manifeste **avant** la première exécution de recette, jamais ajustés après |
| Acceptation | §7, I4 | l'exemple Lyon-Alger, fourni sous forme structurée, produit une proposition complète ; la non-régression v1 est prouvée par K1 |

---

## 2. Constats dans le code

### B1. Aucune règle ne dit quand une demande est « v2 »

**Constat.** ID-8 rend l'origine, la fenêtre de départ et le type de trajet
obligatoires. Si on les ajoutait tels quels à `REQUIRED_FIELDS`
(`request_understanding.py`), toute demande v1 deviendrait `needs_clarification` : E3,
les tests d'I3, et `process_travel_request` avec ses tests. K1 l'interdit.

**Décision proposée (D-I4-1).** Une demande est **v2** dès qu'elle contient un champ de
trajet, sinon elle est **v1**. Les champs de trajet sont :

- au niveau de la demande : `origin`, `trip_type`, `departure_before`, `return_after`,
  `return_before` ;
- au niveau d'un profil : `departure_before`, `return_after`, `return_before`.

Une demande v1 suit exactement le chemin d'aujourd'hui : champs obligatoires v1,
catalogue v1, carnet v1, politique V1, clés v2 et documents d'I3 inchangés. Une demande
v2 suit le chemin v2 tout entier.

**Conséquence assumée.** « De Paris à Tokyo », extrait avec une origine, devient une
demande v2. Paris et Tokyo ne sont pas dans le référentiel v2 : la commande demande donc
de préciser le lieu, en listant les lieux disponibles. Aujourd'hui, l'origine est perdue
sans rien dire (B1 d'I3). Le nouveau comportement est plus honnête.

**Alternative :** une option explicite (`--catalog v2`). Elle ne règle pas le cas de la
saisie en langage naturel.

### B2. La commande ne peut pas ouvrir le marché avant de connaître la demande

**Constat.** La commande ouvre le catalogue v1 et le carnet v1 avant d'obtenir la
demande (§6.2 du périmètre d'I3). Or K9 refuse un lot mixte, et une unité v2 face à une
offre v1.

**Décision proposée (D-I4-2).**

- La commande obtient et valide la demande d'abord. Elle choisit ensuite le catalogue et
  le carnet selon la version : v1 avec v1, v2 avec v2.
- L'ordre des étapes change, mais pas les sorties v1 : l'ouverture du marché ne négocie
  rien, et le test I3-A13 continue de compter les sessions.
- La provenance affiche `catalog-v2` et `demand-pool-v2` pour une demande v2.

### B3. La « liste complète » des champs obligatoires n'est pas écrite

**Constat.** ID-8 renvoie au §6.4 du plan, qui décrit les clés et pas les champs
obligatoires. « Fenêtre de départ » n'y est pas définie : une borne ou deux ? Et le
retour d'un aller-retour n'y figure pas.

**Décision proposée (D-I4-3).** Pour une demande v2, les champs obligatoires sont, dans
cet ordre :

| Champ | Toujours | Seulement si `trip_type = round_trip` |
|---|---|---|
| `origin` | ✓ | |
| `destination` | ✓ | |
| `travellers` | ✓ | |
| `budget_per_person` | ✓ | |
| `trip_type` | ✓ | |
| `departure_after`, `departure_before` | ✓ (fenêtre fermée) | |
| `return_after`, `return_before` | | ✓ (fenêtre fermée) |

**Pourquoi des fenêtres fermées.** Une date exacte (« le 15 février ») ou un mois
(« en juillet ») donnent les deux bornes. Une fenêtre ouverte laisserait le retour d'un
forfait à n'importe quelle date. La clarification pose donc une question par fenêtre.

**Alternative :** n'exiger que la borne basse. Elle demande moins de précisions, au prix
de propositions dont le retour ne serait pas contraint.

### B4. Les règles de validation v2 n'existent pas

**Constat.** `validate_request_draft` ne contrôle que l'ordre et le passé des dates v1.

**Décision proposée (D-I4-4).** Pour une demande v2 seulement, de nouveaux messages fixes
s'ajoutent. Ils sont en anglais, comme les existants :

| # | Message |
|---|---|
| V1 | `departure_after must not be after departure_before` |
| V2 | `return_after must not be after return_before` |
| V3 | `a one_way request must not have a return window` |
| V4 | `the return window must not end before the departure window starts` |
| V5 | `departure_before must not be before the reference date` (et de même pour `return_after` et `return_before`) |
| V6 | `profile <id>: …` : les mêmes contrôles sur les fenêtres effectives d'un profil |

Ces messages entrent dans le domaine fermé E du document `trip-request-status-v2` (B10).

### B5. Les profils consolidés fusionneraient deux fenêtres différentes

**Constat.** `consolidate_profiles` fusionne deux profils dont `negotiation_profile_key`
est égale (`profiles.py`). Cette clé ne connaît que les champs v1. Deux profils d'une
demande v2 aux fenêtres de retour différentes seraient donc fusionnés, et une contrainte
serait perdue en silence.

**Décision proposée (D-I4-5).** La clé de consolidation reçoit les fenêtres v2 sous la
même condition que les clés v3 : document v1 identique octet pour octet sans champ de
trajet. Ainsi, l'identifiant `merged-<préfixe>` d'un profil v1 ne change pas. Un test
étend K1 à cette clé.

### B6. Une offre v2 n'a pas de place pour son origine ni pour ses jambes

**Constat.** `OfferQuote` a une destination, deux dates, `direct` et une capacité. Le
lecteur du catalogue (`json_catalog.py`) refuse toute clé inconnue, ce qui est voulu.

**Décision proposée (D-I4-6).**

- **`OfferQuote` reçoit, par ajout et avec la valeur `None` par défaut :** `origin`,
  `outbound` et `return_leg`, le mot `return` étant réservé en Python. Une jambe est un
  objet `OfferLeg` : `departure_date`, `arrival_date`, `direct`, `capacity_seats`,
  `leg_ref`.
- **Pour une offre v2, les champs existants gardent un sens aller :** `departure_date` et
  `arrival_date` sont ceux de l'aller. Ainsi, les règles v1 de départ et d'arrivée
  s'appliquent à l'aller sans changement. `direct` vaut C3, `capacity_seats` vaut C2.
- **C1 à C4 sont des invariants de `OfferQuote`,** contrôlés à la construction. C5 et C6
  sont contrôlés par `OfferCatalog` et par le lecteur. `trip_type` est une propriété
  déduite du bloc `return_leg`.
- **Le fichier v2 se distingue par une clé de premier niveau
  `"format": "offer-catalog-v2"`.** Un fichier sans cette clé est lu par le lecteur v1
  actuel, sans changement : le catalogue v1 garde ses octets et son empreinte. Un
  catalogue v2 ne contient que des offres v2.

### B7. L'admissibilité n'accepte qu'un seul registre de règles

**Constat.** `evaluate_unit_offer` lève une erreur si les règles du registre ne sont pas
exactement `RULE_ORDER`. `RULE_REASONS` associe un seul motif à chaque règle, alors que
la fenêtre de départ v2 en a deux.

**Décision proposée (D-I4-7).**

- **Un registre `NON_FINANCIAL_V2`,** avec un ordre `RULE_ORDER_V2` : route (destination,
  puis origine), type de trajet, offre avant la date de référence, fenêtre de départ
  (deux bornes), fenêtre d'arrivée de l'aller, fenêtre de retour (deux bornes), vol
  direct, exclusion de fournisseur, capacité.
- **Le contrôle du registre se généralise :** chaque politique doit contenir toutes les
  règles obligatoires de sa version. Le registre v1, `RULE_ORDER` et `RULE_REASONS` ne
  changent pas.
- **Les motifs v2 sont dans une table séparée,** qui peut donner deux motifs à une règle.
- **Un écart de route court-circuite le reste,** comme `destination_mismatch` en v1 : on
  ne publie que `destination_mismatch` et/ou `origin_mismatch`.
- **Les règles de retour ne s'appliquent qu'à un aller-retour.** Un aller simple demandé
  face à un forfait donne `trip_type_mismatch`.

### B8. Le choix de la politique toucherait P4

**Constat.** `run_formation_stages` (P4) appelle `lot_admissibility` sans politique,
donc avec V1. Passer V2 à cet endroit modifierait P4.

**Décision proposée (D-I4-8).**

- Le paramètre `policy` de `lot_admissibility` passe à `None` par défaut. `None` veut dire
  « déduite » :
  - V1 si toutes les unités et toutes les offres sont v1 ;
  - V2 si elles sont toutes v2 ;
  - sinon `LotInputError` (K9).
- Une politique explicite qui contredit les données est refusée.
- P4 n'est pas modifié, et `admissibility_id` d'un lot v1 est inchangé, puisque la
  politique déduite y vaut V1.

### B9. La résolution des lieux : où, et sur quelle valeur

**Constat.** §6.5 prévoit une résolution « avant `build_travel_unit` ». Mais
`build_travel_unit` est appelé dans `plan_lot`, pour la demande de la personne comme pour
celles du carnet. Le référentiel est un fichier, donc de l'infrastructure. D-I3-17
interdit de réécrire en silence une valeur saisie.

**Décision proposée (D-I4-9).**

- **Un objet du domaine, `PlaceDirectory`,** construit à partir de `places_v1.json` par un
  lecteur d'infrastructure. Il porte le nom canonique et les alias de chaque lieu, et
  résout un nom par NFC, `casefold` et suppression des espaces aux extrémités.
- **La commande résout l'origine et la destination d'une demande v2 avant le résumé.**
  Le brouillon validé porte alors les noms canoniques : « Algiers » devient « Alger ».
  - La personne voit ce nom dans le résumé et le valide (ID-10). La réécriture n'est
    donc pas silencieuse : le résumé la montre avant toute négociation.
  - Le texte brut n'est jamais recopié (B9 d'I3).
- **Les demandes du carnet v2 utilisent déjà les noms canoniques.** Le lecteur du carnet
  le vérifie.
- **Un lieu inconnu :**
  - avec `--prompt` ou la saisie, c'est un tour de clarification qui liste les lieux
    connus ;
  - avec `--draft-json`, c'est le code 2 et un document `unknown_place` (B10) ;
  - la valeur inconnue n'est jamais citée.
- **Une demande v1 n'est pas résolue.**

### B10. Les contrats publics d'I3 sont des schémas fermés

**Constat :**

- `trip-proposal-v1` a 107 noms de champs figés (T-CONF-3). Une offre v2 a une origine
  et des jambes ; une demande v2 a de nouvelles clés.
- `trip-request-status-v1` ferme `missing_fields` sur `REQUIRED_FIELDS`, ferme le domaine
  E, et n'a pas de statut pour un lieu inconnu.
- De plus, `request.draft` est `model_dump(mode="json")`. Dès que `TravelRequestDraft`
  gagne des champs, il contient des clés `null` de plus, et le JSON d'E3 change d'octets.

**Décision proposée (D-I4-10).** Les documents publics suivent la même règle que les
clés : identiques pour v1, étiquetés v2 pour v2.

- **Une demande v1 :**
  - `trip-proposal-v1` et `trip-request-status-v1`, identiques octet pour octet à I3 ;
  - `request.draft` n'y contient jamais de champ de trajet.
- **Une demande v2, `trip-proposal-v2` :** le contrat v1, plus des ajouts fermés :
  - `request.draft` complet ;
  - `unit.origin_key` et `unit.trip_type` ;
  - pour chaque offre, `origin`, `trip_type`, `outbound` et `return` (jambes publiques,
    `leg_ref` compris) ;
  - les nouveaux motifs de rejet.
- **Une demande v2, `trip-request-status-v2` :**
  - `missing_fields` est fermé sur la liste ordonnée de B3 ;
  - le domaine E reçoit les messages V1 à V6 ;
  - un cinquième statut, `unknown_place` (code 2), a pour champs propres `fields`
    (`origin` et/ou `destination`) et `known_places` (les noms canoniques, triés).
- Un test vérifie, comme K8, qu'un document v1 ne contient jamais de champ de trajet.

**Alternative :** un seul schéma v2 pour tout. Les sorties v1 changeraient, ce qui
contredit l'esprit de K1.

### B11. La clé de requête contrôle la destination, pas la route

**Constat.** `negotiation_request_for` refuse une unité dont la destination diffère de
celle de l'offre, mais ne connaît ni l'origine ni le type de trajet.

**Décision proposée (D-I4-11).** Pour une unité ou une offre v2, l'origine et le type de
trajet doivent aussi être égaux. Sinon, `ValueError`, comme pour la destination
aujourd'hui.

### B12. Le prompt v1 changerait sans le dire

**Constat.** L'extracteur Ollama envoie le schéma JSON de `TravelRequestDraft`. Dès que
ce modèle gagne des champs, le prompt v1 envoie un schéma différent tout en gardant
l'étiquette `travel-request-extraction-v1`.

**Décision proposée (D-I4-12).**

- **Le prompt v2 remplace le prompt v1,** et `EXTRACTION_PROMPT_VERSION` devient
  `travel-request-extraction-v2`.
- **Il ajoute trois consignes :**
  - recopier les noms de lieux tels qu'ils sont écrits ;
  - ne remplir `origin` et `trip_type` que s'ils sont dits ;
  - convertir une date exacte en fenêtre de même début et de même fin.
- **Il ne peut pas être mesuré en I4 :** Ollama n'est pas installé. La mesure est en I5.
  En I4, seul `--validate-only` est exécuté sur le jeu v3.

---

## 3. Contrats ajoutés

### 3.1 Demande, profils, unité

| Objet | Champ ajouté | Type | Défaut |
|---|---|---|---|
| `TravelRequestDraft` | `origin` | `str`, de 2 à 120 caractères | `None` |
| `TravelRequestDraft` | `trip_type` | `"one_way"` ou `"round_trip"` | `None` |
| `TravelRequestDraft` | `departure_before`, `return_after`, `return_before` | date | `None` |
| `TravelerProfileDraft` | `departure_before`, `return_after`, `return_before` | date | `None` |
| `TravelerProfile` | les mêmes, valeurs effectives après héritage (`build_profiles`) | date | `None` |
| `TravelUnit` | `origin_key` | clé normalisée du lieu résolu | `None` |
| `TravelUnit` | `trip_type` | littéral | `None` |

**L'unité est v2 exactement quand `origin_key` n'est pas `None`.** `trip_type` est alors
obligatoire. Un invariant de `TravelUnit` le vérifie.

### 3.2 Offre et catalogue v2

**Format du fichier :**

```json
{
  "format": "offer-catalog-v2",
  "catalog_version": "catalog-v2",
  "currency": "EUR",
  "synthetic": true,
  "offers": [
    {
      "offer_id": "lys-alg-...",
      "supplier_id": "...",
      "origin": "Lyon",
      "destination": "Alger",
      "outbound": {"departure_date": "...", "arrival_date": "...", "direct": true,
                   "capacity_seats": 0, "leg_ref": "XX-123-20270215"},
      "return":   {"departure_date": "...", "arrival_date": "...", "direct": true,
                   "capacity_seats": 0, "leg_ref": "XX-124-20270225"},
      "capacity_seats": 0,
      "tiers": [{"min_seats": 1, "list_per_seat_cents": 0, "seller_floor_per_seat_cents": 0}]
    }
  ]
}
```

- **Le bloc `return` est absent pour un aller simple.** Un bloc partiel est refusé.
- **Les règles C1 à C6** sont celles du plan (§6.2), contrôlées comme il est dit en B6.
- **Le lecteur refuse un écart à C2 ou à C3,** au lieu de le corriger.
- **Le manifeste** a la même forme que celui de v1.

### 3.3 Référentiel des lieux

**`data/catalog/places_v1.json`,** avec son manifeste `places_v1.manifest.json`
(version, fichier, SHA-256, nombre de lieux, objet, limites) :

```json
{"version": "places-v1", "places": [{"name": "Alger", "aliases": ["Algiers", "ALG"]}]}
```

**Règles au chargement :**

- chaque nom et chaque alias se résout vers un seul lieu ;
- aucune collision après normalisation ;
- chaque origine et chaque destination du catalogue v2 est un nom canonique du
  référentiel.

### 3.4 Clés v3

C'est le §6.4 du plan, appliqué aux trois identités, et, d'après B5, à la clé de
consolidation des profils.

- **Le document v3 est produit dès qu'une unité ou l'offre est v2.** Le schéma de la clé
  de requête devient `negotiation-request-key-v3`.
- **Sans champ de trajet, le document v2 est identique octet pour octet,** et
  l'empreinte `ae759f83…` est inchangée.

### 3.5 Admissibilité v2

| Règle (`AdmissibilityRuleId`) | Motif(s) |
|---|---|
| `destination` | `destination_mismatch` |
| `origin` | `origin_mismatch` |
| `trip_type` | `trip_type_mismatch` |
| `offer_not_before_reference` | `offer_departs_before_reference_date` |
| `departure_window` | `departure_before_window`, `departure_after_window` |
| `arrival_window` | `arrival_after_window` (sur l'arrivée de l'aller) |
| `return_window` | `return_before_window`, `return_after_window` (sur le départ du retour) |
| `direct_flight` | `direct_flight_required` (C3 : tous les segments) |
| `supplier_exclusion` | `excluded_supplier` |
| `unit_capacity` | `unit_exceeds_offer_capacity` (capacité effective C2) |

Les messages français de ces motifs s'ajoutent à `explanations_fr`.

### 3.6 Documents publics v2

Ce sont les ajouts de B10. Le §4 du périmètre d'I3 est repris, et il est étendu champ
par champ dans la révision suivante de ce document, une fois D-I4-10 tranchée.

---

## 4. La commande et le workflow

1. **Les options ne changent pas.** Il n'y a toujours ni `--catalog` ni `--pool` (ID-1).
2. **La demande est obtenue, puis le contrôle D-I3-17 s'applique,** sur les chaînes
   v2 aussi (`origin`).
3. **La version est déterminée (D-I4-1).**
4. **Pour une demande v2 :**
   - les lieux sont résolus ; un lieu inconnu demande une clarification, ou donne le
     code 2 ;
   - la demande est validée selon les règles v2 ;
   - la clarification porte sur les champs obligatoires de B3.
5. **Le catalogue et le carnet sont choisis selon la version, puis ouverts (D-I4-2).**
6. **Le résumé est affiché.** Pour une demande v2, il montre l'origine, le type de
   trajet et les fenêtres. Pour une demande v1, il est identique à I3.
7. **La validation, `plan_travel_request` et le rendu** ne changent pas ; le rendu est v1
   ou v2 selon la version.

**`plan_travel_request` garde sa signature.** La politique est déduite par
`lot_admissibility` (D-I4-8).

---

## 5. Données

### 5.1 La règle de calibration

Le catalogue v2 et le carnet v2 sont écrits à partir de règles énoncées à l'avance, puis
figés par leur manifeste avant toute exécution de planification. Ils ne sont jamais
ajustés au vu d'un résultat.

**Le critère d'acceptation du plan est une proposition complète, quel que soit son
statut.** Le statut attendu n'est donc pas fixé d'avance. Cela évite la tentation
d'ajuster les données pour obtenir une coalition.

### 5.2 Ce que les données doivent permettre (proposition, à figer en I4-B)

| Donnée | Contenu proposé | Ce qu'il permet de tester |
|---|---|---|
| Lyon → Alger, aller-retour, aller le 2027-02-15, retour le 2027-02-25 | deux fournisseurs fictifs : l'un direct, l'autre avec escale sur une jambe | l'exemple de référence ; C3 ; la préférence pour un vol direct |
| Lyon → Alger, aller simple, le 2027-02-15 | un fournisseur | `trip_type_mismatch` |
| Marseille → Alger, aller-retour, mêmes dates | un fournisseur | `origin_mismatch` |
| Lyon → Alger, aller-retour, retour le 2027-02-27 | un fournisseur | `return_after_window` |
| Paliers et planchers | même structure qu'en v1 : 2 ou 3 paliers, plancher privé au-dessous du prix catalogue | le groupement par palier |
| Capacités | marges telles que H2 tienne pour la plus grande demande admise (20 places) | H2 |
| Carnet v2 | 4 à 6 demandes Lyon → Alger aux mêmes fenêtres, de 1 à 3 voyageurs, budgets de part et d'autre des prix catalogue | une coalition possible, sans qu'elle soit garantie |
| `places_v1.json` | Lyon, Marseille, Alger, avec leurs alias usuels (Algiers, ALG, LYS, MRS…) | K3, la résolution des alias, `unknown_place` |

**L'exemple de référence sous forme structurée (D-I4-13) :** Lyon → Alger, `round_trip`,
2 voyageurs, 500 € par personne, départ entre le 2027-02-15 et le 2027-02-15, retour
entre le 2027-02-25 et le 2027-02-25. Le plan ne fixe ni le nombre de voyageurs ni le
budget de cet exemple. Je reprends le budget de l'exemple de la spécification d'I3
(500 € par personne) et je propose 2 voyageurs.

### 5.3 Le jeu `request_extraction_v3.jsonl`

- le texte de référence complet, et la même demande sans nombre de voyageurs
  (`needs_clarification`) ;
- un alias (« Algiers ») ;
- un lieu inconnu ;
- un aller simple ;
- une date exacte et un mois ;
- des cas v1 repris du jeu v2, pour vérifier qu'une demande sans trajet reste v1.

Il a un manifeste. `evaluate_requests.py --validate-only --dataset …v3` le valide sans
Ollama.

---

## 6. Ce qui change dans la base, et ce qui ne change pas

| Fichier | Changement |
|---|---|
| `application/request_contracts.py` | champs ajoutés (§3.1) |
| `application/request_understanding.py` | version d'une demande ; champs obligatoires et règles v2 (B3, B4). Les règles v1 sont inchangées |
| `application/profiles.py` | héritage des fenêtres v2 ; clé de consolidation conditionnelle (B5) |
| `application/travel_units.py` | origine et type de trajet ; empreinte v3 conditionnelle |
| `domain/traveler_profile.py`, `domain/travel_unit.py` | champs ajoutés et invariants |
| `domain/offer.py` | `OfferLeg`, champs v2 de `OfferQuote`, C1 à C4 ; C5 et C6 dans `OfferCatalog` |
| `domain/negotiation_request.py` | documents v3 conditionnels ; contrôle de route (B11) |
| `domain/admissibility.py` | registre V2, règles et motifs v2 (B7) ; le registre v1 est inchangé |
| `application/lot_admissibility.py` | politique déduite ; K9 (B8) |
| `infrastructure/catalog/json_catalog.py` | lecteur v2 selon la clé `format` (B6) ; le lecteur v1 est inchangé |
| `infrastructure/llm/ollama.py` | prompt v2 (B12) |
| I3 : `trip_proposal.py`, `explanations_fr.py`, `json_renderer.py`, `text_renderer.py`, `plan_trip.py` | documents v2, résolution des lieux, choix du catalogue (B2, B9, B10) |
| **Nouveaux** | `domain/places.py`, `infrastructure/catalog/places.py`, `data/catalog/catalog_v2.json` et `places_v1.json` avec leurs manifestes, `data/demand/demand_pool_v2.jsonl` avec son manifeste, `data/eval/request_extraction_v3.jsonl` avec son manifeste, tests |
| **Inchangés** | P4 (`coalition_*`, `partition_solver`, `formation_*`), P5 (`savings_allocation`), le simulateur P3, `trip_planning.py`, `process_travel_request`, le catalogue v1, le carnet v1, les fichiers historiques et le golden master |

**`demand_pool.py` ne change pas.** Il valide déjà chaque brouillon par
`TravelRequestDraft`, et vérifie le `catalog_version` du manifeste. Le contrôle des noms
canoniques du carnet v2 se fait au chargement du lot, dans la commande.

---

## 7. Tests et critères

### 7.1 Tests

- **K1 à K10** (plan, §6.4), sur les trois identités et sur la clé de consolidation.
  - K1 reproduit toutes les empreintes figées : `ae759f83…`, P1.3, `admissibility_id`,
    `formation_run_id` et `result_sha256` du lot figé.
  - K1 reproduit aussi l'empreinte exploratoire `997109ee…`, régénérée en environ 23
    minutes.
- **C1 à C6 et H-forfait au chargement.** Pour chaque règle, un aller simple et un
  aller-retour. Sont refusés :
  - un bloc `return` partiel ;
  - un `leg_ref` non canonique ;
  - une date de suffixe incohérente ;
  - un `leg_ref` dupliqué entre deux forfaits, ou à l'intérieur d'un forfait.
- **Un test par règle v2,** et pour chaque motif.
- **Le référentiel des lieux :**
  - les alias ;
  - un lieu inconnu, par `--draft-json` (code 2) et par clarification ;
  - un référentiel invalide refusé (collision, lieu du catalogue absent).
- **La version d'une demande :**
  - une demande sans champ de trajet garde ses sorties d'I3 octet pour octet ;
  - un document v1 ne contient jamais de champ de trajet (comme K8).
- **La validation v2 :** V1 à V6, et la clarification sur les champs de B3.
- **`--validate-only` sur le jeu v3.**
- **Bout en bout :** `--draft-json` sur l'exemple Lyon-Alger, en texte et en JSON, et
  une proposition `trip-proposal-v2` complète.
- **Les tests d'I3 existants passent sans modification,** sur le chemin v1.

### 7.2 Critères d'acceptation

| Id | Critère |
|---|---|
| I4-A1 | l'exemple Lyon-Alger structuré produit une proposition v2 complète, quel que soit son statut |
| I4-A2 | K1 : toutes les empreintes figées, dont `997109ee…`, sont reproduites ; les sorties v1 d'I3 sont identiques octet pour octet |
| I4-A3 | K2 à K10 passent sur les trois identités |
| I4-A4 | C1 à C6 et H-forfait sont contrôlés au chargement, avec les refus listés |
| I4-A5 | un test par règle et par motif v2 |
| I4-A6 | référentiel : alias, lieu inconnu, refus d'un référentiel invalide |
| I4-A7 | P4, P5, le simulateur P3 et `process_travel_request` sont inchangés (manifeste) |
| I4-A8 | les documents v2 ont un schéma fermé, et T-CONF-1 à T-CONF-3 s'y appliquent comme en v1 |
| I4-A9 | `--validate-only` sur le jeu v3 |
| I4-A10 | calibration : manifestes des données v2 figés avant la première exécution, sans retouche ensuite |
| I4-A11 | Python 3.10, ruff, `git diff --check`, golden master, suite complète avec deux graines, mutants des règles nouvelles |

---

## 8. Découpage

**Chaque sous-étape est revue et autorisée séparément.**

| Sous-étape | Contenu | Preuve demandée |
|---|---|---|
| I4-A | contrats : demande, profils, unité, offre v2 et C1 à C4, clés v3 avec K1 à K10, clé de consolidation, `PlaceDirectory` | K1 à K10 ; empreintes figées reproduites, dont `997109ee…` |
| I4-B | données et P2 : lecteur v2 (C5, C6, H-forfait), `catalog_v2.json`, `places_v1.json` et leurs manifestes, politique V2 et sa déduction, K9, carnet v2, validation v2 | tests C et V2 ; manifestes figés avant toute planification |
| I4-C | workflow et présentation : version d'une demande, résolution des lieux, `unknown_place`, choix du catalogue, documents v2, prompt v2, jeu v3 | Lyon-Alger de bout en bout ; sorties v1 d'I3 identiques ; `--validate-only` |

Chaque sous-étape fournit, comme en I3 :

- un manifeste de la base et un diff cumulé ;
- un rapport, `docs/PHASE_I4_ROUTE_REPORT.md`, complété section par section.

La copie de l'état accepté de chaque sous-étape est conservée telle quelle, pour que le
diff incrémental suivant ne repose pas sur une reconstruction : c'est la limite relevée
à la clôture d'I3.

---

## 9. Décisions demandées

| Id | Décision proposée | Alternative |
|---|---|---|
| D-I4-1 | une demande est v2 dès qu'elle a un champ de trajet ; sinon elle suit le chemin v1 inchangé | option `--catalog` |
| D-I4-2 | la commande choisit le catalogue et le carnet après avoir obtenu la demande, selon sa version | ouvrir les deux marchés d'avance |
| D-I4-3 | champs obligatoires v2 : origine, destination, voyageurs, budget, type de trajet, fenêtre de départ fermée ; fenêtre de retour fermée pour un aller-retour | borne basse seulement |
| D-I4-4 | règles de validation v2 V1 à V6, messages fixes ajoutés au domaine E v2 | – |
| D-I4-5 | clé de consolidation des profils étendue sous condition, v1 identique | ne pas consolider les profils v2 |
| D-I4-6 | `OfferQuote` étendue (`origin`, `outbound`, `return_leg`) ; les dates existantes désignent l'aller ; fichier v2 repéré par `"format": "offer-catalog-v2"` | un type d'offre séparé, que P2 à P5 devraient connaître |
| D-I4-7 | registre V2 séparé, contrôle de registre généralisé, motifs v2 dans une table propre ; court-circuit de route | – |
| D-I4-8 | politique déduite dans `lot_admissibility` (`None` par défaut) ; lot mixte refusé ; P4 inchangé | passer la politique depuis P4, ce qui modifierait P4 |
| D-I4-9 | `PlaceDirectory` ; résolution par la commande avant le résumé, visible et validée ; lieu inconnu : clarification ou code 2, sans citer la valeur | garder la valeur saisie et ne résoudre que la clé |
| D-I4-10 | `trip-proposal-v2` et `trip-request-status-v2` pour les seules demandes v2 ; sorties v1 identiques | un schéma v2 unique pour tout |
| D-I4-11 | contrôle de route (origine, type de trajet) dans `negotiation_request_for` | – |
| D-I4-12 | prompt v2 à la place du prompt v1 ; mesure reportée en I5 | garder les deux prompts |
| D-I4-13 | exemple structuré : Lyon → Alger, aller-retour, 2 voyageurs, 500 €, fenêtres d'un jour | – |

---

## 10. Risques

| Risque | Traitement |
|---|---|
| Une évolution de `TravelRequestDraft` change en silence les sorties v1 (clés `null`) | règle de B10 ; test octet pour octet sur les sorties d'I3 |
| Une clé v1 change par mégarde | K1, avec toutes les empreintes figées, dont la régénération exploratoire |
| Deux profils aux fenêtres différentes sont fusionnés | clé de consolidation étendue (B5) |
| Deux forfaits partagent une jambe, ce qui couplerait leurs capacités | C5 et C6 au chargement (H-forfait) |
| Les données v2 sont ajustées pour obtenir une coalition | calibration figée d'avance ; acceptation sur une proposition complète, quel que soit le statut |
| Une demande « Paris → Tokyo » change de comportement | conséquence assumée de D-I4-1 : clarification au lieu d'une perte silencieuse de l'origine |
| Le prompt v2 n'est pas mesuré | mesure en I5, sur le jeu v3 ; I4 ne valide que le format |

---

## 11. Gouvernance

- **Cette révision 1 doit être revue,** et les décisions D-I4-1 à D-I4-13 tranchées,
  avant toute demande d'autorisation.
- **Chaque sous-étape (I4-A, puis I4-B, puis I4-C) est autorisée séparément,** après la
  revue de la précédente.
- **Aucune opération Git** sans autorisation distincte, et jamais `git add .` ni
  `git add -A`. Les 18 fichiers personnels restent exclus.
