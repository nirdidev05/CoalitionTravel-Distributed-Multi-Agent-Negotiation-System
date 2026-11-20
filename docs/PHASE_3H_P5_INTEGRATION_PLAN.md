# Phase 3H et P5 : intégration de bout en bout

**Statut : proposition, révision 4.**

- **Validation :** l'architecture générale est validée.
- **Feu vert conditionnel à I0 :** revue de P4, vérification des rapports et inventaire
  des fichiers. Ce feu vert n'autorise **aucune opération Git**.
- **Code :** aucun fichier de code n'a été modifié pour écrire ce document.

- **Date :** 2026-11-19.
- **Arbre de travail audité :** branche `p1-coalition-foundations`. P2, P3 et P4 n'y sont
  pas commités, et P4 attend encore sa revue finale.
- **Suite de tests :** 662 tests collectés.
- **Révisions :** les révisions 2, 3 et 4 intègrent les trois revues successives de
  ChatGPT. Les changements sont listés au §10.

Les identifiants de décision de ce document commencent par **ID-** (« intégration »). Ils
ne se confondent pas avec les décisions D1 à D11 de la spécification P4.

---

## 0. Résumé

1. **État actuel.** Les composants existent, mais aucun chemin ne va du texte de
   l'utilisateur jusqu'au résultat :
   - `process_travel_request` s'arrête à l'envoi d'un `SUBSCRIBE` au Broker ;
   - le Broker ne négocie pas dans ce chemin (`negotiate=False`) ;
   - `run_formation_pipeline` (P4) n'est appelé que par `evaluate_formation.py`.
2. **Quatre écarts bloquent l'exemple Lyon-Alger :**
   - **une demande donne une seule unité indivisible.** Il faut donc un carnet de
     demandes synthétique ;
   - **le modèle n'a ni origine ni retour,** et le catalogue v1 ne contient que 3 offres
     aller simple ;
   - **P5 n'est pas implémentée,** et la répartition par voyageur n'est pas spécifiée ;
   - **il n'y a pas de point d'entrée,** et Ollama n'est pas installé.
3. **Architecture :**
   - un orchestrateur applicatif remplace le Broker dans le chemin IA ;
   - P2, P3 et P4 sont réutilisés avec un seul cache ;
   - P5 lit les jeux de P4 sans nouvel appel à l'oracle ;
   - la présentation est déterministe et construite à partir de codes de raison.
4. **Ce que produit le système :** une **proposition de voyage simulée**, avec un prix
   négocié contre des vendeurs fictifs et une répartition calculée. Ce n'est jamais un
   billet réservé ni émis.
5. **Plan en six étapes, de I0 à I5 :**
   - chaque étape est revue et acceptée avant que la suivante commence ;
   - I4 ne peut avancer en parallèle de I2 qu'au niveau de la conception et de tests
     isolés.

---

## 1. Objectif et périmètre

### 1.1 Objectif

Un prototype **local** et réellement utilisable :

1. on lance une commande ;
2. on écrit une demande en langage naturel ;
3. on obtient une proposition qui enchaîne la compréhension par le LLM, la négociation
   multi-agents simulée, la formation optimale des coalitions et la répartition des
   économies.

### 1.2 Nature du résultat

Le résultat est une **proposition simulée** :

- **un catalogue fictif et local :** compagnies, offres, paliers, capacités et planchers
  vendeurs privés ;
- **des vendeurs simulés ;**
- **aucune réservation, aucun billet, aucun paiement.**

Cette mention figure en tête de la sortie texte et dans le JSON (`simulation`, §7, I3).

**Texte exact de l'avertissement** (il ne contient aucun mot interdit) :

> Proposition simulée : catalogue et vendeurs fictifs. Aucune réservation n'est
> effectuée et aucun titre de transport n'est délivré.

**Vocabulaire de la sortie :**

- **mots employés :** « proposition », « prix négocié (simulation) », « répartition
  calculée ». Pour l'étape de confirmation (ID-10), la sortie dit « demande validée »
  ou « demande retenue », et jamais « demande confirmée » ;
- **mots interdits,** avec toutes leurs formes fléchies :
  - « billet », « billets » ;
  - « réservé », « réservée », « réservés », « réservées » ;
  - « confirmé », « confirmée », « confirmés », « confirmées » ;
  - « émis », « émise », « émises ».

**Règle de test, sans exception :** la recherche porte sur des **mots entiers**. Les
deux sorties (texte et JSON) sont mises en NFC et en minuscules (casefold), puis
découpées en mots par une frontière de mot Unicode. Un mot interdit n'est pas toléré,
même dans une phrase négative.

Cette règle laisse passer, à juste titre, les mots qui ne font que **contenir** un mot
interdit :

- « réservation » ;
- « émission », qui contient la sous-chaîne « émis » ;
- « confirmation ».

Un test par sous-chaîne les refuserait à tort. Le test vérifie donc les deux faces de
la règle :

- **refus :** chaque mot interdit est rejeté ;
- **acceptation :** l'avertissement exact ci-dessus et les mots « réservation »,
  « émission » et « confirmation » passent.

### 1.3 Le résultat doit montrer

1. les offres initiales ;
2. les groupes de voyageurs constitués ;
3. les négociations effectuées ;
4. l'offre commune retenue ;
5. le prix avant négociation et le prix après négociation ;
6. l'économie collective ;
7. le montant payé par chaque voyageur ;
8. les raisons de chaque acceptation et de chaque rejet ;
9. l'explication des cas où aucune coalition avantageuse n'existe.

### 1.4 Hors périmètre

- vraies compagnies, API externes, réservation, paiement ;
- interface web : plus tard, et elle réutilisera le DTO public ;
- serveur multi-utilisateur concurrent. Le simulateur P3 capture `stdout` de façon
  globale et doit être appelé en série ;
- **mode session dans la première version** (§6.3).

---

## 2. Audit maillon par maillon

| # | Étape cible | Existant | État vérifié | Ce qui manque |
|---|---|---|---|---|
| 1 | Compréhension par le LLM | `infrastructure/llm/ollama.py` : `OllamaStructuredRequestExtractor`, prompt `travel-request-extraction-v1`, schéma Pydantic transmis à `format` | tests avec un faux transport. **Ollama absent** : commande introuvable, port 11434 sans réponse | installation, choix et mesure d'un modèle |
| 2 | Demande structurée | `TravelRequestDraft` : destination, travellers ≤ 20, budget_per_person, departure_after, arrival_before, direct_flight, excluded_suppliers, profiles ; `extra="forbid"` | testé | **origine**, **retour**, borne haute de la date de départ |
| 3 | Validation et clarification | `validate_request_draft`, `understand_request` : statuts `ready`, `needs_clarification`, `invalid` ; `REQUIRED_FIELDS` = destination, travellers, budget | testé | aucune **boucle de dialogue** |
| 4 | Profils et unités | `build_profiles`, `consolidate_profiles`, `build_travel_unit` | testé (P1.3) | **une demande donne une seule unité indivisible** (§3.1) |
| 5 | Catalogue et admissibilité P2 | `load_offer_catalog` (lecture stricte, manifeste, SHA-256) ; `lot_admissibility` (`non_financial_v1`, 7 règles, H2) ; note `direct_preference_not_met` | testé (P1.4, P2) | catalogue v1 : **3 offres** (Rome, Tokyo ×2), aller simple, sans origine. La normalisation des lieux ne gère pas les alias (§6.5) |
| 6 | Références individuelles | `compute_reference_costs` : `ref_u` = meilleur accord solo, départage par (montant, `offer_id`) | testé | rien |
| 7 | Négociation P3 | `SimulatedNegotiationOracle` : agents historiques. `negotiate_detailed` renvoie un journal sans plancher | testé (P3, P3-bis) | le cache ne garde que `NegotiationOutcome` : **les journaux sont perdus** |
| 8 | Formation P4 | `form_coalitions`, `run_formation_pipeline`. `ComponentFormation.game` et `FormationResult.evaluations` sont conservés | 116 tests P4, revue en attente | `run_formation_pipeline` ne renvoie ni le lot ni les références |
| 9 | Répartition P5 | spécification P4 §9 ; `CoalitionGame.cover_values(subset)` ; `shapley_value` historique en flottants | **non implémentée** | le module ; la répartition par voyageur (§6.1) |
| 10 | Présentation | `formation_report.py` produit des rapports de banc d'essai, avec une garde contre la fuite des clés de plancher | rapports de recherche | DTO public, rendu texte et JSON, explications |
| – | Point d'entrée | scripts `coalition-travel`, `coalition-travel-eval`, `coalition-travel-eval-rag` | – | **aucune commande de planification** |

**Composants qui restent dans le dépôt mais ne seront pas sur le nouveau chemin :**

- `BrokerAgent`, `Leader.CoalitionLeaderAgent`, `Entry.py` : figés par le golden master
  et utilisés par la baseline B0 ;
