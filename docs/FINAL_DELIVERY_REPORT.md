# Rapport final de livraison : CoalitionTravel

**Date :** 2026-11-20.
**Commit évalué :** `5d547ec18a10965f52f1572296cfdd7dd95fa79f`, plus les modifications
de la mission finale, **laissées dans l'arbre de travail.** Aucun commit, aucun push,
aucune opération Git d'écriture n'a été faite pendant la mission.

**Statut final : COMPLET AVEC LIMITES.** Les limites sont au §14, les critères non
atteints au §16.

---

## 1. Résumé exécutif

CoalitionTravel est une plateforme expérimentale locale. À partir d'une demande de
voyage, elle extrait les faits par un LLM local, les valide de façon déterministe,
simule les négociations entre agents, forme les coalitions optimales (P4 exact) et
répartit les économies en rationnels exacts (P5). Elle produit ensuite une proposition
simulée expliquée.

**Ce que la mission a apporté :**

1. **Clôture d'I4 sur preuves.**
   - L'empreinte exploratoire ne peut plus être `997109ee…` par construction, puisque
     `code_sha256` change avec le code. L'équivalence des résultats métier est prouvée
     sur les 1 740 enregistrements.
   - L'empreinte de performance `3024fef1…` est reproduite telle quelle.
2. **Première évaluation réelle des LLM.** Elle a révélé et corrigé un **défaut
   d'intégration majeur** : le schéma était transmis sans clés obligatoires, et le
   décodage contraint omettait la destination. La destination est maintenant extraite
   dans 25 à 100 % des cas, contre 0 à 12 % avant.
   - Elle a aussi mesuré la limite principale : l'exact match par demande reste proche
     de 0 %, à cause de profils inventés.
   - La reproductibilité est totale : 270 extractions sur 270 identiques entre deux
     passes.
3. **Évaluation du RAG** sur 3 modèles d'embedding et 4 découpages, et **mesure de
   l'injection** par document hostile. Une injection directe réussit sur 7 demandes sur
   8 avec `llama3.2:3b`. Cette mesure confirme le choix de ne pas brancher le RAG sur la
   décision.
4. **Quatre failles corrigées :**
   - S1 : sortie anticipée du bloc délimité ;
   - S2 : lecture non bornée des fichiers d'entrée ;
   - S4 : délai d'attente trop court ;
   - le transport du schéma.

   Chacune est testée.
5. **18 scénarios économiques** versionnés, résultats figés, invariants de paiement
   vérifiés.
6. **Intégration continue** hors ligne, **démonstration** reproductible, **documentation**
   finale.

## 2. État initial

Voir `docs/FINAL_PROJECT_AUDIT.md`.

- **Suite de tests :** 976 tests verts.
- **Jamais exécutés avec de vrais modèles :** l'extraction par LLM et le RAG (Ollama
  absent).
- **Absents :** l'intégration continue, l'API et l'interface.
- **README** obsolète, décrivant la phase 3G.
- **Python 3.10 :** seule la grammaire était vérifiée.
- **I4** non clôturée, avec l'empreinte exploratoire en suspens.

## 3. Étapes réalisées

| Étape | Livrable | Statut |
|---|---|---|
| 0. Audit et clôture d'I4 | `docs/FINAL_PROJECT_AUDIT.md`, rapport I4 §7.2 corrigé | fait ; I4 clôturée |
| 1. Évaluation LLM réelle | `docs/FINAL_LLM_EVALUATION.md`, `docs/final_results/llm/` | fait |
| 2. Évaluation RAG et injection | `docs/FINAL_RAG_EVALUATION.md`, `docs/final_results/rag/`, `injection/` | fait |
| 3. Workflow, fiabilité, scénarios économiques | `docs/FINAL_ARCHITECTURE.md` §4, `data/scenarios/`, tests | fait |
| 4. CLI, UI et architecture distribuée | décision au §15 | CLI vérifiée ; UI, API et distribution non construites, par choix |
| 5. Performance | `docs/FINAL_PERFORMANCE_REPORT.md` | fait |
| 6. Sécurité | `docs/FINAL_SECURITY_REVIEW.md` | fait |
| 7. Documentation | README, architecture, dossier, guide | fait |
| 8. Intégration continue | `.github/workflows/ci.yml` | écrit, étapes exécutées localement ; pas encore exécuté sur GitHub |
| 9. Démonstration | `demo/` | fait, exécutée |

## 4. Fichiers créés et modifiés

**Modifiés (7) :**

