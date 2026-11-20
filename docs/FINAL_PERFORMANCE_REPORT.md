# Rapport de performance

**Date :** 2026-11-20.

**Machine :** MacBook Air M1 (MacBookAir10,1), 16 Go, macOS 27, Python 3.14.2,
NumPy 2.4.1, SciPy 1.17.1. La mesure P4 a été faite **seule** : Ollama était au repos
et ses modèles déchargés, et aucune autre mesure ne tournait.

---

## 1. Protocole

| Élément | Valeur |
|---|---|
| Commande | `PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=Multi-Agent python Multi-Agent/evaluate_formation.py performance --output <rép.>` |
| Tailles | 6, 8, 10, 12, 14 et 16 unités ; 10 instances par taille (graines dérivées) |
| Répétitions | 1 chauffe, conservée à part, puis 5 répétitions chronométrées par instance ; chaque répétition doit redonner le même résultat, sinon arrêt |
| Mesures | durée totale et durée par phase ; médiane, quartiles et maximum |
| Entrées | identiques à la référence historique : même empreinte de `results.json` |
| Données brutes | `docs/final_results/p4_performance_report_2026-11-20.md` (tableaux volatils et détail par instance) |
| Commit | arbre de travail issu de `5d547ec` ; aucun module de P4 ni de P5 modifié par la mission |

**Empreinte de `results.json` :**
`3024fef1187ece03e97c4da3391b2bb9e7c458f8346fad007402dc29310b0b85`. Elle est identique
à la référence de `docs/p4_results/README.md` : **les mêmes instances donnent les mêmes
résultats.** Les durées n'entrent pas dans cette empreinte.

## 2. P4 : durée totale par taille

En secondes, sur 50 mesures par taille.

| Unités | Médiane 2026-11-20 | [Q1, Q3] | Maximum | Médiane historique (`docs/p4_results/performance_report.md`) |
|---:|---:|---|---:|---:|
| 6 | 0,0148 | [0,0128 ; 0,0158] | 0,0209 | – |
| 8 | 0,0733 | [0,0719 ; 0,0744] | 0,0835 | – |
| 10 | 0,2035 | [0,1888 ; 0,2111] | 0,2177 | – |
| 12 | 1,0529 | [1,0415 ; 1,0609] | 1,1261 | – |
| 14 | **6,6386** | [6,5939 ; 6,6913] | 6,8087 | **6,6323** |
| 16 | 0,0017 | [0,0016 ; 0,0018] | 0,0019 | – |

**Lecture des résultats :**

1. **Croissance exponentielle.** La durée est multipliée par 5 à 6 entre 10, 12 et 14
   unités. C'est attendu : à 14 unités, l'énumération porte sur 16 383 coalitions
   candidates par composante (détail par instance).
2. **Reproductibilité des durées.** À 14 unités, la médiane diffère de la mesure
   historique de 0,1 %, à l'intérieur de l'écart interquartile. Une seule session ne
   suffit pas à prétendre davantage.
3. **16 unités.** La composante dépasse `max_component_units` : le statut est
   `component_too_large`, sans approximation et sans calcul. D'où la durée quasi nulle.
   **C'est la limite réelle du solveur exact dans sa configuration actuelle.**

## 3. P4 : où va le temps (14 unités)

Médiane des médianes par instance, en secondes.

| Phase | Durée | Part |
|---|---:|---:|
| négociations collectives (oracle simulé, cache compris) | 2,150 | 32 % |
| contrôle croisé (programmation dynamique) | 1,881 | 28 % |
| solveur (`idp_search`) | 1,828 | 28 % |
| faisabilité des candidats | 0,648 | 10 % |
| jeu, énumération, références, admissibilité | 0,136 | 2 % |

- **Le contrôle croisé de la DP double presque le coût du solveur.** C'est le prix de
  la certification par une seconde méthode exacte, et un compromis assumé.
- **Le cache de négociation :** sur l'instance de 14 unités de la graine 2, il donne
  16 098 succès pour 299 appels réels à l'oracle (détail par instance).

## 4. P5 (mesures historiques, code inchangé)

P5 n'a pas été modifié par la mission : les mesures M0 à M2 d'I2 restent valables
(`docs/PHASE_I2_ALLOCATION_REPORT.md`, §5). Ces mesures datent de la phase I2 [R] :

| Mesure | Résultat | Seuil fixé avant la mesure |
|---|---|---|
| M1 : médiane `T_P5` (dense, k = 14) | 0,385 s, contre 6,727 s pour `T_P4_total(14)` | < `T_P4_total(14)` |
| M2 : médiane `T_P5 / T_P4_total` sur 1 616 instances avec blocs | 0,0307 | ≤ 0,25 |

## 5. Bout en bout

| Mesure | Valeur | Nature |
|---|---|---|
| 18 scénarios économiques, par la commande publique | 0,90 s au total, mesure `time` d'une exécution | [E], indicatif |
| Lyon-Alger, de la demande structurée à la proposition | moins d'une seconde | [E], indicatif |
| Extraction LLM, `qwen2.5:7b`, transport corrigé | 22 à 39 s en médiane par appel selon le jeu | [E], `docs/FINAL_LLM_EVALUATION.md` |
| Extraction LLM, modèles 3B | 9 à 23 s en médiane | [E] |
| Retrieval, embedding de la requête et recherche | 13 à 67 ms | [E], `docs/FINAL_RAG_EVALUATION.md` |

**L'extraction LLM domine de deux ordres de grandeur** le temps d'une demande dont les
composantes restent petites. Le calcul exact ne devient coûteux qu'au-delà d'une dizaine
d'unités dans une même composante.

## 6. Limites

- **Une seule machine, une seule session** par mesure. Les comparaisons entre machines
  ne sont pas faites.
- **Laptop sans ventilateur :** un bridage thermique sur de longues séries n'est pas
  exclu. L'écart interquartile reste faible (moins de 1,5 % à 14 unités).
- **Mémoire non mesurée** par l'outillage actuel.
- **Le MILP** n'est pas chronométré dans cette strate. Son exactitude dépend de la roue
  SciPy de la plateforme (`docs/FINAL_PROJECT_AUDIT.md`, §5).
