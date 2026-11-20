# CoalitionTravel — négociation multi-agents et coalitions de voyageurs

**Plateforme expérimentale locale** de simulation de négociation et de formation de
coalitions de voyageurs.

À partir d'une demande de voyage en langage naturel, le système :

1. extrait les faits ;
2. les valide ;
3. simule les négociations entre agents acheteurs et vendeurs ;
4. forme les coalitions optimales ;
5. répartit les économies de façon exacte ;
6. explique sa **proposition simulée**.

> Les fournisseurs, les prix, les vols et les places sont **fictifs**. Rien n'est
> réservé, payé ni émis. Les agents s'exécutent dans **un seul processus Python,
> de façon synchrone** : ce n'est ni un moteur de réservation ni un système distribué.

---

## Le problème

Des voyageurs qui partent vers la même destination peuvent obtenir de meilleurs tarifs
en se regroupant : paliers de prix par nombre de places, négociation de groupe. Cela
soulève trois questions :

1. **Qui regrouper ?** C'est la formation de coalitions, une partition optimale (P4).
2. **À quel prix ?** C'est la négociation entre agents aux informations privées :
   budgets des acheteurs, planchers des vendeurs (P3).
3. **Comment répartir l'économie ?** C'est l'allocation exacte : valeur de Shapley et
   projection sous contraintes de budget (P5).

## La chaîne

```
texte → extraction LLM (Ollama, schéma Pydantic) → validation déterministe
      → clarification → résolution des lieux → sélection des données v1/v2
      → profils et unités → admissibilité → références individuelles (négociations)
      → négociations collectives → formation optimale P4 → allocation exacte P5
      → explications → proposition publique (texte ou JSON)
```

Le LLM **n'extrait que les faits exprimés**. Il ne décide ni des prix, ni des offres,
ni de la disponibilité, ni des coalitions, ni des paiements. Toutes les décisions sont
déterministes et reproductibles.

Détails : [docs/FINAL_ARCHITECTURE.md](docs/FINAL_ARCHITECTURE.md), avec diagrammes
Mermaid, frontières du workflow et modèle mathématique.

## Installation

Python 3.11 ou plus récent est recommandé. Le code respecte la grammaire 3.10, mais la
suite complète n'est pas verte sous 3.10 ; voir les limites.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Démonstration

**Sans LLM.** La démonstration est reproductible, à partir d'une demande structurée :

```bash
coalition-travel-plan --draft-json demo/lyon_alger.json --reference-date 2027-01-15
coalition-travel-plan --draft-json demo/lyon_alger.json --reference-date 2027-01-15 --yes --json
```

