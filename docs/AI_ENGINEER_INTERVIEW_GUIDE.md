# Guide d'entretien AI Engineer : CoalitionTravel

Questions difficiles qu'un ingénieur senior peut poser, avec des réponses honnêtes et
reliées au code. Les chemins sont relatifs à `Multi-Agent/coalition_travel/`, sauf
mention contraire.

---

### Pourquoi une approche multi-agents ?

Le problème met face à face des intérêts privés :

- chaque acheteur a un budget qu'il ne révèle pas ;
- chaque vendeur a un plancher qu'il ne révèle pas.

Le prix final résulte d'une **négociation par offres alternées** entre ces parties
(agents historiques `BuyerAgent`, `SellerAgent` et `Negotiation.py`, encapsulés par
`infrastructure/negotiation/simulated_oracle.py`). Le modèle multi-agents rend
explicite **qui sait quoi**. Les tests de confidentialité T-CONF le vérifient sur la
sortie publique.

**Limite à reconnaître :** les agents sont simulés dans un seul processus, de façon
synchrone. Ce n'est pas un système distribué.

### Pourquoi un LLM, et pas une extraction déterministe ?

La demande arrive en langage naturel, avec des dates relatives, des groupes aux
contraintes différentes et des formulations variées : une grammaire figée couvre mal
cela. Le LLM n'y fait qu'**une** chose : extraire les faits exprimés dans un schéma
Pydantic (`infrastructure/llm/ollama.py`).

Tout le reste est déterministe :

- la validation, la clarification et les lieux ;
- l'admissibilité, la négociation, P4 et P5.

Pour les tests et la démonstration, un **extracteur de rejeu**
(`infrastructure/llm/replay.py`) remplace le modèle : les résultats sont reproductibles
sans GPU. Les performances réelles du LLM sont mesurées dans
`docs/FINAL_LLM_EVALUATION.md`. Elles montrent aussi ses erreurs.

### Pourquoi Pydantic ?

C'est un contrat exécutable à la frontière :

- `TravelRequestDraft` refuse les champs inattendus et typifie dates, montants et
  effectifs ;
- son schéma JSON est envoyé à Ollama, ce qui contraint la génération.

Une réponse hors contrat devient une `StructuredOutputError` : une erreur
**technique**, jamais présentée comme une erreur de la personne.

### Pourquoi le LLM ne décide-t-il pas des prix ?

Parce qu'un prix doit être reproductible, auditable et borné par des contrats :

- les prix viennent d'un catalogue figé par manifeste ;
- les accords viennent de négociations simulées et journalisées ;
- les paiements sont calculés en rationnels exacts.

Aucun module de décision n'importe la couche LLM ni la couche RAG. Un test AST le
vérifie (`tests/test_final_hostile_context.py`).

### Pourquoi un RAG local, et pourquoi SQLite ?

- **Le corpus est petit et documentaire** : règles métier, descriptions fournisseurs
  fictives.
- **SQLite suffit à cette échelle :**
  - il est transactionnel, puisque la réindexation remplace un document dans une
    transaction ;
  - il n'ajoute ni service ni dépendance ;
  - il enregistre l'identité de l'espace vectoriel et refuse de mélanger deux modèles.

Un moteur vectoriel dédié ne se justifierait qu'avec un corpus bien plus grand. Les
mesures sont dans `docs/FINAL_RAG_EVALUATION.md`.

**Limite :** le RAG n'est pas branché sur la commande principale. Il est seulement
injectable dans `understand_request`.

### Pourquoi DP/IDP et MILP ?

La formation de coalitions est un problème de **partition optimale**, dit *coalition
structure generation*.

- La programmation dynamique (`dp`) et `idp_search` sont **exactes** sur une composante
  bornée. Elles exploitent la structure du jeu.
- Le MILP de partitionnement (`infrastructure/optimization/exact_milp.py`, HiGHS) donne
  une **seconde méthode indépendante**. Le code exige que les deux valeurs optimales
  soient égales, ce qui sert de certification croisée.

Au-delà de `max_component_units`, le statut est `component_too_large`. Il n'y a **pas**
d'heuristique silencieuse.

### Comment prouver l'optimalité ?

Par trois éléments :

1. **L'exactitude des algorithmes,** testée contre un oracle exhaustif sur de petites
   instances.
2. **L'égalité des valeurs** entre méthodes indépendantes, vérifiée à l'exécution.
3. **La vérification que la structure est une partition,** à l'exécution :
   `PartitionInvalid` sinon.