| Fichier | Changement |
|---|---|
| `Multi-Agent/coalition_travel/infrastructure/llm/ollama.py` | `transport_schema()` (toutes les clés exigées) ; neutralisation des balises (S1) |
| `Multi-Agent/coalition_travel/infrastructure/llm/replay.py` | lecture bornée à 1 Mo (S2) |
| `Multi-Agent/plan_trip.py` | lecture bornée à 1 Mo (S2) ; `OLLAMA_TIMEOUT_SECONDS`, 180 s par défaut (S4) |
| `Multi-Agent/evaluate_requests.py` | `schema_transport` enregistré dans la provenance d'une évaluation |
| `tests/test_ollama_adapter.py` | une ligne adaptée (schéma de transport) et un test ajouté |
| `README.md` | réécrit |
| `docs/PHASE_I4_ROUTE_REPORT.md` | statut, §2, §7.1, §7.2 et §8 corrigés |

**Créés :**

- **Code :**
  - `Multi-Agent/evaluate_scenarios.py` ;
  - `Multi-Agent/evaluate_injection.py`.
- **Tests :**
  - `tests/test_final_hostile_context.py` (4 tests) ;
  - `tests/test_final_input_limits.py` (11) ;
  - `tests/test_final_economic_scenarios.py` (4).
- **Données :**
  - `data/scenarios/economic_scenarios_v1.json` ;
  - `data/eval/rag/hostile_documents_v1.jsonl` et son manifeste.
- **Résultats :**
  - `docs/final_results/llm/` (3 passes et scripts) ;
  - `docs/final_results/rag/` (12 configurations et script) ;
  - `docs/final_results/injection/` ;
  - `docs/final_results/economic_scenarios_v1.results.json` ;
  - `docs/final_results/p4_performance_report_2026-11-20.md`.
- **Documents :**
  - `docs/FINAL_PROJECT_AUDIT.md`, `docs/FINAL_ARCHITECTURE.md` ;
  - `docs/FINAL_LLM_EVALUATION.md`, `docs/FINAL_RAG_EVALUATION.md` ;
  - `docs/FINAL_PERFORMANCE_REPORT.md`, `docs/FINAL_SECURITY_REVIEW.md` ;
  - `docs/FINAL_DEFENSE_DOSSIER.md`, `docs/AI_ENGINEER_INTERVIEW_GUIDE.md` ;
  - ce rapport.
- **Intégration et démonstration :**
  - `.github/workflows/ci.yml` ;
  - `demo/` (`run_demo.sh`, `README.md`, 6 demandes, 2 rejeux réels).

**Inchangés :**

- P4, P5 et le simulateur P3 ;
- les 12 modules hachés par `code_sha256` ;
- les catalogues, carnets et jeux d'évaluation existants ;
- le golden master et les fichiers historiques ;
- `docs/p4_results/` et `docs/p5_results/`.

Les 18 fichiers personnels n'ont pas été touchés.

## 5. Architecture finale

Voir `docs/FINAL_ARCHITECTURE.md`. L'architecture est inchangée sur le fond. Les ajouts
se limitent à l'adaptateur Ollama (transport, neutralisation), aux bornes d'entrée de la
commande et à deux évaluateurs.

## 6. Fonctionnalités

- **Commande `coalition-travel-plan` :**
  - entrées : texte, brouillon JSON ou rejeu ;
  - clarification en 3 tours au plus ;
  - résolution des lieux et des alias ;
  - chemins v1 et v2 ;
  - sorties texte et JSON canonique ;
  - codes de sortie 0, 1, 2, 3, 4, 64 et 130.
- **Les 7 statuts d'unité et les 2 modificateurs** sont tous atteints par les scénarios
  économiques, sauf `projection_active`, impossible à atteindre avec les données de
  catalogue (§14).
- **Les évaluateurs :** extraction, profils, retrieval, injection, P4, P5 et scénarios.

## 7. Tests exécutés

Toutes ces commandes ont été exécutées le 2026-11-20 [E].

