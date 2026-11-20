# Évaluation réelle de l'extraction LLM

**Date :** 2026-11-20. **Tout ce document est exécuté [E]** sur la machine décrite au §1.
Les fichiers bruts sont dans `docs/final_results/llm/` :

- `run1/` : passe 1 ;
- `run2/` et `run3/` : passes 2 et 3 ;
- `matrix.sh` et `aggregate.py` : les scripts.

---

## 1. Protocole

| Élément | Valeur |
|---|---|
| Machine | MacBook Air M1 (MacBookAir10,1), 16 Go, macOS 27 ; aucune autre charge pendant les passes |
| Serveur | Ollama 0.40.16 (Homebrew), lancé pour la session |
| Modèles | `qwen2.5:3b` (`357c53fb659c…`), `llama3.2:3b` (`a80c4f17acd5…`), `qwen2.5:7b` (`845dbda0ea48…`). Ce sont les plus grands modèles raisonnables pour 16 Go de mémoire partagée |
| Paramètres | température 0, graine 0, délai d'attente de 180 s |
| Prompt v1 | `travel-request-extraction-v1`, code exact du commit `dbf5bd4`, exécuté depuis une copie hors du dépôt |
| Prompt v2 | `travel-request-extraction-v2`, code courant |
| Jeux | `request_extraction` (8 exemples, v1), `request_extraction_v2` (26), `request_profiles_v1` (7), `request_extraction_v3` (8, trajets ; prompt v2 seulement) |
| Mesures | exact match par demande et par champ ; statut de validation ; précision et rappel des clarifications et des demandes invalides ; profils ; erreurs ; latence médiane et moyenne ; reproductibilité |

**Règle respectée :**

- les jeux et les prompts ont été figés avant la première mesure ;
- aucun texte de prompt n'a été modifié après observation des résultats.

## 2. Défaut d'intégration découvert par la mesure

**La passe 1 a été faite avec le code tel que livré.** Elle donne une extraction
quasiment inutilisable pour tous les modèles : `destination` est juste dans 0 à 12 % des
cas.

**Diagnostic contrôlé,** sur une seule demande du jeu v1 (« Nous sommes deux et cherchons
un voyage à Tokyo… ») :

| Format transmis à Ollama | Sortie de `qwen2.5:7b` |
|---|---|
| schéma Pydantic tel quel | `{"travellers": 2, "departure_before": null, …}` : **`destination` et `budget_per_person` omis** |
| mode `json` libre | destination et budget présents, mais clés hors contrat |
| schéma Pydantic, toutes les clés exigées | `destination: "Tokyo"`, `travellers: 2`, `budget_per_person: 500` |

**Cause.** Tous les champs de `TravelRequestDraft` ont une valeur par défaut. Le schéma
JSON de Pydantic ne contient donc **aucune liste `required`**. Avec le décodage contraint
d'Ollama, le modèle a le droit d'omettre des clés, et il omet justement les plus
importantes. Pydantic les remplit ensuite avec `null`, ce qui transforme chaque demande
en demande à clarifier.

**Correction.** `infrastructure/llm/ollama.py`, `transport_schema()`,
`SCHEMA_TRANSPORT_VERSION = "all-keys-required-v1"` :

- le schéma transmis exige toutes les clés ;
- les champs facultatifs acceptent toujours `null` ;
- le modèle Pydantic, qui valide la réponse, est inchangé ;
- le texte du prompt est inchangé.

Le test `test_the_transport_schema_requires_every_key_and_changes_nothing_else` fixe ce
comportement. **Pour comparer v1 et v2 à transport égal,** la même correction a été
appliquée à la copie du code v1, hors du dépôt.

**Ce n'est pas un ajustement au jeu d'évaluation :**

- le diagnostic porte sur un exemple ;
- la cause est mécanique (une clé absente du schéma) ;
- le prompt n'a pas changé ;
- les résultats de la passe 1 sont conservés et publiés.

## 3. Résultats par champ (passe 2, transport corrigé)

Exact match par champ, en %. La passe 1 est donnée entre parenthèses pour `destination`.

| Modèle | Prompt | Jeu | destination | voyageurs | budget | vol direct | départ après | profils | origine | type de trajet |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen2.5:7b | v1 | v1 (8) | 100 (12) | 25 | 100 | 38 | 38 | 25 | – | – |
| qwen2.5:7b | v2 | v1 (8) | 100 (12) | 25 | 100 | 38 | 25 | 0 | 100 | 100 |
| qwen2.5:7b | v1 | v2 (26) | 88 (12) | 35 | 85 | 15 | 38 | 15 | – | – |
| qwen2.5:7b | v2 | v2 (26) | 88 (12) | 23 | 85 | 12 | 19 | 0 | 92 | 81 |
| qwen2.5:7b | v2 | v3 (8) | 100 (0) | 38 | 100 | 12 | 75 | 0 | 100 | 100 |
| llama3.2:3b | v1 | v1 | 88 (0) | 38 | 88 | 25 | 62 | 38 | – | – |
| llama3.2:3b | v2 | v1 | 88 (0) | 12 | 88 | 25 | 62 | 38 | 88 | 88 |
| llama3.2:3b | v1 | v2 | 73 (8) | 35 | 73 | 12 | 77 | 35 | – | – |
| llama3.2:3b | v2 | v2 | 81 (8) | 19 | 81 | 8 | 77 | 23 | 85 | 85 |
| llama3.2:3b | v2 | v3 | 62 (0) | 12 | 88 | 0 | 88 | 12 | 88 | 88 |
| qwen2.5:3b | v1 | v1 | 88 (0) | 62 | 88 | 50 | 38 | 0 | – | – |
| qwen2.5:3b | v2 | v1 | 75 (0) | 50 | 75 | 50 | 25 | 12 | 75 | 75 |
| qwen2.5:3b | v1 | v2 | 65 (8) | 62 | 58 | 12 | 27 | 0 | – | – |
| qwen2.5:3b | v2 | v2 | 50 (8) | 42 | 42 | 15 | 27 | 4 | 54 | 50 |
| qwen2.5:3b | v2 | v3 | 25 (0) | 25 | 25 | 12 | 0 | 0 | 25 | 25 |

