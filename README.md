# CoalitionTravel — négociation multi-agents

Projet pédagogique Python qui simule la négociation de billets entre acheteurs, vendeurs et un broker, puis compare des méthodes d’optimisation de structures de coalitions.

## État du projet

Le dépôt contient maintenant une démonstration exécutable des négociations bilatérales et de groupe, de la formation de coalitions, de la répartition des paiements et de l’optimisation DP / IDP / IP. Le point d’entrée des démonstrations est `Multi-Agent/Entry.py`.

## Installation et lancement

Python 3.10 ou ultérieur est recommandé. Depuis la racine du dépôt :

```bash
python -m pip install -r requirements.txt
python Multi-Agent/Entry.py
```

Les dépendances pour la recherche IP sont NumPy et SciPy. SciPy fournit le solveur HiGHS utilisé par `scipy.optimize.milp`.

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
- **Dépendances déclarées** — `requirements.txt` liste NumPy et SciPy pour permettre une installation reproductible des bibliothèques utilisées par les algorithmes.

Ces corrections visent surtout la cohérence des résultats, la reproductibilité et la détection des erreurs. Les mesures ponctuelles sur l’instance de démonstration ont donné un IDP plus rapide que DP pour 5 et 8 agents, tandis que IP et l’oracle exhaustif étaient plus lents sur ces tailles. Elles ne constituent pas une preuve d’accélération par rapport à une version antérieure, faute de benchmark de référence mesuré dans les mêmes conditions.

## Résultats de validation

La dernière exécution de `python Multi-Agent/Entry.py` dans un conteneur Docker Python s’est terminée avec le code de sortie 0 et a atteint `FIN DES SCÉNARIOS`. Les accords et allocations affichés dans les scénarios exécutés respectaient les budgets des membres. Les temps des algorithmes varient selon l’environnement et la fonction de valeur; les chiffres ponctuels ci-dessus ne sont pas des garanties de performance.

## Structure principale

- `Multi-Agent/Entry.py` — scénarios de démonstration et fonction de valeur.
- `Multi-Agent/BuyerAgent.py` — préférences, budget, échéance et stratégie d’achat.
- `Multi-Agent/SellerAgent.py` — prix plancher et stratégie du vendeur.
- `Multi-Agent/BrokerAgent.py` — inscriptions et formation de coalitions.
- `Multi-Agent/Leader.py` — négociation de groupe et allocations.
- `Multi-Agent/Negotiation.py` — routage des offres alternées.
- `Multi-Agent/CoalitionStructureSearch.py` — DP, IDP, IP, oracle exhaustif et Shapley.
- `Multi-Agent/Message.py`, `Multi-Agent/Agent.py` — messages et classe agent de base.