- `application/compatibility.py` : décision sur une seule `CommonOffer`, remplacée par P2
  dans le nouveau chemin ;
- `profiles.create_buyer_agents` : P3 crée ses propres `BuyerAgent` ;
- `application/optimization.py`, `domain/partition_optimization.py` : remplacés par P4 ;
- `cooperative_game.allocate_shapley_payments` : remplacée par P5. `shapley_value` reste
  l'oracle différentiel des tests.

---

## 3. Écarts structurants

### 3.1 Une coalition suppose plusieurs demandes

- **Le joueur de P4 est une `TravelUnit`.** Une demande donne une seule unité, qui n'est
  jamais découpée entre plusieurs blocs (P1.3).
- **Les 8 voyageurs du prompt négocient déjà ensemble,** au palier de 8 sièges.
- **Un lot d'un seul joueur ne produit aucune économie collective :** il forme une seule
  composante singleton, de valeur 0.

**Décision ID-1 (validée sur le principe).** La première version fonctionne en **mode
démonstration** : la demande de l'utilisateur rejoint un **carnet synthétique versionné**
de demandes déjà structurées. Le lot réunit l'utilisateur et les demandes du carnet
**sur le même trajet**, pour deux raisons :

- le contrôle H2 porte sur le lot entier ;
- une composante est limitée à 14 unités, donc le carnet contient au plus 13 demandes
  par trajet.

Le mode session est reporté (§6.3).

### 3.2 Le modèle de trajet ne représente pas l'exemple

Exemple : « Lyon-Alger, départ le 15 février 2027, retour le 25 février 2027 ».

- **L'origine est perdue :** aucun champ ne la reçoit.
- **Le retour est mal interprété :** « retour le 25 février » ne peut aller, au mieux,
  que dans `arrival_before`, dont le sens est différent.
- **Alger n'existe pas** dans le catalogue.

**Décision ID-2 (validée sous condition) : l'aller-retour est un forfait.** On évite
ainsi de découper le budget entre l'aller et le retour, et de former deux coalitions
incohérentes. La capacité et les autres conditions sont définies au §6.2.

### 3.3 Le chemin IA s'arrête au Broker

Le chemin actuel de `process_travel_request` :

1. compréhension de la demande ;
2. création des profils et des acheteurs ;
3. `evaluate_compatibility`, sur une seule offre souvent absente ;
4. un `SUBSCRIBE` par profil vers le Broker.

Le chemin « cohorte » du Broker ne regroupe que les profils d'une même demande. Il
appelle `form_coalition(..., negotiate=False)` : il n'y a ni négociation, ni remise autre
que celle d'une table fixe.

**Décision ID-3 (validée) :**

- le Broker reste intact, pour le scénario historique et pour B0 ;
- un orchestrateur indépendant prend son rôle ;
- `process_travel_request` reste inchangé.

Le système reste multi-agents, car chaque négociation P3 fait dialoguer les agents
historiques.

### 3.4 Les journaux de négociation sont perdus

Le cache ne garde que le résultat de chaque négociation. La solution est au §4.4.

### 3.5 P5 et la répartition par voyageur

La spécification §9 fixe :

- Shapley calculé sur `v*|C` ;
- la projection dans `[0, ref_u]` ;
- la convention λ* ;
- l'arrondi au plus fort reste.

Elle laisse la répartition à l'intérieur d'une unité hors périmètre. Celle-ci est définie
au §6.1.

### 3.6 Écarts opérationnels

- il n'existe aucune commande de planification ;
- Ollama n'est pas installé ;
- P2 à P4 ne sont pas commités (§7, I0).

---

## 4. Architecture cible

### 4.1 Flux et types échangés

```
Texte utilisateur
  │ OllamaStructuredRequestExtractor (+ KnowledgeService : règles métier, jamais de prix)
  ▼
TravelRequestDraft ─ validate_request_draft ─► needs_clarification ─► question (CLI)
  │                                              └─► ré-extraction sur texte + précisions (≤ 3 tours)
  │ ready ─► résolution des lieux (§6.5) ─► confirmation par l'utilisateur
  ▼
build_travel_unit ─► TravelUnit (joueur)          DemandPool ─► TravelUnit × k (synthétiques)
  └───────────────────────┬─────────────────────────────┘
                          ▼ sélection du lot (même trajet)
lot_admissibility (P2) ─► LotAdmissibilityResult : relation, violations, composantes, H2
                          ▼
compute_reference_costs (P2/P3) ─► ReferenceCostsResult : ref_u, tentatives solo
                          │   CachingNegotiationOracle ─► JournalingNegotiationOracle
                          │                                 ─► SimulatedNegotiationOracle (agents P3)
                          ▼ même instance de cache
form_coalitions (P4) ─► FormationResult : jeux, blocs, évaluations
                          ▼ jeux déjà construits : zéro appel d'oracle
allocate_savings (P5) ─► AllocationResult : φ, y, y', paiements, parts par voyageur (§6.1)
                          ▼
build_trip_proposal ─► TripProposal (public, une unité, marqué « simulation ») ─► texte | JSON
```

### 4.2 Rôle de chaque composant

| Composant | Rôle | Interdit |
|---|---|---|
| LLM (Ollama) | extraire les faits de la demande | voir le catalogue ; produire un prix, une offre ou une disponibilité. Le schéma n'a aucun champ tarifaire, et `extra="forbid"` refuse tout champ inconnu |
| RAG | fournir le contexte métier de l'extraction ; citer ses sources | fournir une valeur numérique en sortie ou une offre |
| Catalogue public | seule source des offres et des prix catalogue | contenir les planchers |
| Termes vendeurs | utilisés seulement par le simulateur (allow-list AST) | toute autre lecture |
| P2 | admissibilité non financière, H2, références | décider sur le prix |
| P3 | seule source des prix négociés | – |
| P4 | seule source de la structure de coalitions | – |
| P5 | seule source des paiements | appeler l'oracle |
| Orchestrateur | enchaîner les étapes, traduire les erreurs en statuts | prendre une décision métier |
| Présentation | mettre en forme un `TripProposal` | calculer un montant |

### 4.3 Transmission de P3 à P4 puis à P5, sans renégocier

- **Les références et la formation partagent un cache unique.** C'est déjà le contrat
  P4 :
  - `form_coalitions` refuse un oracle qui ne passe pas par le cache ;
  - il refuse aussi une configuration différente ;
  - le lot figé compte 10 succès du cache.
- **Une seule modification d'un module P4 :** `run_formation_stages(...)` renvoie
  `(lot, references, formation)`, et `run_formation_pipeline` devient une enveloppe.
  Aucun comportement ne change ; c'est prouvé par les empreintes (I1).
- **P5 lit `ComponentFormation.game` :** toutes les sous-coalitions d'un bloc partagent
  son offre et sont déjà évaluées par P4 (spécification §9.2).

### 4.4 Journaux : un adaptateur placé sous le cache

`JournalingNegotiationOracle` (infrastructure) enveloppe le simulateur.

**Ce qu'il expose :** le même `oracle_configuration_id`.

**À chaque appel de `negotiate(request)`, dans cet ordre :**

1. il appelle `negotiate_detailed` ;
2. il valide le résultat avec **la même fonction que le cache**
   (`validate_negotiation_outcome`). Ainsi, un journal n'est jamais mémorisé pour un
   résultat que le cache refuserait ;
3. il vérifie que le journal concorde avec le résultat (§4.4.1, J2) ;
4. il mémorise le journal sous sa `request_key`, ou le déduplique (§4.4.2) ;
5. il renvoie le résultat.

#### 4.4.1 Invariants, cohérents avec le cache

Un appel au cache peut être un **échec** (la clé est absente : le cache appelle
l'adaptateur, qui appelle l'oracle) ou un **succès** (la clé est présente : le cache
répond seul). Un succès ne crée aucun journal ; il réutilise le journal créé lors de
l'échec correspondant. On ne parle donc pas de bijection entre tentatives et journaux :
plusieurs tentatives peuvent partager le même journal.

