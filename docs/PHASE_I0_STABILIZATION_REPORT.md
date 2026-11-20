# I0 : rapport de stabilisation

**Statut : I0 clôturée techniquement par la revue de ChatGPT** (2026-11-19).

- **Portée de la clôture.** ChatGPT n'a pas exécuté les commandes lui-même : la clôture
  porte sur les résultats rapportés ici.
- **I1 :** non autorisée.
- **Opérations Git :** non autorisées.
- **Réserves.** Elles restent ouvertes et seront traitées dans leurs phases : arrondis
  P3, ID-6, durées variables.

**Date :** 2026-11-19.

**Cadre :** la validation documentaire de la révision 4 de
`docs/PHASE_3H_P5_INTEGRATION_PLAN.md` donne un feu vert limité aux vérifications d'I0.

**Ce rapport n'autorise rien :**

- aucune opération Git ;
- aucun démarrage d'I1.

Ces deux décisions restent distinctes et demandent un accord explicite.

---

## 1. Règles respectées pendant I0

- **Aucun fichier de code modifié.** Seul ce rapport a été ajouté, dans `docs/`.
- **Aucune opération Git qui écrit.** Ni add, commit, stash, reset, clean, checkout,
  création de branche, fetch ou push. Les seules commandes Git utilisées sont des
  lectures : `status`, `diff`, `log`, `ls-files`, `show HEAD:<fichier>`, `remote -v`,
  `branch -vv`, `rev-list --count`. Toutes sont passées avec `--no-optional-locks`, pour
  que `status` ne réécrive pas l'index.
- **Aucun fichier personnel ouvert, modifié ou déplacé.** Seules leur taille et leur
  présence ont été relevées.
- **Rien n'est écrit dans le dépôt pendant les exécutions :**
  - tests et scripts sont lancés avec `PYTHONDONTWRITEBYTECODE=1` et sans cache pytest
    (`-p no:cacheprovider`) ;
  - les régénérations de P4, les états intermédiaires par phase et les mutants
    s'exécutent dans le répertoire temporaire de la session, hors du dépôt.

---

## 2. État du dépôt

| Élément | Valeur |
|---|---|
| Branche | `p1-coalition-foundations` |
| HEAD | `f2cef07` (« Add money, travel unit and synthetic catalogue foundations (P1) ») |
| Branche suivie | `github/p1-coalition-foundations`, à jour d'après les références locales (aucun fetch fait) |
| `main` | `53649ef`, en retard de 3 commits sur la branche courante |
| Remotes | `github` : dépôt GitHub **public** ; `origin` : forge de l'université |
| Fichiers suivis modifiés | 2 : `tests/test_offer_catalog.py`, `tests/test_python310_compatibility.py` |
| Fichiers non suivis | 69 : 49 des phases P2 à P4 (§4.1 à §4.4, soit 10 + 7 + 1 + 31), 2 documents de préparation de 3H et P5 (§4.6, dont ce rapport) et 18 fichiers personnels (§5) |
| Fichiers ignorés présents | `.venv/`, caches, `Multi-Agent/coalition_travel.egg-info/` |
| Artefacts générés dans l'arbre | aucun : pas de `results.json`, pas d'`environment.json`, pas de catalogue de scénarios |

---

## 3. Vérifications techniques

### 3.1 Suite de tests, qualité et compatibilité

| Vérification | Résultat |
|---|---|
| `PYTHONHASHSEED=0 python -m pytest -q` | **662 passed** (42,4 s) |
| `PYTHONHASHSEED=2 python -m pytest -q` | **662 passed** (40,4 s) |
| Compatibilité Python 3.10 et golden master (`test_python310_compatibility.py` + `test_entry_golden_master.py`) | 7 passed. L'interpréteur `python3.10` est installé, donc le test n'est pas sauté |
| Golden master, contrats historiques et agents | **48 passed** |
| `ruff check` sur les 43 fichiers Python ajoutés ou modifiés | All checks passed |
| `ruff format --check` sur ces 43 fichiers | 43 files already formatted |
| `ruff check` sur tout le dépôt | 4 erreurs, toutes dans des fichiers historiques non modifiés (`Entry.py`, `Negotiation.py`, `SellerAgent.py`). Elles existaient déjà, sont documentées dans le README et ne doivent pas être corrigées (golden master) |
| `git diff --check` | propre |

