# Phase P1.2 — union des exclusions et consolidation

## Fichiers

- Modifié : `Multi-Agent/coalition_travel/application/profiles.py` (seul fichier suivi modifié de toute la phase P1)
- Créé : `tests/test_exclusion_union.py` (17 tests)

## Changements

1. **Union.** Exclusions effectives d'un profil = exclusions de la demande ∪ exclusions du profil, sans doublon à la casse près, en gardant la première graphie (demande d'abord, puis profil). Une liste de profil `None` ou `[]` n'ajoute ni n'efface rien. Auparavant, la liste du profil remplaçait celle de la demande, et `[]` effaçait les exclusions de la demande.
2. **Clé de consolidation.** `negotiation_profile_key` sérialise les exclusions normalisées (`casefold`, dédoublonnées, triées). Deux profils qui ne diffèrent que par « SkyWays » / « skyways » sont consolidés; la graphie du premier profil rencontré est conservée.
3. **Fonctions publiques.** `negotiation_profile_key(profile)` et `consolidate_profiles(profiles)` sont exposées et utilisées par `build_profiles` lui-même (identifiant `merged-<clé[:16]>`, tri et contrôle de collision inchangés). `consolidate_profiles` est idempotente et refuse les objets qui ne sont pas des `TravelerProfile`.

## Défaut latent découvert et corrigé dans la même fonction

L'ancienne clé appelait `Decimal.normalize()`, qui arrondit à la précision du contexte global. Avec une précision de 5, 123 456,78 € et 123 456,79 € donnaient la même clé et les deux profils étaient fusionnés à tort. La clé utilise désormais `_canonical_decimal()`, qui normalise sous un contexte dont la précision couvre tous les chiffres du montant : la sérialisation est exacte quel que soit le contexte de l'appelant.

## Effets assumés

- Le chemin IA actuel (`travel_workflow` → `create_buyer_agents`) reçoit des listes de refus en union.
- Les identifiants de fusion ne changent que pour des profils dont une exclusion contient des majuscules. Le test `test_keys_are_unchanged_for_profiles_without_uppercase_exclusions` compare la nouvelle clé à l'ancienne formule pour les autres cas : elles sont identiques.
- `Entry.py`, les agents et l'évaluation ne sont pas touchés. Le golden master reste vert.

## Non modifié

`create_buyer_agents` utilise toujours `TravelerProfile.total_budget`, propriété existante sensible au contexte `Decimal` global. Ce chemin historique est hors périmètre; le nouveau flux (P1.3) calcule ses totaux en centimes entiers et ne s'appuiera jamais sur `BuyerAgent.budget`.