| Id | Invariant |
|---|---|
| J1, unicité | le magasin contient au plus un journal par `request_key` : le **journal canonique** de cette clé. L'adaptateur n'a qu'une configuration, donc la clé du cache (`request_key`, configuration) et celle du magasin désignent la même négociation |
| J2, concordance | pour le journal canonique `j` de la clé `k` et le résultat `o` renvoyé pour k, en cache ou non : `j.request_key = o.request_key = k`, `j.oracle_configuration_id = o.oracle_configuration_id`, `j.status = o.status`, `j.agreed_total_cents = o.agreed_total_cents` et `j.router_iterations = o.turns` (le simulateur définit `turns` comme le nombre d'itérations du routeur) |
| J3, couverture | chaque tentative du `TripPlan` (`ReferenceAttempt` ou `CoalitionAttempt`) retrouve son journal canonique par sa `request_key`, et la tentative concorde avec ce journal (statut, montant, tours) |
| J4, pas de journal superflu | chaque journal du magasin est le journal canonique d'au moins une tentative du plan |
| J5, comptage **dans le chemin normal de planification** | nombre de journaux = `cache_statistics.oracle_calls` = nombre de `request_key` distinctes parmi les tentatives ; nombre total de tentatives = `cache_statistics.requests`. Ces égalités supposent le cache placé au-dessus de l'adaptateur. La déduplication hors cache (§4.4.2), où deux appels réels à l'oracle laissent un seul journal, relève de J1 et n'est pas soumise à J5 |

**Fondement de J4 et J5 (vérifié dans le code).** Les seuls appels à l'oracle sont
`reference_costs.py:190` et `coalition_costs.py:93`. Chacun est suivi immédiatement de
l'enregistrement d'une tentative ; un appel non enregistré ne peut se produire que sur
exception, et celle-ci interrompt la planification.

Le banc d'essai P4 le confirme : à n = 14, on compte 16 397 requêtes au cache, pour
16 383 candidates et 14 références. Si une évolution future ajoutait un appel sans
tentative, J5 échouerait, et c'est voulu.

#### 4.4.2 Même `request_key` présentée deux fois à l'adaptateur sans cache

L'adaptateur ne met pas les résultats en cache, ce qui reste le rôle du cache. Il
délègue donc chaque appel à l'oracle, puis :

- **journaux identiques** (même `journal_sha256`, et résultat égal au premier) :
  **déduplication**. Le magasin garde le journal canonique déjà présent, sans le
  remplacer, et l'appel renvoie le résultat ;
- **journaux différents** : **erreur** (`NonDeterministicJournalError`). Le magasin
  n'est pas modifié, aucun résultat n'est renvoyé, et la planification s'arrête avec une
  erreur technique.

En usage normal, le cache placé au-dessus empêche ce cas. Il est tout de même spécifié
et testé, parce qu'il protège contre un déterminisme rompu et contre un mauvais
câblage.

#### 4.4.3 Lecture

Le planificateur obtient un journal par `journal_for(request_key)`, qui renvoie le
journal canonique, et seulement pour les clés de tentatives acceptées.

**Erreurs.** Toute erreur de l'oracle ou de son contrat interrompt la planification. Elle
est rapportée comme une erreur technique (code de sortie 1), et aucune proposition
partielle n'est produite.

### 4.5 Frontière de confidentialité

- **Racine de composition.** Un seul module, `infrastructure/negotiation/market.py`,
  construit `(OfferCatalog, oracle)`. Il est ajouté explicitement à l'allow-list.
- **Journaux.** Ils ne contiennent aucun plancher (vérifié dans `_make_journal`).
- **Risque résiduel, accepté et documenté.** Les contre-offres du vendeur sont visibles,
  comme dans une vraie négociation.
- **Garde JSON.** Elle refuse toute clé privée, en réutilisant le contrôle de
  `formation_report`.

### 4.6 Contrats principaux

**`PlanningInput`**

- les demandes « au premier plan » : un tuple de `request_id` et de
  `TravelRequestDraft` au statut `ready`. La CLI v1 n'en fournit qu'une (§6.3) ;
- les demandes du carnet ;
- `reference_date` ;
- `FormationLimits`.

**`TripPlan`** : interne à l'application.

- la compréhension, les unités ;
- `LotAdmissibilityResult`, `ReferenceCostsResult`, `FormationResult`,
  `AllocationResult` ;
- les journaux ;
- les statistiques du cache ;
- les compteurs et les durées de P5 ;
- la provenance.

**`TripProposal`** : vue publique pour une unité ; schéma `trip-proposal-v1`.

- le bloc `simulation` : `synthetic_catalog: true`, `simulated_sellers: true`,
  `booking: false`, et le texte d'avertissement ;
- la demande validée par l'utilisateur à l'étape de confirmation (libellé de sortie : « demande validée », §1.2) ;
- les offres admissibles et les offres rejetées, avec leurs règles ;
- les négociations solo et la référence ;
- le bloc retenu : membres anonymisés, offre, prix catalogue au palier groupé, coût
  négocié, journal ;
- la décomposition des économies ;
- l'allocation de P5 ;
- les parts par voyageur ;
- les explications ;
- la provenance.

---

## 5. Décisions après la revue

| Id | Décision | Statut | Où |
|---|---|---|---|
| ID-1 | carnet synthétique, lot pris sur le même trajet ; **mode session reporté** | validé (seconde revue) | §3.1, §6.3 |
| ID-2 | aller-retour forfaitaire | validé avec H-forfait (seconde revue) ; C1 à C6 précisées en révision 3 | §6.2 |
| ID-3 | Broker hors du nouveau chemin | validé | §3.3 |
| ID-4 | clé v2 identique octet pour octet sans les champs de trajet, v3 avec eux ; lot mixte refusé | validé avec K1 à K10 (seconde revue) | §6.4 |
| ID-5 | répartition par voyageur : gains égaux sous plafonds (projection) | reformulé en révision 2 ; R7 scindée en R7a, R7b et R7c en révision 3 ; validation à la vérification finale | §6.1 |
| ID-6 | θ_u = 0 | à confirmer au début de I2. Dans la spécification P4, D6 est listée parmi les décisions, mais §9.5 la marque « à valider en P5 » | §7, I2 |
| ID-7 | « direct de préférence » : information seulement en v1 | validé pour v1 | – |
| ID-8 | champs obligatoires : origine, destination, voyageurs, budget, fenêtre de départ, type de trajet | validé sous condition : liste complète au §6.4 | §6.4 |
| ID-9 | explications déterministes | validé | §7, I3 |
| ID-10 | confirmation avant négociation ; `--yes` explicite | validé | §7, I3 |
| ID-11 | référentiel de lieux fermé, avec alias | validé (seconde revue) | §6.5 |

---

## 6. Spécifications complémentaires

### 6.1 Répartition à l'intérieur d'une unité (ID-5)

#### Correction de la révision 1

La révision 1 disait : « parts égales par siège, projetées sous le budget de chaque
profil ; faisable car `x_u ≤ ref_u ≤ B_u = Σ b_s` ».

- **L'inégalité justifiait la faisabilité de la projection,** pas celle du partage
  égal.
- **Le contre-exemple de la revue le montre :**
  - données : budgets de 10 € et 100 €, paiement de 50 € ;
  - le partage égal (25 €, 25 €) n'est pas admissible ;
  - la projection donne (10 €, 40 €).
- **La formulation était trop elliptique** : objectif, contraintes, unicité, calcul,
  arrondi et départage n'étaient pas écrits. Les voici.

#### Données

- **unité et sièges :** une unité u, et `S` l'ensemble de ses sièges, avec
  `|S| = m = u.seats`. Chaque siège `s` est un voyageur et appartient à un profil
  `p(s)` ;
- **budgets :** `b_s` est le budget par siège du profil, en centimes entiers
  (`TravelUnit.budget_per_seat_cents`), et `B_u = Σ_s b_s = budget_total_cents` ;
- **montant à répartir :** `X = x'_u`, le paiement de l'unité donné par P5 après arrondi,
  en centimes entiers. Pour un singleton, `X = ref_u`.

#### Bornes de X (justifiées)

On a `0 ≤ X ≤ ref_u ≤ B_u` :

- **`X ≥ 0` :** l'économie arrondie vérifie `y'_u ≤ h_u = ref_u`, puisque θ = 0 ;
- **`X ≤ ref_u` :** `y'_u ≥ 0` ;
- **`ref_u ≤ B_u` :** un accord est toujours au plus égal à la réservation, qui vaut le
  budget total de l'unité. `validate_negotiation_outcome` le vérifie :
  `0 < agreed ≤ reservation`.

#### Problème (P_u), résolu en rationnels

```
minimiser    Σ_s (q_s − X/m)²
sous         Σ_s q_s = X
             0 ≤ q_s ≤ b_s   pour tout s
```

- **Interprétation.** Comme `Σ q_s = X` est fixé,
  `Σ (q_s − X/m)² = Σ q_s² − X²/m`. Être au plus près du partage égal revient donc à
  minimiser `Σ q_s²` : c'est la répartition la plus égale possible sous les plafonds.
- **Faisabilité.** L'ensemble admissible est non vide si et seulement si
  `0 ≤ X ≤ Σ b_s = B_u`. C'est vrai d'après les bornes ci-dessus.
- **Unicité.** L'objectif est strictement convexe, et l'ensemble admissible est convexe,
  compact et non vide : le vecteur `q` est unique.
- **Caractérisation par les conditions KKT.**
  - `q` est optimal si et seulement s'il existe τ tel que `q_s = min(b_s, max(0, τ))`
    pour tout s, avec `Σ q_s = X`.
  - Le Lagrangien donne `q_s = clip(X/m − μ/2, 0, b_s)`, où μ est le multiplicateur de
    la contrainte d'égalité. On pose `τ = X/m − μ/2`.
  - Comme `X ≥ 0`, on peut prendre `τ ≥ 0`, et alors `q_s = min(b_s, τ)`.
- **Lecture.** Tout le monde paie le même montant τ, sauf les voyageurs dont le budget
  est inférieur à τ : ceux-là paient exactement leur budget, et le reste est réparti à
  parts égales entre les autres. C'est la règle des **gains égaux contraints**
  (*constrained equal awards*) des problèmes de répartition, appliquée aux paiements,
  avec les budgets comme plafonds.
- **Choix de τ.** On définit `G(τ) = Σ_s min(b_s, τ)`.
  - G est continue et croissante. Elle est strictement croissante sur `[0, max b]`, avec
    `G(0) = 0` et `G(max b) = B_u`.
  - Si `X < B_u`, τ est unique dans `[0, max b)`.
  - Si `X = B_u`, tout `τ ≥ max b` convient. **Convention : `τ = max_s b_s`.** Le vecteur
    est le même dans tous les cas : `q = b`.
- **Calcul exact.** Les sièges d'un même profil sont symétriques. On calcule donc profil
  par profil :
  1. trier les profils par budget croissant `b_(1) ≤ … ≤ b_(k)`, d'effectifs `n_(i)` ;
  2. pour j = 0, 1, …, k − 1, supposer saturés les j premiers profils et poser
     `τ_j = (X − Σ_{i≤j} n_(i) b_(i)) / (m − Σ_{i≤j} n_(i))`, en `Fraction` ;
  3. retenir le premier j tel que `τ_j ≤ b_(j+1)` ;
  4. si aucun j ne convient, c'est que `X = B_u`, et τ suit la convention ci-dessus.
- **Certificat d'optimalité exact,** utilisé par les tests : q est optimal si et
  seulement si, pour tous s et t, `q_s < q_t` implique `q_s = b_s`. Sinon, déplacer ε de
  t vers s diminuerait `Σ q²`.

#### Propriétés (toutes testées)

| # | Propriété | Justification |
|---|---|---|
| R1 | `Σ q_s = X` exactement | contrainte |
| R2 | `0 ≤ q_s ≤ b_s` | contraintes |
| R3 | deux voyageurs de même budget paient le même montant | forme `min(b_s, τ)` |
| R4 | monotonie : `b_s ≤ b_t ⇒ q_s ≤ q_t` | idem |
| R5 | si `X/m ≤ min_s b_s`, alors `q_s = X/m` pour tout s (aucun plafond actif) | τ = X/m est solution |
| R6 | `q_s = b_s` si `b_s ≤ τ`, et `q_s = τ` si `b_s ≥ τ` ; les deux expressions coïncident quand `b_s = τ`, ce qui n'arrive que si τ est entier. **Définition :** un profil est *saturé* si `b_s < τ` ; il est *non saturé* si `b_s ≥ τ`, et paie alors τ | forme `min(b_s, τ)` |
| R7a | la **solution rationnelle** (τ, q) et le **multiensemble des caractéristiques des profils saturés**, c'est-à-dire des couples (budget, effectif), ne dépendent ni de l'ordre ni du nom des profils. La valeur rationnelle d'un siège ne dépend que de son budget : `q_s = min(b_s, τ)`. Le statut de saturation d'un profil donné reste attaché à son identité dans l'entrée considérée : renommer `a` en `x` change l'ensemble des identifiants saturés, mais pas ce multiensemble | le calcul n'utilise que les budgets et les effectifs |
| R7b | le **multiensemble** des montants arrondis `{q'_s}` ne dépend pas non plus du nom des profils | voir la structure de l'arrondi ci-dessous |
| R7c | en revanche, **l'attribution des centimes** à tel ou tel siège dépend de la clé de départage (`profile_id`, rang). Renommer un profil peut donc déplacer un centime d'un profil non saturé vers un autre, sans changer aucun montant du multiensemble. Permuter l'ordre d'entrée ne change rien, puisque `TravelUnit` trie ses profils par `profile_id` | règle de départage |

#### Arrondi au centime : plus fort reste, par siège

1. `q'_s = ⌊q_s⌋` ;
2. `r = X − Σ_s ⌊q_s⌋`, entier compris entre 0 et m − 1 ;
3. +1 centime aux r sièges de plus grande partie fractionnaire. Départage par
   (`profile_id`, rang du siège dans le profil) croissants.

**Preuve des bornes** (même raisonnement que la spécification §9.6) :

- `⌊q_s⌋ ≥ 0`.
- **Un siège à partie fractionnaire positive peut recevoir le centime sans dépasser son
  budget.** En effet `q_s` n'est pas entier, `q_s ≤ b_s` et `b_s` est entier, donc
  `q_s < b_s` et `⌊q_s⌋ + 1 ≤ b_s`.
- **Un siège à partie fractionnaire nulle ne reçoit jamais de centime.**
  - Les parties fractionnaires valent chacune moins de 1, et leur somme vaut r.
  - Il y a donc strictement plus de r sièges à partie fractionnaire positive, dès que
    r ≥ 1.
  - Les r centimes vont tous à des sièges de cette catégorie.
- **Résultat :** `Σ q' = X` et `0 ≤ q'_s ≤ b_s`, en entiers.
- **Conséquence :** dans un même profil, deux voyageurs peuvent différer d'au plus un
  centime. C'est documenté et affiché.

**Structure de l'arrondi** (elle justifie R7b et R7c) :

- **Sièges saturés :** `q_s = b_s`, un entier ; la partie fractionnaire est nulle.
- **Sièges non saturés :** `q_s = τ` ; ils ont tous la même partie fractionnaire,
  `frac(τ)`.
- **Si τ est entier,** r = 0 et aucun centime n'est distribué.
- **Sinon,** les sièges à partie fractionnaire positive sont exactement les sièges non
  saturés. Il y en a N, et `r = N · frac(τ)`. Exactement r d'entre eux paient `⌈τ⌉`, et
  les N − r autres paient `⌊τ⌋`.

Les montants et leur nombre d'occurrences ne dépendent donc que des budgets ; seul le
choix des r sièges dépend de la clé de départage. La même remarque vaut pour l'arrondi
de P5 au niveau des blocs (spécification §9.6, départage par `unit_id`) : en cas
d'égalité des parties fractionnaires, le centime suit l'identifiant.

#### Données conservées

- τ (rationnel) ;
- les profils saturés ;
- `q` par profil (rationnel) ;
- `q'` par siège ;
- l'écart d'arrondi.

#### Alternatives écartées

- **Partage égal non projeté :** il viole les budgets (contre-exemple de la revue).
- **Prorata des budgets** (`q_s = X·b_s/B_u`) :
  - il est admissible ;
  - mais le même siège coûte plus cher à qui a déclaré un budget plus élevé ;
  - c'est d'autant plus discutable que ce budget sert aussi de réservation dans la
    négociation P3.

#### Tests prévus

- **Contre-exemple de la revue :** budgets (1 000, 10 000), X = 5 000, résultat attendu
  (1 000, 4 000).
- **Cas limites :** X = 0, X = B_u, un seul profil, tous les budgets égaux, profils à
  effectifs inégaux.
- **Propriétés R1 à R7c** et certificat exact sur au moins 1 000 unités aléatoires
  (m ≤ 20, budgets et X tirés dans le domaine).
- **Arrondi :** bornes vérifiées, départage déterministe, invariance par permutation de
  l'ordre d'entrée.
- **Renommage** (test dédié à R7) : on renomme les profils d'une unité et l'on vérifie
  que :
  - τ est identique, chaque profil renommé a la même valeur rationnelle que le profil
    d'origine, et le multiensemble des couples (budget, effectif) des profils saturés
    est identique. On compare ce multiensemble, pas l'ensemble des identifiants (R7a) ;
  - le multiensemble des `q'` est identique (R7b) ;
  - au moins un cas construit montre une attribution des centimes différente, le
    déplacement restant limité aux sièges non saturés (R7c). Ce cas est écrit
    explicitement :
    - données : profils `a` (1 siège, budget 10 000) et `b` (1 siège, budget 20 000),
      X = 3 001 ;
    - calcul : τ = 1 500,5, les deux profils sont non saturés, et r = 1 ;
    - avant le renommage, `a` paie 1 501 et `b` paie 1 500 ;
    - après échange des noms, le siège de budget 20 000 paie 1 501.

    Les budgets diffèrent volontairement : deux profils de contraintes identiques
    seraient fusionnés par `consolidate_profiles` lors de `build_travel_unit`.
- **Mutants :**
  - partage égal sans plafonds ;
  - prorata ;
  - arrondi à l'entier inférieur sans reste ;
  - départage inversé ;
  - τ calculé avec le mauvais effectif.

### 6.2 Forfait aller-retour (ID-2)

#### Structure d'une offre forfaitaire du catalogue v2

| Champ | Sens |
|---|---|
| `origin`, `destination` | trajet aller ; le retour fait le trajet inverse |
| `outbound.departure_date`, `outbound.arrival_date`, `outbound.direct`, `outbound.capacity_seats`, `outbound.leg_ref` | jambe aller |
| `return.departure_date`, `return.arrival_date`, `return.direct`, `return.capacity_seats`, `return.leg_ref` | jambe retour (absente pour un aller simple) |
| `capacity_seats` | **capacité effective du forfait**, seule utilisée par P2, H2, P3 et la clé |
| `tiers` | prix par siège **pour le forfait entier**, et planchers privés par palier |

#### Type de trajet d'une offre

Le type de trajet d'une offre **se déduit** de la présence du bloc `return` ; il n'est
pas stocké dans un champ séparé, qui pourrait contredire le bloc :

- `round_trip` si le bloc `return` est présent et complet ;
- `one_way` s'il est entièrement absent.

Un bloc `return` partiel est refusé.

#### Règles de validation au chargement

| # | Règle | Aller simple | Aller-retour |
|---|---|---|---|
| C1 | ordre des dates | `outbound.departure_date ≤ outbound.arrival_date` seulement | `outbound.departure_date ≤ outbound.arrival_date ≤ return.departure_date ≤ return.arrival_date` |
| C2 | capacité effective, seule utilisée par P2, H2, P3 et la clé | `capacity_seats = outbound.capacity_seats` | `capacity_seats = min(outbound.capacity_seats, return.capacity_seats)` |
| C3 | `OfferQuote.direct`, calculé par le lecteur (il ne fait pas confiance à un champ redondant) | `outbound.direct` | `outbound.direct ∧ return.direct` : tous les segments des deux jambes sont directs |
| C4 | paliers | le dernier palier commence au plus à `capacity_seats` | idem |
| C5 | forme canonique des `leg_ref` | voir ci-dessous | idem |
| C6 | unicité des `leg_ref` dans tout le catalogue | voir ci-dessous | idem |

Dans tous les cas, le lecteur refuse un écart à C2 au lieu de le corriger.

#### Identifiants de jambe `leg_ref`

- **Ce que désigne un `leg_ref` :** une jambe, c'est-à-dire un vol fictif à une date,
  sur laquelle un forfait détient un contingent.
- **Forme canonique, contrôlée au chargement (C5) :**
  - format `<FOURNISSEUR>-<NUMÉRO>-<AAAAMMJJ>`, en majuscules ASCII, chiffres et
    tirets ; expression régulière `^[A-Z0-9]{2,12}-[0-9]{1,5}-[0-9]{8}$` ;
  - le suffixe de date doit égaler la `departure_date` de la jambe ;
  - aucune normalisation n'est appliquée : une variante (minuscules, espaces, autre
    séparateur) est **refusée**, et non convertie. Deux écritures d'une même jambe ne
    peuvent donc pas passer pour deux jambes différentes.