### 3.2 Mutants P4

On relance les 16 mutants de la revue P4 sur une copie de travail.

**Résultat : 16 tués sur 16.**

- Chaque mutant est détecté par le test attendu : poids K, pénalité, décodage, contrôle
  des singletons, élagage, clé du cache, coût collectif, contre-vérification, contrôle
  structurel, signe de la mise en commun des paliers, ordre d'arrivée B0, intégralité
  MILP, garde des planchers, garde numérique, contrôle idp/dp, étiquette du résidu.
- La copie de travail a été supprimée par le script.

### 3.3 Reproduction des empreintes P4

Les deux strates ont été régénérées avec les commandes du §12 du rapport
d'implémentation, en écrivant dans le répertoire temporaire de la session.

#### Performance

**Commande** (lancée à la racine du dépôt) :

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=Multi-Agent \
  .venv/bin/python Multi-Agent/evaluate_formation.py performance --output <répertoire temporaire de session>/i0/performance
```

**Exécution :** code de retour 0, 60 instances, 10 min 36 s.

| | SHA-256 de `results.json` |
|---|---|
| Publiée (`docs/p4_results/README.md`) | `3024fef1187ece03e97c4da3391b2bb9e7c458f8346fad007402dc29310b0b85` |
| Régénérée | `3024fef1187ece03e97c4da3391b2bb9e7c458f8346fad007402dc29310b0b85` |
| **Verdict** | **IDENTIQUE.** Comparaison des 64 caractères par égalité de chaînes, pas seulement du préfixe et du suffixe |

**Comparaison du rapport Markdown régénéré avec `docs/p4_results/performance_report.md`.**

- **Lignes qui diffèrent :** uniquement les tableaux de durées, que le rapport déclare
  volatils et exclus de l'empreinte :
  - « Durée totale par taille » ;
  - « Médiane par phase » ;
  - les colonnes de durée du « Détail par instance ».
- **Lignes identiques :**
  - le tableau « Charge déterministe par taille » ;
  - les six colonnes déterministes du détail par instance, sur les 60 lignes :
    unités, graine, plus grande composante, candidats, appels à l'oracle, succès du
    cache.

**Durées plus longues que celles publiées** : n = 14, médiane 7,86 s contre 6,63 s.

- **Cause.** Cette exécution tournait en même temps que la régénération exploratoire,
  sur la même machine. Les deux processus se partageaient le processeur.
- **Conséquence pour I2.** Cet écart illustre pourquoi la mesure M0 de la révision 4
  remesure `T_P4_total` dans la même session au lieu de reprendre la valeur archivée.

#### Exploratoire

**Commande** (lancée à la racine du dépôt) :

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=Multi-Agent \
  .venv/bin/python Multi-Agent/evaluate_formation.py exploratory --output <répertoire temporaire de session>/i0/exploratory
```

**Exécution :** code de retour 0, 1 740 instances, 24 min 32 s.

| | SHA-256 de `results.json` |
|---|---|
| Publiée (`docs/p4_results/README.md`) | `997109eee5a9ee4c6567410066730e2f8b5c8dd01bd46ff958b586f4c33eced4` |
| Régénérée | `997109eee5a9ee4c6567410066730e2f8b5c8dd01bd46ff958b586f4c33eced4` |
| **Verdict** | **IDENTIQUE.** Comparaison des 64 caractères par égalité de chaînes |

