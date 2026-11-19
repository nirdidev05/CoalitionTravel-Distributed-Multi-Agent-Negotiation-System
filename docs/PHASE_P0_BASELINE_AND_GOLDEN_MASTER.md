# Phase P0 — baseline et Golden Master

## Résumé

P0 a ajouté uniquement les trois nouveaux fichiers autorisés : le test du Golden Master et de la limite historique, sa sortie de référence, et ce rapport. Aucun fichier suivi préexistant n’a été modifié. Les changements locaux et fichiers non suivis déjà présents ont été conservés. Aucune commande Git d’écriture, aucun commit et aucun push n’ont été effectués.

## Inventaire initial

Relevé avant toute écriture P0 :

- Branche : `main`.
- HEAD : `53649ef3c5788edcf0dfd9dd01da14f1b0ae777d` (`Integrate adaptive traveler profiles and shared RAG`).
- `git status --porcelain -uall` : 13 chemins suivis modifiés et 40 chemins non suivis.
- `git diff --stat` : 13 fichiers suivis, 960 insertions, 416 suppressions.
- Aucun fichier suivi supprimé ou renommé.

Fichiers suivis modifiés au départ :

| Catégorie | Chemins |
| --- | --- |
| Moteur historique / domaine | `Multi-Agent/CoalitionStructureSearch.py`, `Multi-Agent/coalition_travel/application/optimization.py` |
| Application | `Multi-Agent/coalition_travel/application/evaluation.py`, `Multi-Agent/coalition_travel/application/knowledge.py` |
| Infrastructure | `Multi-Agent/coalition_travel/infrastructure/knowledge/ollama_embeddings.py`, `Multi-Agent/coalition_travel/infrastructure/knowledge/sqlite_store.py`, `Multi-Agent/coalition_travel/infrastructure/llm/ollama.py` |
| CLI et configuration | `Multi-Agent/evaluate_requests.py`, `pyproject.toml` |
| Documentation | `README.md` |
| Tests | `tests/test_knowledge_rag.py`, `tests/test_ollama_adapter.py`, `tests/test_profiles_compatibility_workflow.py` |

Fichiers non suivis préexistants, classés par nature :

- **Code (9)** : `Multi-Agent/coalition_travel/domain/{cooperative_game,partition,partition_optimization}.py`; `Multi-Agent/coalition_travel/infrastructure/evaluation/{__init__,provenance,retrieval_metrics}.py`; `Multi-Agent/coalition_travel/infrastructure/optimization/{__init__,scipy_ip}.py`; `Multi-Agent/evaluate_retrieval.py`.
- **Tests (4)** : `tests/test_coalition_legacy_contracts.py`, `tests/test_coalition_module_boundaries.py`, `tests/test_evaluation_profiles.py`, `tests/test_retrieval_evaluation.py`.
- **Données (8)** : les quatre fichiers `data/eval/rag/` (corpus, requêtes et manifestes), `data/eval/request_extraction_v2.jsonl` et son manifeste, `data/eval/request_profiles_v1.jsonl` et son manifeste.
- **Documentation / fichiers pédagogiques (6)** : `COALITIONTRAVEL_CONTEXTE_CLAUDE.txt`, `CoalitionTravel_Dossier_Complet_Conception_Realisation.md`, `RAPPORT.md`, `copied.txt`, `rapport.latex`, `docs/PHASE_3G_EVALUATION_AND_ARCHITECTURE.md`.
- **Archives (2)** : `CoalitionTravel_AI_Engineering.zip`, `Multi-Agent.zip`.
- **PDF (8)** : les deux rapports de lecture IA/RAG, `C1_unlocked.pdf`, `C2_unlocked.pdf`, `C3a_unlocked.pdf`, `C3b_unlocked.pdf`, `rapport.pdf`, `rapport_architecture_final.pdf`.
- **Cache / système / image (3)** : `.DS_Store`, `.pdfpreview/p1.png`, `lyon.png`.