- **Unicité, contrôlée au chargement (C6) :** chaque `leg_ref` apparaît au plus une
  fois dans tout le catalogue. Cela couvre deux cas :
  - deux forfaits ne déclarent jamais la même jambe ;
  - à l'intérieur d'un aller-retour, `outbound.leg_ref ≠ return.leg_ref`.

#### Hypothèse H-forfait : les capacités sont indépendantes d'un forfait à l'autre

- **Le principe.** Chaque forfait dispose de son propre contingent de sièges sur chacune
  de ses jambes.
- **Pourquoi c'est nécessaire.** Si deux forfaits partageaient une même jambe (même vol
  aller, retours différents), leurs capacités seraient couplées. H2, vérifiée offre par
  offre, ne suffirait plus.
- **Comment on la garantit.** Par C5 et C6. Les contingents de groupe dédiés sont un
  modèle courant en tarification de groupe ; pour nous, c'est une hypothèse de
  simulation explicite.

#### Admissibilité v2 : nouvelles règles de la politique `NON_FINANCIAL_V2`

| Règle | Violation |
|---|---|
| origine | `origin_mismatch` (testée avec la destination) |
| type de trajet | `trip_type_mismatch` (aller-retour demandé contre une offre sans retour, ou l'inverse) |
| départ aller, borne haute (`departure_before`) | `departure_after_window` : l'offre part après la fin de la fenêtre. Ce code s'ajoute au code existant `departure_before_window`, qui correspond à la borne basse `departure_after` |
| départ retour (`return_after`, `return_before`) | `return_before_window` (départ du retour avant la fenêtre), `return_after_window` (après la fenêtre) |

Les noms suivent la convention existante : le code dit où se situe l'offre par rapport à
la fenêtre.

Les autres règles sont reprises sans modification. Le registre v1 n'est pas modifié.

### 6.3 Mode démonstration et mode session (ID-1)

- **Version 1, mode démonstration (seul mode livré) :**
  - une demande saisie par l'utilisateur, plus le carnet synthétique versionné (v1 en
    I1, v2 en I4) ;
  - le lot réunit les demandes du même trajet ;
  - le résultat est reproductible, puisque le carnet est figé par son manifeste.