**Anecdote réelle :** une roue SciPy 1.14.1 défaillante sur macOS 27 a produit une
sélection MILP invalide. Le contrôle l'a détectée au lieu de l'accepter
(`docs/FINAL_PROJECT_AUDIT.md`, §5).

### Pourquoi Shapley ?

La valeur de Shapley est la seule allocation qui satisfait à la fois l'efficacité, la
symétrie, le joueur nul et l'additivité. Elle répartit l'économie selon la contribution
marginale moyenne de chacun. Elle est calculée **en rationnels exacts**
(`domain/savings_allocation.py`), sur le jeu de couverture `v*`.

### Pourquoi projeter le vecteur de Shapley ?

Shapley peut sortir des bornes admissibles : une économie négative, ou supérieure à la
référence. La projection euclidienne sur `{Σ y = v*(C), 0 ≤ y ≤ ref}` garantit deux
choses :

- personne ne paie plus que son coût solo ;
- personne n'est payé pour voyager (θ = 0, `docs/PHASE_P5_ADDENDUM_ID6.md`).

Les mesures M2 ont montré que la projection n'a **jamais** été active sur la strate
exploratoire, car `v*` y est superadditif. Elle n'est démontrée que sur des cas
construits.

### Comment protéger les données privées ?

- **Contrats de sortie fermés :** `trip-proposal-v1` / `-v2` ont des noms de champs
  figés (T-CONF-3).
- **Non-interférence :** changer le budget d'un autre membre ne change pas un octet de
  la sortie (T-CONF-1).
- **Aucune empreinte calculée sur des données privées** dans la provenance publique.
  C'est le cas de `catalog_sha256`, retiré par D-I3-18.
- **Risque résiduel B7, déclaré :** un montant public peut coïncider avec un plancher.

### Comment gérer l'idempotence ?

- **Clés de requête économiques :** chaque négociation a une clé recalculée à partir de
  son contenu (`domain/negotiation_request.py`, `negotiation-request-key-v2` /
  `-v3`).
- **Cache :** il garantit *une clé, une réponse*.
- **Journaux :** ils sont vérifiés par les invariants J1 à J5. Un journal non
  déterministe pour une même clé lève `NonDeterministicJournalError`.
- **Empreintes :** les identifiants de formation et de résultat permettent de rejouer
  et de comparer une exécution.

### Comment passer à une vraie architecture distribuée ?

Sans réécrire P4 ni P5 :

1. **Remplacer l'oracle simulé** par un adaptateur de messages, par exemple
   XMPP/SPADE ou une file de messages, qui expose la même interface `negotiate`.
2. **Utiliser la clé de requête** comme identifiant d'idempotence des messages.
3. **Ajouter des temporisations,** avec un statut terminal typé `timeout`.
4. **Garder le simulateur** comme baseline et comme oracle de test.

Rien de cela n'est réalisé (`docs/FINAL_ARCHITECTURE.md`, §8).

### Comment gérer la disponibilité fournisseur ?

Aujourd'hui, la disponibilité est la capacité figée du catalogue, avec la précondition
H2 : la demande ne dépasse la capacité d'aucune offre. Une vraie disponibilité
viendrait d'un adaptateur fournisseur, interrogé avant la négociation. **Jamais** du LLM
ni du RAG.

### Quelles sont les limites du système ?

Voir `docs/FINAL_DELIVERY_REPORT.md`, §14. Les principales :

- les données sont fictives ;
- les agents s'exécutent dans un processus local synchrone ;
- l'extraction par LLM est imparfaite, avec des scores mesurés ;
- le RAG n'est pas branché sur la commande principale ;
- la suite complète n'est pas verte sous Python 3.10 (ordre d'affichage du golden
  master) ;
- il n'y a ni API ni interface.

### Quelles mesures ont été réellement obtenues ?

| Mesure | Valeur | Source |
|---|---|---|
| P4 performance, 14 unités | médiane 6,63 s par instance, 5 répétitions après une chauffe | `docs/p4_results/performance_report.md` |
| P4 exploratoire | 1 740 instances, dont 1 616 avec blocs | `docs/p4_results/exploratory_report.md` |
| P5 M1 | 0,385 s, contre 6,727 s pour P4 (k = 14) | `docs/PHASE_I2_ALLOCATION_REPORT.md`, §5 |
| P5 M2 | ratio médian `T_P5 / T_P4` de 0,0307 | idem |
| Extraction LLM, 3 modèles locaux | voir le rapport | `docs/FINAL_LLM_EVALUATION.md` |
| Retrieval, 3 modèles d'embedding | voir le rapport | `docs/FINAL_RAG_EVALUATION.md` |
| Suite de tests | voir le rapport final | `docs/FINAL_DELIVERY_REPORT.md` |
