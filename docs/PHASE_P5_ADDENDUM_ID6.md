# Addendum P5 : confirmation d'ID-6 (θ_u = 0)

**Statut :** décision validée par la validation finale du périmètre d'I2 (2026-11-19). La conséquence « une unité peut payer zéro » est acceptée explicitement.

**Ce que fait cet addendum :** il complète `docs/PHASE_P4_SPECIFICATION.md` sans la
modifier.

- Le §9.5 de la spécification marque la décision D6 « [Décision, à valider en P5] ».
- La liste des décisions du même document l'énonce ainsi : « D6. Paiement minimal
  θ_u = 0 et projection euclidienne en P5 (§9.5) ».
- Cet addendum confirme cette décision pour l'allocation `p5-allocation-v1`.

**Pourquoi un fichier séparé :** la spécification P4 fait partie des fichiers dont
l'identité prouve qu'I2 ne modifie pas P2 à P4 (critère A9 de
`docs/PHASE_I2_SCOPE_REVIEW.md`).

---

## 1. Décision

**Pour toute unité u d'un bloc C, le paiement minimal est θ_u = 0.**

Les bornes de la projection (spécification §9.5) deviennent :

- `l_u = 0` : l'économie ne peut pas être négative, donc personne ne paie plus que sa
  référence ;
- `h_u = ref_u − θ_u = ref_u` : l'économie ne peut pas dépasser la référence, donc
  personne n'est payé pour voyager.

Ces deux bornes reviennent à :

```
0 ≤ y_u ≤ ref_u      ⇔      0 ≤ x_u ≤ ref_u      avec x_u = ref_u − y_u
```

---

## 2. Conséquences démontrées

1. **La projection est toujours faisable.**
   - **Condition.** Elle est faisable si et seulement si `Σ l ≤ V ≤ Σ h`, c'est-à-dire
     `0 ≤ v(C) ≤ Σ ref_u`, c'est-à-dire `c(C) ≥ 0`.
   - **Elle est toujours remplie.** Le contrat P2 impose un accord strictement positif
     (`0 < agreed`, contrôlé par `validate_negotiation_outcome`). Donc `c(C) > 0`, et
     `V < Σ ref_u` strictement.
   - **Conséquence.** Les unités ne peuvent pas être toutes saturées à leur borne haute
     en même temps.
2. **Aucun paramètre arbitraire.** Toute valeur `θ_u > 0` introduirait un paramètre
   extérieur au jeu. Elle pourrait même rendre la projection infaisable dès que
   `Σ θ_u > c(C)`.
3. **Un paiement nul est possible, et c'est voulu.**
   - **Exemple** (E2 de `docs/PHASE_I2_SCOPE_REVIEW.md`) :
     - φ = (300, 300, 300) et références (100, 1 000, 1 000) ;
     - la projection donne y = (100, 400, 400) ;
     - les paiements valent x = (0, 600, 600).
   - **Lecture.** La première unité est saturée. Sa référence entière est couverte par
     l'économie collective, et elle paie 0.
   - **Garantie.** Cela n'autorise pas de paiement négatif : `x_u ≥ 0` est garanti par
     `h_u = ref_u`.
4. **Répartition entre les voyageurs.** Si `x'_u = 0`, chaque siège de l'unité paie 0
   (plan §6.1 : `0 ≤ q_s ≤ b_s`, avec `Σ q_s = 0`).
5. **Les budgets sont respectés.** `x'_u ≤ ref_u ≤ B_u`. La première inégalité découle
   de `y'_u ≥ 0`, la seconde du contrat P2. Aucun écrêtage heuristique n'est
   nécessaire (spécification §9.6).

---

## 3. Traçabilité et affichage

- **Traçabilité.** `AllocationResult` enregistre `"theta_cents": 0` dans le contenu
  canonique de `allocation_sha256`. Changer θ changerait donc l'empreinte et la
  version (`p5-allocation-v1`).
- **Affichage (I3).** Un paiement nul s'affiche comme une part **entièrement couverte
  par l'économie collective**, dans le cadre de la proposition simulée. Il ne doit
  jamais être présenté comme une gratuité commerciale. Le vocabulaire est celui du §1.2
  du plan.

---

## 4. Ce que cet addendum ne change pas

- Les autres règles de la spécification §9 restent valables :
  - Shapley sur `v*|C` ;
  - convention λ* (point de Λ le plus proche de 0) ;
  - arrondi au plus fort reste, départagé par `unit_id` ;
  - stabilité mesurée et non garantie.
- Aucun code, aucun test et aucun fichier de P2 à P4 n'est modifié par cet addendum.
