# Démonstration officielle (5 à 10 minutes)

```bash
source .venv/bin/activate              # or: PLAN=.venv/bin/coalition-travel-plan
bash demo/run_demo.sh                  # text output
bash demo/run_demo.sh --json           # canonical JSON output
OLLAMA_MODEL=qwen2.5:7b bash demo/run_demo.sh   # step 1 with the live local model
```

Toutes les sorties sont produites par le programme au moment de l'exécution. Avec la
date de référence fixe (2027-01-15) et les données figées, elles sont identiques d'une
exécution à l'autre. Seule l'étape 1 dépend du modèle quand elle est jouée en direct.

| Étape | Ce qu'elle montre | Résultat obtenu le 2026-11-20 |
|---|---|---|
| 1 | Langage naturel → extraction réelle de `qwen2.5:7b` (rejeu de sa sortie enregistrée, ou appel direct) | le modèle place les 2 voyageurs dans un profil inventé ; la validation demande le nombre de voyageurs ; code 2. Limite mesurée, `docs/FINAL_LLM_EVALUATION.md` |
| 1 bis | La même demande, structurée : alias « Algiers » → Alger, résumé, validation, négociations, coalition, allocation | `served_in_coalition`, Brisolis, économie de 46,17 € ; code 0 |
| 2 | Clarification : « Tokyo, 500 euros » puis la réponse « 2 voyageurs » (deux extractions réelles enregistrées) | demande traitée seule ; code 0 |
| 3 | Demande v1, coalition avantageuse (Tokyo, 8 voyageurs) | `served_in_coalition` ; code 0 |
| 4 | Pas de coalition avantageuse (Tokyo, 2 voyageurs) | demande traitée seule ; code 0 |
| 5 | Contrainte bloquante : budget de 100 €, aucun accord individuel | `no_solo_reference` ; code 0 |
| 6 | Contrainte bloquante : destination absente du catalogue (Oslo) | `no_admissible_offer` ; code 0 |
| 7 | Lieu inconnu (Oran) | clarification avec la liste des lieux connus ; code 2 |

**Fichiers.**

- **Demandes structurées :** `*.json`.
- **Rejeux :** `replay_*.json`. Ce sont des sorties réelles de `qwen2.5:7b`
  (température 0, graine 0, prompt `travel-request-extraction-v2`, transport
  `all-keys-required-v1`), enregistrées le 2026-11-20. Elles n'ont pas été écrites à la
  main.

Rien n'est réservé, payé ni émis : catalogue et vendeurs fictifs.
