# I3 : périmètre et contrats figés (présentation, explications et CLI)

**Statut :** proposition de périmètre, **révision 4**, en attente de la dernière revue.
I3 n'est pas autorisée.

- La révision 1 a été validée dans sa direction, sous sept corrections. La révision 2 les
  intègre (§15).
- La revue de la révision 2 a été favorable, sous trois corrections : la provenance du
  rejeu, la contradiction entre T-CONF-2 et B7, et les domaines du statut
  `request_rejected`. La révision 3 les intègre, et le §16 indique où. Elle corrige aussi
  quatre erreurs de la révision 2, trouvées en vérifiant le code (§16).
- La revue de la révision 3 a été favorable. Elle valide les deux extensions proposées :
  le retrait de `catalog_sha256` et l'absence de chemin de fichier dans les sorties. Elle
  demande une dernière précision : l'anonymisation effective des autres membres dans
  T-CONF-2, et un cas de fichier de rejeu illisible dans T-REPLAY. La révision 4
  n'ajoute que cela (§17).

- I3 **n'est pas démarrée** et aucun code n'a été écrit pour elle.
- Aucune opération Git n'a été faite.

**Rôle de ce document.** La spécification technique d'I3 laisse sept points ouverts (son
§14) et demande qu'ils soient « tranchés à partir des contrats existants ou par une
décision explicite avant implémentation ». Ce document :

- tranche ces points, et quatre autres trouvés en lisant le code ;
- fige le contrat public `trip-proposal-v1`, champ par champ, avec le champ source de
  chacun ;
- numérote chaque décision proposée (D-I3-n, récapitulées au §11). Ce qui n'est pas
  tranché ici ne doit pas être choisi en silence pendant l'implémentation.

**Textes de référence :**

- la spécification technique d'I3, « Présentation, explications et CLI », transmise en
  revue le 2026-11-19 ; on s'y réfère sous le nom de « spécification » ;
- `docs/PHASE_3H_P5_INTEGRATION_PLAN.md`, révision 4 (« le plan ») : §1.2 (avertissement
  et vocabulaire), §1.3 (les neuf éléments), §4.5 (confidentialité), §4.6 (contrats),
  §6.3 (mode démonstration), §6.5 (référentiel des lieux) et §7, I3 ;
- les décisions validées ID-1, ID-7, ID-9, ID-10 et ID-11 (plan, §5).

**Ce qui a déjà été accepté :** I0 est clôturée, I1 est acceptée, et I2 est acceptée et
clôturée depuis le 2026-11-20 (`docs/PHASE_I2_ALLOCATION_REPORT.md`).

---

## 0. Résumé

- **La spécification est fidèle au plan.** Elle reprend les modules, les options de la
  CLI, les codes de sortie et les 13 codes d'explication du §7 I3. Elle y ajoute des
  critères d'acceptation (I3-A1 à A16) et un découpage en trois sous-étapes, tous deux
  utiles.
- **Onze points ne pouvaient pas être implémentés tels quels** (§3). Chacun est présenté
  avec son constat dans le code et une décision proposée.
- **Le contrat `trip-proposal-v1` est figé au §4.** Chaque champ a un nom, un type et un
  champ source existant.
- **Les 13 codes sont rangés par niveau au §5.** Aucun code n'est ajouté :
  - un statut unique par unité, à choisir parmi 7 ;
  - 2 modificateurs ;
  - 2 annotations d'offre ;
  - 2 codes de niveau demande, qui ne figurent pas dans une proposition.
- **La fonction `plan_travel_request` et la CLI sont spécifiées au §6.** Trois codes de
  sortie s'ajoutent aux quatre de la spécification : 4 (annulé), 64 (usage incorrect) et
  130 (interruption).
- **Trois corrections par rapport à ma revue en conversation** (§12) :
  - la date de référence ne change pas les prix ;
  - le plan accepte déjà la visibilité des contre-offres du vendeur ;
  - `plan_travel_request` peut rester synchrone.
- **La révision 2** :
  - retire de la provenance publique toute empreinte calculée sur des données privées,
    celles des autres demandes comme celles des vendeurs ;
  - applique sans exception le contrôle du vocabulaire ;
  - précise les deux explications de P4 ;
  - ferme le schéma des documents de statut ;
  - ajoute les tests demandés : confidentialité à budget variable, interruption, et des
    mutants pour chacun (§9).
- **La révision 3** :
  - ne publie plus aucune empreinte dans la provenance. L'empreinte du fichier de rejeu
    est remplacée par une constante. `catalog_sha256` est retiré aussi : le fichier du
    catalogue contient les planchers des vendeurs, contrairement à ce qu'affirmait la
    révision 2 ;
  - réécrit T-CONF-2 : le test vérifie l'absence de divulgation directe, et non plus
    l'absence de tout montant égal à un plancher. La visibilité des contre-offres devient
    une assertion du test ;
  - ferme les domaines de valeurs de `request_rejected` et de `invalid`, à partir des
    valeurs que le dépôt produit réellement. Le validateur contrôle les valeurs, et non
    plus seulement les clés.

---

## 1. Ce que le dépôt fournit déjà

Les contrats ci-dessous existent et ne changent pas. Toute la proposition publique en est
une projection.

| Objet | Où | Ce qu'I3 en utilise |
|---|---|---|
| `TravelRequestDraft`, `TravelerProfileDraft` | `application/request_contracts.py` | la demande validée ; format de `--draft-json` |
| `RequestUnderstandingResult`, `validate_request_draft`, `understand_request`, `REQUIRED_FIELDS` | `application/request_understanding.py` | statuts `ready`, `needs_clarification` et `invalid` ; champs manquants |
| `PlanningInput`, `PlanningRequest`, `TripPlan`, `PlanStatus`, `RequestRejection`, `plan_lot` | `application/trip_planning.py` | statuts `planned` et `request_rejected` ; provenance |
| `LotAdmissibilityResult`, `PairAdmissibility`, `AdmissibilityViolation`, `AdmissibilityNote` | `application/lot_admissibility.py`, `domain/admissibility.py` | offres admissibles et rejetées, règles, notes |
| `UnitReferenceCost`, `ReferenceAttempt` | `application/reference_costs.py` | négociations solo et référence |
| `FormationResult`, `FormedBlock`, `ComponentFormation`, `CoalitionCost` | `application/coalition_formation.py`, `application/coalition_costs.py` | blocs, valeur, coalitions évaluées |
| `CoalitionGame` (`value`, `is_feasible`, `feasible_coalitions`, `cover_values`) | `domain/coalition_game.py` | explication `alone_social_optimum` |
| `AllocationResult`, `BlockAllocation`, `TravelerShare`, `UnallocatedUnit` | `application/savings_allocation.py` | φ, y, paiements, parts par voyageur |
| `NegotiationJournal`, `NegotiationEvent` | `infrastructure/negotiation/simulated_oracle.py` | journaux publics |
| `OfferQuote` (`tier_for`, `list_total`) | `domain/offer.py` | données publiques du catalogue |
| `open_simulated_market`, `load_demand_pool` | `infrastructure/negotiation/market.py`, `infrastructure/demand/demand_pool.py` | catalogue v1 et carnet v1 |

**Données v1 :**

- **le catalogue `catalog-v1`** a 3 offres : Rome (CloudWing, direct, 2027-04-05), Tokyo
  (Northstar, direct, 2027-03-10) et Tokyo (SkyWays, avec escale, 2027-03-12) ;
- **le carnet `demand_pool_v1`** contient 6 demandes synthétiques : 4 pour Tokyo et 2 pour
  Rome.

---

## 2. Périmètre

### 2.1 Fichiers

| Fichier | Nature | Sous-étape |
|---|---|---|
| `Multi-Agent/coalition_travel/application/trip_proposal.py` | nouveau : DTO, énumérations des codes, constructeur `build_trip_proposal`, invariants | I3-A |
| `Multi-Agent/coalition_travel/infrastructure/presentation/` : `__init__.py`, `explanations_fr.py`, `text_renderer.py`, `json_renderer.py` | nouveaux | I3-B |
| `Multi-Agent/coalition_travel/infrastructure/llm/replay.py` | nouveau : extracteur de rejeu (D-I3-10) | I3-C |
| `Multi-Agent/coalition_travel/application/travel_workflow.py` | **modifié** : ajout de `plan_travel_request` et de son résultat ; `process_travel_request` ne change pas | I3-C |
| `Multi-Agent/plan_trip.py` | nouveau : point d'entrée de la CLI | I3-C |
| `pyproject.toml` | **modifié** : une ligne, `coalition-travel-plan = "plan_trip:main"` | I3-C |
| `tests/test_trip_proposal.py`, `tests/test_presentation.py`, `tests/test_plan_trip_cli.py`, et un module d'aide au contrôle du vocabulaire | nouveaux | A, B, C |

**Fichiers de la base modifiés.** Il y en a deux : `travel_workflow.py` (ajouts seulement)
et `pyproject.toml` (une ligne). Ils figureront dans le diff, comme les deux fichiers d'I1
l'ont été en I2.

### 2.2 Exclu

- tout ce qu'exclut le §2.2 de la spécification : web, réservation réelle, changement de
  P2 à P5, de `process_travel_request` ou du Broker ;
- **le mode session** (plan, §6.3) : la CLI v1 fournit une seule demande au premier plan ;
- **l'émission de `unknown_place` par le workflow** : elle attend le référentiel des lieux
  d'I4 (D-I3-1) ;
- **le RAG dans la CLI** : `understand_request` est appelée sans `knowledge_service`. On
  pourra le reprendre en I5 ;
- **les options `--catalog` et `--pool`** : la CLI v1 utilise le catalogue v1 et le carnet
  v1 versionnés (ID-1, mode démonstration).

---

## 3. Points tranchés

### B1. L'exemple Lyon-Alger et le code `unknown_place`

**Constat :**

- Le catalogue v1 ne propose que Rome et Tokyo.
- Il n'y a pas d'origine dans le modèle avant I4 (ID-2). `TravelRequestDraft` n'a pas de
  champ d'origine, et `route_key` vaut la destination.
- Le référentiel des lieux (§6.5, ID-11) arrive avec le catalogue v2, en I4, et le plan
  précise : « Le chemin v1 n'est pas touché ».

Dans I3, une demande « de Lyon à Alger » perd donc son origine à l'extraction. Les 3
offres sont ensuite rejetées par la règle `destination` (`destination_mismatch`) : l'unité
reçoit `no_admissible_offer`.

**Décision proposée (D-I3-1) :**

- **L'exemple de la spécification est remplacé par une demande pour Tokyo.** C'est le
  scénario E3 d'I2 : 8 voyageurs, 500 € par personne, carnet v1.
- **`unknown_place` reste dans l'énumération fermée dès I3.** Son message est écrit et
  testé au niveau des explications (I3-B).
- **Le workflow ne l'émettra qu'en I4,** quand le référentiel existera. En I3, une
  destination absente du catalogue donne `no_admissible_offer`, avec les rejets
  `destination_mismatch`.
- **L'origine perdue reste visible.** Le résumé de la demande validée n'affiche aucune
  origine, ce que la personne voit avant de valider.

**Alternative écartée :** comparer la destination aux destinations du catalogue v1. Ce
serait une règle nouvelle, que le plan réserve à I4.

### B2. La date de référence par défaut

**Constat.** `plan_lot`, `open_simulated_market` et `validate_request_draft` exigent une
date explicite : le nouveau workflow n'a pas de valeur par défaut. La seule règle
existante dans le dépôt est `reference_date or date.today()` dans `BuyerAgent.py`.

La date intervient à quatre endroits :

1. **la validation :** une date passée est invalide ;
2. **l'admissibilité,** par la règle `offer_not_before_reference` : après le 2027-03-10,
   l'offre Northstar pour Tokyo est rejetée ; après le 2027-04-05, toutes le sont ;
3. **l'extraction** des dates relatives (« en juillet ») ;
4. **la provenance :** la date fait partie de `SimulatedOracleConfig`, donc de
   `oracle_configuration_id`, interne. Dans la proposition, elle apparaît dans
   `provenance.reference_date`.

**Elle ne change pas les prix.** L'oracle passe la date de référence comme échéance de
l'acheteur (`_buyer_for` dans `simulated_oracle.py`). Le nombre de jours restants calculé
dans `BuyerAgent` vaut donc toujours 0, et le taux de concession ne varie pas.

**Décision proposée (D-I3-2) :**

- par défaut, `date.today()`, la seule règle existante, comme le demande le §8.7 de la
  spécification ;
- `--reference-date AAAA-MM-JJ`, lu par `date.fromisoformat` ;
- la date utilisée est toujours affichée : en tête du texte, et dans
  `provenance.reference_date` en JSON ;
- les tests passent toujours la date. On prend le 2026-11-19, la date de référence des
  tests d'I1 et d'I2 ;
- la documentation de la commande signale qu'avec le catalogue v1, la démonstration ne
  trouve plus d'offre après le 2027-04-05.

**Alternative :** rendre l'option obligatoire.

### B3. Le code 2 et argparse

**Constat.** `argparse` sort avec le code 2 pour toute erreur d'usage. Une option inconnue
serait alors lue comme « clarification requise ».

**Décision proposée (D-I3-3).** `ArgumentParser.error` est redéfinie pour sortir avec le
code **64** (`EX_USAGE`, la convention `sysexits`). Le code 64 couvre :

- une option inconnue ;
- `--prompt` employé avec `--draft-json` ;
- une date mal formée ;
- un fichier introuvable ou illisible.

**Alternative :** le code 3. Mais un usage incorrect n'est pas une demande invalide.

### B4. L'annulation de la confirmation

