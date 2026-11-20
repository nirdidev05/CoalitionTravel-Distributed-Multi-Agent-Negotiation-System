# Résultats P4 : artefacts de synthèse

Ce dossier contient les rapports Markdown produits par
`Multi-Agent/evaluate_formation.py`, copiés tels quels. L'analyse et les réserves sont
dans `docs/PHASE_P4_IMPLEMENTATION.md`, §9.

| Fichier | Strate | Empreinte SHA-256 du `results.json` d'origine |
|---|---|---|
| `performance_report.md` | performance | `3024fef1187ece03e97c4da3391b2bb9e7c458f8346fad007402dc29310b0b85` |
| `exploratory_report.md` | exploratoire (descriptive) | `997109eee5a9ee4c6567410066730e2f8b5c8dd01bd46ff958b586f4c33eced4` |

- Les fichiers `results.json`, `environment.json` et les catalogues de scénarios
  générés ne sont **pas** versionnés : les catalogues contiennent des termes vendeurs
  privés. On les régénère avec les commandes du §12 du rapport d'implémentation ; les
  graines dérivées rendent les données identiques octet pour octet.
- Les tableaux de durées (strate performance) sont volatils : ils dépendent de la
  machine et n'entrent pas dans l'empreinte de `results.json`.
- Aucun de ces rapports ne contient de valeur de plancher (contrôlé par
  `write_report`).

## Lire ces rapports

Les rapports copiés gardent les intitulés courts produits par le script. Leurs
définitions exactes sont dans `docs/PHASE_P4_IMPLEMENTATION.md`, §9.2 :

- **populations** : la colonne « instances » compte toutes les instances d'une
  cellule. Les médianes, quartiles, baselines et décompositions ne portent que sur les
  instances qui ont au moins un bloc (1 616 sur 1 740). Les instances
  `no_eligible_units`, `capacity_model_violated` et `incomplete` n'y contribuent
  jamais ;
- **statuts** : la colonne « statuts » donne l'ensemble des statuts d'une cellule ;
  les effectifs des 20 cellules mixtes sont dans le rapport d'implémentation ;
- **B0 / optimum** : `ρ = V̄_B0 / V*`, défini seulement si `V* > 0`. On a `ρ ≤ 1`
  toujours ; ρ est négatif quand B0 forme des coalitions qui coûtent plus cher que
  leurs membres séparés, et inférieur à −1 quand cette perte dépasse l'économie
  optimale. ρ est instable quand V* est minuscule (jusqu'à −26 650 pour V* = 0,01 €) :
  il faut toujours le lire avec les valeurs absolues de `results.json` ;
- **écart relatif B1** : `(V* − V_B1) / V*`, défini seulement si `V* > 0` ; il est
  compris entre 0 inclus et 1 exclu. Si `V* = 0`, alors `V_B1 = 0`.

Mises en garde :

- le taux de succès du cache de la strate performance (98,3 % à 14 unités) est propre
  à sa cellule homogène. En exploration, la médiane est de 24,1 %, et de 1,6 % pour
  les instances de 1 000 candidats ou plus ;
- la limite de 14 unités est un garde-fou opérationnel configurable, mesuré sur une
  seule machine et une seule charge. Elle doit être recalibrée sur la machine et la
  charge cibles.
