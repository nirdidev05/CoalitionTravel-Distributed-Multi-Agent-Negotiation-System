# Les 6 scénarios de démonstration — explication, utilité et résultats

> Fichier produit à partir de [Multi-Agent/Entry.py](Multi-Agent/Entry.py).
> Pour tout relancer : `cd Multi-Agent && python3 Entry.py`

Ce document décrit **chaque scénario** orchestré par `Entry.py` : ce qu'il met en scène,
**à quoi il sert** (le concept du cours qu'il démontre) et **les résultats réels** obtenus
à l'exécution.

| # | Scénario | Concept démontré | Réf. cours |
|---|----------|------------------|------------|
| 1 | Alice ↔ AirFrance | Négociation bilatérale (Rubinstein + Zeuthen) | C2 |
| 2 | Coalition Tokyo (Bob, Carol, Dave) | Formation de coalition via courtier (Ketchpel) | C3a |
| 3 | Eve blackliste AirFrance | Préférences / acte déclaratif de refus | C1 |
| 4 | Frank vs Grace | Concession dynamique (facteur d'escompte) | C2 |
| 5 | 5 agents → SC* | Génération de structure de coalitions (DP/IDP/IP) | C3b |
| 6 | Ketchpel vs IDP | Comparaison d'algorithmes + Shapley | C3a/C3b |

---

## Scénario 1 — Négociation bilatérale Alice ↔ AirFrance

### Objectif et utilité
Démontrer une **négociation un-à-un** complète selon le **protocole d'offres alternées de
Rubinstein** (C2, p.7), enrichie de la **stratégie de Zeuthen** (C2, p.13-17) côté acheteur :
c'est le *risque de conflit* qui décide de l'ampleur de la concession. Ce scénario valide
la mécanique de base : messages FIPA-ACL (`CFP`, `PROPOSE`, `ACCEPT`/`REJECT`), borne de
budget, plafond de 6 soumissions et concession bornée à 10 %.

### Mise en place
| Agent | Rôle | Paramètres |
|-------|------|------------|
| Alice | Acheteur | budget = 500 €, deadline = 01-Dec, offre initiale = 300 € (60 %) |
| AirFrance | Vendeur | prix min = 400 €, offre initiale = 560 € (×1,4) |

### Déroulement
1. AirFrance propose **560 €** → trop cher pour Alice.
2. Alice calcule un **risque de Zeuthen = 0,37** → concession +1,3 % → contre-offre ≈ 303,77 €.
3. AirFrance concède (−10 %) → **504 €** ; Alice : risque = 0,29 → +1,4 % → ≈ 308,10 €.
4. AirFrance concède → **453,60 €**, désormais **≤ budget** → Alice **ACCEPTE**.

### Résultat
```
→ ACCORD ✅  prix = 453,60 €
```
Convergence en 3 tours. L'acheteur ne dépasse jamais son budget ; le vendeur ne descend
jamais sous son prix minimal → **rationalité individuelle** respectée des deux côtés.

---

## Scénario 2 — Formation de coalition Tokyo (courtier / Ketchpel)

### Objectif et utilité
Montrer la **formation automatique de coalition** par un **courtier** (`BrokerAgent`) selon
une logique inspirée de **Ketchpel** (C3a, p.62) : dès qu'un **seuil** d'acheteurs partageant
la même destination est atteint, le courtier crée un **chef de coalition**
(`CoalitionLeaderAgent`) qui négocie **au nom du groupe** et obtient une **remise de volume**.

### Mise en place
| Acheteur | Budget | Destination |
|----------|--------|-------------|
| Bob | 550 € | Tokyo |
| Carol | 600 € | Tokyo |
| Dave | 520 € | Tokyo |

Règle du courtier : 3 membres → remise **10 %** (4 membres → 20 %).

### Déroulement
1. Les 3 acheteurs s'inscrivent (`SUBSCRIBE`) → seuil de 3 atteint.
2. Le courtier crée `Coalition_Tokyo_(3_membres)` et **délègue** la négociation.
3. Le chef négocie avec un `GroupSeller` (prix min vendeur abaissé par la remise) et accepte
   un prix de groupe, **réparti à parts égales**.

### Résultat
```
ACCORD de groupe : 490,98 €  →  163,66 € / personne
Bob   : économise 386,34 €   (budget 550 €)
Carol : économise 436,34 €   (budget 600 €)
Dave  : économise 356,34 €   (budget 520 €)
Avantage coalition : −10 % garanti → 38,97 € / personne de gain
```
**Utilité** : la coordination via courtier transforme 3 négociations isolées en **un seul
pouvoir d'achat groupé** → prix unitaire bien inférieur à une négociation individuelle.

---

## Scénario 3 — Blacklist (refus catégorique)

### Objectif et utilité
Illustrer les **préférences** d'un agent, en particulier une **préférence négative**
(blacklist) traitée comme un **acte déclaratif de refus** (C1, p.51) : le refus est
**inconditionnel**, évalué **avant** tout calcul de prix.

### Mise en place
| Agent | Paramètres |
|-------|------------|
| Eve | budget = 700 €, **blacklist = [AirFrance]** |
| AirFrance | propose un **excellent** prix : 350 € (bien sous le budget) |

### Déroulement
AirFrance envoie une offre très attractive (350 € ≪ 700 €). Eve vérifie d'abord sa
blacklist → AirFrance y figure → **REJECT immédiat**, sans même considérer le prix.

### Résultat
```
Eve → REJECT  {reason: 'AirFrance blacklisted'}
```
**Utilité** : démontre qu'une contrainte de préférence **prime** sur l'intérêt économique.
Un prix imbattable ne suffit pas à lever un refus déclaratif.

---

## Scénario 4 — Concession dynamique (pression temporelle)

### Objectif et utilité
Démontrer le **facteur d'escompte de Rubinstein** (C2, p.10) : l'**intensité de la
concession** dépend de la **proximité de la deadline**. Un agent pressé concède vite, un
agent patient concède prudemment. Le taux est borné à **10 %** (contrainte de l'énoncé).

### Mise en place
| Agent | Budget | Deadline | Intention |
|-------|--------|----------|-----------|
| Frank | 450 € | 20-May | « deadline urgente » → concession agressive attendue |
| Grace | 450 € | 20-Dec | « deadline lointaine » → concession prudente attendue |

### Déroulement et résultat
Les deux acheteurs négocient avec AirFrance (mêmes conditions). Tous deux concluent :
```
Frank  → ACCORD ✅  408,24 €
Grace  → ACCORD ✅  408,24 €
```

> **⚠️ Observation importante (dates périmées).** Le scénario est conçu pour que Frank soit
> *urgent* et Grace *patiente*. Mais les deadlines sont **codées en dur** (`20-May`, `20-Dec`)
> et, à la date d'exécution actuelle, elles tombent **toutes deux loin** dans le futur
> (Frank ~347 j, Grace ~196 j). Résultat : `urgency ≈ 0` pour les deux → plafond de
> concession identique (~2 %) → **même prix final (408,24 €)**. L'effet pédagogique
> « urgent vs patient » n'est donc **plus visible** tel quel.
>
> **Correctif possible** : rendre les deadlines **relatives à la date du jour**
> (ex. `today + 5 jours` pour Frank, `today + 6 mois` pour Grace). Frank concéderait alors
> jusqu'à ~9 %/tour et accepterait un prix plus élevé, plus vite, que Grace.

---

## Scénario 5 — Génération de structure de coalitions optimale (DP / IDP / IP)

### Objectif et utilité
Trouver **SC\*** = la **partition** des agents qui **maximise** la valeur totale
$\sum_{c \in SC} v(c)$, avec **trois algorithmes** et vérifier qu'ils **convergent** :

- **DP** (C3b, slides 3-8) — programmation dynamique de Bellman, $O(3^n)$.
- **IDP** (C3b, slides 11-15) — DP amélioré avec **élagage par borne supérieure**.
- **IP** (C3b, slides 16-21) — formulation en **programme linéaire en nombres entiers**
  (set partitioning), résolue par le solveur **HiGHS** (`scipy.optimize.milp`).

### Mise en place — fonction caractéristique
5 agents (Alice, Bob, Carol, Dave, Eve). Valeur d'une coalition = économies totales :

| Taille | 1 | 2 | 3 | 4 | 5 |
|--------|---|---|---|---|---|
| Remise | 0 % | 5 % | **12 %** | 8 % | 6 % |

Ce jeu est **NON super-additif** : le trio est très rentable (12 %), mais regrouper tout le
monde fait *baisser* la remise (overhead de coordination) → la grand coalition est
**sous-optimale**.

### Résultat
```
Grand coalition seule      : v(ABCDE) = 159,60
Meilleure scission trouvée : {Alice, Dave} | {Bob, Carol, Eve}

DP   → SC* = {Alice,Dave} | {Bob,Carol,Eve}   V = 250,60   (31 coalitions évaluées)
IDP  → SC* = idem                              V = 250,60   (31 évaluées, 37 paires élaguées)
IP   → SC* = idem                              V = 250,60   (31 variables ILP)

✅ Les trois algorithmes convergent : V(SC*) = 250,60
```
**Utilité** : démontre (1) qu'on **ne doit pas** systématiquement tout regrouper, (2) que
les trois approches donnent le **même optimum**, (3) que l'**IDP élague** 37 paires de
tailles sans perdre l'optimalité (gain de calcul vs DP).

---

## Scénario 6 — Analyse comparative : Ketchpel glouton vs IDP optimal

### Objectif et utilité
**Confronter** un couplage **glouton** (Ketchpel, dépendant de l'ordre d'arrivée) à l'**IDP**
(optimal global), sur **trois situations**. Le scénario referme la boucle : la **SC\*** trouvée
par IDP **instancie de vrais agents** qui négocient (`negotiate_for_group`) et **répartissent**
le prix via la **valeur de Shapley** (C3a, p.36-45).

### Stratégie 1 — Arrivée simultanée
```
Ketchpel : {Alice,Bob,Carol} | {Dave,Eve}        V = 248,50
IDP      : {Alice,Dave} | {Bob,Carol,Eve}         V = 250,60
Δ = +2,10  (+0,8 %)
```
Écart faible : quand tout le monde arrive en même temps, le glouton s'en sort presque bien.

### Stratégie 2 — Arrivée décalée (le glouton décroche)
Ordre : Alice → Bob → Carol → Dave → Eve. Le glouton forme {Alice,Bob,Carol} dès le 3ᵉ,
**vide sa liste**, puis Dave et Eve n'atteignent jamais le seuil → restent **isolés**.
```
Ketchpel : {Alice,Bob,Carol} | {Dave} | {Eve}     V = 198,00
IDP      : {Alice,Dave} | {Bob,Carol,Eve}          V = 250,60
Δ = +52,60  (+26,6 %)
```
**Négociations réelles + transferts Shapley** déclenchés sur la SC\* d'IDP :

**Coalition {Alice, Dave}** — accord 456,19 € (228,09 €/pers) :
| Agent | φᵢ(v) | Part payée | Part égale | Token |
|-------|-------|-----------|-----------|-------|
| Alice | 24,50 | 228,09 € | 228,09 € | 0,00 € (= moyenne) |
| Dave  | 24,50 | 228,09 € | 228,09 € | 0,00 € (= moyenne) |

Agents **symétriques** → Shapley redonne la **part égale** (token = 0).

**Coalition {Bob, Carol, Eve}** — accord 482,94 € (160,98 €/pers) :
| Agent | φᵢ(v) | Part payée | Part égale | Token |
|-------|-------|-----------|-----------|-------|
| Bob   | 68,20 | 159,98 € | 160,98 € | **reçoit +1,00 €** (atout) |
| Carol | 66,95 | 161,23 € | 160,98 € | envoie −0,25 € (fardeau) |
| Eve   | 66,45 | 161,73 € | 160,98 € | envoie −0,75 € (fardeau) |

Bob contribue **plus** que la moyenne → c'est un **atout** → il **paie moins**. Somme des
tokens = 0 (efficacité).

### Stratégie 3 — Jeu super-additif (la grand coalition redevient optimale)
Avec des remises **strictement croissantes** (2 → 5 %, 3 → 10 %, 4 → 20 %, 5 → 30 %), le jeu
devient **super-additif** → regrouper tout le monde est cette fois optimal.
```
IDP → SC* = {Alice,Bob,Carol,Dave,Eve}   V = 798,00
Meilleure scission 3+2 : 217,00  <  798,00
→ IDP retourne la grand coalition ✅
```
**Répartition Shapley** (accord 364,95 € → 72,99 €/pers) :
| Agent | φᵢ(v) | Part payée | Token |
|-------|-------|-----------|-------|
| Alice | 156,80 | 75,79 € | envoie −2,80 € (fardeau) |
| Bob   | 165,55 | 67,04 € | **reçoit +5,95 €** (atout) |
| Carol | 161,18 | 71,42 € | reçoit +1,58 € (atout) |
| Dave  | 155,05 | 77,54 € | envoie −4,55 € (fardeau) |
| Eve   | 159,43 | 73,17 € | envoie −0,17 € (fardeau) |

Bob (plus gros budget = plus gros levier de remise) est le **principal atout** → il paie le
moins ; Dave (plus petit budget) paie le plus.

### Synthèse comparative
| Stratégie | V(Ketchpel) | V(IDP) | Gain IDP |
|-----------|-------------|--------|----------|
| S1 — Arrivée simultanée | 248,50 | 250,60 | +2,10 (+0,8 %) |
| S2 — Arrivée décalée | 198,00 | 250,60 | **+52,60 (+26,6 %)** |
| S3 — Jeu super-additif | n/a | 798,00 | grand coalition |

**Conclusions**
- IDP est **indépendant de l'ordre d'arrivée** et garantit l'**optimalité globale**.
- Le glouton **décroche** dès que l'ordre d'arrivée diverge de la partition optimale
  (jusqu'à **+27 %** d'écart en S2).
- Sur un jeu **super-additif**, IDP **converge** vers la grand coalition ; sur un jeu **non
  super-additif** (scénario 5), il **l'évite** et trouve la meilleure scission.

---

## Boucle fermée du TP
Le scénario 6 démontre que les **algorithmes de la partie (b)** (DP/IDP/IP) **pilotent** le
**système multi-agent de la partie (a)** : `IDP(v) → SC* → (BuyerAgent + CoalitionLeaderAgent
+ SellerAgent)`. Ce ne sont pas des exercices isolés — la structure optimale calculée est
**réellement négociée** par les agents, puis **équitablement répartie** par Shapley.