- **Mode session : reporté après I5,** et non présenté comme inclus. Ce qu'on en
  retient dès maintenant :
  - chaque demande de la session passe séparément par l'extraction, la clarification
    et la confirmation ;
  - les identifiants sont `session-01`, `session-02`, etc. ;
  - le lot réunit les demandes de la session, avec en option celles du carnet, sur le
    même trajet ;
  - chaque demande reçoit son propre `TripProposal`.
- **Ce qui est préparé dès I1.** `PlanningInput` accepte un tuple de demandes au premier
  plan, testé avec une et deux demandes. Le mode session ne demandera donc qu'un
  changement de la CLI, sans toucher à l'architecture.

### 6.4 Matrice de compatibilité des clés v2 et v3 (ID-4, ID-8)

#### Identités concernées, avec la même règle conditionnelle pour toutes

- `request_key` (`request_key_content`) ;
- `unit_economic_digest` (entre dans `admissibility_id`) ;
- `unit_fingerprint` (P1.3).

**Ce que contient déjà v2 :**

- côté offre : `offer_id`, `catalog_version`, fournisseur, destination, dates, `direct`,
  capacité, paliers ;
- côté unité : destination, et par profil le budget, `departure_after`, `arrival_before`,
  `direct_flight`, les exclusions.

#### Champs ajoutés en v3

| Côté | Champ | Normalisation |
|---|---|---|
| demande et unité | `origin` | lieu résolu (§6.5), puis `normalize_destination_key` |
| demande et unité | `trip_type` | littéral fermé |
| profil (valeur effective, après héritage) | `departure_before`, `return_after`, `return_before` | ISO, ou `null` |
| offre | `origin` | comme ci-dessus |
| offre | jambes : dates, `direct`, `capacity_seats`, `leg_ref` | ISO, booléen, entier, chaîne exacte |

**Choix prudent : toutes les données publiques d'une offre entrent dans la clé.** Une
clé trop fine coûte au pire quelques succès de cache ; une clé trop grossière donnerait
des résultats faux.

#### Tests

Chaque test porte sur **chacune** des trois identités et sur **chacun** des champs du
tableau.

| Test | Énoncé |
|---|---|
| K1, absence | entrées v1, sans champ de trajet : document v2 identique octet pour octet. Toutes les empreintes figées restent inchangées : `ae759f83…` de `test_negotiation_request_key.py`, empreintes P1.3, `admissibility_id`, `formation_run_id` et `result_sha256` du lot figé, empreinte exploratoire P4 `997109ee…` |
| K2, sensibilité | pour chaque champ f, deux entrées qui ne diffèrent que par f ont des clés v3 différentes |
| K3, normalisation | `" Lyon"`, `"LYON"`, `"lyon"` et la forme NFD ou NFC donnent la même clé ; un alias résolu (`Algiers` → `Alger`) aussi |
| K4, absence de valeur | un champ omis dans le JSON de la demande et un champ explicitement `null` donnent la même clé |
| K5, héritage | une fenêtre héritée de la demande et la même fenêtre surchargée par le profil donnent la même clé, puisque la clé porte sur la valeur effective |
| K6, invariances | renommer les identifiants, permuter les profils ou découper un profil en parties identiques ne change pas la clé (propriétés v2 étendues) |
| K7, séparation des trajets | deux demandes économiquement identiques sur des trajets différents n'ont jamais la même clé |
| K8, étiquette | un document v3 contient `negotiation-request-key-v3`, et un document v2 ne contient jamais de champ de trajet |
| K9, lot mixte | une unité v1 et une unité v2 dans le même lot : `LotInputError`. Une unité v2 contre une offre v1 aussi |
| K10, propriété | sur des combinaisons aléatoires de champs, deux entrées ont la même clé si et seulement si leurs documents canoniques sont égaux |

