# Phase P0-ter — robustesse du Golden Master

## Objet

La revue de P0-bis a relevé un défaut de robustesse démontré et deux remarques mineures. P0-ter les traite sans toucher à la référence historique. Seul `tests/test_entry_golden_master.py` est modifié (fichier non suivi créé par P0); le rapport P0-bis est conservé tel quel et ce document le complète.

## 1. Défaut corrigé : héritage de l'environnement Python

Constat : le sous-processus partait de `os.environ.copy()`. Avec `PYTHONIOENCODING=latin-1` défini chez le développeur, 2 tests sur 3 échouaient alors que le code n'avait pas changé (la sortie contient `É` et `€`).

Correction : `_subprocess_environment()` retire toutes les variables héritées commençant par `PYTHON`, puis fixe `PYTHONHASHSEED=0`, `PYTHONPATH`, `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`, `PYTHONDONTWRITEBYTECODE=1`, `LC_ALL=C`, `LANG=C`, `TZ=UTC`.

Nouveau test : `test_golden_master_ignores_inherited_python_environment` définit `PYTHONIOENCODING=latin-1`, `PYTHONUTF8=0`, `PYTHONWARNINGS=error`, `PYTHONOPTIMIZE=2` et `PYTHONHASHSEED=123` via `monkeypatch`, puis exige une sortie identique octet pour octet à la référence.

## 2. Remarque 1 corrigée : précision sur l'isolement de la copie

Le rapport P0-bis affirmait que le méta-test « n'accède pas au dépôt ». C'est approximatif : l'installation éditable (`__editable__.coalition_travel-0.2.0.pth`) ajoute `Multi-Agent/` du dépôt à `sys.path`, après `PYTHONPATH`. Un module absent de la copie serait donc chargé depuis le dépôt sans erreur.

Correction : `_module_origins()` lance un sous-processus de contrôle qui importe `Entry`, `SellerAgent`, `Leader` et `coalition_travel` et renvoie leur fichier source. Le méta-test exige que tous résolvent sous la copie `tmp_path` avant d'exécuter le témoin et la mutation.

## 3. Remarque 2 traitée : cible du test principal

Le test principal exige désormais, avec le même contrôle, que ces modules résolvent sous `REPOSITORY_ROOT/Multi-Agent`. Le test prouve ainsi lui-même qu'il exécute le working tree, et pas une archive ou une copie.

## Résultats

```text
.venv/bin/python -m pytest -q tests/test_entry_golden_master.py
4 passed

PYTHONIOENCODING=latin-1 .venv/bin/python -m pytest -q tests/test_entry_golden_master.py
4 passed            (avant P0-ter : 2 failed, 1 passed)
```

Référence inchangée : SHA-256 `a5977fde152d329b53c2651ff89534a5fdd605b38b1419efacc6e1d533bd08b7`. Aucune opération Git d'écriture.
