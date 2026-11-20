# Revue de sécurité et de robustesse

**Date :** 2026-11-20.
**Périmètre :** l'arbre de travail issu de `5d547ec`, plus les modifications de la
mission finale.

Ce document recense les frontières de confiance, ce qui a été vérifié, les failles
trouvées et leur traitement.

---

## 1. Frontières de confiance

| Frontière | Donnée non fiable | Contrôle en place |
|---|---|---|
| Texte de la personne | instructions cachées, longueur, mots interdits | 12 000 caractères au plus (adaptateur Ollama) ; règle lexicale sur les chaînes saisies (D-I3-17) ; le texte est placé dans un bloc `<request>` délimité |
| Sortie du LLM | JSON hors schéma, faits inventés | schéma JSON imposé à Ollama ; `TravelRequestDraft` refuse les champs inattendus ; validation déterministe ensuite ; erreurs techniques distinctes (`StructuredOutputError`, `LLMProviderError`) |
| Contexte RAG | document hostile | bloc `<knowledge_context>` délimité et déclaré non fiable dans le prompt système ; aucun module de décision n'importe la couche RAG ; RAG absent de la commande |
| Fichiers `--draft-json`, `--extractor-replay` | taille, contenu | lecture bornée à 1 000 000 d'octets (ajout de cette mission) ; JSON strict ; aucun chemin dans les messages d'erreur |
| Catalogues et carnets | altération | SHA-256 comparé au manifeste ; JSON strict (pas de flottants, de NaN ni de clés dupliquées) ; C1 à C6 |
| Sortie CLI | fuite de données privées | contrats fermés ; T-CONF-1 à T-CONF-3 ; aucune empreinte privée ni aucun chemin |
| SQLite (RAG) | concurrence, réindexation | écritures dans `BEGIN IMMEDIATE` ; remplacement transactionnel d'un document ; identité de l'espace vectoriel vérifiée |
| Configuration | `OLLAMA_MODEL`, `OLLAMA_BASE_URL` | URL HTTP(S) absolue exigée ; aucun secret n'est requis ni lu dans un fichier versionné |

## 2. Contrôles exécutés

| Contrôle | Résultat |
|---|---|
| Recherche de secrets dans les fichiers suivis : motifs de clés, de jetons et de clés privées | aucun [E] |
| Chemins personnels dans les fichiers suivis | aucun [E] |
| Appels dangereux (`pickle`, `eval(`, `exec(`, `yaml.load`, `shell=True`, `os.system`) dans `Multi-Agent/` | aucun [E] |
| `pip-audit` sur l'environnement local (18 paquets) | 2 vulnérabilités connues, dans `PyPDF2 3.0.1` (PYSEC-2026-1835) et `wheel 0.45.1` (CVE-2026-24049). **Aucune ne concerne une dépendance déclarée du projet** : NumPy, SciPy, Pydantic, pytest et Ruff sont sans alerte. Ces deux paquets, comme `openvino` et `TBB`, ont été installés dans le `.venv` hors du projet ; il est recommandé de les retirer de l'environnement de développement [E] |
| Tests de confidentialité T-CONF (v1, v2) | dans la suite, verts [E] |
| Document RAG hostile et requête hostile | `tests/test_final_hostile_context.py` : voir le §3 |
| Fichiers d'entrée énormes ou sans fin (`/dev/zero`) | `tests/test_final_input_limits.py` : voir le §3 |

## 3. Failles trouvées et traitement

### S1 : sortie anticipée du bloc délimité, par injection

- **Constat.** Le contexte récupéré et le texte de la personne étaient insérés tels
  quels entre `<knowledge_context>…</knowledge_context>` et `<request>…</request>`.
  Un document contenant `</knowledge_context>`, ou une demande contenant `</request>`,
  pouvait fermer son bloc et placer du texte hors de la zone déclarée non fiable.
- **Gravité.** Moyenne. Le LLM ne décide de rien d'économique : un brouillon falsifié
  est encore validé, résumé et soumis à la personne avant toute simulation. L'effet
  serait donc une extraction fausse, pas une décision fausse.
- **Correction.** Les balises de délimitation présentes dans les données sont
  neutralisées avant insertion (`infrastructure/llm/ollama.py`). Le gabarit du prompt
  est inchangé pour toute entrée qui ne contient pas ces balises.
- **Test.** `test_a_hostile_document_stays_inside_its_delimited_block` et
  `test_a_hostile_request_cannot_open_a_fake_context_block`.

### S2 : lecture non bornée des fichiers d'entrée

- **Constat.** `--draft-json` et `--extractor-replay` lisaient le fichier entier en
  mémoire. `--draft-json /dev/zero` ne se terminait pas.
- **Gravité.** Faible : l'outil est local, et la personne choisit le fichier.
- **Correction.** La lecture est bornée à 1 000 000 d'octets. Au-delà, c'est une erreur
  d'usage (code 64), dont le message ne cite pas le chemin.
- **Test.** `tests/test_final_input_limits.py`, 5 tests.

### S3 : chemin absolu dans une sortie de l'évaluateur (non corrigé, documenté)

- **Constat.** `coalition-travel-eval --task profiles --validate-only` affiche le chemin
  absolu du jeu de données.
- **Gravité.** Très faible : c'est un outil local de développeur, et la sortie n'est pas
  versionnée.
- **Traitement.** Les résultats versionnés de cette mission utilisent des chemins
  relatifs.

### S4 : délai d'attente trop court pour un modèle 7B (corrigé)

- **Constat.** La commande créait l'extracteur avec le délai par défaut de 60 s. Un
  modèle 7B met environ 30 s par appel sur la machine de référence, et dépasse 60 s
  quand Ollama est chargé. L'essai réel a échoué en `LLMProviderError`, une erreur
  technique correctement séparée, code 1.
- **Correction.** Le délai par défaut vaut 180 s, réglable par
  `OLLAMA_TIMEOUT_SECONDS` (de 0 exclu à 3 600 s). Une valeur invalide est une erreur
  d'usage, code 64.
- **Test.** `tests/test_final_input_limits.py`.

## 4. Risques résiduels

1. **Injection sémantique.** Neutraliser les balises n'empêche pas un modèle d'obéir à
   une instruction placée *dans* le bloc. La protection repose sur deux éléments :
   - la consigne système ;
   - surtout, le fait que la sortie du LLM n'est qu'un brouillon, validé de façon
     déterministe puis soumis à la personne.

   **La mesure réelle confirme ce risque** (`docs/FINAL_RAG_EVALUATION.md`, §4) :
   - une instruction directe réussit sur 7 demandes sur 8 avec `llama3.2:3b`, et sur
     6 sur 8 avec `qwen2.5:3b` ;
   - le texte qui suit une balise neutralisée réussit encore sur 3 demandes sur 8 avec
     `qwen2.5:7b`.

   C'est pourquoi le RAG n'est pas branché sur la commande.
2. **Inférence des planchers.** Le risque résiduel B7 d'I3 demeure : un montant public
   peut coïncider avec un plancher, sans divulgation directe.
3. **SQLite.** La base RAG est mono-utilisateur et locale. Les écritures concurrentes
   sont sérialisées par `BEGIN IMMEDIATE`, avec le délai d'attente par défaut de
   `sqlite3`, soit 5 s. Aucune opération longue n'est faite sous verrou.
4. **Dépendance binaire.** L'exactitude du MILP dépend de la roue SciPy de la
   plateforme : voir `docs/FINAL_PROJECT_AUDIT.md`, §5. Une sélection invalide est
   détectée (`PartitionInvalid`), jamais acceptée en silence.
