# Phase P0-bis — Golden Master sur le working tree

## 1. Objectif et correction

Le test P0 exécutait une archive du commit historique au lieu du code actuellement présent dans le working tree. P0-bis corrige uniquement la cible d’exécution : le Golden Master historique reste le même, mais `Entry.py` est maintenant exécuté depuis `Multi-Agent/` du dépôt réel. Le SHA documentaire du commit d’origine reste dans le test; le test ne consulte plus Git et n’exécute plus ce commit.

## 2. Inventaire initial

Avant modification, `git status --porcelain -uall` présentait les mêmes 13 fichiers suivis modifiés et 43 chemins non suivis qu’à la clôture de P0 (40 non suivis préexistants et les trois fichiers ajoutés par P0). Aucun changement inattendu n’a été trouvé dans le test P0, la référence ou les dépendances nécessaires.

`git diff --stat` était toujours de 13 fichiers, 960 insertions et 416 suppressions. Les fichiers suivis modifiés étaient les 13 déjà recensés dans le [rapport P0](PHASE_P0_BASELINE_AND_GOLDEN_MASTER.md). `Entry.py` et `SellerAgent.py` ne sont pas modifiés. Le rapport et les autres fichiers P0 étaient présents et inchangés.

Avant intervention, le test utilisait `_export_baseline`, `git archive`, `io` et `tarfile`. La référence existait en UTF-8, faisait 21 173 octets et son SHA-256 était le SHA attendu.

## 3. Modifications limitées

Deux chemins seulement ont été touchés :

1. **Modifié** `tests/test_entry_golden_master.py` : la cible est le working tree; un méta-test de mutation est ajouté. Le test historique de caractérisation et les assertions métier sont conservés.
2. **Créé** `docs/PHASE_P0_BIS_GOLDEN_MASTER_TARGET.md` : ce rapport.

Aucun fichier suivi historique, aucune autre donnée ou documentation, et aucun des 40 fichiers non suivis préexistants n’a été modifié, supprimé ou déplacé.

## 4. Nouvelle cible d’exécution

Le helper commun lance un sous-processus avec `cwd=REPOSITORY_ROOT / "Multi-Agent"`, `PYTHONPATH` pointant vers ce même répertoire et `runpy.run_path` sur le chemin absolu de `Multi-Agent/Entry.py`. Il passe la date `2026-11-19` au point d’entrée existant. Le processus capture stdout/stderr en octets et dispose d’un timeout de 90 secondes.

Il fixe `PYTHONHASHSEED=0`, `LC_ALL=C`, `LANG=C`, `TZ=UTC` et `PYTHONDONTWRITEBYTECODE=1`. La comparaison avec la référence reste octet par octet, sans normalisation.

`BASELINE_COMMIT` est conservé uniquement comme provenance documentaire. Aucun test n’appelle `git`, et le méta-test n’accède pas à `.git`.

## 5. Référence et Golden Master

- Référence : `tests/golden/entry_run_scenarios_2026-11-19.txt`.
- SHA-256 avant : `a5977fde152d329b53c2651ff89534a5fdd605b38b1419efacc6e1d533bd08b7`.
- SHA-256 après : `a5977fde152d329b53c2651ff89534a5fdd605b38b1419efacc6e1d533bd08b7`.
- Taille : 21 173 octets.

Le test recalcule et compare le hash attendu avant de lancer `Entry.py`. La fixture n’a pas été régénérée ni modifiée.

## 6. Méta-test de mutation

Le méta-test copie `Multi-Agent/` sous `tmp_path`, en excluant `__pycache__`, `.pyc` et `*.egg-info`. Le témoin exécute cette copie inchangée avec le même environnement et confirme que sa sortie égale la référence.

Dans la copie temporaire seulement, le test vérifie que `self.current_offer * 0.90` apparaît exactement une fois, le remplace par `self.current_offer * 0.91`, puis vérifie que la mutation est présente. La sortie mutée reste un processus réussi, mais ses octets diffèrent de la référence. Le code source `Multi-Agent/SellerAgent.py` du dépôt est ensuite confirmé inchangé.

Diagnostic observé :

```text
witness_matches_reference=True
mutation_target_occurrences=1
mutated_output_differs=True
changed_output_lines=41
reference_sha256=a5977fde152d329b53c2651ff89534a5fdd605b38b1419efacc6e1d533bd08b7
```

Les 41 lignes différentes confirment que la mutation choisie est visible par le Golden Master. Aucun code de régénération de référence n’a été ajouté.

## 7. Test de caractérisation conservé

`test_historical_characterization_known_per_ticket_vs_group_total_quantity_defect` garde son intention P0 : profil historique de quatre voyageurs, 500 € de budget par personne, acceptation de 560 € au total et conclusion en deux tours. Ce test documente une limite du système historique; ce n’est pas le comportement souhaité pour le nouveau système.

## 8. Commandes et sorties

Test ciblé :

```text
.venv/bin/python -m pytest -q tests/test_entry_golden_master.py
...                                                                      [100%]
3 passed in 1.61s
```

Suite complète, graine 0 :

```text
PYTHONHASHSEED=0 .venv/bin/python -m pytest -q
...........................................                             [ 53%]
..............................................................           [100%]
134 passed in 2.90s
```

Suite complète, graine 2 :

```text
PYTHONHASHSEED=2 .venv/bin/python -m pytest -q
...........................................                             [ 53%]
..............................................................           [100%]
134 passed in 2.83s
```

Ruff sur le fichier de code touché :

```text
.venv/bin/ruff check tests/test_entry_golden_master.py
All checks passed!

.venv/bin/ruff format --check tests/test_entry_golden_master.py
1 file already formatted
```

`git diff --check` n’a signalé aucune erreur. Aucun échec n’a été masqué.

## 9. État Git final

Le statut final contient toujours les 13 fichiers suivis modifiés antérieurement. `git diff --stat` reste à 13 fichiers, 960 insertions, 416 suppressions, et `git diff --name-only` reste identique à l’inventaire initial. Les 40 fichiers non suivis préexistants et les trois fichiers P0 sont toujours présents. Le nouveau rapport est le seul nouveau chemin non suivi de P0-bis.

Aucun fichier suivi n’a été modifié. Aucun fichier préexistant n’a été supprimé ou déplacé. Le hash de la référence est inchangé.

## 10. Gouvernance et limites

Aucune opération Git d’écriture n’a eu lieu : pas de `git add`, commit, push, branche, stash, reset ou clean. `.gitignore` n’a pas été modifié. Aucun fichier historique n’a été modifié. Le méta-test ne dépend ni de Git ni du dépôt pendant son exécution; il utilise exclusivement sa copie sous `tmp_path`.

La sortie exacte dépend toujours de l’interpréteur et des dépendances installées. L’environnement vérifié ici est Python 3.14.2, NumPy 2.4.1, SciPy 1.17.1 et Pydantic 2.14.3. La référence historique reste figée et toute évolution volontaire de sortie devra être examinée séparément.

**P0-bis accepté.** Les critères demandés sont satisfaits. Aucune phase suivante n’a été engagée.