**Comparaison du rapport Markdown régénéré avec
`docs/p4_results/exploratory_report.md` :** `diff` renvoie le code 0, avec **0 ligne
différente**. Le rapport exploratoire ne contient pas de tableau de durées ; il est donc
reproduit octet pour octet.

#### Artefacts générés

Les catalogues de scénarios contiennent des termes privés. Ils sont restés dans le
répertoire temporaire de la session, hors du dépôt, avec `results.json` et
`environment.json`. Rien n'a été écrit dans l'arbre de travail.

### 3.4 Confidentialité

- **Clé `seller_floor_per_seat_cents` :** elle n'apparaît que dans les fichiers prévus.
  - le lecteur du catalogue (`json_catalog.py`) ;
  - le générateur de scénarios (`formation_scenarios.py`, décision D8) ;
  - `data/catalog/catalog_v1.json`, suivi depuis P1 et déjà poussé ;
  - `tests/test_offer_catalog.py` ;
  - une phrase descriptive de `docs/PHASE_P4_IMPLEMENTATION.md`, sans aucune valeur.
- **Chemins personnels :** aucun chemin personnel ni identifiant de compte dans `docs/`,
  `Multi-Agent/coalition_travel/`, `tests/`, `data/` ou le README.

---

## 4. Inventaire du projet par phase

La phase indiquée est celle qui a **créé** le fichier. Certains fichiers ont été modifiés
par une phase ultérieure ; c'est indiqué. Tous les fichiers sont dans leur état final,
car aucun état intermédiaire n'a été commité.

### 4.1 P2 : admissibilité et références (85 tests)

| Fichier | Rôle | Modifié ensuite par |
|---|---|---|
| `Multi-Agent/coalition_travel/domain/admissibility.py` | règles non financières, politique `non_financial_v1` | – |
| `Multi-Agent/coalition_travel/domain/offer_graph.py` | relation unités × offres, composantes | – |
| `Multi-Agent/coalition_travel/domain/negotiation_request.py` | `NegotiationRequest`, protocole de l'oracle, `request_key` | Mission A (schéma v2) |
| `Multi-Agent/coalition_travel/application/lot_admissibility.py` | admissibilité du lot, H2 | Mission A (`unit_economic_digest`) |
| `Multi-Agent/coalition_travel/application/reference_costs.py` | références individuelles | P4 (`validate_negotiation_outcome`) |
| `tests/test_admissibility.py` | 27 tests | – |
| `tests/test_offer_graph.py` | 11 tests | – |
| `tests/test_lot_admissibility.py` | 20 tests | – |
| `tests/test_reference_costs.py` | 27 tests | – |
| `docs/PHASE_P2_ADMISSIBILITY.md` | rapport P2, réécrit lors de la Mission A | Mission A |

### 4.2 P3 et P3-bis : négociation simulée (31 + 23 tests)

| Fichier | Rôle |
|---|---|
| `Multi-Agent/coalition_travel/infrastructure/negotiation/__init__.py` | paquet |
| `Multi-Agent/coalition_travel/infrastructure/negotiation/mandate_leader.py` | `MandateLeader` |
| `Multi-Agent/coalition_travel/infrastructure/negotiation/simulated_oracle.py` | `SimulatedNegotiationOracle`, journal |
| `tests/test_simulated_negotiation_oracle.py` | 31 tests (P3) |
| `tests/test_simulated_negotiation_fidelity.py` | 23 tests (P3-bis) |
| `docs/PHASE_P3_SIMULATED_NEGOTIATION.md` | rapport P3 |
| `docs/PHASE_P3_BIS_FIDELITY.md` | rapport P3-bis |

### 4.3 Mission A : `request_key` v2 (30 tests)

| Fichier | Rôle |
|---|---|
| `tests/test_negotiation_request_key.py` | 30 tests. **Il importe `simulated_oracle` (P3)** |

Le code de la Mission A se trouve dans des fichiers créés par P2
(`negotiation_request.py`, `lot_admissibility.py`).

