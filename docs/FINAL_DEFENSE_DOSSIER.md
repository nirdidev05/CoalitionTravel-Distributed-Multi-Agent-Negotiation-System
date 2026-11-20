# Dossier de soutenance : CoalitionTravel

**Plateforme expérimentale locale de simulation de négociation et de formation de
coalitions de voyageurs.** Fournisseurs, prix et places sont fictifs ; le résultat est
une proposition simulée.

---

## 1. Problématique

Des voyageurs indépendants qui partent vers la même destination pourraient obtenir de
meilleurs tarifs en achetant ensemble. Cela soulève trois questions liées :

1. **Qui regrouper ?** Il faut une partition des demandes en coalitions qui maximise
   l'économie totale.
2. **À quel prix ?** Le prix résulte d'une négociation entre agents dont les
   informations sont privées : budgets des acheteurs, planchers des vendeurs.
3. **Comment répartir l'économie ?** La répartition doit être équitable, exacte et
   respecter les budgets.

S'y ajoute une question d'ingénierie IA : **comment accepter une demande en langage
naturel sans laisser un modèle de langage décider de ce qui doit rester exact et
auditable ?**

## 2. Objectifs

- Une chaîne complète, de la demande en texte libre à la proposition expliquée.
- Un **résultat déterministe et reproductible** à données égales.
- Une séparation stricte : le LLM extrait les faits, le code déterministe décide.
- Une évaluation mesurée de chaque composant d'IA : extraction, retrieval, résistance
  à l'injection.
- La protection des informations privées dans les sorties publiques.

## 3. Contributions

1. **Pipeline hybride** LLM, validation, négociation multi-agents, formation exacte et
   allocation exacte. Les frontières sont typées (Pydantic) et les contrats publics
   fermés (`trip-proposal-v1` / `-v2`).
2. **Formation de coalitions exacte** (P4) : programmation dynamique ou `idp_search`,
   certifiée par un MILP indépendant. Les valeurs doivent être égales, et la partition
   est vérifiée à l'exécution.
3. **Allocation exacte** (P5) : Shapley en rationnels, projection euclidienne sous
   bornes `0 ≤ y ≤ référence` (θ = 0), centimes par la méthode du plus fort reste.
   Aucun paiement ne dépasse le budget.
4. **Confidentialité vérifiée** par des tests de non-interférence (T-CONF) sur la
   sortie publique.
5. **Reproductibilité outillée :**
   - empreintes des strates P4 ;
   - manifestes des données ;
   - golden master des démonstrations historiques ;
   - scénarios économiques versionnés.
6. **Évaluation réelle de l'extraction LLM.** Elle a mis au jour un **défaut
   d'intégration** : le schéma transmis sans clés obligatoires permettait au décodage
   contraint d'omettre des champs. Ce défaut est mesuré, corrigé et documenté.

## 4. État de l'art pertinent

Ce dossier ne cite que des domaines bien établis, sans prétendre avoir reproduit un
article :

- **Génération de structures de coalitions** (*coalition structure generation*) :
  partition optimale d'un ensemble de joueurs. Les familles de méthodes sont la
  programmation dynamique, les algorithmes améliorés de type IDP et les formulations
  en programmation en nombres entiers. Le module historique
  `CoalitionStructureSearch.py` et les supports de cours du TP en sont la référence
  locale.
- **Valeur de Shapley :** l'allocation caractérisée par les axiomes d'efficacité, de
  symétrie, de joueur nul et d'additivité.
- **Négociation par offres alternées** entre agents à informations privées.
- **Extraction structurée par LLM** sous schéma JSON, et **RAG** (génération augmentée
  par récupération) avec un index vectoriel.

## 5. Architecture

Voir `docs/FINAL_ARCHITECTURE.md` :

- diagramme de composants et diagramme de séquence ;
- frontières des 17 étapes ;
- contrats ;
- architecture réelle et architecture cible.

**Principe directeur :** les modules de décision (prix, offres, admissibilité,
coalitions, paiements) n'importent ni le LLM ni le RAG. Un test AST le vérifie.

## 6. Méthodologie

- **Développement par phases**, de P0 à P5 puis de I0 à I4. Chaque phase a eu :
  - un périmètre revu ;
  - une base figée par manifeste ;
  - un diff, des tests et des mutants ;
  - un rapport.
- **Non-régression prouvée par des empreintes.** Le golden master des démonstrations
  historiques et les empreintes P4 (`997109ee…`, `3024fef1…`) en font partie.