## 4. Résultats par demande

Les taux de statut et de clarification portent sur le statut de validation déterministe
du brouillon extrait (`ready`, `needs_clarification` ou `invalid`).

| Modèle | Prompt | Jeu | Exact match demande | Statut juste | Clarif. P / R | Invalide P / R | Échecs techniques | Latence médiane (s) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| qwen2.5:7b | v1 | v1 | 0 % | 37,5 % | 28,6 / 100 | – | 0 / 8 | 22,6 |
| qwen2.5:7b | v2 | v1 | 0 % | 37,5 % | 28,6 / 100 | – | 0 / 8 | 30,2 |
| qwen2.5:7b | v1 | v2 | 0 % | 53,8 % | 44,4 / 88,9 | 0 / 0 | 2 / 26 | 22,2 |
| qwen2.5:7b | v2 | v2 | 0 % | 38,5 % | 35,0 / 77,8 | 0 / 0 | 2 / 26 | 31,0 |
| qwen2.5:7b | v2 | v3 | 0 % | 25,0 % | 14,3 / 100 | – | 0 / 8 | 30,8 |
| llama3.2:3b | v1 | v2 | 0 % | 34,6 % | 33,3 / 44,4 | 0 / 0 | 6 / 26 | 9,2 |
| llama3.2:3b | v2 | v2 | 0 % | 38,5 % | 40,0 / 88,9 | 0 / 0 | 4 / 26 | 16,1 |
| qwen2.5:3b | v1 | v2 | 0 % | 46,2 % | 60,0 / 33,3 | 100 / 50 | 8 / 26 | 11,9 |
| qwen2.5:3b | v2 | v1 | 12,5 % | 50,0 % | 50,0 / 100 | – | 2 / 8 | 15,0 |
| qwen2.5:3b | v2 | v2 | 3,8 % | 26,9 % | 44,4 / 44,4 | 0 / 0 | 12 / 26 | 15,1 |

**Profils** (`request_profiles_v1`, 7 cas) : l'exact match des profils vaut 0 % pour
les trois modèles et les deux prompts. Le meilleur exact match du nombre de profils est
de 57 % (`qwen2.5:7b`).

**Échecs techniques.** Une réponse qui ne respecte pas le schéma devient une
`StructuredOutputError`, une erreur technique. Ce n'est jamais une demande invalide.

## 5. Reproductibilité

À température 0 et graine 0, **les brouillons extraits sont identiques entre les passes
2 et 3 pour 270 exemples sur 270** (3 modèles, 2 prompts, tous les jeux). Les latences,
elles, varient d'une passe à l'autre.

## 6. Analyse

1. **La correction du transport est décisive.** `destination` passe de 0–12 % à
   25–100 % selon le modèle et le jeu (62–100 % hors `qwen2.5:3b`) ; le budget passe
   de 0–62 % à 25–100 %.
2. **Le meilleur modèle est `qwen2.5:7b`,** sur les champs centraux (destination,
   budget, origine, type de trajet). Ce classement n'est établi que sur ces jeux
   synthétiques et ce matériel.
3. **Aucun modèle n'atteint un exact match par demande utilisable.** Trois erreurs
   reviennent systématiquement :
   - **un profil est inventé** alors que la demande n'en décrit pas, et le nombre de
     voyageurs y est placé au lieu du niveau de la demande. Les champs « voyageurs »
     et « profils » sont faibles ;
   - **`departure_after` reçoit la date de référence,** un fait non exprimé ;
   - **`direct_flight` est rempli** (`preferred`) sans indication dans la demande.
4. **Le prompt v2 ne fait pas mieux que le v1 sur les cas v1.** Il est même plus lent
   (schéma plus long : 22,6 s contre 30,2 s en médiane pour `qwen2.5:7b`). Son apport
   est d'extraire l'origine et le type de trajet, à 81–100 % pour `qwen2.5:7b`.
5. **Les clarifications.** Le rappel des demandes à clarifier est élevé (78–100 %),
   mais leur précision est faible (14–44 %). Le système demande donc trop souvent une
   clarification, ce qui est sûr mais coûteux pour la personne. Les demandes invalides
   (dates impossibles, nombres hors contrat) ne sont presque jamais reconnues comme
   telles.

## 7. Conséquences pour l'architecture

Ces mesures confirment le choix de conception :

- le LLM ne produit qu'un **brouillon** ;
- ce brouillon est validé de façon déterministe et **résumé à la personne, qui le
  valide** avant toute simulation ;
- une erreur d'extraction ne peut donc pas déclencher une négociation ni un paiement à
  l'insu de la personne.

Pour la démonstration, `--draft-json` et le rejeu restent les chemins reproductibles.

## 8. Limites

- **Échantillons petits,** de 7 à 26 cas par jeu, et synthétiques. Les écarts de
  quelques points ne sont pas significatifs.
- **L'exact match est strict :** une valeur sémantiquement juste mais formulée
  autrement compte comme fausse. Les nombres sont comparés par leur valeur.
- **Les latences** sont celles d'un M1 de 16 Go, sans optimisation de quantification.
- **Le prompt n'a pas été amélioré** après mesure, par règle. Un prompt v3 corrigeant
  les profils inventés devrait être évalué sur un jeu **nouveau**, tenu à l'écart.