### 4.4 P4 : formation des coalitions (116 + 1 tests)

| Fichier | Rôle |
|---|---|
| `Multi-Agent/coalition_travel/domain/coalition_game.py` | jeu, poids, couverture `v*` |
| `Multi-Agent/coalition_travel/application/coalition_candidates.py` | énumération, `FormationLimits` |
| `Multi-Agent/coalition_travel/application/coalition_feasibility.py` | contrôle structurel |
| `Multi-Agent/coalition_travel/application/negotiation_cache.py` | cache des négociations |
| `Multi-Agent/coalition_travel/application/coalition_costs.py` | coût des coalitions |
| `Multi-Agent/coalition_travel/application/partition_solver.py` | solveurs et contre-vérifications |
| `Multi-Agent/coalition_travel/application/coalition_formation.py` | formation, pipeline |
| `Multi-Agent/coalition_travel/application/formation_baselines.py` | B1, re-calcul des scores |
| `Multi-Agent/coalition_travel/application/formation_evaluation.py` | décomposition des économies, métriques |
| `Multi-Agent/coalition_travel/infrastructure/baselines/__init__.py` | paquet (non cité dans le rapport P4) |
| `Multi-Agent/coalition_travel/infrastructure/baselines/legacy_broker.py` | B0 |
| `Multi-Agent/coalition_travel/infrastructure/optimization/exact_milp.py` | adaptateur MILP |
| `Multi-Agent/coalition_travel/infrastructure/evaluation/formation_scenarios.py` | générateur de scénarios (allow-list D8) |
| `Multi-Agent/coalition_travel/infrastructure/evaluation/formation_report.py` | rapports, garde contre les clés privées |
| `Multi-Agent/evaluate_formation.py` | banc d'essai |
| `tests/p4_support.py` | utilitaires de test (aucun test ; non cité dans le rapport P4) |
| `tests/test_coalition_game.py` | 29 tests |
| `tests/test_coalition_candidates.py` | 12 tests |
| `tests/test_negotiation_cache.py` | 8 tests |
| `tests/test_partition_solver.py` | 12 tests |
| `tests/test_coalition_formation.py` | 10 tests |
| `tests/test_formation_baselines.py` | 8 tests |
| `tests/test_exact_milp.py` | 7 tests |
| `tests/test_formation_evaluation.py` | 18 tests |
| `tests/test_formation_report.py` | 8 tests |
| `tests/test_p4_module_boundaries.py` | 4 tests |
| `docs/PHASE_P4_SPECIFICATION.md` | spécification |
| `docs/PHASE_P4_IMPLEMENTATION.md` | rapport d'implémentation |
| `docs/p4_results/README.md`, `performance_report.md`, `exploratory_report.md` | résultats publiés |

Le « + 1 » est `test_floor_allow_list_contains_exactly_the_reviewed_modules`, ajouté
dans le fichier suivi `tests/test_offer_catalog.py`.

### 4.5 Fichiers suivis modifiés : blocs de modification par phase

| Fichier | P2 | P3 | P4 |
|---|---|---|---|
| `tests/test_offer_catalog.py` | – | entrée `simulated_oracle.py` dans l'allow-list | entrée `formation_scenarios.py` (D8) ; test d'égalité exacte de l'allow-list |
| `tests/test_python310_compatibility.py` | 5 modules (`admissibility`, `offer_graph`, `negotiation_request`, `lot_admissibility`, `reference_costs`) | 2 modules (`mandate_leader`, `simulated_oracle`) et leur commentaire | 7 modules P4 et leur commentaire |

### 4.6 Hors P2 à P4