### 6.5 Référentiel de lieux fermé (ID-11, ajouté par Claude)

- **Le constat.** `normalize_destination_key` ne fait que normaliser (NFC, espaces,
  casse) ; elle n'applique aucun alias. Le prompt système de l'extracteur est en
  anglais : le modèle peut donc renvoyer « Algiers » pour « Alger ». La demande ne
  trouverait alors aucune offre, alors qu'il s'agit seulement d'une différence de
  langue.
- **La proposition :**
  - un fichier `data/catalog/places_v1.json`, versionné avec son manifeste, qui associe
    chaque lieu du catalogue v2 à ses alias (Alger, Algiers, ALG…) ;
  - une résolution applicative **avant** `build_travel_unit` ;
  - un lieu inconnu déclenche une clarification qui liste les lieux disponibles ;
  - le prompt v2 demande de recopier les noms de lieux tels qu'ils sont écrits.
- **Portée.** Ce n'est pas le normaliseur général prévu plus tard (P7) : ce référentiel
  est limité aux lieux du catalogue. Le chemin v1 n'est pas touché.

---

## 7. Plan d'implémentation

**Règles communes :**

- chaque étape est revue et acceptée avant que la suivante commence ;
- on ne confie jamais plusieurs étapes à Codex en une seule fois ;
- chaque étape se termine par :
  - un rapport dans `docs/` ;
  - la suite complète, avec `PYTHONHASHSEED` 0 et 2 ;
  - la compatibilité Python 3.10 ;
  - le golden master ;
  - ruff ;
  - les mutants propres à l'étape ;
- I4 ne peut avancer en parallèle de I2 qu'au niveau de la conception et de tests
  isolés. On ne modifie jamais en même temps les contrats P1/P2 et l'orchestration I1.

### I0 : stabilisation (sans code et sans opération Git)

1. terminer la revue finale de P4 ;
2. vérifier les rapports et les modifications réellement présentes dans l'arbre de
   travail ;
3. dresser la liste exacte des fichiers de P2, de P3 et de P4, et celle des fichiers
   personnels exclus ;
4. **obtenir l'autorisation explicite de l'utilisateur** avant toute opération Git (add,
   commit, reset, stash, ou autre). La revue technique et l'autorisation Git sont deux
   décisions distinctes ;
5. ensuite seulement, commencer I1.

Ollama n'est pas nécessaire à cette étape.

### I1 : orchestration (3H, première partie) sur le catalogue v1

**Réutilisés :**

- `build_travel_unit`, `lot_admissibility`, `compute_reference_costs`,
  `form_coalitions` ;
- `CachingNegotiationOracle`, `validate_negotiation_outcome` ;
- `SimulatedNegotiationOracle.negotiate_detailed` ;
- `load_offer_catalog`.

**Nouveaux :**

- `infrastructure/negotiation/journaling_oracle.py` (§4.4) ;
- `infrastructure/negotiation/market.py`, ajouté à l'allow-list ;
- `infrastructure/demand/demand_pool.py`, et `data/demand/demand_pool_v1.jsonl` avec son
  manifeste ;
- `application/trip_planning.py` : `plan_lot(PlanningInput, market) -> TripPlan` ;
- `run_formation_stages` (§4.3).

**Tests du cache et des journaux** (`test_journaling_oracle.py`, `test_trip_planning.py`) :

| Cas | Attendu |
|---|---|
| absence dans le cache | un appel à l'oracle et un journal canonique, conforme à J2 |
| présence dans le cache | aucun nouvel appel, aucun nouveau journal. `journal_for(request_key)` renvoie le journal canonique créé lors de l'échec (même objet, même `journal_sha256`), et ce journal est conforme à J2 avec le résultat mis en cache |
| même clé deux fois, sans cache, journaux identiques | déduplication : deux appels à l'oracle, un seul journal ; le journal canonique est conservé (identité de l'objet vérifiée) |
| même clé deux fois, sans cache, journaux différents (faux oracle non déterministe) | `NonDeterministicJournalError` ; magasin inchangé ; aucun résultat renvoyé |
| journal incohérent (faux oracle : autre clé, autre statut, autre montant, autre configuration, autre nombre de tours) | erreur ; rien n'est mémorisé, ni journal ni entrée de cache |
| résultat contraire au contrat (montant supérieur à la réservation) | refusé par l'adaptateur **avant** la mémorisation ; aucun journal orphelin |
| exception de l'oracle | aucun journal, aucune entrée de cache ; la planification échoue avec une erreur technique, sans proposition partielle |
| invariants J1 à J5 | vérifiés sur le lot figé et sur des lots de la strate exploratoire, planifiés par `plan_lot` avec le cache, donc dans le chemin normal. J5 est vérifié avec ses trois égalités. Le cas de déduplication hors cache est couvert par la ligne qui lui est consacrée ci-dessus (J1) |

**Tests de non-régression** : le lot figé passé par `plan_lot` est comparé à
`run_formation_pipeline`, **champ par champ**, et pas seulement par les totaux :

- blocs : unités, offre, sièges, référence, coût, valeur ;
- composantes : statut, nombre de candidates, de coalitions faisables et de négociations,
  valeurs du jeu, structure, méthode, contre-vérifications ;
- `evaluations` : égalité complète, tentative par tentative ;
- `unserved`, `unresolved_unit_ids`, totaux ;
- `cache_statistics` : requêtes, succès, appels réels ;
- `formation_run_id`, `result_sha256`.

**Autres tests :**

- statuts H2, `no_admissible_offer`, `no_solo_reference`, `request_rejected` ;
- `PlanningInput` avec une puis deux demandes au premier plan ;
- carnet : lecture stricte, manifeste, au plus 13 demandes par trajet, H2 tenu avec la
  plus grande demande admise (20 sièges).

**Critères d'acceptation :**

- les 662 tests existants passent. Seule exception : l'entrée `market.py` de
  l'allow-list ;
- l'empreinte exploratoire P4 `997109ee…` est reproduite ;
- aucun appel d'oracle en plus.

### I2 : P5, répartition des économies

**Préalable :** confirmer ID-6 (θ_u = 0) dans un addendum à la spécification.

**Réutilisés :**

- `CoalitionGame` (valeurs de F) et `cover_values` ;
- `FormedBlock` ;
- les budgets par siège ;
- `shapley_value`, en test seulement.

**Nouveaux :**

- `domain/savings_allocation.py`, des mathématiques pures :
  - Shapley exact, avec une **somme entière** sur le dénominateur `n!` :
    `φ_u = (1/n!) Σ_S |S|!(n−|S|−1)! [v*(S∪u) − v*(S)]`. Le numérateur est un entier
    exact, et l'on ne crée qu'une seule `Fraction` par joueur ;
  - projection par les conditions KKT, avec λ* ;
  - plus fort reste ;
  - gains égaux sous plafonds (§6.1).
- `application/savings_allocation.py` : version `p5-allocation-v1`, avec compteurs et
  durées.

**Performance : où l'on recalcule, et comment l'éviter.**

- **Les tables des solveurs P4 ne sont pas réutilisables,** et ceci précise une
  proposition de la revue.
  - Les fonctions historiques ne les exposent pas (spécification P4, correction 4).
  - Elles calculent sur `w = K·v − (|C| − 1)` avec pénalité, et non sur `v*`
    (spécification §3.4).
  - Ce que P4 fournit et que P5 réutilise, ce sont les **valeurs `v` de F**. C'est cela
    qui garantit zéro appel d'oracle.
- **Mémoire locale des couvertures :** `CoverCache`, propre à une exécution de P5, avec
  des entrées indexées par (`component_id`, sous-ensemble).
  - **Lemme :** pour `S ⊆ bloc ⊆ composante`, `v*` calculé sur la composante et `v*`
    calculé sur le bloc coïncident en S, car `v*(S)` ne dépend que de `F ∩ 2^S`.
  - Si l'explication `alone_social_optimum` (I3) a déjà calculé la couverture de la
    composante, P5 en extrait celle du bloc sans recalcul. Sinon, P5 calcule la
    couverture du bloc seul, en Θ(3^k).
  - Les blocs sont disjoints : P5 ne calcule donc jamais deux fois la même couverture.
- **Compteurs :** nombre de couvertures calculées, masques visités, contributions
  marginales évaluées. Les tests vérifient ces compteurs.
- **Durées mesurées séparément :** couverture, Shapley, projection, arrondi, répartition
  par voyageur.

**Protocole de mesure.** On reprend celui de la strate de performance P4 : un
échauffement, puis 5 répétitions, médiane et intervalle.

**Ce que mesure exactement la valeur P4 de 6,63 s.** C'est la « durée totale par
taille » du rapport de performance P4 (`docs/p4_results/performance_report.md`) :

- elle mesure le pipeline P4 **complet** sur un lot de 14 unités formant une seule
  composante : admissibilité, références, énumération, faisabilité, négociations, jeu,
  solveur `idp` et contre-vérification `dp` ;