**Constat.** Aucun des codes 0 à 3 ne veut dire « la personne a refusé ». Le §10.4 de la
spécification exige de tester par sous-processus une confirmation acceptée et une
confirmation refusée. La confirmation doit donc lire l'entrée standard, même quand ce
n'est pas un terminal.

**Décision proposée (D-I3-4) :**

- **la question** « Valider cette demande et lancer la simulation ? [o/N] » est écrite sur
  la sortie d'erreur, et la réponse est lue sur l'entrée standard ;
- **sont acceptés** « o » et « oui », après suppression des espaces et `casefold`. Toute
  autre réponse, une ligne vide ou la fin de l'entrée est un refus : code **4**, sans
  appel à `plan_travel_request` ni négociation ;
- **`--yes`** saute la question ;
- **une interruption** (Ctrl-C), à n'importe quel moment, donne le code **130**, sans rien
  écrire sur la sortie standard.

### B5. Les niveaux des codes

**Constat.** Les 13 codes mélangent quatre niveaux :

- **la demande :** `needs_clarification`, `unknown_place`. Aucune unité n'existe encore ;
- **l'issue de l'unité ;**
- **des modificateurs :** `projection_active`, `budget_cap_active` ;
- **les offres :** `offer_rejected`, `direct_preference_not_met`.

En l'état, le critère I3-A2 (« exactement un statut ») n'est pas vérifiable.

**Décision proposée (D-I3-5) :** le classement du §5.

### B6. Le cache de couvertures d'I2 n'est pas exposé

**Constat.** Le §5.1 de la spécification demande de réutiliser la couverture « mise en
cache par I2 ». Mais `CoverCache` est local à `allocate_formation` : ni `AllocationResult`
ni `TripPlan` ne portent de couverture, seulement des compteurs.

**Décision proposée (D-I3-6) :**

- **Le constructeur recalcule `CoalitionGame.cover_values()`, une fois par composante
  concernée.** Une composante est concernée si l'unité au premier plan y est seule, si
  elle est optimisée et si elle compte au moins deux unités.
- **Le calcul est exact et n'appelle jamais l'oracle.** Son coût est en Θ(3^m) avec m ≤ 14.
  M1 l'a mesuré à 0,34 s pour k = 14 (rapport d'I2, §5.3).
- **Aucun nouveau seuil n'est nécessaire,** ce qui répond au point 6 du §14. La limite de
  14 unités (`FormationLimits.max_component_units`) borne déjà le calcul : au-delà,
  l'unité reçoit `component_too_large` et rien n'est calculé.

**Alternative écartée :** exposer le cache dans `AllocationResult`. Cela changerait le
contrat d'I2 et son empreinte.

### B7. Les contre-offres du vendeur dans les journaux

**Constat :**

- `NegotiationJournal` ne contient pas de plancher.
- En revanche, ses événements portent les contre-offres successives du vendeur. Quand un
  vendeur descend jusqu'à son plancher, ses dernières offres le laissent deviner.
- Le plan a déjà tranché ce point (§4.5, validé) : « Les contre-offres du vendeur sont
  visibles, comme dans une vraie négociation. » Il le classe en risque résiduel, accepté
  et documenté.

**Décision proposée (D-I3-7).** On suit le plan : la vue publique d'un journal garde les
offres du vendeur. Ma revue en conversation proposait de les masquer ; je la corrige
(§12). Le côté leader est traité par B11.

### B8. Ce qu'on montre des autres membres d'un bloc

**Constat.** Il faut concilier deux exigences :

- la spécification interdit les données personnelles et les identifiants des autres
  demandes ;
- sans le paiement des autres membres, la personne ne peut pas vérifier que la somme des
  paiements égale le coût négocié du bloc.

**Décision proposée (D-I3-8) :**

- **pour chaque autre membre,** on affiche un libellé « autre demande k » (k suit l'ordre
  croissant des `unit_id` dans le bloc), son nombre de places et son paiement en
  centimes ;
- **on n'affiche jamais** l'identifiant de demande ou d'unité, le budget, les profils, la
  référence, φ ni y.

En v1, les autres demandes viennent du carnet synthétique public. La règle ne protège donc
personne aujourd'hui, mais elle fixe le contrat avant le mode session.

### B9. La recopie de la saisie et les messages de validation

**Constat :**