Ces catégories décrivent les fichiers observés, pas leur auteur. Les noms de certains composants suggèrent un lien avec des phases précédentes, mais l’état Git ne permet pas d’attribuer chaque changement à une phase avec certitude. Tout a été traité comme préexistant et préservé. L’environnement `.venv` n’apparaît pas dans le statut Git; les éléments ignorés ne sont pas recensés par `git status --porcelain -uall`.

## Sécurité et décision sur la référence

Le garde-fou a été déclenché : `Entry.py` lui-même était inchangé, mais deux dépendances directes qui déterminent sa sortie étaient modifiées localement : `CoalitionStructureSearch.py` et `application/optimization.py`. `Entry.py` appelle DP, IDP, IP, l’oracle et les fonctions d’affichage de la façade; cette façade importe désormais des modules non suivis. Le service d’optimisation importe également des modules de domaine non suivis. Exécuter le Golden Master sur le working tree aurait donc pris un état local non validé comme référence.

L’équipe a explicitement validé `53649ef` comme référence. Le Golden Master a été généré depuis `git archive` de ce commit dans un répertoire temporaire, en dehors du dépôt. Le test réexporte ce même SHA complet; il n’exécute pas les versions locales modifiées. Le seul mécanisme de date utilisé est l’argument déjà prévu par `run_scenarios(reference_date=...)` dans le commit de référence.

### Checkpoint proposé, non exécuté

Avant une étape ultérieure de migration, proposer :

1. un patch binaire de `git diff --binary HEAD`, stocké hors du dépôt, pour les différences suivies ;
2. une archive avec chemins relatifs et manifeste de hash pour les 40 fichiers non suivis préexistants. `.DS_Store` et `.pdfpreview/p1.png` peuvent être identifiés comme fichiers système/cache dans le manifeste; les documents, PDF, archives, code, données et tests doivent rester inclus tant que l’équipe n’a pas choisi explicitement de les exclure.

Cette sauvegarde ne capture pas les fichiers ignorés par Git, dont `.venv` ou d’autres caches ignorés. Il faut les inventorier séparément si leur conservation est requise. **Aucune sauvegarde n’a été exécutée**, conformément à la demande.

## Golden Master `Entry.py`

Fichier : `tests/golden/entry_run_scenarios_2026-11-19.txt`.

- Commit exporté : `53649ef3c5788edcf0dfd9dd01da14f1b0ae777d`.
- Python : `3.14.2`; pytest `9.2.0`; NumPy `2.4.1`; SciPy `1.17.1`; Pydantic `2.14.3`.
- Répertoire courant et `PYTHONPATH` du sous-processus : `Multi-Agent/` dans l’export temporaire du commit.
- Paramètres : `PYTHONHASHSEED=0`, `LC_ALL=C`, `LANG=C`, `TZ=UTC`, date `2026-11-19`, timeout 90 s.
- Lancement : sous-processus Python qui exécute le fichier `Entry.py` depuis l’export propre avec `runpy.run_path`, puis appelle le point d’entrée existant `run_scenarios(reference_date=date(2026, 11, 19))`.
- Capture : stdout/stderr en octets; code de sortie 0 et stderr vide; comparaison exacte, sans normalisation, de toute la sortie.
- Taille de la sortie de référence : 21 173 octets; SHA-256 `a5977fde152d329b53c2651ff89534a5fdd605b38b1419efacc6e1d533bd08b7`.
- Aucun outil de régénération du fichier de référence n’a été ajouté.

Les assertions lisibles sont liées à leur scénario : scénario 1, accord `453.60€`; scénario 2, accords des groupes Tokyo `1512.00€` et Rome `1792.00€`; scénario 4, deux accords à `408.24€` en huit tours; scénario 5, optimum `250.60`; scénario 6, valeurs broker `198.00€` et `181.20€`, accord de coalition `957.60€`, accord `1478.40€` et paiements Shapley `491.80€`, `493.05€`, `493.55€`; scénario superadditif, accord `1960.00€`. La sortie utilise un point décimal et n’insère pas de séparateur de milliers (par exemple `1512.00`, pas `1,512.00`).

