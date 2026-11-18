# CoalitionTravel — négociation multi-agents

Projet pédagogique Python qui simule la négociation de billets entre acheteurs, vendeurs et un broker, puis compare des méthodes d’optimisation de structures de coalitions.

## État du projet

Le dépôt contient maintenant une démonstration exécutable des négociations bilatérales et de groupe, de la formation de coalitions, de la répartition des paiements et de l’optimisation DP / IDP / IP. Le point d’entrée des démonstrations est `Multi-Agent/Entry.py`.

## Installation et lancement

Python 3.10 ou ultérieur est recommandé. Depuis la racine du dépôt :

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python Multi-Agent/Entry.py
```

Le dépôt est installable en mode éditable avec `python -m pip install -e '.[dev]'`. La commande `coalition-travel` lance les démonstrations. NumPy et SciPy prennent en charge la recherche IP; SciPy fournit le solveur HiGHS utilisé par `scipy.optimize.milp`. Pydantic valide les données à la frontière d’entrée. `pyproject.toml` est la source des métadonnées et dépendances; `requirements.txt` conserve une commande d’installation simple.

## État AI Engineering

Le code reste une **simulation locale synchrone**. Les fondations livrées dans cette version sont :

- `Multi-Agent/coalition_travel/domain/coalition_problem.py` contient une fonction de valeur indépendante des budgets globaux; chaque instance du problème possède ses propres budgets et remises.
- `Multi-Agent/coalition_travel/domain/request.py` définit le contrat Pydantic `TravelRequestDraft` pour les champs candidats extraits d’une demande en langage naturel. Les champs manquants restent explicites et les champs inattendus sont rejetés.
- `Multi-Agent/coalition_travel/application/request_understanding.py` sépare le contrat d’extraction, la validation métier et la demande de clarification. Les résultats exposent le statut, les champs à clarifier, le fournisseur et la latence.
- `Multi-Agent/coalition_travel/infrastructure/llm/ollama.py` fournit un adaptateur Ollama local qui transmet le schéma JSON Pydantic et valide de nouveau la réponse côté application. Il distingue les erreurs de transport des sorties non conformes.
- `data/eval/request_extraction.jsonl` et `Multi-Agent/evaluate_requests.py` fournissent un petit jeu synthétique et un évaluateur d’extraction par exact-match; ce jeu est un point de départ, pas encore un benchmark représentatif.
- `Multi-Agent/coalition_travel/application/optimization.py` encapsule IDP dans un service qui retourne une structure de résultat et une latence mesurée. La vérification par force brute est optionnelle et désactivée par défaut; les démonstrations et tests peuvent l’activer sur les petites instances.
- `tests/` vérifie les contrats, les agents, les règles de négociation et les algorithmes; Ruff contrôle le format et les erreurs de lint sur les nouveaux modules.

**Pas encore réalisés :** SPADE/XMPP, API FastAPI, PostgreSQL, ingestion RAG/Qdrant, interface web et traces distribuées. L’adaptateur LLM existe, mais aucun modèle Ollama n’est installé sur cette machine et aucune inférence réelle n’a été mesurée. Le dossier de conception décrit les composants restants comme des étapes futures; le dépôt ne doit pas être présenté comme les ayant déjà implémentés.

## Tests et qualité

```bash
python -m pytest
ruff format --check Multi-Agent/coalition_travel tests Multi-Agent/evaluate_requests.py
ruff check Multi-Agent/coalition_travel tests Multi-Agent/evaluate_requests.py
```

Avec Ollama installé, démarré et un modèle local téléchargé, évaluer l’extraction sur les exemples synthétiques :

```bash
OLLAMA_MODEL='<nom-du-modele-local>' coalition-travel-eval
```

Le rapport JSON contient le taux d’exact-match par champ, le score exact par demande, les erreurs et la latence moyenne. Les scénarios complets et leurs limites sont décrits dans [SCENARIOS.md](SCENARIOS.md). Les temps mesurés dans une seule exécution ne prouvent pas une accélération relative à une version antérieure.

## Scénarios exécutés

Le programme `Multi-Agent/Entry.py` exécute les démonstrations suivantes :

1. Négociation bilatérale acheteur-vendeur avec propositions alternées.
2. Création de coalitions de trois et quatre acheteurs par le broker, puis négociation d’un tarif de groupe.
3. Refus d’un vendeur figurant dans la liste noire d’un acheteur.
4. Effet de la date limite sur le taux de concession, avec dates de référence contrôlables.
5. Optimisation d’une structure de coalitions avec DP, IDP et IP, vérifiée par un oracle exhaustif sur la petite instance de démonstration.
6. Comparaison de deux ordres d’arrivée traités par le broker avec la structure optimale IDP, puis négociations effectives des groupes retenus.
7. Comparaison entre un jeu de coalition non superadditif et un jeu superadditif.

## Améliorations et corrections

Les changements récents renforcent les comportements du modèle et rendent les démonstrations plus vérifiables :

- **Dates de négociation reproductibles** — `BuyerAgent` accepte une date de référence et des échéances au format date, datetime ou chaîne prise en charge. Les scénarios utilisent des dates relatives à une même référence. Cela évite que les résultats changent selon le jour où le programme est lancé, et corrige les cas où une échéance déjà passée sans année était interprétée avec la mauvaise année.
- **Validation des entrées** — budgets, prix planchers, offres initiales, réductions, identifiants d’agents, valeurs de coalition et limites de tours sont validés. Les erreurs de données sont signalées à leur origine plutôt que de produire des résultats invalides plus loin dans l’exécution.
- **Routage des messages contrôlé** — la boucle de négociation vérifie que chaque message est transmis à son destinataire et respecte la limite de tours. Cela prévient les échanges mal routés et les boucles sans fin.
- **Tarification de groupe cohérente** — le prix plancher et l’offre de départ sont calculés pour le nombre de billets du groupe et à partir d’un tarif catalogue indépendant des budgets des membres. L’ancienne approche mélangeait budget moyen et tarif unitaire, ce qui rendait la comparaison des prix de groupe difficile à interpréter.
- **Répartition des coûts contrainte par les budgets** — les paiements égaux ou issus des transferts de Shapley sont ajustés pour respecter chaque budget individuel, tout en conservant le total de l’accord. Une coalition dont le budget cumulé ne couvre pas l’accord est rejetée explicitement.
- **Formation de coalition plus robuste** — le broker ignore les inscriptions en double, permet de finaliser un groupe incomplet lorsque sa taille minimale est atteinte et conserve l’historique des coalitions formées. Les remises sont configurables.
- **Vérification des partitions et référence exacte** — DP, IDP et IP valident que leur résultat couvre chaque agent exactement une fois. Un oracle exhaustif indépendant est ajouté pour les petites instances; le programme compare les valeurs optimales obtenues par les quatre méthodes et échoue si elles divergent.
- **Démonstrations intégrées** — les scénarios réutilisent une même boucle d’alternance et montrent le fonctionnement réel du broker, les négociations de coalitions, les allocations individuelles et l’impact des ordres d’arrivée.
- **Dépendances déclarées** — `pyproject.toml` décrit NumPy, SciPy, Pydantic et les outils de développement; les fichiers `requirements*.txt` fournissent des commandes d’installation courtes.

Ces corrections visent surtout la cohérence des résultats, la reproductibilité et la détection des erreurs. Les mesures ponctuelles sur l’instance de démonstration ont donné un IDP plus rapide que DP pour 5 et 8 agents, tandis que IP et l’oracle exhaustif étaient plus lents sur ces tailles. Elles ne constituent pas une preuve d’accélération par rapport à une version antérieure, faute de benchmark de référence mesuré dans les mêmes conditions.

## Résultats de validation

La dernière suite locale compte **36 tests réussis**. Le contrôle Ruff passe sur les nouveaux modules. La commande `coalition-travel` s’est terminée avec le code de sortie 0 et a atteint `FIN DES SCÉNARIOS`. Les accords et allocations affichés respectaient les budgets des membres. Les temps varient selon l’environnement et la fonction de valeur; aucune accélération par rapport à une ancienne version n’a été mesurée dans des conditions identiques.

## Structure principale

- `Multi-Agent/Entry.py` — scénarios de démonstration et fonction de valeur.
- `Multi-Agent/BuyerAgent.py` — préférences, budget, échéance et stratégie d’achat.
- `Multi-Agent/SellerAgent.py` — prix plancher et stratégie du vendeur.
- `Multi-Agent/BrokerAgent.py` — inscriptions et formation de coalitions.
- `Multi-Agent/Leader.py` — négociation de groupe et allocations.
- `Multi-Agent/Negotiation.py` — routage des offres alternées.
- `Multi-Agent/CoalitionStructureSearch.py` — DP, IDP, IP, oracle exhaustif et Shapley.
- `Multi-Agent/coalition_travel/domain/` — fonction de valeur explicite et schéma de demande Pydantic.
- `Multi-Agent/coalition_travel/application/` — clarification après extraction, évaluation et service d’optimisation.
- `Multi-Agent/coalition_travel/infrastructure/llm/` — adaptateur Ollama local à sortie structurée.
- `Multi-Agent/evaluate_requests.py` et `data/eval/` — commande et petit jeu synthétique d’évaluation.
- `tests/` — tests unitaires et de contrat pour le domaine, les agents et les algorithmes.
- `Multi-Agent/Message.py`, `Multi-Agent/Agent.py` — messages et classe agent de base.
