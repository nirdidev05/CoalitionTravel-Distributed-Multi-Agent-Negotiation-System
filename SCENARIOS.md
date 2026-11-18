# Scénarios de démonstration CoalitionTravel

Ces résultats correspondent à l’exécution du dépôt après l’ajout du modèle de domaine et du service d’optimisation. Ils sont simulés; les tarifs ne proviennent pas de fournisseurs réels.

Pour lancer les démonstrations :

```bash
python -m pip install -r requirements.txt
python Multi-Agent/Entry.py
```

## 1. Négociation bilatérale

Alice dispose de 500 €. AirFrance démarre à 560 € et ne descend pas sous son plancher de 400 €. L’accord est de **453,60 €**. Le routeur affiche **6 étapes de réception de message**, soit trois cycles aller-retour selon l’ancienne convention du rapport.

## 2. Formation et négociation de coalitions

Le broker forme un groupe de trois pour Tokyo et un groupe de quatre pour Rome.

| Groupe | Remise simulée | Prix total | Moyenne par billet |
|---|---:|---:|---:|
| Bob, Carol, Dave | 10 % | 1 512,00 € | 504,00 € |
| Lina, Marc, Nora, Omar | 20 % | 1 792,00 € | 448,00 € |

Les prix sont des totaux de groupe. La remise affecte le plancher tarifaire simulé; l’acceptation dépend aussi du budget cumulé.

## 3. Préférence négative

Eve place AirFrance dans sa liste noire. Une proposition de 350 € est rejetée avant la comparaison avec son budget : la préférence déclarée prime sur le prix.

## 4. Pression temporelle

Les échéances sont calculées à partir d’une même date de référence afin de rendre les taux reproductibles.

| Acheteur | Échéance | Taux plafond | Prix accepté |
|---|---:|---:|---:|
| Frank | 5 jours | 8,7 % | 408,24 € |
| Grace | 180 jours | 2,0 % | 408,24 € |

**Limite :** les taux diffèrent mais le prix final est identique. Le calendrier de concessions du vendeur mène au même prix accepté; cet exemple ne prouve donc pas à lui seul que l’urgence change l’issue économique.

## 5. Optimisation de partitions

Sur cinq agents, DP, IDP, IP et l’oracle exhaustif retournent tous :

```text
{Alice, Dave} | {Bob, Carol, Eve}
Valeur totale : 250,60
```

DP et IDP évaluent 31 coalitions non vides; IDP élague 37 paires de tailles. IP crée 31 variables binaires. L’oracle parcourt les 52 partitions des cinq agents. Ces mesures décrivent cette petite instance et ne garantissent pas les performances à grande échelle.

## 6. Broker glouton, ordre d’arrivée et partage

Le broker forme un groupe dès que trois inscriptions consécutives atteignent le seuil, puis vide sa liste d’attente. Les personnes qui arrivent ensuite peuvent rester seules.

| Ordre | Partition gloutonne | Valeur | Gain IDP |
|---|---|---:|---:|
| Alice, Bob, Carol, Dave, Eve | `{Alice, Bob, Carol} \| {Dave} \| {Eve}` | 198,00 | +52,60 (+26,6 %) |
| Alice, Dave, Eve, Bob, Carol | `{Alice, Dave, Eve} \| {Bob} \| {Carol}` | 181,20 | +69,40 (+38,3 %) |
| IDP | `{Alice, Dave} \| {Bob, Carol, Eve}` | 250,60 | — |

Les groupes optimaux sont ensuite négociés : Alice et Dave concluent à 957,60 €, soit 478,80 € chacun. Bob, Carol et Eve concluent à 1 478,40 €; les paiements Shapley sont respectivement de 491,80 €, 493,05 € et 493,55 €. Chaque groupe paie exactement le total négocié et reste dans les budgets individuels.

Le jeu superadditif donne une valeur IDP de **798,00** pour la grande coalition. Sa négociation distincte aboutit à un prix total simulé de **1 960,00 €**. La valeur coopérative et le prix fournisseur sont deux grandeurs différentes.

## Vérifications automatisées

`tests/` couvre les contrats de demande, clarifications, validations, valeur de coalition, paiements, inscriptions rejouées, routage, limites de tours, algorithmes et oracle sur petite instance. Lancer la suite avec `python -m pytest`; les chiffres de cette page sont des résultats d’exécution, pas des valeurs garanties.