- c'est une médiane de 50 mesures (10 instances × 5 répétitions), sur la machine décrite
  au §9.1 du rapport d'implémentation, et elle est volatile ;
- ce n'est **pas** une durée de formation d'une composante isolée de ces étapes.

Le présent plan l'appelle donc **`T_P4_total`**.

**Comparateur retenu : `T_P4_total` remesuré dans la même session.** On ne compare pas
à la valeur archivée, qui dépend de la machine et de sa charge. On régénère les
10 instances de 14 unités de la strate de performance avec les mêmes graines, et on
mesure `T_P4_total` selon le même protocole, dans la même exécution que les mesures
de P5. La valeur archivée de 6,63 s n'est citée que comme ordre de grandeur de cette
même métrique.

| Mesure | Objet |
|---|---|
| M0, comparateur | `T_P4_total(14)` : pipeline P4 complet sur les 10 instances de 14 unités de la strate de performance, mêmes graines, même protocole |
| M1, micro | `T_P5` sur des blocs denses (toutes les sous-coalitions faisables, grande coalition optimale), k = 2 à 14. Jeux construits directement, sans négociation ; durées séparées par sous-étape |
| M2, lot représentatif | les 1 616 instances à blocs de la strate exploratoire P4, régénérées avec les mêmes graines (script séparé `evaluate_allocation.py`). Pour chaque instance, on mesure dans la même exécution `T_P4_total(instance)` et `T_P5(instance)`. On rapporte la médiane, le 95e centile et le maximum de `T_P5`, du rapport `T_P5 / T_P4_total` et de la taille des blocs |
| M3, bout en bout | le lot de démonstration, avec les durées par étape de la CLI |

**Seuils proposés, à valider avant la première mesure et non après :**

- M1 : `T_P5` médian du bloc dense k = 14 est **inférieur à la médiane de
  `T_P4_total(14)` mesurée en M0** dans la même session. Le critère se lit ainsi :
  « l'allocation du pire bloc coûte moins que tout le pipeline P4 d'un lot de même
  taille ». Il ne dit pas que P5 est plus rapide que la seule formation ;
- M2 : la médiane du rapport `T_P5 / T_P4_total` par instance est au plus de 0,25.

Une durée isolée de P4 (par exemple solveur et contre-vérifications seuls) n'est pas
utilisée comme comparateur. Si l'équipe préfère ce comparateur, il faudra le mesurer
explicitement à partir des durées par phase, en le nommant différemment.

Si un seuil n'est pas atteint, on optimise P5 avant l'acceptation, par exemple avec une
couverture par masques de bits, testée différentiellement contre `cover_values`. On ne
relâche jamais une limite sans le dire.

**Tests :**

- exemples de la spécification : (4, 4, 1), et (300, 300, 300) avec projection ;
- propriétés de la spécification §9.4 à §9.6, en exact, sur au moins 300 jeux ;
- écart avec `shapley_value` d'au plus 1e-6 × max(1, |V|) ;
- un singleton paie `ref_u` ;
- zéro appel d'oracle ;
- les tests du §6.1 ;
- allocation du lot figé, calculée une fois, expliquée, puis figée ;
- mutants :
  - Shapley calculé sur `v` au lieu de `v*` ;
  - signe de λ inversé ;
  - projection omise ;
  - arrondi à l'entier inférieur ;
  - poids de Shapley décalé de un ;
  - mutants du §6.1.

**Critères d'acceptation :**

- propriétés exactes vérifiées ;
- mutants tués ;
- mesures M0, M1 et M2 rapportées dans la même session, avec les seuils atteints.

### I3 : présentation, explications et CLI (3H, seconde partie)

**Nouveaux :**

- `application/trip_proposal.py` ;
- `infrastructure/presentation/` : `explanations_fr.py`, `text_renderer.py`,
  `json_renderer.py` ;
- `plan_travel_request(...)` dans `travel_workflow.py`, à côté de
  `process_travel_request`, qui ne change pas ;
- `Multi-Agent/plan_trip.py`, avec le script `coalition-travel-plan`. La commande
  propose :
  - `--prompt`, ou la saisie interactive ;
  - `--draft-json` ;
  - une clarification d'au plus 3 tours ;
  - une confirmation, ou `--yes` explicite ;
  - `--json` ;
  - `--reference-date` ;
  - des codes de sortie : 0 = proposition, 2 = clarification requise, 3 = demande
    invalide, 1 = erreur technique.

**Avertissement de simulation :**

- en tête de la sortie texte : le texte exact fixé au §1.2 ;
- dans le JSON : le bloc `simulation` (§4.6), qui contient le même texte ;
- vocabulaire et règle de test fixés au §1.2 (mots entiers, formes fléchies, aucune
  exception pour les phrases négatives).

**Codes d'explication (liste fermée) :**

| Code | Source | Message, en substance |
|---|---|---|
| `needs_clarification` | validation | champs manquants, et la question posée |
| `unknown_place` | référentiel des lieux (§6.5) | lieu inconnu ; liste des lieux disponibles |
| `offer_rejected` | P2, violations | règle violée |
| `direct_preference_not_met` | P2, note | escale retenue ; écart de prix avec la meilleure option directe |
| `no_admissible_offer` | P2 | aucune offre ne respecte les contraintes |
| `no_solo_reference` | P3 | aucune négociation n'a abouti ; le plancher n'est jamais cité |
| `served_in_coalition` | P4 + P5 | membres, offre, économie, part |
| `alone_no_beneficial_coalition` | P4 | aucune coalition qui contient l'unité n'a de valeur positive (décompte par cause) |
| `alone_social_optimum` | P4 | une coalition avantageuse existait, mais l'optimum global est meilleur. Pour les trois meilleures coalitions C, on compare `v(C) + v*(composante \ C)` à V* (couverture mise en mémoire, §7 I2) |
| `component_too_large` | P4 | limite opérationnelle de 14 unités |
| `capacity_model_violated` | P2, H2 | capacité d'une offre dépassée |
| `projection_active` | P5 | la part de Shapley a été plafonnée |
| `budget_cap_active` | §6.1 | des voyageurs paient leur budget, et le reste est réparti entre les autres |

**Tests :**

- un test par code d'explication ;
- schéma JSON, et sortie identique octet pour octet à entrée égale (hors durées) ;
- aucune clé privée ;
- anonymisation des autres demandes ;
- avertissement de simulation présent, et vocabulaire interdit absent (en texte comme en
  JSON) ;
- CLI testée par sous-processus : `--draft-json`, extracteur factice, entrée standard
  scriptée, codes de sortie ;
- les tests de `process_travel_request` sont inchangés.

**Critères d'acceptation :**

- sur le lot figé, les neuf éléments du §1.3 sont affichés ;
- chaque unité a un statut et ses codes ;
- chaque montant vient d'un champ typé.

### I4 : Lyon-Alger, catalogue v2 et référentiel des lieux

**Contrats étendus,** par ajout seulement :

- `TravelRequestDraft` : `origin`, `departure_before`, `return_after`, `return_before`,
  `trip_type` ;
- profils : fenêtres de dates ;
- `TravelUnit` : `origin_key`, `trip_type` ;
- `OfferQuote` : `origin`, jambes (§6.2).

**Nouveaux :**

- `NON_FINANCIAL_V2` ;
- clés v3 conditionnelles (§6.4) ;
- lecteur du catalogue v2 (règles C1 à C6, H-forfait) ;
- `catalog_v2.json`, avec des fournisseurs fictifs ;
- `places_v1.json` (§6.5) ;
- carnet v2 ;
- prompt `travel-request-extraction-v2` ;
- jeu `request_extraction_v3.jsonl`, qui contient l'exemple de référence.

**Règle de calibration.** Le catalogue v2 et le carnet v2 sont figés par leur manifeste
**avant** la première exécution de recette, et ne sont jamais ajustés après coup.

**Tests :**

- matrice K1 à K10 ;
- C1 à C6 et H-forfait au chargement, avec un aller simple et un aller-retour pour chaque règle ; refus d'un bloc `return` partiel, d'un `leg_ref` non canonique, d'une date de suffixe incohérente et d'un `leg_ref` dupliqué entre deux forfaits ou à l'intérieur d'un forfait ;
- un test par règle v2 ;
- les alias du référentiel des lieux ;
- `--validate-only` sur le jeu v3 ;
- bout en bout avec `--draft-json` sur Lyon-Alger.

**Critères d'acceptation :**

- l'exemple Lyon-Alger, fourni sous forme structurée, produit une proposition complète ;
- la non-régression v1 est prouvée par K1.

### I5 : Ollama, recette finale et documentation

- **Installation et modèle :** installer Ollama, puis choisir le modèle par la mesure
  (exact-match par champ sur le jeu v3).