## Limite historique caractérisée

Le test `test_historical_characterization_known_per_ticket_vs_group_total_quantity_defect` utilise réellement `BuyerAgent`, `SellerAgent`, `Message` et `run_alternating_negotiation` du dépôt, sans substitut ni simulation du résultat :

- le BuyerAgent représente 4 voyageurs, avec un budget agrégé de 2 000 € et un budget déclaré de 500 € par personne ;
- le SellerAgent historique a un minimum de 400 € par billet et son offre initiale est 560 € (1,4 × le minimum) ;
- le BuyerAgent accepte 560 € comme prix total après deux tours, soit 140 € par voyageur.

Cela caractérise la confusion historique entre prix vendeur au billet et prix total du profil. Le test est explicitement une limite connue, pas un contrat souhaité pour le nouveau flux. Aucun agent ni algorithme n’a été corrigé.

## Résultats des tests

Test ciblé :

```text
.venv/bin/python -m pytest -q tests/test_entry_golden_master.py
..                                                                       [100%]
2 passed in 0.79s
```

Suite complète, graine 0 :

```text
PYTHONHASHSEED=0 .venv/bin/python -m pytest -q
........................................................................ [ 54%]
.............................................................            [100%]
133 passed in 2.05s
```

Suite complète, graine 2 :

```text
PYTHONHASHSEED=2 .venv/bin/python -m pytest -q
........................................................................ [ 54%]
.............................................................            [100%]
133 passed in 1.84s
```

Les tests ciblés incluent le Golden Master et la caractérisation. Les deux exécutions complètes ont reproduit les mêmes résultats.

## Ruff

Périmètre documenté du projet, étendu aux deux nouvelles CLI :

```text
.venv/bin/ruff check Multi-Agent/coalition_travel tests Multi-Agent/evaluate_requests.py Multi-Agent/evaluate_retrieval.py
All checks passed!

.venv/bin/ruff format --check Multi-Agent/coalition_travel tests Multi-Agent/evaluate_requests.py Multi-Agent/evaluate_retrieval.py
42 files already formatted
```

Aucune erreur Ruff n’a été introduite par P0. Le contrôle est volontairement resté dans le périmètre documenté; le formatage global n’a pas été lancé. Le scan global Ruff de Phase 3G avait déjà relevé quatre problèmes hors de ce périmètre dans `Entry.py`, `Negotiation.py` et `SellerAgent.py`, ainsi que neuf fichiers historiques à reformater. Ils n’ont pas été corrigés ici.

## État Git final

`git status --porcelain -uall` présente 13 fichiers suivis déjà modifiés et 43 fichiers non suivis : les 40 fichiers non suivis préexistants, plus les trois ajouts P0. `git diff --stat` reste identique à l’état initial : 13 fichiers, 960 insertions, 416 suppressions. `git diff --name-only` reste identique à l’inventaire initial. `git diff --check` ne signale aucune erreur.

Fichiers ajoutés par P0, et seulement ceux-ci :

1. `tests/test_entry_golden_master.py`
2. `tests/golden/entry_run_scenarios_2026-11-19.txt`
3. `docs/PHASE_P0_BASELINE_AND_GOLDEN_MASTER.md`

Pas de commit, push, branche, stash, reset, clean, `git add`, suppression ou modification de `.gitignore`. Le document Phase 3G est inchangé.

## Verdict

**P0 accepté.** Le Golden Master est reproductible depuis la révision explicitement validée, la limite historique est caractérisée par le vrai parcours d’agents, les deux suites passent, et aucun fichier suivi n’a été modifié par P0. Les 13 modifications suivies et 40 fichiers non suivis antérieurs restent préservés.