| Commande | Résultat |
|---|---|
| `PYTHONHASHSEED=0 python -m pytest -q -p no:cacheprovider` (`.venv`, Python 3.14.2) | **996 passed** |
| idem avec `PYTHONHASHSEED=2` | **996 passed** |
| idem dans une installation propre (copie de l'arbre final, environnement Python 3.12 neuf, `pip install -e '.[dev]'`, SciPy 1.18.1, NumPy 2.5.5) | **996 passed** |
| `ruff check` et `ruff format --check` sur `Multi-Agent/coalition_travel`, `plan_trip.py`, les deux nouveaux évaluateurs et `tests` | All checks passed ; 128 files already formatted |
| `git diff --check` | propre |
| Mutants d'I4 rejoués | 20 sur 20 tués |
| Python 3.10, suite complète : macOS avec SciPy 1.14.1 ; Linux Docker avec SciPy 1.14.1 et 1.15.3 | 972 passed et 4 failed ; Linux : 972 passed, 3 failed, 1 skipped. **Anomalie ouverte**, causes démontrées (audit, §5) |
| `coalition-travel-plan --help` et Lyon-Alger dans l'installation propre | `trip-proposal-v2`, `served_in_coalition`, économie de 4 617 centimes |
| `bash demo/run_demo.sh` | 8 étapes, codes 2, 0, 0, 0, 0, 0, 0, 2 |

996 = 976 tests d'I4, plus 20 tests de la mission :

| Fichier | Tests |
|---|---:|
| `test_final_hostile_context.py` | 4 |
| `test_final_input_limits.py` | 11 |
| `test_final_economic_scenarios.py` | 4 |
| `test_ollama_adapter.py` | 1 |

## 8. Mesures LLM

Voir `docs/FINAL_LLM_EVALUATION.md`.

- **Meilleur modèle :** `qwen2.5:7b` sur ces jeux. Destination 88 à 100 %, budget 85 à
  100 %, origine 92 à 100 %.
- **Exact match par demande :** environ 0 %, à cause des profils inventés, du nombre de
  voyageurs mal placé et des dates de départ inventées.
- **Clarifications :** rappel de 78 à 100 %, précision de 14 à 44 %.
- **Latence médiane :** 22 à 39 s pour le 7B.
- **Reproductibilité :** 270 extractions sur 270 identiques.

## 9. Mesures RAG

Voir `docs/FINAL_RAG_EVALUATION.md`.

- **Retrieval :** les 3 modèles atteignent le plafond sur le corpus de 12 passages
  (MRR = 1). Le corpus est trop facile pour les classer.
- **Seuil :** il dépend du modèle (`all-minilm` perd 21 points de rappel à 0,6).
- **Latence :** 13 à 67 ms.
- **Injection** dans le pire cas :

  | Modèle | Instruction directe | Sortie de balise |
  |---|---:|---:|
  | `llama3.2:3b` | 7 / 8 | 4 / 8 |
  | `qwen2.5:3b` | 6 / 8 | 0 / 8 |
  | `qwen2.5:7b` | 0 / 8 | 3 / 8 |

## 10. Mesures de performance

Voir `docs/FINAL_PERFORMANCE_REPORT.md`.

- **P4 à 14 unités :** médiane 6,64 s, contre 6,63 s historiquement. L'empreinte
  `3024fef1…` est identique.
- **16 unités :** `component_too_large`.
- **P5 :** les mesures d'I2 restent valables, le code est inchangé.

## 11. Sécurité

Voir `docs/FINAL_SECURITY_REVIEW.md`.

- **Failles corrigées et testées :** S1, S2 et S4. S3 est documentée.
- **Aucun secret versionné.**
- **`pip-audit` :** aucune vulnérabilité connue dans les dépendances déclarées. Deux
  paquets non déclarés du `.venv` local sont concernés : PyPDF2 et `wheel`.

## 12. Intégration continue

`.github/workflows/ci.yml` :

- **job principal,** sur Python 3.11 et 3.12 : Ruff, manifestes, jeux de données, suite
  avec 2 graines, commande installée, Lyon-Alger ;
- **job Python 3.10** non bloquant, qui rend l'anomalie visible ;
- **aucun appel à Ollama.**

Le YAML est valide et l'étape des données a été exécutée localement.
**Le workflow n'a pas été exécuté sur GitHub,** puisqu'aucun push n'a été fait.

## 13. Démonstration

`demo/README.md` et `demo/run_demo.sh`.

- **Étape 1 :** extraction réelle de `qwen2.5:7b`, par rejeu de sa sortie enregistrée,
  ou en direct avec `OLLAMA_MODEL`. Elle montre honnêtement la limite : une
  clarification est demandée.
- **Étapes 1 bis à 7 :** la proposition v2, la clarification, la coalition v1, l'absence
  de coalition avantageuse, l'absence d'accord, l'absence d'offre et le lieu inconnu.

## 14. Limites connues

1. **Données fictives** et propositions simulées. Les agents sont **locaux et
   synchrones** : pas de SPADE/XMPP, ni d'API, ni d'interface.
2. **L'extraction par LLM local ne fait pas aboutir seule la phrase de référence.**
   `qwen2.5:7b` place les voyageurs dans un profil inventé. La demande s'arrête alors
   en clarification, ce qui est sûr mais bloquant. Voir la décision ouverte du §16.
3. **Le RAG est documentaire et non branché,** et vulnérable à l'injection sémantique.
4. **Python 3.10 :** 3 échecs du golden master (ordre d'affichage des ensembles,
   `siphash24`), et une roue SciPy défaillante sur macOS 27.
5. **`projection_active`** ne survient jamais avec les données de catalogue, car le
   jeu `v*` y est superadditif. La projection n'est démontrée que sur des cas
   construits (tests d'I2 et d'I3).
6. **Jeux d'évaluation petits et synthétiques :** de 7 à 26 cas, et un corpus RAG de
   12 passages.
7. **Formation exacte limitée** à `max_component_units`.

## 15. Décisions d'architecture

| Décision | Justification |
|---|---|
| **Pas d'interface web ni d'API** | La CLI couvre toute la démonstration avec des sorties reproductibles et des codes de sortie testés. Une interface n'ajouterait aucune capacité métier et ajouterait une surface non testée. Le contrat API serait la proposition JSON canonique `trip-proposal-v1` / `-v2`, déjà fermée et validée. |
| **Pas de distribution réelle** | Elle n'est pas nécessaire à l'objectif académique. La cible est documentée (`docs/FINAL_ARCHITECTURE.md`, §8). |
| **Correction du transport du schéma, sans changer le prompt** | La cause est mécanique et démontrée sur un exemple. Les résultats avant correction sont conservés. |
| **RAG non branché sur la commande** | L'injection mesurée réussit sur 7 demandes sur 8 avec `llama3.2:3b`. |
| **Empreinte exploratoire du code d'I4** | Équivalence métier hors `formation_run_id` et `result_sha256` ; décision de revue du 2026-11-20. |

## 16. Critères non atteints et décisions ouvertes

| Critère (mission, §14) | État |
|---|---|
| D. Python 3.10 testé | **Non atteint :** anomalie ouverte, causes démontrées, tests non modifiés |
| D. CI opérationnelle | **Partiel :** workflow écrit et validé localement ; pas encore exécuté sur GitHub |
| C. Extraction LLM mesurée | **Atteint ;** qualité insuffisante pour un usage autonome |
| Tous les autres critères A à E | atteints : voir les §3 et §7 |

**Décision ouverte, à trancher par la personne responsable.** La mesure montre que les
modèles placent le nombre de voyageurs dans un profil unique et laissent `travellers`
vide. Une règle déterministe pourrait compléter `travellers` par la somme des effectifs
des profils quand il est absent. Elle ne crée aucun fait : elle additionne des effectifs
extraits.

- **Effet :** la phrase de référence aboutirait à une proposition.
- **Pourquoi ce n'est pas fait :**
  - c'est un changement de la règle de validation, donc d'un contrat ;
  - il améliorerait les scores mesurés *après* leur observation.

**Recommandation :** l'accepter comme règle versionnée, avec un test, et la mesurer sur
un jeu **nouveau**.

## 17. Instructions de reproduction

```bash
python -m venv .venv && source .venv/bin/activate && python -m pip install -e '.[dev]'
PYTHONHASHSEED=0 python -m pytest -q                       # 996 passed
bash demo/run_demo.sh                                      # démonstration
python Multi-Agent/evaluate_scenarios.py                   # scénarios économiques
PYTHONHASHSEED=0 PYTHONPATH=Multi-Agent python Multi-Agent/evaluate_formation.py performance --output /tmp/perf
# Avec Ollama (brew install ollama ; ollama serve ; ollama pull qwen2.5:7b …) :
SCRATCH=/tmp/cw bash docs/final_results/llm/matrix.sh run_x   # V1TREE : copie du commit dbf5bd4
SCRATCH=/tmp/cw bash docs/final_results/rag/sweep.sh
python Multi-Agent/evaluate_injection.py --model qwen2.5:7b
```

## 18. Inventaire des preuves

| Preuve | Emplacement |
|---|---|
| Équivalence exploratoire d'I4, chaîne des empreintes | `docs/PHASE_I4_ROUTE_REPORT.md`, §7.2 |
| Causes des échecs sous Python 3.10 | `docs/FINAL_PROJECT_AUDIT.md`, §5 |
| Extractions brutes (3 passes × 21 fichiers) | `docs/final_results/llm/run1`, `run2`, `run3` |
| Retrieval brut (12 configurations) | `docs/final_results/rag/` |
| Injection brute | `docs/final_results/injection/` |
| Scénarios économiques | `data/scenarios/economic_scenarios_v1.json`, `docs/final_results/economic_scenarios_v1.results.json` |
| Performance P4 du jour | `docs/final_results/p4_performance_report_2026-11-20.md` |
| Rejeux réels de démonstration | `demo/replay_*.json` |

Les SHA-256 des rapports finaux sont donnés à la livraison, avec l'état de
`git status`.

## 19. Commit évalué

`5d547ec18a10965f52f1572296cfdd7dd95fa79f`, plus l'arbre de travail décrit au §4.

## 20. Statut final

**COMPLET AVEC LIMITES.** Le système est fonctionnel, reproductible et documenté. Les
limites sont mesurées et déclarées. Deux critères ne sont pas pleinement atteints :
Python 3.10, et l'exécution de la CI sur GitHub. Une décision reste ouverte au §16.