`docs/PHASE_3H_P5_INTEGRATION_PLAN.md` (plan d'intégration, révision 4) et ce rapport
appartiennent à la préparation de 3H et P5, pas aux phases P2 à P4.

### 4.7 Cohérence des décomptes avec les rapports

| État | Mesuré | Annoncé |
|---|---|---|
| HEAD (P1) | 376 | 376 |
| + P2 | **461** (état intermédiaire reconstitué, §6) | 461 |
| + P3 | 492 | 492 (rapport P3) |
| + P3-bis | 515 | 515 |
| + Mission A | **545** (état intermédiaire reconstitué, §6) | 545 (rapport P3-bis : « 545 = 492 + 23 + 30 ») |
| + P4 | **662** | 662 (rapport P4 : 659, puis 3 tests ajoutés pendant la revue) |
| 10 fichiers P4 seuls | 116 | 116 |
| Golden master, contrats historiques, agents | 48 | 48 |

Toutes les valeurs annoncées sont retrouvées. Les lignes en gras ont été mesurées sur un
état reconstitué, hors du dépôt (§6) ; les autres sont additionnées à partir des
décomptes de collecte par fichier.

---

## 5. Fichiers personnels à exclure (18, non suivis, non modifiés)

| # | Fichier | Nature | Taille |
|---|---|---|---|
| 1 | `.DS_Store` | métadonnées macOS | 8 Ko |
| 2 | `.pdfpreview/p1.png` | aperçu local | 55 Ko |
| 3 | `3530f8ec-…_Useful_tools_for_large_language_models.pdf` | support de cours | 5,8 Mo |
| 4 | `35f0d6dd-…_Retrieval_augmented_generation_(RAG)_and_context-engineering.pdf` | support de cours | 3,0 Mo |
| 5 | `C1_unlocked.pdf` | support de cours | 0,5 Mo |
| 6 | `C2_unlocked.pdf` | support de cours | 0,3 Mo |
| 7 | `C3a_unlocked.pdf` | support de cours | 0,5 Mo |
| 8 | `C3b_unlocked.pdf` | support de cours | 7,4 Mo |
| 9 | `COALITIONTRAVEL_CONTEXTE_CLAUDE.txt` | contexte de travail | 32 Ko |
| 10 | `CoalitionTravel_AI_Engineering.zip` | archive | 0,6 Mo |
| 11 | `CoalitionTravel_Dossier_Complet_Conception_Realisation.md` | dossier de conception (contredit des documents plus récents) | 74 Ko |
| 12 | `Multi-Agent.zip` | archive du code | 38 Ko |
| 13 | `RAPPORT.md` | rapport personnel | 47 Ko |
| 14 | `copied.txt` | notes | 74 Ko |
| 15 | `lyon.png` | image | 6 Ko |
| 16 | `rapport.latex` | source du rapport | 55 Ko |
| 17 | `rapport.pdf` | rapport historique du TP | 186 Ko |
| 18 | `rapport_architecture_final.pdf` | rapport | 282 Ko |

**Écart à signaler.** Les consignes antérieures parlaient de « 11 fichiers personnels
non suivis ». L'arbre réel en contient 18.

**Preuve qu'aucun n'a jamais été versionné.** Pour chacun des 18 chemins, la commande
`git --no-optional-locks log --all --oneline -- <chemin>` (lecture seule, toutes
branches et remotes connues localement) renvoie **0 commit**.

**Mentions de ces fichiers dans des fichiers suivis.** Une seule, dans
`docs/PHASE_P0_BASELINE_AND_GOLDEN_MASTER.md`, ligne 33. Cet inventaire P0 cite les noms
de `COALITIONTRAVEL_CONTEXTE_CLAUDE.txt`, `CoalitionTravel_Dossier_Complet_Conception_Realisation.md`,
`RAPPORT.md`, `copied.txt` et `rapport.latex`. Il cite les noms seulement, sans aucun
contenu.

**Confirmation de Claude.** Les 18 fichiers, y compris `RAPPORT.md` et
`CoalitionTravel_Dossier_Complet_Conception_Realisation.md`, doivent rester hors de
toute future opération Git. Quatre raisons :

1. aucun n'a jamais été commité ;
2. lors du commit P1, ils ont été laissés volontairement hors du dépôt ;
3. le dossier de conception contredit des documents plus récents : il présente encore
   SPADE/XMPP comme l'orientation retenue ;
4. aucun fichier de code ni aucun test n'en dépend.

La décision finale sur la nature de ces fichiers appartient à leur propriétaire.

**Risque.** Le `.gitignore` ne couvre aucun de ces fichiers (ni `.DS_Store`, ni `*.zip`,
ni `*.pdf`). Une commande comme `git add -A` ou `git add .` les intégrerait. Une
éventuelle opération Git devra donc nommer les fichiers explicitement. Modifier le
`.gitignore` est une décision à part, qui n'a pas été prise.

---

## 6. Éléments pour la future décision Git

Il s'agit de constats, pas de demandes. Aucune opération n'est proposée sans accord.

1. **Un commit par phase est possible, mais au sens « fichiers dans leur état final,
   regroupés par phase de création ».** Ce ne sont pas des instantanés historiques :
   - `reference_costs.py` contient l'ajout de P4 ;
   - `negotiation_request.py` et `lot_admissibility.py` contiennent la Mission A.
2. **États intermédiaires vérifiés hors du dépôt.** Ils ont été reconstitués à partir de
   HEAD (`git show`), auxquels on ajoute les fichiers de la phase et seulement les
   blocs des deux tests suivis qui la concernent :

   | État | Résultat |
   |---|---|
   | HEAD + P2, sans `test_negotiation_request_key.py` | **461 passed** |
   | HEAD + P2, avec `test_negotiation_request_key.py` | **échec de collecte** : `ModuleNotFoundError: coalition_travel.infrastructure.negotiation` |
   | HEAD + P2 + P3 + Mission A | **545 passed** |
   | arbre complet (+ P4) | **662 passed** |

   Conséquence : un commit P2 ne doit pas contenir `test_negotiation_request_key.py`.
   Ce fichier doit aller dans le commit P3, ou dans un commit « Mission A » placé après
   P3.
3. **Les deux tests suivis modifiés mélangent les trois phases** (§4.5). Un découpage
   par phase demande d'indexer bloc par bloc. Dans `test_offer_catalog.py`, le test
   d'égalité exacte (P4) mentionne l'entrée P3 : il n'a de sens qu'à l'étape P4.
4. **La remote `github` est publique.** Pousser P2 à P4 publierait :
   - le code ;
   - les rapports, qui ne contiennent ni chemin personnel ni valeur de plancher ;
   - aucun catalogue généré.

   Les planchers du catalogue v1 sont déjà publics depuis le push de P1.
5. **Le choix entre un commit unique P2 à P4 et des commits par phase reste ouvert.**

---

## 7. Revue finale de P4 : synthèse

**Ce qui est vérifié pendant I0 :**

- suite complète avec deux graines ;
- compatibilité Python 3.10 réelle ;
- golden master ;
- lint et formatage ;
- 16 mutants sur 16 tués ;
- décomptes des rapports retrouvés ;
- confidentialité des planchers ;
- absence d'artefacts générés ;
- empreintes P4 des deux strates reproduites à l'identique (§3.3).

**Réserves déjà connues, toujours ouvertes :**

- **Arrondi des flottants dans P3.** Des coalitions qui économisent de 1 à 5 centimes
  proviennent de l'arrondi des flottants dans les trajectoires P3. C'est documenté dans
  le rapport P4.
- **ID-6** (θ_u = 0) sera confirmé au début d'I2.
- **Durées volatiles.** Les tableaux de durées dépendent de la machine et n'entrent dans
  aucune empreinte.

**Points mineurs relevés, sans effet sur le code :** le rapport P4 ne cite ni
`tests/p4_support.py` ni `infrastructure/baselines/__init__.py`.