**Avec un LLM local.** Il faut [Ollama](https://ollama.com/) et un modèle téléchargé :

```bash
OLLAMA_MODEL=qwen2.5:7b coalition-travel-plan --prompt "Deux personnes de Lyon à Alger, aller-retour du 15 au 25 février 2027, 500 euros chacun"
```

**Le script de démonstration officiel,** avec ses scénarios alternatifs, est
[demo/README.md](demo/README.md).

**Codes de sortie :**

| Code | Sens |
|---|---|
| 0 | proposition |
| 1 | erreur technique |
| 2 | clarification nécessaire |
| 3 | demande invalide |
| 4 | non validée |
| 64 | usage incorrect |
| 130 | interruption |

## Données synthétiques

| Données | Fichier | Version |
|---|---|---|
| Catalogue v1 (Tokyo, Rome) | `data/catalog/catalog_v1.json` | figé par manifeste |
| Catalogue v2 (forfaits aller-retour Lyon/Marseille → Alger) | `data/catalog/catalog_v2.json` | figé par manifeste |
| Référentiel des lieux et alias | `data/catalog/places_v1.json` | figé par manifeste |
| Carnets de demandes en attente | `data/demand/demand_pool_v1.jsonl`, `_v2.jsonl` | figés par manifeste |
| Jeux d'évaluation de l'extraction (v1, v2, v3, profils) | `data/eval/` | versionnés |
| Corpus RAG, requêtes et jugements | `data/eval/rag/` | versionnés |
| Documents RAG hostiles | `data/eval/rag/hostile_documents_v1.jsonl` | versionné |
| Scénarios économiques de référence | `data/scenarios/economic_scenarios_v1.json` | versionné |

Les catalogues contiennent des termes privés de vendeurs fictifs. Ils ne sortent jamais
dans les propositions publiques (tests T-CONF).

## Tests et qualité

```bash
PYTHONHASHSEED=0 python -m pytest -q
ruff check Multi-Agent/coalition_travel Multi-Agent/plan_trip.py tests
ruff format --check Multi-Agent/coalition_travel Multi-Agent/plan_trip.py tests
```

- **Contenu de la suite :** contrats, P1 à P5, golden master des démonstrations
  historiques, confidentialité, commande de bout en bout, documents hostiles et limites
  d'entrée.
- **Sans service externe :** aucun test n'appelle Ollama.
- **Intégration continue :** [.github/workflows/ci.yml](.github/workflows/ci.yml),
  hors ligne.

## Évaluations

| Évaluation | Commande | Résultats |
|---|---|---|
| Extraction LLM (3 modèles locaux, prompts v1 et v2) | `coalition-travel-eval --model …` | [docs/FINAL_LLM_EVALUATION.md](docs/FINAL_LLM_EVALUATION.md) |
| Retrieval RAG (3 modèles d'embedding, découpages, Top-K, seuils) | `coalition-travel-eval-rag --model … --database …` | [docs/FINAL_RAG_EVALUATION.md](docs/FINAL_RAG_EVALUATION.md) |
| Injection par document récupéré | `python Multi-Agent/evaluate_injection.py --model …` | idem |
| Formation P4 (performance, exploratoire) | `python Multi-Agent/evaluate_formation.py …` | [docs/p4_results/](docs/p4_results/) |
| Allocation P5 | `python Multi-Agent/evaluate_allocation.py …` | [docs/p5_results/](docs/p5_results/) |
| Scénarios économiques | `python Multi-Agent/evaluate_scenarios.py` | [docs/FINAL_PERFORMANCE_REPORT.md](docs/FINAL_PERFORMANCE_REPORT.md) |

## Optimisation et allocation

- **P4.** Partition optimale exacte par programmation dynamique ou `idp_search`, avec un
  MILP HiGHS en contrôle croisé. Les valeurs doivent être égales, et la partition est
  vérifiée à l'exécution. Une composante trop grande est signalée
  (`component_too_large`), jamais approximée.
- **P5.** Valeur de Shapley exacte en rationnels, projection sur
  `0 ≤ y ≤ référence`, centimes entiers par la méthode du plus fort reste.
  Garanties :
  - Σ paiements = coût négocié ;
  - aucun paiement au-dessus de la référence ni du budget.

## Documentation

- [docs/FINAL_DELIVERY_REPORT.md](docs/FINAL_DELIVERY_REPORT.md) : rapport de livraison
  final.
- [docs/FINAL_PROJECT_AUDIT.md](docs/FINAL_PROJECT_AUDIT.md) : audit et matrice d'état.
- [docs/FINAL_ARCHITECTURE.md](docs/FINAL_ARCHITECTURE.md) : architecture réelle et
  cible.
- [docs/FINAL_SECURITY_REVIEW.md](docs/FINAL_SECURITY_REVIEW.md) : sécurité et
  robustesse.
- [docs/FINAL_PERFORMANCE_REPORT.md](docs/FINAL_PERFORMANCE_REPORT.md) : performances.
- [docs/FINAL_DEFENSE_DOSSIER.md](docs/FINAL_DEFENSE_DOSSIER.md) : dossier de
  soutenance.
- [docs/AI_ENGINEER_INTERVIEW_GUIDE.md](docs/AI_ENGINEER_INTERVIEW_GUIDE.md) : guide
  d'entretien.
- `docs/PHASE_*.md` : rapports des phases P0 à I4. Ils restent la trace historique.

## Démonstrations historiques

`coalition-travel` (ou `python Multi-Agent/Entry.py`) exécute les démonstrations
d'origine du TP :

- négociation bilatérale et négociation de groupe ;
- broker, liste noire, effet de la date limite ;
- DP, IDP et IP contre un oracle exhaustif ;
- ordres d'arrivée, jeux non superadditifs.

Leur sortie est figée par un golden master
(`tests/golden/entry_run_scenarios_2026-11-19.txt`).

## Limites

1. **Données fictives** et propositions simulées.
2. **Agents locaux et synchrones.** Pas de SPADE/XMPP, ni d'API, ni d'interface web.
3. **Extraction par LLM imparfaite.** Les scores réels et les erreurs sont dans le
   rapport LLM. La personne valide toujours la demande résumée avant toute simulation.
4. **RAG non branché sur la commande principale :** il est documentaire et ne prend
   aucune décision.
5. **Python 3.10.** La suite complète y garde 3 échecs : le golden master dépend de
   l'ordre d'affichage des ensembles, qui change avec l'algorithme de hachage des
   chaînes (`siphash24` sous 3.10). Sur macOS 27, la seule roue SciPy installable pour
   3.10 (1.14.1) est défaillante. Voir
   [docs/FINAL_PROJECT_AUDIT.md](docs/FINAL_PROJECT_AUDIT.md), §5.
6. **Composantes bornées.** La formation exacte est limitée en taille.
