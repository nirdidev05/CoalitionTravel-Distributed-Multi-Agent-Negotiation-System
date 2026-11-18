# TP1 — Coordination Multi-Agent
M1 Info — Lyon 1

```bash
cd Multi-Agent && python3 Entry.py
# dépendances : pip install numpy scipy
```

---



6 scénarios lancés en séquence dans `Entry.py`.

---

## Fichiers

```
Agent.py                    → classe de base abstraite
Message.py                  → enveloppe FIPA-ACL (sender, receiver, type, content)
BuyerAgent.py               → acheteur (Rubinstein, deadline, blacklist)
SellerAgent.py              → vendeur (concession monotone)
BrokerAgent.py              → broker (Ketchpel, CNP)
Leader.py                   → CoalitionLeaderAgent (créé dynamiquement)
CoalitionStructureSearch.py → DP / IDP / IP + Shapley  ← partie 2
Entry.py                    → point d'entrée, 6 scénarios
```

---

## Partie 1 — Corrections et ajouts

### Correction — `message.performative` → `message.type`

`BrokerAgent.py` accédait à un attribut qui n'existe pas dans `Message` :

```python
# avant — plantait à l'exécution (AttributeError)
if message.performative == "SUBSCRIBE":

# après — attribut réel défini dans Message.__init__
if message.type == "SUBSCRIBE":
```

Sans ce fix, aucune coalition ne se formait (scénarios 2, 6 complètement cassés).

---

### Ajout — blacklist / preferred dans `BuyerAgent`

L'énoncé demande que l'acheteur puisse refuser certaines compagnies peu importe le prix.

```python
# BuyerAgent.receive_message — évalué avant tout calcul de prix
if seller_name in self.blacklist:
    return Message(self, message.sender, "REJECT", {"reason": f"{seller_name} blacklisted"})
```

Scénario 3 : Eve (budget 700€), AirFrance propose 350€ → REJECT quand même car blacklistée.

---

### Ajout — concession dynamique selon la deadline

Inspiré du facteur d'escompte de Rubinstein (C2 p.10) : plus la deadline est proche, plus l'agent concède vite. Ce taux sert de **plafond** de concession.

```python
urgency  = max(0.0, 1.0 - days_remaining / 30.0)
max_rate = 0.02 + urgency * 0.08   # plafond entre 2% et 10%
```

Scénario 4 : Frank (deadline dans 5j) a un plafond ~9%/tour, Grace (deadline dans 219j) ~2%/tour.

### Ajout — stratégie de Zeuthen (C2 p.13-17)

C'est le **risque de conflit** qui décide *de combien* on concède : l'agent dont le risque est le plus faible concède davantage.

```python
# Formule du cours (C2 p.16), avec u(conflit) = 0 :  risk = (u(d_i) - u(d_j)) / u(d_i)
# Variante du code (robuste, bornée [0,1]) : on pénalise le conflit par u(conflit) = -budget
# Utilité acheteur : u(p) = budget - p.
risk = (u(mon_offre) - u(leur_offre)) / (u(mon_offre) - u(conflit))   # ∈ [0, 1]
rate = max_rate * (1 - risk)   # risque faible → grosse concession ; toujours ≤ 10%
```

> À l'écrit on utilise la formule du cours (`u(conflit)=0` → dénominateur `u(d_i)`). Le code prend `u(conflit) = -budget` pour garder un risque gradué dans `[0,1]` sur ce scénario (sinon, comme l'acheteur ne contre-propose qu'au-dessus de son budget, le risque resterait collé à 1 et il ne concéderait jamais).

- `risk → 0` : l'agent craint le conflit → il concède (proche du plafond).
- `risk → 1` : l'agent a peu à perdre → il tient bon (concession nulle).

Scénario 1 : Alice calcule un risque de Zeuthen de 0.37 puis 0.29 et concède progressivement jusqu'à l'accord à 453.60€.

---

## Partie 2 — DP / IDP / IP + Shapley (`CoalitionStructureSearch.py`)

**Problème :** trouver SC* = la partition des agents qui maximise Σ v(c).
Brute force impossible (B(15) > 1 milliard de partitions).

### DP — Dynamic Programming (C3b slides 3-8)

Équation de Bellman bottom-up :
```
f(C) = max( v(C),  max_{T⊊C} [ f(T) + f(C\T) ] )
```
On mémoïse chaque sous-problème, pivot fixe pour éviter les doublons.
Complexité : O(3^n) temps, O(2^n) espace.

### IDP — Improved DP + UB-Pruning (C3b slides 11-15, Rahwan & Jennings AAMAS 2007)

Même chose que DP mais avant de tester une division (k1, k2) :
```
UB[k] = meilleur f(C) observé parmi toutes les coalitions de taille k

Si UB[k1] + UB[k2] ≤ f(C) courant → on élague toute la paire sans calculer
```
Sur 5 agents : **37 paires élaguées** → moins de calculs à chaque niveau.

### IP — ILP (C3b slides 16-21, Sandholm et al. AAAI 1998)

On formule le problème comme un ILP et on laisse le solveur HiGHS faire le travail :
```
max  Σ v(C)·x_C     s.c.   Σ_{C∋aᵢ} x_C = 1  ∀aᵢ,   x_C ∈ {0,1}
```
Pour n=5 : 31 variables, 5 contraintes. Implémenté avec `scipy.optimize.milp`.

### Résultats Scénario 5 (5 agents, jeu non super-additif)

```
v({Bob,Carol,Eve}) + v({Alice,Dave}) = 201.60 + 49.00 = 250.60
v({tous les 5})                                        = 159.60  ← sous-optimal

DP  → SC* = { {Alice,Dave} | {Bob,Carol,Eve} }   V = 250.60
IDP → SC* = { {Alice,Dave} | {Bob,Carol,Eve} }   V = 250.60   (37 paires élaguées)
IP  → SC* = { {Alice,Dave} | {Bob,Carol,Eve} }   V = 250.60
```

### Partie (c) — Shapley + transferts de tokens

Après accord sur un prix total P, on répartit équitablement selon la contribution réelle de chaque agent :

```
φᵢ(v) = contribution marginale moyenne de aᵢ sur toutes les permutations d'entrée
moyenne = v(c) / n

Token_i = φᵢ(v) − v(c)/n
  > 0 → atout   (contribue plus que la moyenne) → reçoit un token → paie MOINS
  = 0 → agent moyen / dummy                     → paie la part égale
  < 0 → fardeau  (contribue moins)              → envoie un token → paie PLUS

Part payée_i = P/n − Token_i        (Σ Token = 0 → Σ parts = P : efficacité préservée)
```

Activé dans le Scénario 6 via `v_func` passé au `CoalitionLeaderAgent` (optionnel — pas de Shapley dans les scénarios 2/3).

---

## Scénario 6 — Ketchpel vs IDP

| Stratégie | Ketchpel | IDP | Écart |
|---|---|---|---|
| Arrivée simultanée | 248.50 | **250.60** | +0.8% |
| Arrivée décalée | 198.00 | **250.60** | **+26.6%** |
| Jeu super-additif | — | **798.00** (grand coalition) | — |

Conclusion principale : Ketchpel est glouton et dépend de l'ordre d'arrivée. IDP garantit l'optimal quelle que soit l'arrivée, et converge automatiquement vers la grand coalition quand le jeu est super-additif.
