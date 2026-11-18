# Partie C3b du TP -- recherche de la structure de coalitions optimale
# On implémente 3 algos vus en cours : DP, IDP et IP
# Référence : Rahwan & Jennings AAMAS 2007 + Sandholm AAAI 1998

import numpy as np
from itertools import combinations
from scipy.optimize import milp, LinearConstraint, Bounds


# petite fonction utilitaire pour convertir des indices en vrais noms d'agents
def _v_idx(agents, v_named, S_indices):
    return v_named(frozenset(agents[i] for i in S_indices))


# tous les sous-ensembles non vides de {0,...,n-1} classés par taille
def _all_subsets(n):
    for size in range(1, n + 1):
        for combo in combinations(range(n), size):
            yield frozenset(combo)


# -----------------------------------------------------------------------
# ALGO 1 : DP classique  (C3b slides 3-8)
# -----------------------------------------------------------------------
# L'idée c'est l'équation de Bellman :
#   f(C) = max( v(C),  max sur toutes les façons de couper C en deux )
# On calcule du plus petit au plus grand pour avoir les sous-problèmes déjà prêts.
# Astuce pour éviter les doublons : le plus petit agent de C est toujours dans C1.
def dp_search(agents, v):
    n     = len(agents)
    f     = {}   # mémoïsation : frozenset d'indices -> (valeur, structure)
    count = 0    # pour compter combien de coalitions on a évaluées

    for size in range(1, n + 1):
        for combo in combinations(range(n), size):
            C = frozenset(combo)
            count += 1

            # on commence par prendre C entière sans la couper
            opt_val    = _v_idx(agents, v, C)
            opt_struct = [C]

            if size >= 2:
                pivot  = min(C)          # le pivot est toujours dans C1
                others = sorted(C - {pivot})

                for k1 in range(1, size):
                    for sub in combinations(others, k1 - 1):
                        C1 = frozenset([pivot] + list(sub))
                        C2 = C - C1
                        v1, s1 = f[C1]
                        v2, s2 = f[C2]
                        if v1 + v2 > opt_val:
                            opt_val    = v1 + v2
                            opt_struct = s1 + s2

            f[C] = (opt_val, opt_struct)

    S_all       = frozenset(range(n))
    val, struct = f[S_all]
    named       = [frozenset(agents[i] for i in c) for c in struct]
    return val, named, count


# -----------------------------------------------------------------------
# ALGO 2 : IDP avec élagage UB  (C3b slides 11-15 / Rahwan 2007)
# -----------------------------------------------------------------------
# Même principe que DP mais on ajoute un élagage par bornes supérieures.
# Avant de générer toutes les combinaisons pour une paire de tailles (k1, k2)
# on vérifie si UB[k1] + UB[k2] peut encore améliorer f(C).
# Si non, on zappe toute la paire sans générer une seule combinaison.
# UB[k] = meilleure valeur vue jusqu'ici parmi toutes les coalitions de taille k.
def idp_search(agents, v):
    n            = len(agents)
    f            = {}
    UB           = {}   # UB[k] = max f(C) pour |C| = k
    count        = 0
    pruned_pairs = 0    # nb de paires complètement ignorées grâce à l'élagage

    for size in range(1, n + 1):
        UB[size] = 0.0

        for combo in combinations(range(n), size):
            C = frozenset(combo)
            count += 1

            opt_val    = _v_idx(agents, v, C)
            opt_struct = [C]

            if size >= 2:
                pivot  = min(C)
                others = sorted(C - {pivot})

                for k1 in range(1, size):
                    k2 = size - k1

                    # élagage : si même les meilleures coalitions de tailles k1 et k2
                    # ne peuvent pas faire mieux que ce qu'on a déjà, on passe
                    ub_k1 = UB.get(k1, 0.0)
                    ub_k2 = UB.get(k2, 0.0)
                    if ub_k1 + ub_k2 <= opt_val:
                        pruned_pairs += 1
                        continue

                    # sinon on génère vraiment les combinaisons
                    for sub in combinations(others, k1 - 1):
                        C1 = frozenset([pivot] + list(sub))
                        C2 = C - C1
                        v1, s1 = f[C1]
                        v2, s2 = f[C2]
                        if v1 + v2 > opt_val:
                            opt_val    = v1 + v2
                            opt_struct = s1 + s2

            f[C] = (opt_val, opt_struct)

            # on met à jour la borne sup pour cette taille
            if opt_val > UB[size]:
                UB[size] = opt_val

    S_all       = frozenset(range(n))
    val, struct = f[S_all]
    named       = [frozenset(agents[i] for i in c) for c in struct]
    return val, named, count, pruned_pairs