- **Index RAG :** construit à partir du corpus synthétique existant.
- **Recette :**
  - le prompt de référence est exécuté 5 fois, avec une température de 0 et une graine
    fixe ;
  - attendus : la même demande structurée et le même JSON (hors durées) ;
  - la clarification est testée en direct ;
  - la latence est mesurée par étape.
- **Documentation :** une section « Lancer le prototype » dans le README, vérifiée en la
  suivant pas à pas à partir d'un clone propre.

---

## 8. Définition de « terminé »

1. `coalition-travel-plan`, lancé sur l'exemple Lyon-Alger avec Ollama, affiche les neuf
   éléments du §1.3. Il annonce une **proposition simulée** et écrit un JSON
   `trip-proposal-v1` valide.
2. Une demande incomplète, ou un lieu inconnu, déclenche une question. Une demande sans
   coalition avantageuse reçoit une explication chiffrée.
3. Chaque montant provient du catalogue, de P3, de P4 ou de P5. Aucun ne provient du LLM
   ni du RAG.
4. **Invariants contrôlés à chaque exécution :**
   - `Σ paiements du bloc = coût négocié` ;
   - `0 ≤ paiement ≤ référence ≤ budget` pour l'unité ;
   - `0 ≤ part ≤ budget` pour chaque voyageur ;
   - chaque tentative retrouve le journal canonique de sa `request_key` (J3). Dans le
     chemin normal de planification, le nombre de journaux est égal au nombre d'appels
     réels à l'oracle et au nombre de clés distinctes des tentatives (J5). La
     déduplication du §4.4.2 n'intervient que hors cache ; elle conserve un seul
     journal canonique par clé (J1).
5. La sortie ne contient aucun plancher ni clé privée. L'allow-list n'est modifiée que
   pour la racine de composition.
6. Golden master identique. Les 662 tests existants passent, avec `PYTHONHASHSEED` 0 et
   2, sous Python 3.10 et 3.14. L'empreinte exploratoire P4 est reproduite. Les
   mesures M0 à M3 sont rapportées.
7. On installe et on lance le prototype en suivant uniquement le README.

---

## 9. Ce qui est vérifié, et ce qui reste à mesurer

**Vérifié** (lecture du code et commandes locales) :

- champs de `TravelRequestDraft` ;
- absence d'origine et de retour ;
- une demande donne une seule unité ;
- `negotiate=False` dans le chemin cohorte du Broker ;
- le cache garde le résultat sans le journal ;
- le journal ne contient pas de plancher ;
- `ComponentFormation.game` est conservé ;
- `cover_values` est en Θ(3^m) et n'est pas appelé en dehors des tests ;
- `run_formation_pipeline` n'est appelé que par `evaluate_formation.py` ;
- `validate_negotiation_outcome` impose `0 < accord ≤ réservation` ;
- la clé v2 contient `offer_id` ;
- `normalize_destination_key` n'applique aucun alias ;
- Ollama est absent ;
- 662 tests sont collectés.

**À mesurer :**

- M0 à M3 ;
- la latence de bout en bout ;
- la qualité d'extraction du modèle retenu, en particulier pour les lieux et les dates
  de retour.

---

## 10. Historique des révisions

### 10.0 Révision 4 : réponse à la troisième revue

Seuls les trois points demandés sont corrigés. Aucun fichier de code n'est modifié, et
I1 n'est pas lancé.

| Point de la revue | Traitement |
|---|---|
| 1.1, R7a : l'ensemble des identifiants saturés n'est pas invariant par renommage | **Accepté.** R7a porte maintenant sur τ, q et le multiensemble des couples (budget, effectif) des profils saturés. Le statut d'un profil reste attaché à son identité dans l'entrée (§6.1). Le test de renommage compare ce multiensemble, et non l'ensemble des identifiants |
| 1.2 : « billet », mot interdit, figurait dans l'avertissement obligatoire | **Accepté**, avec la solution préférée par la revue : l'avertissement est reformulé sans mot interdit (§1.2). Deux pièges de la même règle sont corrigés au même endroit : « émission » contient la sous-chaîne « émis », et « demande confirmée » est une forme fléchie de « confirmé ». La règle devient donc un test sur des **mots entiers**, avec les formes fléchies et sans exception pour les phrases négatives. L'étape de confirmation s'affiche « demande validée ». Le test vérifie le refus de chaque mot interdit et l'acceptation de l'avertissement exact |
| 1.3 : « un journal par appel réel à l'oracle » (§8) contredisait la déduplication | **Accepté.** Le point 4 du §8 reprend la formulation de la revue : J3 pour les tentatives, J5 dans le chemin normal, J1 sous déduplication |
| Complément de la revue : portée de J5 dans le tableau du §4.4.1 | **Accepté.** J5 est restreint explicitement au chemin normal de planification, avec le cache au-dessus de l'adaptateur. La déduplication hors cache du §4.4.2 relève de J1. Rien ne change dans l'architecture ni dans les tests prévus |

### 10.1 Révision 3 : réponse à la seconde revue

| Point de la revue | Traitement |
|---|---|
| ID-5, R7 : contradiction entre l'invariance par renommage et le départage par `profile_id` | **Accepté.** R7 est scindée (§6.1). R7a : la solution rationnelle (τ, q, profils saturés) est invariante. R7b : le multiensemble des montants arrondis l'est aussi, car seuls les sièges non saturés ont une partie fractionnaire positive, toujours `frac(τ)`. R7c : l'attribution des centimes dépend de la clé de départage. Un test de renommage est ajouté, avec un cas construit où l'attribution change. La même remarque est faite pour l'arrondi de P5 par `unit_id` |
| ID-2, C1 : dates selon le type de trajet | **Accepté.** Le type de trajet se déduit de la présence du bloc `return`, et un bloc partiel est refusé. C1, C2 et C3 sont conditionnelles : aller simple = jambe aller seule ; aller-retour = ordre des quatre dates (§6.2). `leg_ref` a une forme canonique stricte, refusée et non normalisée, avec contrôle du suffixe de date (C5). Son unicité est contrôlée dans tout le catalogue, entre forfaits et à l'intérieur d'un forfait (C6) |
| I1, journaux : la « bijection » est incompatible avec le cache | **Accepté.** Remplacée par les invariants J1 à J5 (§4.4.1) : journal canonique unique par clé, concordance (y compris `turns = router_iterations`), couverture des tentatives, absence de journal superflu, comptages. J4 et J5 reposent sur une vérification du code : chaque appel à l'oracle est immédiatement enregistré comme tentative. Même clé sans cache : déduplication si les journaux sont identiques, `NonDeterministicJournalError` sinon (§4.4.2) |
| I2, M1 : référence des 6,63 s | **Accepté.** Cette valeur est la durée totale du pipeline P4 pour n = 14 (rapport de performance, « Durée totale par taille »), et non une durée de formation isolée. Elle est renommée `T_P4_total`. Le comparateur est remesuré dans la même session (M0). Le critère M1 est reformulé contre `T_P4_total(14)`, et M2 utilise le rapport `T_P5 / T_P4_total` par instance |

### 10.2 Révision 2 : réponse à la première revue

| Point de la revue | Traitement |
|---|---|
| ID-5 : répartition non définie | **Accepté.** Définition complète au §6.1 : problème, faisabilité, unicité, conditions KKT, calcul exact, certificat, arrondi, tests. Le contre-exemple réfute le partage égal *non projeté*. La révision 1 proposait déjà la projection, mais sans l'écrire formellement |
| ID-2 : capacité du forfait | **Accepté** et complété : `capacity = min` (C2), conjonction pour `direct` (C3), ordre des dates (C1), et l'hypothèse H-forfait (contingents non partagés), sans laquelle H2 ne suffirait plus |
| ID-1 : mode session | **Accepté :** reporté explicitement après I5 (§6.3). L'API l'anticipe déjà, sans coût |
| ID-4 : tests des clés | **Accepté :** matrice K1 à K10 (§6.4), portant sur chaque champ et sur les trois identités |
| P5 : performance | **Accepté** avec une précision : les tables des solveurs P4 ne sont pas réutilisables. On réutilise les valeurs `v`, et une mémoire des couvertures fondée sur un lemme de restriction. Compteurs, durées séparées, mesures M1 à M3, seuils fixés avant la mesure |
| I0 : revue et Git | **Accepté :** ordre en cinq étapes ; aucune opération Git sans autorisation explicite |
| I1 : cache et journaux | **Accepté** et renforcé : l'adaptateur valide avec la fonction du cache avant de mémoriser, ce qui empêche les journaux orphelins. Sept cas testés, non-régression champ par champ |
| Ordre et parallélisme | **Accepté :** une étape à la fois ; I4 en parallèle seulement pour la conception |
| Proposition simulée | **Accepté :** §1.2, avertissement et bloc `simulation`, vocabulaire testé |
| Ajout de Claude | ID-11, référentiel de lieux fermé (§6.5) : sans lui, « Alger » extrait en « Algiers » ferait échouer l'exemple de référence |