- **Distinction systématique** entre ce qui est exécuté, rapporté et supposé
  (`docs/FINAL_PROJECT_AUDIT.md`).

## 7. Modèle multi-agents

| Agent | Rôle | Information privée |
|---|---|---|
| Acheteur (`BuyerAgent`) | une unité de voyageurs, avec budget et échéance | budget |
| Vendeur (`SellerAgent`) | une offre du catalogue | plancher par place |
| Mandataire de groupe (`mandate_leader`) | négocie pour une coalition | budgets des membres |
| Broker historique | formation de groupes du TP d'origine | — |

- **Protocole :** offres alternées (`Negotiation.py`), avec une issue typée
  (`terminal_reason`).
- **Encapsulation :** chaque négociation passe par un oracle simulé qui calcule une clé
  économique, met la réponse en cache et journalise l'échange. Les journaux vérifient
  les invariants J1 à J5.
- **Limite :** l'exécution est locale et synchrone.

## 8. Algorithmes de coalitions

Voir `docs/FINAL_ARCHITECTURE.md`, §5.1 :

- valeur `v(S) = Σ ref_i − c(S)` ;
- maximisation sur les partitions de chaque composante ;
- départage déterministe ;
- `component_too_large` au-delà de la limite, sans approximation.

## 9. Allocation des gains

Voir `docs/FINAL_ARCHITECTURE.md`, §5.2, et `docs/PHASE_P5_ADDENDUM_ID6.md`.

La projection n'a jamais été active sur les données de catalogue : le jeu `v*` y est
superadditif, donc φ ≥ 0. Elle est démontrée sur des cas construits.

## 10. LLM

- **Adaptateur :** Ollama local, schéma JSON imposé.
- **Prompts :** versionnés ; le v1 est conservé dans l'historique Git (`dbf5bd4`).
- **Évaluation :**
  - 3 modèles locaux, sur 4 jeux synthétiques ;
  - prompts v1 et v2 ;
  - avant et après la correction du transport du schéma.

Résultats : `docs/FINAL_LLM_EVALUATION.md`.

## 11. RAG

- **Fonctionnement :** documentaire, en SQLite, avec embeddings Ollama. Un index par
  modèle et par configuration.
- **Évaluation du retrieval :** Precision@K, Recall@K, MRR et nDCG, sur 3 modèles
  d'embedding et plusieurs découpages.
- **Résistance aux documents hostiles :** mesurée avec 3 attaques.

Résultats : `docs/FINAL_RAG_EVALUATION.md`.

## 12. Protocole expérimental

| Expérience | Protocole |
|---|---|
| Extraction | température 0, graine 0 ; deux passes identiques pour la reproductibilité ; latence médiane et moyenne ; jeux figés avant mesure, jamais utilisés pour ajuster le prompt |
| Retrieval | index neuf par configuration ; Top-K 1, 3 et 5 ; seuils balayés ; jugements gradués |
| Injection | pire cas : le document hostile est toujours récupéré ; comparaison avec l'extraction sans contexte |
| P4 | strates de performance (5 répétitions après une chauffe) et exploratoire (1 740 instances) ; empreintes |
| P5 | M0 à M2 dans une seule session (`docs/PHASE_I2_ALLOCATION_REPORT.md`) |
| Scénarios économiques | 18 scénarios versionnés ; résultats figés ; invariants de paiement vérifiés |

## 13. Résultats

Voir `docs/FINAL_DELIVERY_REPORT.md`, §8 à §10. Les tableaux complets sont dans les
rapports LLM, RAG et performance.

## 14. Limites

Voir `docs/FINAL_DELIVERY_REPORT.md`, §14.

## 15. Perspectives

1. **Distribution réelle des agents** par messages asynchrones. La clé de requête
   économique fournit l'idempotence.
2. **Adaptateur de disponibilité fournisseur,** hors du LLM.
3. **Jeux d'évaluation annotés plus grands et plus réalistes,** avec un jeu de test
   tenu à l'écart.
4. **Extraction plus robuste :** validation croisée de deux extractions, ou modèle plus
   grand si le matériel le permet.
5. **API typée et interface,** sans logique métier.

## 16. Conclusion

CoalitionTravel montre qu'un LLM peut servir d'**interface** à un système de décision
**exact et auditable** sans en compromettre les garanties :

- le modèle extrait ;
- le code valide, négocie, optimise et répartit ;
- chaque résultat est reproductible et vérifié.

Les mesures réelles montrent aussi la limite principale : la qualité de l'extraction par
de petits modèles locaux. Elle est compensée par la validation déterministe et par la
confirmation de la personne avant toute simulation.