- **Recopier le texte saisi** placerait les mots de la personne dans la sortie (« billets
  d'avion ») et ferait échouer le contrôle du vocabulaire.
- **Les erreurs de `validate_request_draft`** sont des phrases libres en anglais.
- **`RequestRejection.reason`** est un code, par exemple `budget_total_out_of_range` ou
  `invalid_request_id`.

- **Les valeurs fournies par la personne** apparaissent dans la sortie : la destination,
  les identifiants de profil (jusqu'à 80 caractères, sans contrainte de contenu) et les
  noms de fournisseurs exclus. Les messages de `validate_request_draft` recopient aussi
  l'identifiant du profil (« profile … : departure_after is before reference date »).
- **Une erreur de pydantic** peut citer la valeur reçue, ou le nom d'une clé inconnue.

**Décision proposée (D-I3-9, révisée) :**

- **Le texte brut n'est jamais recopié.** Le résumé de la demande validée et le bloc
  `request` sont construits à partir des seuls champs validés de `TravelRequestDraft`.
- **La règle du plan (§1.2) s'applique à toute la sortie, sans exception,** valeurs
  fournies par la personne comprises (§7.2). La révision 1 exceptait ces valeurs ; cette
  exception est retirée.
- **Une valeur fournie par la personne n'est jamais réécrite (D-I3-17).** Avant tout
  affichage et avant la validation métier, la commande applique le même contrôle aux
  chaînes de la demande : `destination`, les `profile_id`, et `excluded_suppliers`, au
  niveau de la demande comme des profils.
  - Si l'une d'elles contient un mot interdit, la demande est invalide : code 3.
  - Le message nomme le champ, sans citer la valeur : « Le champ profiles[0].profile_id
    contient un terme qui ne peut pas figurer dans une proposition simulée. »
  - C'est une contrainte de présentation, qui découle de la règle du plan. Ce n'est pas
    une règle métier : elle ne touche ni P2 ni `validate_request_draft`.
- **En v1, les erreurs de validation sont affichées telles quelles,** sous l'en-tête
  « Demande invalide » et la mention « détail technique ». Le contrôle préalable garantit
  qu'elles ne contiennent pas de mot interdit.
- **Les erreurs de pydantic sont réduites à `chemin: type`,** sans la valeur reçue. Par
  exemple : `travellers: int_type`. Un segment de chemin qui n'est pas un nom de champ
  connu ni un indice est remplacé par `?`. Par exemple : `?: extra_forbidden`.

**Alternative :** remplacer les valeurs fournies par des libellés neutres (« profil 1 »…)
dans toute la sortie. Elle est écartée : la personne ne retrouverait plus ses propres
identifiants.

### B10. L'extracteur factice

**Constat :**

- Le seul extracteur du code produit est `OllamaStructuredRequestExtractor`.
- Les extracteurs factices (`StaticExtractor`…) sont dans les tests, et un sous-processus
  ne peut pas en recevoir un.
- Ollama n'est pas installé sur la machine de développement.

**Décision proposée (D-I3-10) :**

- **un extracteur de rejeu,** `ReplayStructuredRequestExtractor`, dans
  `infrastructure/llm/replay.py`, choisi par l'option `--extractor-replay FICHIER` ;
- **le fichier** contient une liste JSON de `TravelRequestDraft`. Le n-ième appel renvoie
  le n-ième élément, validé par `model_validate`. Au-delà de la liste, l'extracteur lève
  `ExtractorContractError` (code 1) ;
- **la provenance** indique `provider = "replay"` et `model = "replay-v1"`
  (D-I3-10, révisée en révision 3) :
  - `"replay-v1"` est la constante `REPLAY_FORMAT_VERSION` de `replay.py`. Elle désigne
    le format du fichier, et ne dépend pas de son contenu ;
  - **la révision 2 publiait le SHA-256 du fichier,** ce qui contredisait B11. Le fichier
    peut contenir plusieurs `TravelRequestDraft`, donc les données d'autres demandes,
    et une empreinte permet de vérifier une hypothèse sur ce contenu ;
- **aucun chemin de fichier n'apparaît dans les sorties,** ni pour `--extractor-replay`,
  ni pour `--draft-json`. Un chemin peut contenir un nom de personne, et il n'est pas
  soumis au contrôle de D-I3-17. Un message sur un fichier nomme l'option, pas le chemin.
  Par exemple : « Fichier de --draft-json introuvable ou illisible. » C'est une
  conséquence du point 1 de la revue, validée à la revue de la révision 3 (§17) ;
- **l'option est documentée** comme outil de test et de démonstration hors ligne. Elle
  n'est jamais utilisée par défaut ;
- le vrai chemin `--prompt` avec Ollama sera vérifié en I5.
- **Test de contrat : T-REPLAY** (§9.1).

### B11. Les offres du leader et les empreintes, dans un bloc (point nouveau)

**Constat :**

1. **Les offres du leader révèlent la somme des budgets.**
   - L'offre initiale du leader vaut 0,60 × `reservation_cents`
     (`initial_offer_fraction` dans `mandate_leader.py`).
   - `reservation_cents` est la somme des budgets des membres (`negotiation_request.py`).
   - Dans le journal d'un bloc, `initial_leader_total_cents` et les offres du leader
     dérivent donc de la somme des budgets.
   - La personne connaît son propre budget. Elle en déduit la somme des budgets des
     autres, et même le budget exact s'il n'y a qu'un autre membre.
   - **Vérifié sur E3,** en lecture seule. Le journal du bloc porte
     `initial_leader_total_cents = 339 600`, soit 0,60 × 566 000, la somme des budgets du
     bloc. Le budget de la personne étant de 400 000, la somme des trois autres vaut
     166 000.
2. **Les empreintes permettent de retrouver des données privées.**
   - `request_key`, `journal_sha256`, `formation_run_id` et `allocation_sha256` portent
     sur des contenus qui incluent les budgets des autres membres.
   - **`pool_sha256`** est l'empreinte du carnet, qui contient les budgets des autres
     demandes. La révision 1 l'avait gardé à tort.
   - **`oracle_configuration_id`** est l'empreinte d'un contenu qui inclut
     `seller_terms_sha256`, celle des conditions privées des vendeurs (`_configuration_id`
     dans `simulated_oracle.py`). C'est une « référence interne » au sens du §4.4 de la
     spécification.
   - **`catalog_sha256`** (révision 3) est le SHA-256 du fichier `catalog_v1.json` tout
     entier (`load_offer_catalog`, dans `json_catalog.py`). Or ce fichier contient les
     planchers des vendeurs : chaque palier porte `seller_floor_per_seat_cents`. Le
     chargeur en tire à la fois le catalogue public et `SellerTermsBook`, avec la même
     empreinte. `seller_terms_sha256` et `catalog_sha256` sont donc la même valeur. La
     révision 2 affirmait à tort que le fichier ne contenait aucun plancher.
   - **L'empreinte du fichier de rejeu** (révision 3) porte sur des brouillons qui peuvent
     être ceux d'autres demandes (B10).
   - Ces données prennent peu de valeurs : on peut les retrouver en essayant toutes les
     valeurs possibles et en comparant les empreintes.
3. **Les prix d'accord, eux, sont des prix du vendeur.**
   - Dans le protocole actuel, le leader accepte une proposition du vendeur. Dans E3, tous
     les accords, solo et de bloc, se font à un prix proposé par le vendeur.
   - Le budget d'un membre ne détermine que le moment où le leader accepte : le premier
     prix du vendeur qui ne dépasse pas son plafond.

**Décision proposée (D-I3-11, révisée) :**

- **Dans un journal de bloc,** la vue publique ne garde que le côté vendeur. Les montants
  du leader valent `null`.
- **Dans les journaux solo de la personne,** les deux côtés sont montrés. Ils ne dépendent
  que de son propre budget.
- **Aucune empreinte calculée sur des données privées n'entre dans la proposition,**
  qu'il s'agisse des données d'une autre demande, des conditions des vendeurs ou d'un
  fichier de rejeu. En pratique, depuis la révision 3, **la proposition ne contient plus
  aucune empreinte.** La provenance (§4.10) ne garde que :
  - des versions ;
  - la date de référence ;
  - la description de l'extraction, faite de constantes ou du nom du modèle.

  `pool_sha256`, `oracle_configuration_id` et `catalog_sha256` en sortent (D-I3-18).
  `pool_version` et `catalog_version` restent.
- **Des tests le prouvent** (§9.1) : T-CONF-1 à 3, à budget variable, et T-REPLAY, à
  fichier de rejeu variable.

**Limite, documentée et non masquée.** Les montants publics restent des conséquences de
la négociation : le coût du bloc, la somme des références, les paiements des autres
membres. Ils peuvent varier avec le budget d'un autre membre, par exemple si ce budget
change le tour où son leader solo accepte. La garantie porte donc sur trois points :

- aucun champ privé ;
- aucune empreinte de données privées ;
- aucun montant du leader de bloc.

Elle ne va pas jusqu'à empêcher toute inférence à partir des résultats publics. En v1, le
carnet est public et ce risque est nul. Il devra être réexaminé avant le mode session.

---

## 4. Contrat `trip-proposal-v1`

**Règles générales :**

- **Forme.** Des dataclasses gelées, dans `application/trip_proposal.py`. Les collections
  sont des tuples. Les clés du JSON sont les noms des champs.
- **Montants.** Ce sont des entiers en centimes, dont le nom finit par `_cents`. Les
  rationnels (φ, y, λ\*, τ) sont des chaînes `"p/q"`, la convention de l'empreinte d'I2
  (`_fraction`). Leur nom finit aussi par `_cents`.
- **Dates.** Chaînes ISO.
- **Absence.** Un champ facultatif vaut `null`.
- **Un seul point d'entrée pour la présentation.** Les afficheurs ne reçoivent qu'une
  `TripProposal`.

### 4.1 Racine

| Champ | Type | Source |
|---|---|---|
| `schema` | `"trip-proposal-v1"` | constante |
| `simulation` | `Simulation` | constantes du plan, §1.2 |
| `request` | `ValidatedRequest` | demande validée |
| `unit` | `UnitView` | `TravelUnit` |
| `status` | `UnitStatus` | §5 |
| `offers` | tuple de `OfferView` | `OfferQuote` et `PairAdmissibility` |
| `solo` | `SoloView` | `UnitReferenceCost` et journaux |
| `block` | `BlockView` ou `null` | `FormedBlock`, `BlockAllocation` et journal |
| `allocation` | `UnitAllocationView` ou `null` | ligne de l'unité dans `BlockAllocation` |
| `travellers` | tuple de `TravellerView` | `TravelerShare` |
| `explanations` | tuple de `Explanation` | §5 |
| `provenance` | `Provenance` | `TripPlan` et versions |

`block` et `allocation` ne valent pas `null` exactement quand l'unité fait partie d'un
bloc, qu'il compte une ou plusieurs unités.

### 4.2 `simulation`

| Champ | Type | Valeur |
|---|---|---|
| `synthetic_catalog` | bool | `true` |
| `simulated_sellers` | bool | `true` |
| `booking` | bool | `false` |
| `notice` | str | le texte exact du plan, §1.2 |

### 4.3 `request` et `unit`

| Champ | Type | Source |
|---|---|---|
| `request.request_id` | str | `"user"`, la valeur fixe de la CLI v1 (D-I3-16) |
| `request.draft` | objet | `TravelRequestDraft.model_dump(mode="json")` : la demande validée, telle quelle |
| `unit.unit_id` | str | `TravelUnit.unit_id` |
| `unit.seats` | int | `TravelUnit.seats` |
| `unit.budget_total_cents` | int | `TravelUnit.budget_total_cents` (le budget de la personne, dans sa propre proposition) |

### 4.4 `offers`

Une entrée par offre du catalogue, triée par `offer_id`.

| Champ | Type | Source |
|---|---|---|
| `offer_id`, `supplier_id`, `destination` | str | `OfferQuote` |
| `departure_date`, `arrival_date` | date | `OfferQuote` |
| `direct` | bool | `OfferQuote` |
| `capacity_seats` | int | `OfferQuote` |
| `tiers` | tuple de `{min_seats, list_per_seat_cents}` | `OfferQuote.tiers` (`PriceTier`) |
| `admissible` | bool | `PairAdmissibility` pour (unité, offre) |
| `violations` | tuple de `{rule, reason, profile_id}` | `AdmissibilityViolation`, dans l'ordre `RULE_ORDER` |
| `notes` | tuple de `{code, profile_id}` | `AdmissibilityNote` |

### 4.5 `solo`

| Champ | Type | Source |
|---|---|---|
| `status` | `"referenced"`, `"no_admissible_offer"` ou `"no_solo_reference"` | `UnitReferenceCost.status` |
| `offer_id`, `agreed_total_cents`, `turns` | str, int, int, ou `null` | `UnitReferenceCost` |
| `attempts` | tuple de `{offer_id, status, agreed_total_cents, turns, journal}` | `ReferenceAttempt`, et le journal retrouvé par sa clé |

La `request_key` sert à retrouver le journal, mais elle n'est pas exposée (B11).

**`JournalView`**, la vue publique d'un `NegotiationJournal` :

| Champ | Type | Source |
|---|---|---|
| `offer_id`, `quantity_seats` | str, int | journal |
| `price_tier_min_seats` | int | `selected_price_tier_min_seats` |
| `catalog_total_cents` | int | `initial_seller_total_cents`, le prix catalogue au palier |
| `leader_initial_total_cents` | int ou `null` | `initial_leader_total_cents` ; `null` pour un bloc (B11) |
| `messages` | tuple de `{index, actor, type, total_cents}` | `NegotiationEvent` : `call_index`, `actor`, `outgoing_type`, `outgoing_total_cents` ; `total_cents` vaut `null` quand `actor = "leader"` dans un journal de bloc |
| `status`, `terminal_reason` | littéraux | journal |
| `turns` | int | `router_iterations` |
| `agreed_total_cents` | int ou `null` | journal |

### 4.6 `block`

| Champ | Type | Source |
|---|---|---|
| `offer_id`, `seats` | str, int | `FormedBlock` |
| `price_tier_min_seats` | int | journal de l'accord du bloc |
| `catalog_total_cents` | int | `initial_seller_total_cents` de ce journal : le prix catalogue au palier groupé |
| `reference_total_cents` | int | `FormedBlock.reference_total_cents` |
| `cost_cents` | int | `FormedBlock.cost_cents`, le prix négocié (simulation) |
| `value_cents` | int | `FormedBlock.value_cents` = v(C), la valeur créée |
| `members` | tuple de `{label, you, seats, payment_cents}` | `BlockAllocation.payments_cents` et `TravelUnit.seats` (B8) |
| `negotiation` | `JournalView` ou `null` | pour un bloc d'au moins 2 unités : l'essai `agreement` de `CoalitionCost` pour l'offre retenue ; pour une unité seule : `null`, car son journal est dans `solo` |

### 4.7 `allocation` et `travellers`

`allocation` est la ligne de l'unité au premier plan dans `BlockAllocation`.

| Champ | Type | Source |
|---|---|---|
| `reference_cents` | int | `references_cents` |
| `phi_cents` | `"p/q"` | `phi` : la contribution |
| `y_cents` | `"p/q"` | `y`, l'économie après projection |
| `saving_cents` | int | `y_rounded`, l'économie arrondie de l'unité |
| `payment_cents` | int | `payments_cents` : le paiement |
| `projection_active` | bool | `projection_active`, au niveau du bloc |
| `unit_saturated` | bool | l'unité figure dans `saturated_unit_ids` |
| `lambda_star_cents` | `"p/q"` | `lambda_star` |
| `unit_tau_cents` | `"p/q"` | `TravelerShare.unit_tau`, le même pour toute l'unité |

`travellers` contient les parts de l'unité au premier plan, triées par
(`profile_id`, `seat_rank`). Chaque part reprend `profile_id`, `seat_rank`, `budget_cents`,
`amount_cents` et `profile_saturated` de `TravelerShare`.

**La décomposition des économies (D-I3-12)** se limite à des montants typés :

- v(C) = Σ références − c(C), soit les trois champs `reference_total_cents`, `cost_cents`
  et `value_cents` ;
- la contribution `phi_cents` ;
- l'économie de l'unité `saving_cents` ;
- le paiement `payment_cents`.

On ne sépare pas un « effet palier » d'un « effet négociation » : ce serait une logique
nouvelle. Le texte distingue ainsi la valeur créée, la contribution et le paiement
(spécification, §4.3).

### 4.8 `status`

| Champ | Type |
|---|---|
| `code` | l'un des 7 statuts d'unité (§5.1) |
| `modifiers` | tuple de 0 à 2 codes (§5.2) |

### 4.9 `explanations`

| Champ | Type |
|---|---|
| `code` | l'un des 13 codes |
| `level` | `"status"`, `"modifier"` ou `"offer"` |
| `params` | objet aux clés fermées, propres à chaque code (§5.4) |

Le message français n'est pas dans le DTO. Les afficheurs le produisent avec
`explanations_fr` : le JSON contient `code`, `level`, `params` et `message`.

### 4.10 `provenance`

| Champ | Source |
|---|---|
| `reference_date` | `TripPlan.reference_date` |
| `catalog_version` | `TripPlan`. La version seule : le fichier du catalogue contient les planchers des vendeurs (B11, révision 3) |
| `pool_version` | `TripPlan`. La version seule : le carnet contient les budgets des autres demandes |
| `planning_version` | `PLANNING_VERSION` (`3h-planning-v1`) |
| `formation_adapter_version`, `formation_method` | `FORMATION_ADAPTER_VERSION` et `FormationResult.method` |
| `allocation_version`, `theta_cents` | `ALLOCATION_VERSION` (`p5-allocation-v1`) et `THETA_CENTS` |
| `extraction` | `ExtractionProvenance` : `{source, provider, model}`, sous l'une des trois formes du tableau ci-dessous |

**`extraction` : trois formes, et aucune autre (révision 3).** Le constructeur de
`ExtractionProvenance` refuse toute autre combinaison.

| `source` | `provider` | `model` | Option |
|---|---|---|---|
| `"draft-json"` | `null` | `null` | `--draft-json` |
| `"llm"` | `"ollama"` (`provider_name` de l'extracteur) | le nom du modèle configuré (`OllamaStructuredRequestExtractor.model`), un paramètre public | `--prompt` ou saisie interactive |
| `"replay"` | `"replay"` | `"replay-v1"` (`REPLAY_FORMAT_VERSION`), une constante | `--prompt` ou saisie, avec `--extractor-replay` |

`understand_request` lit déjà `provider_name` et `model` sur l'extracteur. L'extracteur
de rejeu expose donc ces deux attributs avec ces valeurs.

**Exclus de la provenance :**

- **les durées et la latence,** pour que la sortie soit identique octet pour octet (§7) ;
- **les chemins des fichiers d'entrée** (B10) ;
- **toute empreinte** (B11). Toutes celles du dépôt portent sur des données privées :
  - sur les données des autres demandes : `pool_sha256`, `formation_run_id`,
    `allocation_sha256`, `result_sha256`, `request_key`, `run_id` et `journal_sha256` ;
  - sur les conditions des vendeurs : `catalog_sha256`, qui égale `seller_terms_sha256`,
    et `oracle_configuration_id`, qui l'inclut ;
  - sur un fichier de rejeu : son SHA-256.

Ces identifiants restent dans `TripPlan`, interne, pour les audits et les rapports.

---

## 5. Statuts et codes

### 5.1 Statut de l'unité : exactement un

Le statut est déterminé dans cet ordre. Le constructeur lève `ProposalConsistencyError`
si aucune ou plusieurs règles s'appliquent.

| Ordre | Condition, sur des champs typés | `status.code` |
|---|---|---|
| 1 | l'unité est dans `AllocationResult.unallocated` | sa `reason` : `no_admissible_offer`, `no_solo_reference`, `component_too_large` ou `capacity_model_violated` |
| 2 | l'unité est dans un bloc d'au moins 2 unités | `served_in_coalition` |
| 3 | l'unité est seule dans son bloc, et aucune coalition **évaluée par P4** qui la contient, d'au moins 2 unités, n'a abouti à un accord avec v(C) > 0 | `alone_no_beneficial_coalition` |
| 4 | l'unité est seule dans son bloc, et au moins une telle coalition évaluée existe | `alone_social_optimum` |

**Ce que veut dire « évaluée par P4 ».** Une coalition est évaluée si elle figure dans
`FormationResult.evaluations`, c'est-à-dire parmi les candidates de
`enumerate_candidates`.

- **Les candidates sont toutes les coalitions de la composante qui partagent au moins une
  offre admissible commune.** L'énumération est exhaustive, puisqu'une composante traitée
  compte au plus 14 unités et que son voisinage d'offres est borné de même.
- **Chaque candidate est négociée** sur chacune de ses offres communes. Elle est
  réalisable si au moins une négociation aboutit (`cost_cents` non nul).
- **Une coalition sans offre commune n'est pas évaluée :** dans ce modèle, ses membres ne
  peuvent pas voyager ensemble.
- **Les statuts 3 et 4 ne parlent donc que des coalitions évaluées.** Ils ne disent rien
  des coalitions imaginables mais non évaluées, et les messages ne le prétendent pas.

**Le code de sortie est 0 pour toute proposition produite, quel que soit ce statut
(D-I3-15).** Une proposition qui explique l'absence d'offre reste une réponse valide : la
demande n'était pas invalide.

### 5.2 Modificateurs : 0, 1 ou 2

| Code | Condition | `params` |
|---|---|---|
| `projection_active` | le bloc compte au moins 2 unités et `projection_active` est vrai. La projection déplace les parts de tous les membres d'un même λ\*, d'où le code pour chacun | `unit_saturated`, `lambda_star_cents` |
| `budget_cap_active` | au moins une part de l'unité a `profile_saturated` | `saturated_profile_ids`, `unit_tau_cents` |

### 5.3 Annotations d'offre

| Code | Condition | `params` |
|---|---|---|
| `offer_rejected` | une par couple (unité, offre) non admissible | `offer_id`, `violations` |
| `direct_preference_not_met` | une note `direct_preference_not_met` porte sur l'offre du bloc de l'unité | `offer_id`, `profile_ids`, `retained_list_total_cents`, `best_direct` (`{offer_id, list_total_cents}` ou `null`) |

**Pour `direct_preference_not_met` (D-I3-14) :**

- le code ne porte que sur l'offre **retenue**. Les notes des autres offres restent
  visibles dans `offers[].notes` ;
- les deux prix catalogue sont lus par `OfferQuote.list_total(seats)`, une fonction
  existante, pour le même nombre de places, celui du bloc ;
- `best_direct` est l'offre directe admissible la moins chère pour l'unité, ou `null` ;
- aucun écart n'est calculé, conformément à ID-7 (l'information seule, en v1).

### 5.4 Les deux explications de P4

**`alone_no_beneficial_coalition`,** avec un décompte par cause. Les `params` sont :

- `component_units` : le nombre d'unités de la composante ;
- `singleton_component` : vrai si `ComponentFormation.status` vaut `singleton_component` ;
- `evaluated` : les coalitions de `FormationResult.evaluations` qui contiennent l'unité et
  comptent au moins 2 unités ;
- `without_agreement` : celles dont `cost_cents` vaut `null` ;
- `without_saving` : celles qui sont réalisables mais dont v(C) ≤ 0.

**Gabarit du message,** au sens près : « Parmi les {evaluated} coalitions évaluées par P4
qui vous incluaient (toutes celles qui partageaient une offre admissible avec vous),
{without_agreement} n'ont abouti à aucun accord et {without_saving} n'ont dégagé aucune
économie. Vous voyagez seul, au prix négocié de votre référence. »

- **Si `evaluated` vaut 0,** le message dit qu'aucune autre demande ne partageait d'offre
  admissible avec la vôtre.
- **Le message ne parle jamais** de « toutes les coalitions possibles ».

**`alone_social_optimum`.** On calcule `cover = game.cover_values()` une seule fois (B6).
Pour chaque C **évaluée par P4** qui contient l'unité, compte au moins 2 unités et vérifie
v(C) > 0 :

- total(C) = v(C) + cover\[composante \ C\] ;
- écart(C) = V\* − total(C), où V\* = cover\[composante\].

Les **trois** coalitions de plus grand total sont retenues, à égalité dans l'ordre canonique
des coalitions. Chacune est publiée **sans ses membres**, sous la forme
`{size, offer_id, value_cents, best_total_cents, gap_cents}`. S'y ajoute
`component_value_cents`, qui vaut V\*.

**Invariants, contrôlés à chaque exécution :**

- V\* égale `ComponentSolution.value_cents` ;
- chaque écart est positif ou nul.

**Ce que le statut décrit.** Il décrit deux choses :

- **la structure optimale retenue :** sa valeur totale V\*, et le fait que l'unité y voyage
  seule, au prix de sa référence ;
- **les alternatives évaluées :** au plus trois, avec leur écart.

Il ne prétend **pas** que rester seul est meilleur, que ce soit pour l'unité, pour les
autres demandes ou en soi. P4 maximise la valeur totale de la composante ; ce critère
collectif peut laisser une unité seule alors qu'une coalition à valeur positive l'incluait.
La spécification, au §5.1, demande de le dire.

**Gabarit du message,** au sens près : « La répartition retenue maximise la valeur totale
du groupe de demandes ({component_value_cents}). Elle ne vous inclut dans aucune
coalition : vous voyagez seul, au prix négocié de votre référence. Parmi les coalitions
évaluées qui vous incluaient, voici les meilleures, avec la valeur totale qu'elles
auraient permise et l'écart avec la répartition retenue. Ce résultat découle de
l'objectif collectif ; il ne signifie pas qu'une coalition vous aurait été défavorable. »

**Un écart nul signifie une égalité de valeur.** Le message dit alors que cette
alternative donnait la même valeur totale, et que la structure retenue a été choisie par
la règle de départage documentée de P4. Il ne dit ni « meilleure » ni « plus
avantageuse ».

**Les mots « meilleur », « optimal » et « avantageux » ne sont jamais appliqués à la
situation de l'unité.** Ils ne qualifient que la valeur totale de la composante. Un test
le vérifie sur le gabarit.

### 5.5 Codes de niveau demande

Ces codes ne figurent jamais dans une `TripProposal`.

| Code | Émis par | Code de sortie |
|---|---|---|
| `needs_clarification` | `RequestUnderstandingResult` (`missing_fields`), ou `RequestRejection` dont le statut vaut `needs_clarification` | 2 |
| `unknown_place` | le référentiel des lieux, en I4 (D-I3-1) | 2, à partir d'I4 |

**Une demande invalide n'a pas de code d'explication,** et la liste fermée reste à 13
codes. Le statut `invalid` et ses erreurs sont présentés selon D-I3-9.

---

## 6. `plan_travel_request` et la CLI

### 6.1 La fonction

```python
def plan_travel_request(
    request: TravelRequestDraft,      # demande déjà validée par la personne
    *,
    market: NegotiationMarket,
    pool: DemandPoolSnapshot,
    reference_date: date,
    extraction: ExtractionProvenance,
    request_id: str = "user",
    limits: FormationLimits = DEFAULT_LIMITS,
) -> TravelPlanningResult: ...

@dataclass(frozen=True)
class TravelPlanningResult:
    plan: TripPlan                      # interne
    proposal: TripProposal | None       # None exactement quand plan.status == "request_rejected"
```

**Ce qu'elle fait.** Elle construit
`PlanningInput((PlanningRequest(request_id, request),), pool, reference_date, limits)`,
appelle `plan_lot`, puis `build_trip_proposal` si le plan est `planned`.

**Pourquoi cette forme :**

- **Elle reçoit une demande déjà validée.** La compréhension et la clarification restent
  dans la CLI, avec les fonctions existantes. La confirmation (ID-10) peut ainsi se placer
  entre la compréhension et la négociation.
- **Elle est synchrone,** puisque `plan_lot` l'est.
- **Elle n'ajoute aucun statut :** les statuts restent ceux de
  `RequestUnderstandingResult` et de `TripPlan` (point 3 du §14).

### 6.2 Déroulement de la commande

1. **Lecture des options.** En cas d'erreur, code 64.
2. **Date de référence :** l'option `--reference-date`, sinon `date.today()` (D-I3-2).
3. **Ouverture du marché v1** (`open_simulated_market`) et **chargement du carnet v1**
   (`load_demand_pool`).
4. **Obtention de la demande :**
   - **avec `--draft-json FICHIER` :**
     - lecture par `TravelRequestDraft.model_validate_json` ; un JSON malformé ou un
       écart de schéma donne le code 3 ;
     - puis `validate_request_draft` : `ready` permet de continuer, `invalid` donne le
       code 3 ;
     - `needs_clarification` donne directement le code 2, avec la liste des champs : il
       n'y a pas de dialogue, faute de LLM pour intégrer les réponses ;
   - **avec `--prompt TEXTE` ou la saisie interactive :**
     - en saisie interactive, la commande demande « Décrivez votre demande de voyage » sur
       la sortie d'erreur, puis lit une ligne ;
     - la demande passe par `understand_request` ;
     - **tant que** le statut est `needs_clarification`, avec au plus 3 tours : la question
       tirée des `missing_fields` est affichée, la réponse lue, le texte devient
       `texte + "\n" + réponse`, puis la compréhension est relancée. Une fin d'entrée
       pendant un tour donne le code 2 ;
     - **après 3 tours** encore incomplets, code 2 ; si la demande est `invalid`, code 3.
   - **Pour toute demande obtenue,** par l'une ou l'autre voie et avant tout affichage
     qui en dérive, le contrôle des mots interdits porte sur les chaînes fournies par la
     personne (D-I3-17). En cas de mot interdit, la demande est `invalid` : code 3.
5. **Résumé de la demande validée,** sur la sortie d'erreur, construit à partir des seuls
   champs (B9).
6. **Confirmation,** sauf avec `--yes` (B4). Un refus donne le code 4.
7. **`plan_travel_request`.** Un plan `request_rejected` donne le code 3, ou le code 2 si
   le rejet porte le statut `needs_clarification`.
8. **Affichage** de la proposition, en texte ou en JSON, sur la sortie standard. Code 0.

**Les deux sorties :**

- **la sortie standard** ne reçoit que le document final : la proposition, ou, avec
  `--json`, le document de statut du §6.4 ;
- **la sortie d'erreur** reçoit les questions, le résumé, la demande de validation et les
  messages.

Le simulateur P3 capture la sortie standard pendant les négociations : la commande
n'écrit rien pendant `plan_travel_request`. Un test vérifie que la sortie standard de
`--json` est un document JSON valide, et rien d'autre.

### 6.3 Codes de sortie

| Code | Signification |
|---:|---|
| 0 | proposition produite, quel que soit le statut de l'unité (D-I3-15) |
| 1 | erreur technique |
| 2 | clarification requise |
| 3 | demande invalide |
| 4 | demande non validée : refus, réponse vide ou fin d'entrée (D-I3-4) |
| 64 | usage incorrect de la commande (D-I3-3) |
| 130 | interruption (Ctrl-C) |

**Propagation des erreurs (point 7 du §14) :**

| Origine | Erreur | Code |
|---|---|---|
| `--draft-json` | JSON malformé, `ValidationError` de pydantic | 3 |
| compréhension | statut `invalid` | 3 |
| extraction | `RequestInputError` (texte vide ou trop long) : la demande est en cause, pas le système | 3 |
| extraction | `StructuredOutputError`, `ExtractorContractError`, `RequestProviderError` | 1 |
| `plan_lot` | plan `request_rejected` | 3, ou 2 selon le statut du rejet |
| données | `DemandPoolError`, `PoolRequestError`, `PlanningInputError`, `OSError` | 1 |
| moteur | `NegotiationOracleError`, `AgentExecutionError`, `JournalConsistencyError`, `NonDeterministicJournalError`, `PlanConsistencyError`, `FormationConsistencyError`, `AllocationPreconditionError`, `AllocationConsistencyError`, `ProposalConsistencyError` | 1 |
| autre | toute autre exception | 1 |
| interruption | `KeyboardInterrupt` | 130 |

Pour les codes 1, le message sur la sortie d'erreur donne le nom de la classe et le
message, sans trace de pile.

**Sans chemin de fichier (révision 3, B10).** Certains messages d'erreur contiennent un
chemin : celui d'une `OSError`, ou celui que `CatalogValidationError` place en tête.
Avant l'affichage, la commande remplace chaque chemin qu'elle a elle-même ouvert :

- un fichier d'entrée devient le nom de son option (`--draft-json`, `--extractor-replay`) ;
- un fichier versionné devient son nom de base (`catalog_v1.json`, `demand_pool_v1.jsonl`).

### 6.4 `--json` quand il n'y a pas de proposition (D-I3-13, schéma fermé)

**Quand ce document est produit.** Avec `--json`, pour les codes 2, 3 et 4, la sortie
standard reçoit un document `trip-request-status-v1`. Pour les codes 1, 64 et 130, elle
reste vide.

**Champs communs aux quatre statuts :**

| Champ | Type | Valeurs |
|---|---|---|
| `schema` | str | `"trip-request-status-v1"` |
| `status` | str | `needs_clarification`, `invalid`, `request_rejected` ou `not_validated` |
| `source` | str | `draft-json`, `llm` ou `replay` |
| `reference_date` | date ISO | la date utilisée |

**Champs propres à chaque statut.** L'ensemble des clés est **exactement** celui-ci :
aucune clé en plus, aucune en moins, et aucun `null`.

| `status` | Code | Champs propres | Domaine des valeurs |
|---|---|---|---|
| `needs_clarification` | 2 | `missing_fields`, `rounds` | `missing_fields` : liste non vide, sous-ensemble de `REQUIRED_FIELDS` (`destination`, `travellers`, `budget_per_person`), dans cet ordre. `rounds` : entier de 0 à 3, le nombre de tours de clarification effectués (toujours 0 avec `--draft-json`) |
| `invalid` | 3 | `errors` | liste non vide ; chaque chaîne a l'une des formes du domaine **E** ci-dessous |
| `request_rejected` | 3, ou 2 | `reason`, `rejection_status`, `missing_fields`, `errors` | une des cinq combinaisons du tableau « Domaine de `request_rejected` » ci-dessous, et aucune autre |
| `not_validated` | 4 | `reason` | `refused` (réponse autre que « o » ou « oui »), `empty_answer` (ligne vide) ou `end_of_input` (fin de l'entrée) |

**Domaine E : les chaînes d'erreur permises (révision 3).** Chaque chaîne doit avoir
exactement l'une des formes suivantes. Les formes sont disjointes, et le validateur les
contrôle par des expressions régulières ancrées.

| Forme | Chaîne exacte ou motif | Origine dans le dépôt |
|---|---|---|
| E1 | `departure_after must not be before the reference date` | `validate_request_draft` |
| E2 | `arrival_before must not be before the reference date` | `validate_request_draft` |
| E3 | `departure_after must not be after arrival_before` | `validate_request_draft` |
| E4 | `profile <id>: departure_after is before reference date` | `validate_request_draft` |
| E5 | `profile <id>: arrival_before is before reference date` | `validate_request_draft` |
| E6 | `request text must not be blank` | `understand_request`, et `RequestInputError` de l'extracteur |
| E7 | `request text exceeds <n> characters`, où `<n>` est un entier positif | `RequestInputError` de l'extracteur |
| E8 | `<chemin>: <type>`, où `<type>` suit `[a-z][a-z0-9_]*` | une erreur de pydantic, réduite (B9) |
| E9 | `forbidden_term: <chemin>` | le contrôle de D-I3-17 |

- **`<id>`** est un `profile_id` : de 1 à 80 caractères, sans saut de ligne. C'est une
  valeur fournie par la personne, qui a déjà passé le contrôle de D-I3-17.
- **`<chemin>`** vaut `$` pour la racine. Sinon, c'est une suite de segments séparés par
  des points. Un segment est un nom de champ de `TravelRequestDraft` ou de
  `TravelerProfileDraft`, suivi d'éventuels indices `[k]`, ou bien `?` pour un nom
  inconnu. Exemples : `travellers`, `profiles[0].profile_id`, `?`, `$`.
- **Aucune autre chaîne n'est permise.** En particulier, ni une valeur reçue par pydantic,
  ni un message libre.

Les messages E1 à E5 sont les cinq seuls que produit `validate_request_draft`. E6 et E7
sont les seuls messages de saisie : celui du statut `invalid` de `understand_request`, et
ceux de `RequestInputError` dans `ollama.py`. L'extracteur de rejeu n'en ajoute aucun.

**Domaine de `request_rejected` (révision 3).** Dans le dépôt, un plan n'est
`request_rejected` que si `build_travel_unit` lève `TravelUnitError`. Je les ai toutes
relevées dans `travel_units.py`. Chaque document doit correspondre exactement à l'une
des lignes ci-dessous.

| `reason` | `rejection_status` | `missing_fields` | `errors` | Code | Atteignable depuis la CLI | Message (texte) |
|---|---|---|---|---:|---|---|
| `request_not_ready` | `needs_clarification` | non vide, sous-ensemble ordonné de `REQUIRED_FIELDS` | `[]` | 2 | non : la CLI valide la demande, à la même date, avant `plan_travel_request` | celui de `needs_clarification` |
| `request_not_ready` | `invalid` | `[]` | non vide, formes E1 à E5 seulement | 3 | non, pour la même raison | celui de `invalid` |
| `budget_below_one_cent` | `other` | `[]` | `[]` | 3 | **oui** : par exemple `budget_per_person = "0.001"` | « Le budget par personne est inférieur à un centime. » |
| `budget_out_of_range` | `other` | `[]` | `[]` | 3 | **oui** : par exemple `"2000000000"` | « Le budget par personne dépasse le montant maximal pris en charge (1 000 000 000 €). » |
| `budget_total_out_of_range` | `other` | `[]` | `[]` | 3 | **oui** : par exemple 20 voyageurs à `"600000000"` | « Le budget total de la demande dépasse le montant maximal pris en charge (1 000 000 000 €). » |

- **`rejection_status`** vaut `other` exactement quand `RequestRejection.status` vaut
  `None`. Le code de sortie vaut 2 exactement quand il vaut `needs_clarification`.
- **Les trois motifs de budget sont atteignables par `--draft-json`.** La validation
  métier ne borne pas le budget, et `build_travel_unit` le convertit en centimes après
  elle. C'est vérifié sur le code actuel, par un script en lecture seule hors du dépôt :
  pour les trois exemples, `validate_request_draft` répond `ready` et `plan_lot` rejette
  la demande avec le motif attendu. La révision 2 affirmait le contraire (§16).
- **`invalid_request_id` est exclu du domaine.** `build_travel_unit` peut le produire,
  mais pas par `plan_lot` : `PlanningRequest` refuse d'abord un identifiant vide ou non
  épuré, avec `PlanningInputError` (code 1). C'est aussi vérifié. De plus, la CLI fixe
  l'identifiant à `"user"`.
- **Le profil en cause n'est jamais publié.** `TravelUnitError` porte un `profile_id`
  pour les deux premiers motifs de budget, mais `RequestRejection` ne le reprend pas.
- **Le montant maximal** est `MAX_CENTS`, soit 10¹¹ centimes (`domain/money.py`).

**Règles communes :**

- même sérialisation canonique que la proposition (§7.1) ;
- même contrôle du vocabulaire (§7.2) ;
- **un validateur de schéma fermé** dans `json_renderer.py` contrôle, avant l'écriture :
  - les clés de chaque statut ;
  - **les valeurs (révision 3) :** chaque valeur dans son domaine, chaque chaîne d'erreur
    dans le domaine E, et chaque document de `request_rejected` sur une ligne de son
    tableau ;
  - le code de sortie associé.

  Un document refusé est un défaut du système : la commande sort avec le code 1, et la
  sortie standard reste vide.

**Exemple :**

```json
{
  "missing_fields": [
    "budget_per_person"
  ],
  "reference_date": "2026-11-19",
  "rounds": 3,
  "schema": "trip-request-status-v1",
  "source": "replay",
  "status": "needs_clarification"
}
```

---

## 7. JSON canonique et vocabulaire

### 7.1 Sérialisation (point 5 du §14)

- **Format.** `json.dumps(document, sort_keys=True, ensure_ascii=False, indent=2)`, suivi
  d'un saut de ligne final, en UTF-8.
- **`ensure_ascii=False` est obligatoire.** Avec des échappements, « émis » deviendrait
  `émis` et échapperait au contrôle du vocabulaire.
- **Ordre des collections :**
  - `offers` par `offer_id` ;
  - `violations` dans `RULE_ORDER` ;
  - `notes` par (`code`, `profile_id`) ;
  - `attempts` par `offer_id` ;
  - `messages` par `index` ;
  - `members` : la personne d'abord, puis les autres demandes dans l'ordre croissant des
    `unit_id` ;
  - `travellers` par (`profile_id`, `seat_rank`) ;
  - `explanations` par niveau (statut, puis modificateurs, puis offres), puis par code,
    puis par `offer_id` ;
  - `request.draft.profiles` dans l'ordre fourni.
- **Aucune durée.** La sortie est donc identique octet pour octet, sans exception. C'est
  plus strict que la spécification, et cela simplifie I3-A6.
- **Portée du déterminisme.** À demande validée, date et artefacts identiques, la sortie
  est identique. Avec `--prompt` et un vrai LLM, l'extraction peut varier ; le
  déterminisme vaut à partir de la demande validée.
- **La sortie texte suit les mêmes règles :** même ordre, et aucun horodatage autre que la
  date de référence.

### 7.2 Contrôle du vocabulaire

C'est la règle normative du plan, §1.2, appliquée sans exception : mise en NFC, puis
`casefold`, puis découpage par `re.findall(r"\w+", texte)`, qui suit les frontières de
mots Unicode, puis comparaison des mots entiers à la liste interdite.

**Textes contrôlés, en entier :**

- la sortie texte ;
- le JSON brut, qu'il s'agisse d'une proposition ou d'un document de statut ;
- tous les messages de la commande sur la sortie d'erreur.

**Aucune partie n'en est exceptée,** pas même les valeurs fournies par la personne. Ces
valeurs ne sont pas réécrites : une demande qui en contient une avec un mot interdit est
refusée avant tout affichage (D-I3-17, §6.2). Le contrôle ne peut donc échouer que sur un
texte du système, et ce serait un défaut.

**Données du système affichées.** Les chaînes du catalogue v1 (offres, fournisseurs,
destinations) sont soumises au même contrôle, par un test sur le fichier.

**Le test vérifie les deux faces de la règle :**

- chaque mot interdit est refusé, avec ses formes en majuscules et en NFD ;
- l'avertissement exact, ainsi que « réservation », « émission » et « confirmation »,
  passent ;
- une demande dont un `profile_id`, la `destination` ou un fournisseur exclu contient un
  mot interdit donne le code 3, et la valeur n'apparaît dans aucune sortie (§9.1, T-LEX).

---

## 8. Réponses aux sept points du §14 de la spécification

| Point | Réponse |
|---|---|
| 1. Noms et types des champs de `TripProposal` | §4, champ par champ, avec la source de chacun |
| 2. Format de `--draft-json` | exactement le JSON de `TravelRequestDraft` (`extra="forbid"`) : `destination`, `travellers`, `budget_per_person` (décimal sous forme de chaîne), `currency`, `departure_after`, `arrival_before`, `direct_flight` (`required`, `preferred` ou `any`), `excluded_suppliers` et `profiles`. C'est le format des brouillons de `demand_pool_v1.jsonl`. Il n'y a pas de second système de validation (§6.2) |
| 3. Réponse de `plan_travel_request` | `TravelPlanningResult(plan, proposal)`, sans nouveau statut (§6.1) |
| 4. Annulation de la confirmation | code 4 ; une fin d'entrée ou une réponse vide est un refus ; 130 pour une interruption (B4) |
| 5. Tri dans le JSON canonique | §7.1 |
| 6. Seuil pour `alone_social_optimum` | aucun seuil nouveau : la limite de 14 unités suffit, avec un coût mesuré de 0,34 s au pire (B6) |
| 7. Propagation des erreurs | §6.3 |

---

## 9. Critères d'acceptation : précisions

Les critères I3-A1 à I3-A16 de la spécification sont repris. Voici leurs précisions, et
les critères ajoutés (I3-A17 à I3-A20).

| ID | Précision |
|---|---|
| I3-A1 | **Les neuf éléments du §1.3** sont vérifiés : (1) `offers` ; (2) `block.members` ; (3) `solo.attempts` et `block.negotiation` ; (4) `block.offer_id` ; (5) `block.catalog_total_cents` et `block.cost_cents` ; (6) `block.value_cents` ; (7) `travellers[].amount_cents` ; (8) `offers[].violations` et `explanations` ; (9) `alone_*` et ses `params`. **Deux lots :** le lot figé (deux demandes au premier plan, `a` et `e`), testé au niveau du constructeur et des afficheurs, car la CLI v1 ne fournit qu'une demande ; et E3 de bout en bout, par sous-processus, avec `--draft-json` et `--reference-date 2026-11-19`. Les montants d'E3 doivent égaler ceux d'I2 : paiement de la personne 380 100 centimes, soit 4 × 47 513 + 4 × 47 512 |
| I3-A2 | Exactement un `status.code` parmi les 7 du §5.1. Le constructeur lève une erreur sinon |
| I3-A3 | Chaque montant vient d'un champ typé du §4. **Trois dérivations seulement sont permises :** `CoalitionGame.cover_values` ; l'écart V\* − total(C) ; `OfferQuote.list_total`. Un test relie chaque montant à son champ source |
| I3-A4 | Un test par code. Le code est produit par le vrai pipeline quand le catalogue v1 et le carnet le permettent, sinon par une formation construite, comme E2 et E6 en I2. `unknown_place` est testé au niveau des explications (D-I3-1). Le rapport dira, code par code, quelle voie est utilisée |
| I3-A6 | Sortie identique octet pour octet, sans exception (§7.1) |
| I3-A7 | Schéma fermé : la liste des clés est fixe. Aucune clé ne contient « floor » (la règle de `formation_report`). Aucun objet `SellerTerms` n'est accessible. Les montants du leader valent `null` dans un journal de bloc. La proposition ne porte aucune empreinte (B11, révision 3), et `extraction` a l'une des trois formes du §4.10. Les contre-offres du vendeur restent visibles (B7). **Prouvé par T-CONF-1 à 3 et T-REPLAY** (§9.1) |
| I3-A8 | Les autres membres n'apparaissent que sous la forme « autre demande k », avec leurs places et leur paiement (B8). **Prouvé par T-CONF-2 (e)** (révision 4), et couvert aussi par T-CONF-1 |
| I3-A10 | Le contrôle du §7.2 porte sur le texte, le JSON et les messages de la commande, sans exception. **Prouvé par T-LEX** |
| I3-A11 | **Scénarios par sous-processus :** `--draft-json` ; `--prompt` avec `--extractor-replay` ; saisie interactive ; clarification par une entrée scriptée ; la limite de 3 tours ; validation acceptée, refusée, réponse vide et fin d'entrée ; `--yes` ; texte ; `--json` ; date de référence ; codes 0, 1, 2, 3, 4 et 64 ; **interruption : code 130 et sortie standard vide (T-SIGINT)** |
| I3-A12 | La clarification s'arrête après 3 tours. Une quatrième réponse fournie sur l'entrée n'est jamais lue : le test le vérifie par le nombre de lignes consommées |
| I3-A13 | Aucune négociation avant la validation. Un refus (code 4) ou une interruption (code 130) laisse le compteur d'appels de la session à 0, ce que vérifie un test au niveau de la fonction |
| I3-A14 | Les codes de sortie du §6.3 |
| I3-A15 | Les tests de `process_travel_request` ne changent pas et passent. Le diff de `travel_workflow.py` ne contient que des ajouts |
| I3-A16 | **Option A, comme en I2 :** un manifeste SHA-256 de la base au démarrage d'I3. Les seuls écarts attendus sont `travel_workflow.py` et `pyproject.toml`, plus les fichiers nouveaux. Aucun fichier de P2 à P5 ne change |
| I3-A17 (ajouté) | Python 3.10 pour les nouveaux modules, ruff propre, `git diff --check` propre, golden master vert, suite complète verte avec deux graines |
| I3-A18 (ajouté) | Le rapport d'I3 donne, pour chaque sous-étape, les commandes, la version de Python et les graines. Il distingue ce que j'ai exécuté de ce qui est seulement déclaré |
| I3-A19 (ajouté) | Les documents `trip-request-status-v1` respectent exactement le schéma fermé du §6.4, pour chacun des quatre statuts : les clés, et, depuis la révision 3, les valeurs (domaine E, tableau de `request_rejected`). **Prouvé par T-STATUS,** avec des cas positifs et des cas négatifs |
| I3-A20 (ajouté) | Les mutants du §9.2 sont tous tués |

### 9.1 Règles des tests nouveaux

**T-CONF : confidentialité, en faisant varier le seul budget d'un autre membre.**

- **Scénario.** E3, avec `--reference-date 2026-11-19`. On produit deux plans, A et B, qui
  ne diffèrent que par le budget de `pool-tyo-01`, membre du bloc de la personne :
  - A : 520,00 € ;
  - B : 521,37 €. Cette valeur est choisie pour ne coïncider avec aucun montant d'E3.

  B est construit soit à partir d'une copie du carnet, faite dans un répertoire temporaire
  du test, soit par un `DemandPoolSnapshot` construit en mémoire, comme le lot figé. Le
  fichier versionné n'est jamais modifié.
- **Précondition, vérifiée par le test.** A et B ont les mêmes :
  - références solo ;
  - coûts de coalition (`FormationResult.evaluations`) ;
  - structure ;
  - allocation pour les paiements.

  D'après les journaux d'E3, c'est attendu : `pool-tyo-01` accepte 48 600 et 50 400 en
  solo, et le bloc accepte le premier prix du vendeur. Une hausse de 1,37 € ne change donc
  aucun tour d'acceptation. Si la précondition échoue, le test échoue avec un message
  explicite, et le scénario doit être revu. Le test ne doit pas être assoupli.
- **Conception vérifiée sur le code actuel,** le 2026-11-20, par un script en lecture
  seule, hors du dépôt :
  - **identiques entre A et B :** les références, les coûts de coalition, les blocs,
    l'allocation publique (paiements, φ, y′, λ\*), les parts de la personne, le côté
    vendeur du journal du bloc et les journaux solo de la personne ;
  - **différents :** `formation_run_id`, `allocation_sha256`, la `request_key` et le
    `journal_sha256` du bloc, et `initial_leader_total_cents`, qui passe de 339 600 à
    339 682 ;
  - **`oracle_configuration_id` et `catalog_sha256`** sont identiques dans A et B,
    puisqu'ils ne dépendent pas du carnet. T-CONF-1 ne peut donc pas les détecter ;
    T-CONF-2 et T-CONF-3 les couvrent (§9.2).
- **Coïncidences, vérifiées en révision 3** par un second script en lecture seule. Le
  script compare les valeurs privées aux montants entiers que la proposition publiera :
  catalogue, journaux de la personne, côté vendeur du journal du bloc, bloc, allocation
  et parts.
  - **Dans B, aucune valeur privée de `pool-tyo-01` ne coïncide avec un montant public :**
    ni son budget (52 137), ni la somme des budgets du bloc (566 137), ni celle des trois
    autres membres (166 137), ni l'offre initiale du leader (339 682).
  - **Dans A, le budget de `pool-tyo-01` (52 000) égale un montant public :** le prix
    catalogue par place de Northstar au palier de 3 places. Ce n'est pas une fuite, mais
    la règle de la révision 2, appliquée à A, aurait échoué. T-CONF-2 porte donc sur B
    seul (ci-dessous).
- **T-CONF-1, non-interférence.**
  - `TripProposal(A)` égale `TripProposal(B)`.
  - Le JSON public et la sortie texte de A et de B sont identiques octet pour octet.
  - Dans le même temps, le test vérifie que les données privées diffèrent bien entre A et
    B : `pool_sha256`, la `request_key` et le `journal_sha256` du bloc,
    `initial_leader_total_cents`, `formation_run_id` et `allocation_sha256`. Puisque la
    sortie, elle, reste identique, aucune de ces données n'y passe.
- **T-CONF-2, absence de divulgation directe (réécrit en révision 3).** Le test vérifie
  qu'aucun champ ni aucune donnée privée n'est publié comme tel. Il ne cherche pas à
  exclure toute coïncidence numérique. Cinq vérifications, dont (e), ajoutée en
  révision 4 :
  - **(a) Aucun objet privé.** Un parcours récursif de `TripProposal` ne rencontre aucune
    instance de `SellerTerms`, `SellerFloorTier`, `SellerTermsBook`, `TravelUnit` d'une
    autre demande, ni `NegotiationJournal` brut.
  - **(b) Aucune empreinte.** Ni le JSON, ni le texte, ni la sortie d'erreur ne contient
    de suite de 64 chiffres hexadécimaux. Le test cherche aussi, par égalité, chacune des
    empreintes réelles du plan : `catalog_sha256`, `oracle_configuration_id`,
    `pool_sha256`, `formation_run_id`, `allocation_sha256`, `result_sha256`, et la
    `request_key`, le `run_id` et le `journal_sha256` de chaque journal. Le message
    d'échec nomme ainsi l'empreinte en cause.
  - **(c) Aucune donnée privée des autres membres, sur B.** Aucun montant entier du JSON,
    et aucun montant affiché dans le texte, ne vaut :
    - le budget par personne ou total de `pool-tyo-01` ;
    - la somme des budgets du bloc, ou celle des autres membres ;
    - 0,60 fois la somme des budgets du bloc.

    Les valeurs de B ont été vérifiées sans coïncidence (ci-dessus). Le test vérifie
    d'abord cette précondition, sur les montants publics du plan. Si une évolution du
    catalogue crée une coïncidence, le test échoue avec un message qui demande de changer
    la valeur de B, sans assouplir la règle. Il ne porte pas sur A : T-CONF-1 prouve déjà
    que la sortie ne dépend pas de ces valeurs, et une coïncidence avec A n'est pas une
    fuite.
  - **(d) Les contre-offres du vendeur restent visibles (B7).** Pour chaque message
    `actor = "seller"` du journal du bloc et des journaux solo de la personne,
    `total_cents` n'est pas `null` et égale `outgoing_total_cents` dans le journal
    interne. Le test fige ainsi la décision du plan (§4.5) : une évolution qui masquerait
    ces offres échoue.
  - **(e) Anonymisation effective des autres membres (révision 4).** T-CONF-1 prouve que
    la sortie ne dépend pas du budget d'un autre membre. Il ne prouve pas, à lui seul,
    que les identifiants et les données des autres membres sont absents. (e) le vérifie
    directement, en comparant les données privées du carnet aux valeurs publiées. Seul
    ce que permet B8 reste publié : le libellé « autre demande k », le nombre de places
    et le paiement.

    **Le carnet marqué M.** Dans le carnet v1, les données des autres membres ne se
    distinguent pas des données publiques, si bien qu'une comparaison directe sur E3
    échouerait sans qu'il y ait de fuite :
    - toute demande sans profil explicite reçoit le `profile_id` `"all"`
      (`build_profiles`), comme celle de la personne ;
    - le budget de `pool-tyo-03` (500 €) égale celui de la personne ;
    - ceux de `pool-tyo-01` (520 €) et de `pool-tyo-02` (540 €) égalent des prix
      catalogue par place : Northstar au palier de 3 places, et SkyWays au premier
      palier.

    Le test construit donc en mémoire un carnet M, sans toucher au fichier versionné.
    Chaque demande du carnet garde son `request_id`, sa destination et son nombre de
    voyageurs. Elle reçoit des valeurs marquées :

    | Demande | Budget par personne |
    |---|---|
    | `pool-tyo-01` | 521,37 € |
    | `pool-tyo-02` | 541,29 € |
    | `pool-tyo-03` | 501,43 € |
    | `pool-tyo-04` | 601,17 € |
    | `pool-rom-01` | 451,61 € |
    | `pool-rom-02` | 331,53 € |

    Chaque demande reçoit aussi un profil explicite, avec le même nombre de voyageurs :
    - le `profile_id` `zq-membre-<request_id>` ;
    - `departure_after = 2027-01-07` et `arrival_before = 2027-12-29` ;
    - `excluded_suppliers = ["Zq Fournisseur Fictif"]`, un nom absent du catalogue.

    La demande de la personne est celle d'E3, inchangée.

    **Les marques ne changent pas l'économie du scénario.** Les dates encadrent toutes
    les offres, et le fournisseur exclu n'existe pas. Je l'ai vérifié sur le code actuel,
    par un script en lecture seule hors du dépôt. M donne le même bloc qu'E3 :
    - Northstar, 11 places ;
    - membres `pool-tyo-01`, `pool-tyo-02`, `pool-tyo-04` et la personne ;
    - coût 528 000 ;
    - mêmes références (48 600, 50 400, 54 000, 384 000) ;
    - mêmes φ (600, 1 500, 3 000, 3 900) ;
    - mêmes paiements (48 000, 48 900, 51 000, 380 100).

    Le test vérifie d'abord que le bloc de la personne compte au moins un autre membre :
    sinon, (e) ne prouverait rien.

    **(e1) Structure, sur E3 et sur M :**
    - **Les seuls objets du JSON qui concernent un autre membre** sont les
      `block.members[k]` avec `you = false`. Chacun a exactement les clés `label`, `you`,
      `seats` et `payment_cents`.
    - **`label`** vaut « autre demande k », avec k = 1, 2… dans l'ordre croissant des
      `unit_id`.
    - **`seats` et `payment_cents`** égalent `TravelUnit.seats` et le paiement du membre
      dans `BlockAllocation`.
    - **Tout ce qui est propre à une unité est celui de la personne :**
      - `unit.unit_id` vaut `"user"` ;
      - les `profile_id` de `travellers[]` sont ceux de la personne, et leur nombre égale
        ses places ;
      - `allocation` est sa ligne ;
      - `solo.attempts` sont ses essais ;
      - `request.draft` égale sa demande validée.

    **(e2) Valeurs, sur M.** Le test relève, dans le carnet et dans le `TripPlan` interne,
    les données privées de chaque autre demande du carnet, membre du bloc ou non, Rome
    comprise :
    - **identifiants :** `request_id`, qui est aussi l'`unit_id` ; `profile_id`, le seul
      nom de profil du modèle ; `rounded_budget_profiles` ;
    - **champs de `TravelerProfileDraft` :** `departure_after`, `arrival_before`,
      `excluded_suppliers` ;
    - **montants :**
      - le budget par personne de chaque profil ;
      - `budget_total_cents` ;
      - la référence solo ;
      - `y_rounded` ;
      - le montant et le budget de chaque `TravelerShare` ;
    - **rationnels :** φ, y et τ, sous la forme `"p/q"` et comme valeurs.

    Il les compare à toutes les valeurs publiées :
    - dans le JSON, chaque feuille : inclusion pour les chaînes, égalité pour les
      entiers, égalité de valeur pour les `"p/q"` ;
    - dans la sortie texte et dans les messages de la sortie d'erreur, les montants sous
      leur forme affichée.

    **Aucune ne doit y apparaître.**

    **Exclusions : fermées, calculées et comptées.** Une donnée privée n'est pas comparée
    quand elle ne se distingue pas d'une valeur publiée légitimement. Il y a quatre cas, et
    la vérification de structure (e1) les couvre :
    1. elle égale une valeur que B8 publie pour le même membre, son paiement ou ses
       places. Pour un membre d'une seule place, par exemple, le montant par place et τ
       égalent le paiement ;
    2. elle égale une valeur que la proposition publie à partir d'une source publique ou
       des données de la personne, calculée par le test à partir de ces sources ;
    3. elle vaut 0 ;
    4. c'est une valeur énumérée ou partagée : la destination, identique à celle de la
       personne dans un même bloc, `direct_flight`, ou `traveller_count`, que B8 publie
       sous le nom `seats`.

    **Le test calcule l'ensemble des exclusions et le compare à l'ensemble documenté.**
    Une exclusion nouvelle fait échouer le test et doit être revue. Les exclusions ne
    peuvent donc pas s'étendre en silence.

    Dans M, l'ensemble attendu, vérifié par le même script, est le suivant :
    - la référence solo de `pool-tyo-04` (54 000). Elle égale le prix catalogue par
      place de SkyWays, car l'accord s'est fait au prix du vendeur (cas 2) ;
    - le montant par place et τ de `pool-tyo-01`, `pool-tyo-02` et `pool-tyo-04`, qui
      égalent leurs paiements de 48 000, 48 900 et 51 000 (cas 1) ;
    - φ et y de `pool-tyo-03`, nuls, car l'unité est seule dans son bloc (cas 3).

    **Aucun autre recouvrement.** Aucun budget marqué, aucun identifiant, aucun
    `profile_id`, aucune date marquée ni le fournisseur marqué ne coïncide avec une valeur
    publiée. Le script a fait cette comparaison sur une approximation des valeurs
    publiées, reconstruite à partir du plan, puisque le JSON n'existe pas encore. Le test
    la refera sur le JSON réel.

  **Ce que T-CONF-2 ne vérifie pas, par décision : les planchers comme valeurs.** Une
  contre-offre ou un accord peut égaler un plancher, ou le laisser deviner. C'est le
  risque résiduel accepté par le plan (§4.5) et par B7, et il reste documenté (§13). Un
  test qui refuserait tout montant égal à un plancher contredirait B7. Il échouerait de
  plus sur de simples coïncidences : dans E3, le prix catalogue par place de SkyWays
  (54 000) égale déjà 3 fois le plancher par place de CloudWing au palier de 3 places
  (18 000). Les planchers sont protégés contre la divulgation directe par (a) et (b) :
  aucun champ et aucune empreinte. Ils ne le sont pas contre l'inférence tirée des offres
  du vendeur.

  **On ne fait pas varier un plancher.** Les contre-offres en dépendent, et le plan
  accepte qu'elles soient visibles : la sortie changerait légitimement. Il n'y a donc pas
  de test de non-interférence sur les conditions des vendeurs.
- **T-CONF-3, clés.** L'ensemble des clés du JSON égale l'ensemble attendu du schéma
  fermé. Aucune clé ne contient `floor`, `seller_terms`, `request_key`, `sha256` (sans
  exception depuis la révision 3), `run_id`, `configuration`, ni `budget`, en dehors des
  champs de la personne (`unit.budget_total_cents` et `travellers[].budget_cents`).
  Aucune clé n'est un nom de champ de `SellerTerms` ou de `SellerFloorTier`, lus par
  `dataclasses.fields`.

**T-REPLAY : provenance du rejeu (ajouté en révision 3).**

- **Au niveau du contrat (I3-A).** `ExtractionProvenance` accepte les trois formes du
  §4.10 et refuse toute autre combinaison. Le test essaie en particulier
  `source = "replay"` avec un `model` de 64 chiffres hexadécimaux, et `source =
  "draft-json"` avec un `provider` non nul.
- **De bout en bout, par sous-processus (I3-C).** Deux fichiers de rejeu :
  - R1 contient le seul brouillon d'E3 ;
  - R2 contient le même brouillon, suivi d'un second, jamais lu : une copie du brouillon
    de `pool-tyo-01` avec un autre budget.

  La commande est lancée deux fois, avec `--prompt`, `--extractor-replay R1` puis `R2`,
  `--yes`, `--reference-date 2026-11-19`, en JSON puis en texte.
- **Attendu :**
  - les sorties standard de R1 et de R2 sont identiques octet pour octet ;
  - `provenance.extraction` vaut exactement
    `{"model": "replay-v1", "provider": "replay", "source": "replay"}` ;
  - ni le SHA-256 de R1 ou de R2, ni le chemin de l'un ou de l'autre, n'apparaît sur la
    sortie standard ou sur la sortie d'erreur ;
  - un troisième fichier R0, qui contient une liste vide, donne le code 1
    (`ExtractorContractError`). Son message ne contient ni le chemin ni le contenu du
    fichier ;
  - un `--draft-json` vers un fichier absent donne le code 64. Le message nomme l'option,
    sans le chemin.
- **Fichier de rejeu illisible (ajouté en révision 4).** Le fichier est placé dans un
  répertoire temporaire dont le nom contient une marque, par exemple `zq-chemin-prive`.
  Deux cas :
  - un fichier présent mais sans droit de lecture (`chmod 000`) ;
  - un répertoire à la place du fichier.

  **Attendu, pour chacun :**
  - code 64, comme pour tout fichier introuvable ou illisible (B3) ;
  - l'erreur survient à la lecture des options, avant toute question ;
  - le message est « Fichier de --extractor-replay introuvable ou illisible. » Il ne
    contient ni le chemin complet, ni la marque, ni le texte de l'erreur système qui
    citerait le chemin ;
  - la sortie standard est vide.

  **Plateforme.** Le premier cas est sauté quand le test s'exécute avec l'identifiant 0
  (`root`), qui lit le fichier malgré `chmod 000`, et sous Windows. Le second cas
  s'exécute partout.

**T-LEX : vocabulaire.**

- les deux faces de la règle (§7.2) ;
- le contrôle des sorties de la commande sur E3, en texte et en JSON ;
- trois demandes par `--draft-json`, contenant chacune un mot interdit : dans
  `destination`, dans un `profile_id`, dans `excluded_suppliers`. Chacune donne le code 3
  et un document `invalid` avec `forbidden_term: chemin`. Le mot n'apparaît ni sur la
  sortie standard ni sur la sortie d'erreur.

**T-SIGINT : interruption.**

- La commande est lancée sur E3 par `--draft-json`, sans `--yes`.
- Le test lit la sortie d'erreur jusqu'à la question de validation, envoie `SIGINT` au
  processus, puis attend sa fin.
- **Attendu :** code 130, sortie standard vide (zéro octet), aucune trace de pile sur la
  sortie d'erreur.
- **Même test pendant la saisie interactive** de la demande, avant toute compréhension.
- **Plateforme.** Le test s'exécute sous macOS et Linux. Il est marqué non applicable
  sous Windows, où ce signal n'existe pas sous cette forme.

**T-STATUS : schémas de statut.**

- **Cas positifs, un par forme de valeur :**
  - `needs_clarification`, par `--draft-json` et par 3 tours avec rejeu ;
  - `invalid` : une erreur de validation (E1), une erreur de profil (E4), une erreur de
    pydantic (E8, dont `$: json_invalid` pour un JSON malformé), un mot interdit (E9) et
    un texte vide (E6) ;
  - `request_rejected` (révision 3) :
    - par sous-processus, avec `--draft-json`, les trois motifs de budget du §6.4 :
      code 3 ;
    - au niveau de l'afficheur, les deux lignes `request_not_ready`. Elles sont obtenues
      en appelant `plan_travel_request` sur un brouillon non validé : un champ manquant
      (code 2) et une date passée (code 3). La CLI ne peut pas les produire ;
  - `not_validated`, avec ses trois raisons.
- Pour chacun : l'ensemble exact des clés, chaque valeur dans son domaine, et le code de
  sortie.
- **Cas négatifs (révision 3), sur le validateur seul.** Chacun des documents suivants est
  refusé :
  - `reason = "invalid_request_id"`, et un `reason` inconnu ;
  - un motif de budget avec `missing_fields` ou `errors` non vide, ou avec
    `rejection_status` différent de `other` ;
  - `request_not_ready` avec `rejection_status = "other"` ;
  - une erreur hors du domaine E : une phrase libre, une erreur de pydantic qui cite une
    valeur, ou un `<chemin>` qui contient un nom de champ inconnu ;
  - un `missing_fields` hors de `REQUIRED_FIELDS`, ou dans le désordre ;
  - un code de sortie qui ne correspond pas au statut.
- **Refus à l'exécution.** Un test force un document invalide jusqu'à l'écriture. Il
  attend le code 1 et une sortie standard vide.

### 9.2 Mutants exigés

Chaque mutant est réintroduit seul, dans une copie de travail, comme en I2. Il doit faire
échouer au moins un test.

| # | Mutant | Test qui doit le tuer |
|---|---|---|
| 1 | `pool_sha256` remis dans la provenance | T-CONF-1, T-CONF-2 (b) et T-CONF-3 |
| 2 | `oracle_configuration_id` remis dans la provenance | T-CONF-3 (clé hors schéma) et T-CONF-2 (b). T-CONF-1 ne suffit pas : l'identifiant ne dépend pas du carnet, et il est identique dans A et B |
| 3 | les montants du leader visibles dans un journal de bloc | T-CONF-1 et T-CONF-2 (c) |
| 4 | la `request_key` exposée dans un essai | T-CONF-1 et T-CONF-3 |
| 5 | contrôle du vocabulaire par sous-chaîne | T-LEX, face « acceptation » |
| 6 | contrôle des valeurs fournies par la personne retiré | T-LEX |
| 7 | interruption convertie en code 1 | T-SIGINT |
| 8 | une clé en trop dans un document de statut | T-STATUS |
| 9 | `alone_social_optimum` retenu dès que v(C) ≥ 0 au lieu de v(C) > 0 | test du code `alone_no_beneficial_coalition` |
| 10 | une validation acceptée sur une réponse vide | test de validation, réponse vide |
| 11 (révision 3) | `catalog_sha256` remis dans la provenance | T-CONF-3 (clé `sha256`) et T-CONF-2 (b). T-CONF-1 ne suffit pas, pour la même raison qu'au mutant 2 |
| 12 (révision 3) | `model` du rejeu égal au SHA-256 du fichier, comme en révision 2 | T-REPLAY : les sorties de R1 et de R2 diffèrent, et l'empreinte apparaît |
| 13 (révision 3) | un chemin de fichier dans un message d'erreur | T-REPLAY : fichier R0, `--draft-json` vers un fichier absent et, depuis la révision 4, fichier de rejeu illisible |
| 14 (révision 3) | les contre-offres du vendeur masquées dans le journal du bloc | T-CONF-2 (d) |
| 15 (révision 3) | le validateur de statut ne contrôle que les clés | T-STATUS, cas négatifs |
| 16 (révision 4) | le libellé d'un autre membre remplacé par son `unit_id` | T-CONF-2 (e1) et (e2) |
| 17 (révision 4) | les parts de tous les membres du bloc publiées dans `travellers`, et pas seulement celles de la personne | T-CONF-2 (e1) et (e2) |

---

## 10. Découpage et preuves

Les trois sous-étapes viennent de la spécification. **Chacune est revue et autorisée
séparément.**

| Sous-étape | Contenu | Preuve demandée |
|---|---|---|
| I3-A | `trip_proposal.py` : DTO, énumérations, constructeur, invariants, calcul des explications de P4 (§5.4) ; tests de contrat, de confidentialité et de statut | une proposition construite à partir de plans réels (E3 et le lot figé), et les tests par code au niveau du constructeur |
| I3-B | `explanations_fr`, les afficheurs texte et JSON, le contrôle du vocabulaire ; tests de rendu et de sérialisation | les sorties d'E3 en texte et en JSON, identiques sur deux exécutions |
| I3-C | `plan_travel_request`, l'extracteur de rejeu, `plan_trip.py`, la ligne de `pyproject.toml` ; tests par sous-processus | les scénarios d'I3-A11, et le parcours E3 complet depuis le terminal |

**À chaque sous-étape :**

- le diff cumulé depuis la base ;
- la comparaison au manifeste ;
- un rapport, `docs/PHASE_I3_PRESENTATION_REPORT.md`, complété section par section.

---

## 11. Décisions demandées

| Id | Décision proposée | Alternative |
|---|---|---|
| D-I3-1 | Exemple pour Tokyo (E3). `unknown_place` est dans l'énumération et testé au niveau des explications, mais émis seulement à partir d'I4 | vérifier en v1 contre les destinations du catalogue |
| D-I3-2 | Date par défaut `date.today()`, toujours affichée ; date fixe dans les tests | option obligatoire |
| D-I3-3 | Usage incorrect : code 64 | code 3 |
| D-I3-4 | Confirmation lue sur l'entrée standard ; « o » ou « oui » seulement ; refus, réponse vide ou fin d'entrée : code 4 ; interruption : 130 | – |
| D-I3-5 | Les codes rangés par niveau (§5), sans code ajouté | – |
| D-I3-6 | Recalcul de `cover_values` par composante, sans nouveau seuil | exposer le cache dans le contrat d'I2 |
| D-I3-7 | Contre-offres du vendeur visibles, comme le décide le plan au §4.5 | les masquer, en revenant sur le plan |
| D-I3-8 | Autres membres : un libellé, les places et le paiement | n'afficher que la somme des autres paiements |
| D-I3-9 | Aucune recopie du texte brut ; erreurs de validation affichées telles quelles ; erreurs de pydantic réduites à `chemin: type` ; règle de vocabulaire appliquée à toute la sortie, sans exception (révision 2) | traduire les erreurs, ce qui exigerait une liste fermée de codes d'erreur |
| D-I3-10 (révisée en révision 3) | Extracteur de rejeu, `--extractor-replay`. Sa provenance est `provider = "replay"` et `model = "replay-v1"`, une constante, et non plus l'empreinte du fichier. Aucun chemin de fichier dans les sorties | variable d'environnement cachée ; pour la provenance, `model = null` |
| D-I3-11 (révisée en révision 3) | Côté leader masqué dans les journaux de bloc ; contre-offres du vendeur visibles, et vérifiées comme telles ; aucune empreinte dans la proposition ; preuve par T-CONF et T-REPLAY | tout montrer, puisque le carnet v1 est public |
| D-I3-12 | Décomposition des économies limitée aux montants typés | séparer un effet palier d'un effet négociation, ce qui serait une logique nouvelle |
| D-I3-13 (précisée en révision 3) | Document `trip-request-status-v1` sur la sortie standard, avec `--json`, pour les codes 2, 3 et 4 ; schéma fermé par statut, pour les clés et les valeurs : domaine E des erreurs, cinq lignes pour `request_rejected` (§6.4) | sortie standard vide |
| D-I3-14 | `direct_preference_not_met` : offre retenue seulement, deux prix catalogue lus par `list_total`, sans écart calculé | ne montrer aucun prix |
| D-I3-15 | Code 0 pour toute proposition produite, quel que soit le statut de l'unité | code non nul quand l'unité n'est pas servie |
| D-I3-16 | `plan_travel_request` synchrone, sur une demande déjà validée ; identifiant fixe `"user"` ; pas de RAG dans la CLI d'I3 ; mode démonstration seul | – |
| D-I3-17 (révision 2) | Une demande dont une chaîne fournie par la personne contient un mot interdit est invalide (code 3), avec un message qui nomme le champ sans citer la valeur | remplacer ces valeurs par des libellés neutres dans toute la sortie |
| D-I3-18 (révision 2, étendue en révision 3) | `pool_sha256` et `oracle_configuration_id` retirés de la provenance publique ; **en révision 3, `catalog_sha256` aussi,** puisqu'il égale `seller_terms_sha256` (validé à la revue de la révision 3) ; la proposition ne contient plus aucune empreinte ; elles restent dans `TripPlan` | publier, à la place de l'identifiant, les seuls paramètres publics de l'oracle ; pour le catalogue, publier l'empreinte de sa seule partie publique, ce qui serait une dérivation nouvelle |

---

## 12. Corrections par rapport à ma revue en conversation

1. **La date et les prix.** J'avais écrit que les prix dépendent de la date de référence.
   C'est faux dans le code actuel : l'échéance de l'acheteur est la date de référence
   elle-même, donc le nombre de jours restants vaut toujours 0. La date compte pour la
   validation, l'admissibilité, l'extraction et la provenance (B2).
2. **Les contre-offres du vendeur.** J'avais proposé de les masquer. Le plan, validé, les
   accepte déjà comme risque résiduel (§4.5). Je m'aligne sur lui (B7). Le vrai point
   nouveau se trouve côté leader (B11).
3. **`plan_travel_request` asynchrone.** Puisque la fonction reçoit une demande déjà
   validée et que `plan_lot` est synchrone, elle peut rester synchrone (§6.1).
4. **La confirmation sans terminal.** J'avais proposé de refuser par défaut quand l'entrée
   n'est pas un terminal. Cela empêcherait les tests par sous-processus exigés par la
   spécification. La réponse est donc lue sur l'entrée standard dans tous les cas, et
   seule une réponse explicite « o » ou « oui » vaut validation (B4).

---

## 13. Risques

| Risque | Traitement |
|---|---|
| Le LLM réinterprète tout le texte à chaque tour de clarification | le résumé des champs validés est montré avant la validation (ID-10) |
| Avec la date par défaut, le catalogue v1 ne propose plus d'offre après le 2027-04-05 | la date est affichée, et la limite documentée (B2) |
| Le simulateur P3 capture la sortie standard de façon globale | la commande n'écrit rien pendant le calcul et s'exécute en série ; un test le vérifie (§6.2) |
| Une contre-offre ou un accord tombe exactement au plancher, ce qui le révèle | risque résiduel accepté par le plan, §4.5 (B7). Les contre-offres restent visibles, et T-CONF-2 le vérifie. Le test ne cherche pas les planchers parmi les montants : il protège les planchers contre la divulgation directe (champs et empreintes), pas contre l'inférence (§9.1) |
| Une valeur fournie par la personne contient un mot interdit | la demande est refusée avant tout affichage, avec le code 3, sans réécrire la valeur (D-I3-17) |
| Les montants publics (coût du bloc, somme des références, paiements des autres) restent fonction des budgets des autres membres | limite documentée en B11 : la garantie porte sur les champs privés, les empreintes et les montants du leader, pas sur toute inférence. Sans effet en v1, où le carnet est public ; à réexaminer avant le mode session |
| Le coût de `cover_values` | borné par la limite de 14 unités : 0,34 s au pire, mesuré en I2 (B6) |

---

## 14. Gouvernance

- **La conception d'I3 peut reprendre,** depuis la clôture d'I2 du 2026-11-20.
  L'implémentation n'est pas autorisée.
- **Cette révision 4 doit être revue,** et les décisions D-I3-1 à D-I3-18 tranchées, avant
  toute demande d'autorisation.
- **Chaque sous-étape (I3-A, puis I3-B, puis I3-C) est autorisée séparément,** après la
  revue de la précédente.
- **Aucune opération Git** sans autorisation distincte, et jamais `git add .` ni
  `git add -A`. Les 18 fichiers personnels restent exclus.

---

## 15. Révision 2 : réponse à la revue de la révision 1

La revue a validé la direction de la révision 1 et les décisions D-I3-1 à D-I3-16, sous
sept corrections.

| # | Correction demandée | Traitement | Où |
|---|---|---|---|
| 1 | Retirer `pool_sha256` de la provenance publique et garder `pool_version` | Fait. **Extension, à confirmer :** par la même règle, `oracle_configuration_id` est retiré aussi, car il inclut `seller_terms_sha256`, l'empreinte des conditions privées des vendeurs (D-I3-18) | B11, §4.10 |
| 2 | Aligner le contrôle du vocabulaire sur la règle du plan, sans exception implicite pour les valeurs fournies par la personne | Le contrôle porte sur toute la sortie. Une valeur fournie contenant un mot interdit fait refuser la demande avant tout affichage (code 3), sans réécriture (D-I3-17). Les erreurs de pydantic ne citent plus les valeurs reçues | B9, §6.2, §7.2, T-LEX |
| 3 | Préciser que `alone_no_beneficial_coalition` porte sur les coalitions réalisables effectivement évaluées par P4 | Définition de « évaluée par P4 » à partir de `enumerate_candidates`, et gabarit du message | §5.1, §5.4 |
| 4 | Préciser que `alone_social_optimum` décrit la structure retenue et les alternatives évaluées, sans prétendre que rester seul est meilleur | Ce que le statut décrit et ne prétend pas, gabarit du message, cas de l'égalité, test sur le gabarit | §5.4 |
| 5 | Ajouter un test de confidentialité sur toute la `TripProposal` et son JSON, en ne faisant varier que le budget d'un autre membre | T-CONF-1 (identité octet pour octet), T-CONF-2 (aucune valeur privée), T-CONF-3 (clés). La conception a été vérifiée sur le code actuel. Mutants 1 à 4 | B11, §9.1, §9.2 |
| 6 | Tester l'interruption : code 130 et sortie standard vide | T-SIGINT, à la question de validation et pendant la saisie. Mutant 7 | I3-A11, §9.1 |
| 7 | Fermer les schémas de `trip-request-status-v1` pour les quatre statuts | Champs communs, champs propres à chaque statut, domaines des valeurs, codes de sortie, validateur avant écriture, T-STATUS. Mutant 8 | §6.4, I3-A19 |

**Autres changements de la révision 2 :**

- **B11 est étayé par des chiffres d'E3,** relevés en lecture seule :
  `initial_leader_total_cents = 339 600 = 0,60 × 566 000`.
- **Ce que la garantie de confidentialité ne couvre pas est écrit.** Les montants publics
  restent fonction des budgets des autres membres.
- **Les critères I3-A12 et I3-A13 sont précisés,** et trois critères sont ajoutés :
  I3-A19 (schémas de statut), I3-A20 (mutants) et I3-A18 (déjà présent).
- **Les décisions D-I3-17 et D-I3-18** s'ajoutent au §11.

Aucun code n'a été écrit, aucune opération Git n'a été faite, et les 18 fichiers
personnels n'ont pas été touchés. Le seul calcul effectué est une lecture d'E3 par un
script hors du dépôt, qui n'a rien écrit dans le dépôt.

---

## 16. Révision 3 : réponse à la revue de la révision 2

La revue de la révision 2 a été favorable, sous trois corrections.

**Ce qui est conservé :**

- les décisions déjà validées. Trois sont précisées (D-I3-10, D-I3-11 et D-I3-13), et une
  est étendue (D-I3-18) ;
- T-CONF-1 et T-SIGINT, sans changement ;
- les mutants 1 à 10, dont seule la colonne des tests change pour les trois premiers.

### 16.1 Les trois corrections

| # | Correction demandée | Traitement | Où |
|---|---|---|---|
| 1 | Retirer de la provenance publique l'empreinte du fichier de rejeu, ou la remplacer par un identifiant stable, et ajouter un test de contrat | Remplacée par la constante `"replay-v1"`. `ExtractionProvenance` n'admet que trois formes. Test T-REPLAY : deux fichiers qui ne diffèrent que par un brouillon non lu donnent des sorties identiques, et aucune empreinte n'apparaît. Mutant 12. **Extension, à confirmer :** aucun chemin de fichier dans les sorties (mutant 13) | B10, §4.10, §6.3, §9.1 |
| 2 | Lever la contradiction entre T-CONF-2 et B7 : vérifier l'absence de divulgation directe, garder le risque résiduel, ne pas masquer les contre-offres | T-CONF-2 est réécrit en quatre vérifications : (a) aucun objet privé ; (b) aucune empreinte ; (c) aucune donnée des autres membres, sur B ; (d) contre-offres du vendeur visibles, vérifiées comme telles. Les planchers ne sont plus cherchés parmi les montants, et le risque résiduel est écrit dans le test et au §13. Mutant 14 | §9.1, §13, D-I3-11 |
| 3 | Fermer les domaines de `reason`, `missing_fields` et `errors` de `request_rejected`, à partir des valeurs réellement produites, et faire contrôler les valeurs par le validateur | Les cinq motifs de `TravelUnitError` sont relevés. Quatre forment le domaine, et `invalid_request_id` en est exclu, faute de pouvoir être atteint. Cinq combinaisons sont permises, avec le code de sortie et le message de chacune. Les erreurs ont un domaine fermé, E, de neuf formes, commun à `invalid`. Le validateur contrôle les valeurs, et T-STATUS a des cas négatifs. Mutant 15 | §6.4, I3-A19, §9.1 |

### 16.2 Erreurs de la révision 2, corrigées

1. **`catalog_sha256`.** J'avais écrit que le fichier du catalogue ne contenait aucun
   plancher. C'est faux :
   - `catalog_v1.json` porte `seller_floor_per_seat_cents` à chaque palier ;
   - `catalog_sha256` est l'empreinte de tout le fichier ;
   - le simulateur vérifie que le catalogue et `SellerTermsBook` portent la même version
     et la même empreinte. `seller_terms_sha256` égale donc `catalog_sha256`.

   La révision 2 retirait `oracle_configuration_id` parce qu'il inclut
   `seller_terms_sha256`, mais gardait cette même valeur sous un autre nom. Par la même
   règle, `catalog_sha256` sort de la provenance (D-I3-18, étendue, **à confirmer**).
   C'est le mutant 11.
2. **T-STATUS.** J'avais écrit qu'aucun scénario v1 ne passe la validation pour échouer
   ensuite dans `build_travel_unit`. C'est faux : les trois motifs de budget sont
   atteignables par `--draft-json`. Le test les produit maintenant par sous-processus.
3. **Le domaine de `invalid`.** La révision 2 annonçait « trois formes seulement » et en
   énumérait quatre. Il y manquait aussi le message de texte vide de `understand_request`.
   Le domaine E en donne neuf, exactes.
4. **T-CONF-2 appliqué à A** aurait échoué sans aucune fuite. Le budget de `pool-tyo-01`
   dans A, 52 000, égale le prix catalogue par place de Northstar au palier de 3 places.
   La vérification (c) porte donc sur B seul. Cela reste suffisant, puisque T-CONF-1
   prouve que la sortie ne dépend pas de ces valeurs.

### 16.3 Vérifications faites pour cette révision

Trois scripts en lecture seule, hors du dépôt, sans écriture de bytecode dans le dépôt,
sur le code actuel et avec la date de référence du 2026-11-19 :

- **Motifs de rejet atteignables.**

  | Demande | `validate_request_draft` | `plan_lot` |
  |---|---|---|
  | `budget_per_person = "0.001"` | `ready` | `request_rejected`, `budget_below_one_cent` |
  | `budget_per_person = "2000000000"` | `ready` | `request_rejected`, `budget_out_of_range` |
  | 20 voyageurs à `"600000000"` | `ready` | `request_rejected`, `budget_total_out_of_range` |
  | budget manquant | `needs_clarification` | `request_not_ready`, statut `needs_clarification`, `missing_fields = (budget_per_person,)` |
  | date de départ passée | `invalid` | `request_not_ready`, statut `invalid`, erreur E1 |

  `PlanningRequest` refuse `""` et `" user"` avec `PlanningInputError`, avant
  `build_travel_unit`.
- **Coïncidences dans E3,** détaillées au §9.1 :
  - dans B, aucune ;
  - dans A, une seule : le budget de `pool-tyo-01` ;
  - pour les planchers, un montant public égale 3 fois un plancher par place
    (54 000 = 3 × 18 000).
- **Lecture du code :**
  - `load_offer_catalog` calcule l'empreinte sur le fichier entier ;
  - `SimulatedNegotiationOracle` compare `(catalog.version, catalog.sha256)` à
    `(terms_book.version, terms_book.sha256)` ;
  - `understand_request` lit `provider_name` et `model` sur l'extracteur.

### 16.4 Points à trancher dans cette revue

- **L'extension de D-I3-18 à `catalog_sha256`.** L'alternative serait d'en publier une
  empreinte limitée à la partie publique, ce qui demanderait une dérivation nouvelle.
- **L'extension « aucun chemin de fichier dans les sorties »** (B10, §6.3).

Aucun code n'a été écrit, aucune opération Git n'a été faite, et les 18 fichiers
personnels n'ont pas été touchés. I3 n'est pas démarrée.

---

## 17. Révision 4 : réponse à la revue de la révision 3

La revue de la révision 3 a été favorable.

**Validé par la revue :**

- **D-I3-18 étendue :** `catalog_sha256` sort de la provenance publique, et seul
  `catalog_version` reste ;
- **B10 :** aucun chemin de fichier dans les sorties, avec la règle de remplacement par
  le nom de l'option ou le nom de base du fichier versionné.

Les mentions « à confirmer » de B10 et de D-I3-18 (§11) sont remplacées par « validé ».
Le §16 est laissé tel quel, comme trace de la révision 3.

### 17.1 Les deux précisions demandées

| # | Demande | Traitement | Où |
|---|---|---|---|
| 1 | Compléter T-CONF-2 : vérifier que la proposition sérialisée ne contient aucun identifiant de demande ou d'unité, `profile_id`, budget, référence, φ ou y individuels, ni autre donnée de `TravelUnit` ou de `TravelerProfileDraft` des autres membres, en comparant les données privées du carnet aux valeurs publiées. Garder ce que permet B8 | Vérification (e) : un carnet marqué M, aux valeurs distinctives, qui donne le même bloc qu'E3 ; (e1), la structure, sur E3 et M ; (e2), les valeurs, sur M, avec un ensemble d'exclusions fermé, calculé et comparé à l'ensemble documenté. Mutants 16 et 17. Le critère I3-A8 renvoie maintenant à T-CONF-2 (e) | §9.1, §9.2, I3-A8 |
| 2 | Ajouter, si possible, un cas T-REPLAY pour un fichier de rejeu illisible | Deux cas, sans droit de lecture et répertoire à la place du fichier : code 64, message sans chemin ni marque, sortie standard vide. Le mutant 13 couvre aussi ces cas | §9.1, §9.2 |

### 17.2 Pourquoi un carnet marqué

Une comparaison sur le carnet v1 tel quel ne distingue pas une fuite d'une coïncidence :

- **les profils par défaut :** toute demande sans profil explicite reçoit le
  `profile_id` `"all"`, comme celle de la personne ;
- **les budgets :** celui de `pool-tyo-03` égale celui de la personne, et ceux de
  `pool-tyo-01` et de `pool-tyo-02` égalent des prix catalogue.

Il faudrait donc, soit accepter des échecs sans fuite, soit des exceptions assez larges
pour masquer une vraie fuite. Le carnet M rend chaque donnée privée distinctive sans
changer l'économie du scénario. Les rares recouvrements qui restent sont énumérés, et le
test refuse tout recouvrement nouveau.

### 17.3 Vérifications faites pour cette révision

Deux scripts en lecture seule, hors du dépôt, sans écriture dans le dépôt, sur le code
actuel et à la date du 2026-11-19 :

- **M donne le même bloc qu'E3 :** offre, places, membres, coût, références, φ et
  paiements (§9.1, (e)) ;
- **les exclusions attendues dans M** sont exactement les trois groupes du §9.1, et il n'y
  a aucun autre recouvrement. La comparaison porte sur une approximation des valeurs
  publiées, reconstruite à partir du plan ; le test la refera sur le JSON réel ;
- **la référence solo de `pool-tyo-04`,** 54 000, est l'accord sur SkyWays, conclu au
  premier prix du vendeur. Elle égale donc le prix catalogue public.

**Rien d'autre n'a changé :** décisions, contrats, autres tests et autres mutants.

Aucun code n'a été écrit, aucune opération Git n'a été faite, et les 18 fichiers
personnels n'ont pas été touchés. I3 n'est pas démarrée.