# -----------------------------------------------------------------------
# ALGO 3 : IP -- formulation ILP  (C3b slides 16-21)
# -----------------------------------------------------------------------
# On reformule le problème en programme linéaire en nombres entiers :
#   - une variable binaire x_C pour chaque coalition possible
#   - objectif : maximiser sum(v(C) * x_C)
#   - contrainte : chaque agent appartient à exactement une coalition
# Le solveur HiGHS (via scipy) gère la relaxation LP + branch-and-bound.
def ip_search(agents, v):
    n = len(agents)

    # toutes les coalitions non vides = 2^n - 1 variables
    all_coalitions = list(_all_subsets(n))
    m = len(all_coalitions)

    values = np.array([_v_idx(agents, v, C) for C in all_coalitions], dtype=float)

    # matrice de contraintes : A[i, j] = 1 si l'agent i est dans la coalition j
    A = np.zeros((n, m), dtype=float)
    for j, C in enumerate(all_coalitions):
        for i in C:
            A[i, j] = 1.0

    # milp minimise donc on passe l'objectif en négatif
    result = milp(
        c            = -values,
        constraints  = LinearConstraint(A, lb=np.ones(n), ub=np.ones(n)),
        integrality  = np.ones(m),
        bounds       = Bounds(lb=0.0, ub=1.0)
    )

    if result.status != 0:
        raise RuntimeError(f"ILP solver failed: {result.message}")

    selected   = [j for j in range(m) if result.x[j] > 0.5]
    opt_val    = -result.fun
    opt_struct = [frozenset(agents[i] for i in all_coalitions[j]) for j in selected]

    return opt_val, opt_struct, m


# -----------------------------------------------------------------------
# Fonctions d'affichage
# -----------------------------------------------------------------------

def format_structure(struct):
    parts = ["{" + ", ".join(str(a) for a in sorted(c)) + "}" for c in struct]
    return "{ " + "  |  ".join(parts) + " }"


def print_result(algo_name, val, struct, stat_label, stat_val, extra=None):
    print(f"\n  \u250c\u2500 {algo_name}")
    print(f"  \u2502  SC*           = {format_structure(struct)}")
    print(f"  \u2502  V(SC*)        = {val:.2f}")
    print(f"  \u2502  {stat_label:<14} = {stat_val}")
    if extra:
        print(f"  \u2502  {extra[0]:<14} = {extra[1]}")
    print(f"  \u2514{'\u2500'*58}")


# -----------------------------------------------------------------------
# Valeur de Shapley + transferts de tokens  (C3a p.36-45)
# -----------------------------------------------------------------------
# La valeur de Shapley mesure la contribution marginale moyenne de chaque agent.
# Formule : phi_i = somme pondérée de [v(S + i) - v(S)] sur tous les sous-ensembles S.
# Propriété clé : sum(phi_i) = v(c)  => toute la valeur est bien distribuée.
def shapley_value(agent, coalition, v):
    from math import factorial
    agents_in_c = sorted(coalition)
    n      = len(agents_in_c)
    others = [a for a in agents_in_c if a != agent]
    phi    = 0.0
    for size in range(len(others) + 1):
        for S in combinations(others, size):
            S_set  = frozenset(S)
            weight = factorial(size) * factorial(n - size - 1) / factorial(n)
            phi   += weight * (v(S_set | {agent}) - v(S_set))
    return phi


# Affiche le tableau des transferts : qui paie quoi selon Shapley vs part égale.
#
# token_i = phi_i - (v_c / n)   =   contribution de i  MOINS  la contribution moyenne
#   token_i > 0 : i contribue PLUS que la moyenne  -> ATOUT   -> il REÇOIT des tokens
#                 (sa contribution marginale v(S+i)-v(S) est élevée), donc il paie moins
#   token_i < 0 : i contribue MOINS que la moyenne -> FARDEAU -> il ENVOIE des tokens,
#                 donc il paie plus (cas extrême : agent muet phi=0, ou contribution négative)
#   token_i = 0 : i contribue exactement la moyenne (agents interchangeables, symétrie)
#
# La somme des tokens est toujours nulle (efficacité : Σ phi_i = v_c).
# Paiement final de i : part_égale - token_i  (un atout paie moins, un fardeau paie plus).
def print_shapley_transfers(coalition, v, total_price):
    agents_in_c = sorted(coalition)
    n   = len(agents_in_c)
    v_c = v(frozenset(agents_in_c))
    if v_c == 0:
        return
    equal_share = total_price / n
    avg_phi     = v_c / n   # contribution moyenne = part égale de la valeur créée
    shapley     = {a: shapley_value(a, frozenset(agents_in_c), v) for a in agents_in_c}

    print(f"\n  Valeur de Shapley & transferts de tokens (C3a, p.36-45) :")
    print(f"  {'Agent':<10} {'\u03c6\u1d62(v)':>8}  {'Part pay\u00e9e':>10}  {'Part \u00e9gale':>10}  Transfert token")
    print(f"  {'\u2500'*10} {'\u2500'*8}  {'\u2500'*10}  {'\u2500'*10}  {'\u2500'*22}")
    for a in agents_in_c:
        phi     = shapley[a]
        token   = phi - avg_phi          # > 0 : atout (reçoit) ; < 0 : fardeau (envoie)
        payment = equal_share - token    # un atout paie moins que la part égale
        if abs(token) < 0.005:
            direction = "0.00\u20ac  (= moyenne)"
        elif token > 0:
            direction = f"re\u00e7oit  +{token:.2f}\u20ac  (atout)"
        else:
            direction = f"envoie  {token:.2f}\u20ac  (fardeau)"
        print(f"  {a:<10} {phi:>8.2f}  {payment:>10.2f}\u20ac  {equal_share:>10.2f}\u20ac  {direction}")
    print(f"  {'\u2500'*10} {'\u2500'*8}  {'\u2500'*10}  {'\u2500'*10}  {'\u2500'*22}")
    print(f"  {'\u03a3':<10} {sum(shapley.values()):>8.2f}  {total_price:>10.2f}\u20ac  "
          f"(efficacit\u00e9 : \u03a3\u03c6\u1d62=v(c)={v_c:.2f}, \u03a3token=0)")
