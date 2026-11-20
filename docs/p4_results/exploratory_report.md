# P4 — exploration descriptive

- Schéma : `p4-formation-report-v1`
- Strate : **exploratory**
- Strate exploratoire : statistiques descriptives uniquement, aucune p-valeur, aucune garantie de puissance statistique.
- Données synthétiques ; aucune généralisation à un marché réel.
- Une solution MILP n'est un optimum exact que si son libellé est `milp_certified_exact` ; la structure officielle vient toujours d'`idp_search`.

### Cellules (médianes et quartiles sur les graines)

| famille | cellule | instances | statuts | taux d'économie médian | quartiles [Q1, Q3] | coalitions (médiane) | B1 sous-optimal | écart relatif B1 max | B0 / optimum (médiane) | blocs B0 non réalisables (moyenne) | taux d'accord (C, o) médian |
|---|---|---|---|---|---|---|---|---|---|---|---|
| factorial | factorial n=8 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | optimized | 0.0243 | [0.0121, 0.0355] | 2.0 | 4/20 | 0.3363 | 0.0345 | 1.535 | 0.9722 |
| factorial | factorial n=2 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0182] | 0.0 | 0/16 | 0.0 | 0.0 | 0.0 | 1.0 |
| factorial | factorial n=4 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | optimized | 0.0052 | [0.0, 0.0128] | 1.0 | 1/20 | 0.3687 | 0.2 | 0.775 | 1.0 |
| factorial | factorial n=6 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | optimized | 0.0177 | [0.0034, 0.0243] | 1.0 | 1/20 | 0.0868 | 0.0861 | 1.685 | 1.0 |
| factorial | factorial n=10 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | optimized | 0.0244 | [0.0145, 0.0279] | 2.0 | 6/20 | 0.1678 | 0.0353 | 2.415 | 0.9764 |
| factorial | factorial n=12 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | optimized | 0.0253 | [0.0178, 0.0327] | 2.0 | 7/20 | 0.1089 | -0.0436 | 3.0225 | 1.0 |
| factorial | factorial n=14 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | optimized | 0.0229 | [0.0168, 0.0303] | 2.0 | 11/20 | 0.1385 | -0.0729 | 3.1225 | 0.9886 |
| factorial | factorial n=8 p=1 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | optimized | 0.0171 | [0.008, 0.0554] | 1.0 | 3/20 | 0.1056 | 0.0 | 1.6 | 0.9848 |
| factorial | factorial n=8 p=3 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | optimized | 0.0103 | [0.0058, 0.0192] | 1.0 | 1/20 | 0.1328 | 0.0 | 1.6425 | 1.0 |
| factorial | factorial n=8 p=2 o=1 m=50 g=moderate cv=0 a=80 d=60 | 20 | optimized | 0.0161 | [0.0, 0.0318] | 1.0 | 1/20 | 0.5 | 0.0455 | 1.795 | 1.0 |
| factorial | factorial n=8 p=2 o=3 m=50 g=moderate cv=0 a=80 d=60 | 20 | optimized | 0.0235 | [0.0161, 0.0305] | 2.0 | 7/20 | 0.4113 | -0.0097 | 1.58 | 0.8925 |
| factorial | factorial n=8 p=2 o=5 m=50 g=moderate cv=0 a=80 d=60 | 20 | optimized | 0.018 | [0.0091, 0.0235] | 2.0 | 8/20 | 0.3961 | 0.0156 | 1.44 | 0.7981 |
| factorial | factorial n=8 p=2 o=2 m=0 g=moderate cv=0 a=80 d=60 | 20 | optimized | 0.0184 | [0.0093, 0.0269] | 1.0 | 3/20 | 0.2061 | -0.0109 | 1.67 | 1.0 |
| factorial | factorial n=8 p=2 o=2 m=50 g=flat cv=0 a=80 d=60 | 20 | optimized | 0.0 | [0.0, 0.0066] | 1.0 | 0/20 | 0.0 | -1.0106 | 1.5725 | 0.9559 |
| factorial | factorial n=8 p=2 o=2 m=50 g=steep cv=0 a=80 d=60 | 20 | optimized | 0.0234 | [0.0123, 0.0474] | 1.0 | 4/20 | 0.2969 | 0.0 | 1.7025 | 1.0 |
| factorial | factorial n=8 p=2 o=2 m=50 g=moderate cv=10 a=80 d=60 | 20 | optimized | 0.0369 | [0.0274, 0.0395] | 2.0 | 6/20 | 0.458 | 0.0371 | 1.675 | 0.976 |
| factorial | factorial n=8 p=2 o=2 m=50 g=moderate cv=30 a=80 d=60 | 20 | optimized | 0.032 | [0.0204, 0.0546] | 2.0 | 2/20 | 0.2494 | 0.0 | 1.5675 | 0.946 |
| factorial | factorial n=8 p=2 o=2 m=50 g=moderate cv=0 a=20 d=60 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0] | 0.0 | 0/16 | 0.0 | 0.0 | 1.9937 | 1.0 |
| factorial | factorial n=8 p=2 o=2 m=50 g=moderate cv=0 a=50 d=60 | 20 | optimized | 0.007 | [0.0, 0.0242] | 1.0 | 1/20 | 0.0 | 0.05 | 1.8425 | 1.0 |
| factorial | factorial n=8 p=2 o=2 m=50 g=moderate cv=0 a=100 d=60 | 20 | optimized | 0.0259 | [0.0176, 0.0323] | 2.0 | 5/20 | 0.1639 | 0.0981 | 1.1325 | 1.0 |
| factorial | factorial n=8 p=2 o=2 m=50 g=moderate cv=0 a=80 d=30 | 20 | optimized | 0.0097 | [0.0, 0.0225] | 1.0 | 0/20 | 0.0 | 0.0 | 1.95 | 1.0 |
| factorial | factorial n=8 p=2 o=2 m=50 g=moderate cv=0 a=80 d=90 | 20 | optimized | 0.0206 | [0.0121, 0.0295] | 2.0 | 4/20 | 0.1684 | 0.2 | 0.895 | 0.9814 |
| factorial | factorial n=4 p=3 o=2 m=50 g=steep cv=30 a=80 d=30 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0] | 0.0 | 0/18 | 0.0 | 0.0 | 1.0 | 1.0 |
| factorial | factorial n=14 p=3 o=3 m=50 g=steep cv=10 a=100 d=90 | 20 | optimized | 0.046 | [0.0385, 0.0526] | 4.0 | 18/20 | 0.2519 | 0.0888 | 0.305 | 0.6871 |
| factorial | factorial n=2 p=1 o=2 m=50 g=moderate cv=30 a=50 d=90 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0] | 0.0 | 0/15 | 0.0 | 0.0 | 0.0 | 1.0 |
| factorial | factorial n=14 p=1 o=3 m=0 g=steep cv=10 a=50 d=90 | 20 | optimized | 0.0706 | [0.0499, 0.0983] | 2.0 | 11/20 | 0.4157 | 0.0551 | 3.6125 | 0.9574 |
| factorial | factorial n=4 p=1 o=5 m=50 g=flat cv=10 a=50 d=30 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0] | 0.0 | 0/18 | 0.0 | 0.0 | 1.0 | 0.8125 |
| factorial | factorial n=4 p=2 o=3 m=50 g=flat cv=10 a=20 d=30 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0] | 0.0 | 0/9 | — | — | 1.0 | 1.0 |
| factorial | factorial n=6 p=3 o=2 m=0 g=steep cv=10 a=50 d=90 | 20 | optimized | 0.0003 | [0.0, 0.0281] | 0.5 | 0/20 | 0.0 | 0.0225 | 1.785 | 0.9476 |
| factorial | factorial n=8 p=3 o=2 m=50 g=flat cv=30 a=80 d=60 | 20 | optimized | 0.0303 | [0.0186, 0.0399] | 1.5 | 5/20 | 0.197 | -0.0567 | 1.595 | 0.8848 |
| factorial | factorial n=10 p=3 o=5 m=50 g=flat cv=0 a=100 d=90 | 20 | optimized | 0.0 | [0.0, 0.0] | 0.0 | 0/20 | 0.0 | -0.95 | 0.045 | 0.5861 |
| factorial | factorial n=6 p=1 o=3 m=0 g=moderate cv=0 a=100 d=30 | 20 | optimized | 0.0042 | [0.0, 0.0145] | 1.0 | 3/20 | 0.081 | -0.0662 | 1.825 | 0.9499 |
| factorial | factorial n=4 p=1 o=1 m=0 g=steep cv=10 a=50 d=90 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.026] | 0.0 | 0/17 | 0.0 | 0.0249 | 0.8324 | 1.0 |
| factorial | factorial n=14 p=2 o=1 m=0 g=moderate cv=0 a=100 d=90 | 20 | optimized | 0.0237 | [0.0183, 0.0307] | 3.0 | 7/20 | 0.3333 | 0.3035 | 1.13 | 1.0 |
| factorial | factorial n=2 p=3 o=3 m=0 g=steep cv=30 a=100 d=30 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0] | 0.0 | 0/19 | 0.0 | 0.0 | 0.0 | 1.0 |
| factorial | factorial n=12 p=2 o=5 m=0 g=flat cv=30 a=50 d=30 | 20 | optimized | 0.0 | [0.0, 0.0158] | 0.0 | 2/20 | 0.2647 | 0.0 | 3.9425 | 0.8733 |
| factorial | factorial n=14 p=1 o=5 m=0 g=moderate cv=30 a=80 d=90 | 20 | optimized | 0.0663 | [0.0577, 0.1093] | 3.0 | 12/20 | 0.2043 | 0.0388 | 2.0375 | 0.8038 |
| factorial | factorial n=12 p=1 o=2 m=50 g=steep cv=0 a=100 d=90 | 20 | optimized | 0.0404 | [0.0284, 0.0772] | 3.0 | 16/20 | 0.2643 | 0.054 | 0.2 | 0.9993 |
| factorial | factorial n=8 p=3 o=3 m=50 g=moderate cv=0 a=50 d=90 | 20 | optimized | 0.0 | [0.0, 0.0075] | 0.5 | 0/20 | 0.0 | 0.0094 | 1.8375 | 0.6577 |
| factorial | factorial n=4 p=2 o=3 m=50 g=moderate cv=30 a=100 d=30 | 20 | optimized | 0.0 | [0.0, 0.0059] | 0.0 | 0/20 | 0.0 | 0.0 | 0.9925 | 1.0 |
| factorial | factorial n=12 p=1 o=1 m=0 g=moderate cv=10 a=100 d=90 | 20 | optimized | 0.0564 | [0.051, 0.0618] | 3.0 | 15/20 | 0.1773 | 0.1029 | 1.0475 | 1.0 |
| factorial | factorial n=8 p=1 o=1 m=50 g=moderate cv=30 a=100 d=30 | 20 | no_eligible_units/optimized | 0.0034 | [0.0, 0.0179] | 0.5 | 1/18 | 0.0026 | 0.0 | 1.95 | 1.0 |
| factorial | factorial n=12 p=1 o=1 m=0 g=moderate cv=0 a=100 d=60 | 20 | optimized | 0.0144 | [0.0, 0.0601] | 2.0 | 4/20 | 0.1428 | -0.0217 | 3.2575 | 1.0 |
| factorial | factorial n=8 p=1 o=2 m=0 g=moderate cv=0 a=100 d=30 | 20 | no_eligible_units/optimized | 0.0229 | [0.0, 0.0456] | 1.0 | 4/19 | 0.1293 | 0.0 | 1.8079 | 1.0 |
| factorial | factorial n=14 p=2 o=1 m=0 g=steep cv=30 a=100 d=30 | 20 | optimized | 0.0413 | [0.027, 0.0649] | 1.0 | 0/20 | 0.0 | 0.0 | 3.9525 | 1.0 |
| factorial | factorial n=6 p=2 o=2 m=0 g=moderate cv=0 a=50 d=30 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0096] | 0.0 | 0/16 | 0.0 | 0.0 | 2.0 | 1.0 |
| factorial | factorial n=4 p=2 o=2 m=0 g=flat cv=10 a=100 d=90 | 20 | optimized | 0.0298 | [0.0229, 0.0383] | 1.0 | 2/20 | 0.3524 | 0.1035 | 0.0375 | 0.8818 |
| factorial | factorial n=12 p=1 o=2 m=50 g=moderate cv=30 a=100 d=30 | 20 | optimized | 0.0462 | [0.0296, 0.055] | 2.0 | 5/20 | 0.444 | 0.0 | 3.7575 | 1.0 |
| factorial | factorial n=14 p=3 o=5 m=50 g=flat cv=0 a=50 d=90 | 20 | optimized | 0.0 | [0.0, 0.0026] | 1.0 | 1/20 | 0.5 | -0.2672 | 3.575 | 0.4573 |
| factorial | factorial n=10 p=3 o=1 m=0 g=flat cv=0 a=100 d=60 | 20 | optimized | 0.0 | [0.0, 0.0] | 0.0 | 1/20 | 0.3333 | -0.0125 | 2.3525 | 1.0 |
| factorial | factorial n=14 p=3 o=2 m=50 g=steep cv=30 a=100 d=60 | 20 | optimized | 0.0503 | [0.0418, 0.0584] | 3.0 | 14/20 | 0.3087 | -0.0977 | 2.5625 | 0.985 |
| factorial | factorial n=12 p=1 o=2 m=0 g=moderate cv=30 a=50 d=60 | 20 | optimized | 0.045 | [0.0223, 0.0584] | 2.0 | 6/20 | 0.2764 | 0.0 | 3.835 | 0.971 |
| factorial | factorial n=6 p=3 o=5 m=50 g=steep cv=30 a=20 d=90 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0107] | 0.0 | 0/16 | 0.0 | 0.0 | 1.9656 | 0.2583 |
| factorial | factorial n=10 p=2 o=5 m=50 g=flat cv=30 a=20 d=90 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0137] | 0.0 | 0/19 | 0.0 | 0.0 | 2.9921 | 0.6923 |
| factorial | factorial n=2 p=3 o=2 m=0 g=moderate cv=30 a=50 d=60 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0] | 0.0 | 0/12 | — | — | 0.0 | 1.0 |
| factorial | factorial n=4 p=1 o=5 m=0 g=moderate cv=10 a=80 d=30 | 20 | optimized | 0.0064 | [0.0, 0.0253] | 1.0 | 0/20 | 0.0 | 0.0 | 0.935 | 0.7098 |
| factorial | factorial n=14 p=3 o=5 m=50 g=flat cv=10 a=80 d=90 | 20 | optimized | 0.0342 | [0.0301, 0.0419] | 3.0 | 15/20 | 0.1433 | 0.0121 | 1.8425 | 0.5826 |
| factorial | factorial n=6 p=2 o=5 m=50 g=moderate cv=30 a=50 d=90 | 20 | optimized | 0.0328 | [0.0044, 0.0389] | 1.0 | 3/20 | 0.3481 | 0.1 | 1.68 | 0.547 |
| factorial | factorial n=2 p=3 o=3 m=0 g=flat cv=10 a=80 d=90 | 20 | optimized | 0.0 | [0.0, 0.0227] | 0.0 | 0/20 | 0.0 | 0.0 | 0.0 | 0.4643 |
| factorial | factorial n=6 p=3 o=2 m=0 g=flat cv=0 a=50 d=90 | 20 | optimized | 0.0 | [0.0, 0.0] | 0.0 | 0/20 | 0.0 | 0.075 | 1.8875 | 1.0 |
| factorial | factorial n=12 p=1 o=3 m=50 g=steep cv=30 a=50 d=60 | 20 | optimized | 0.0645 | [0.0481, 0.0951] | 2.0 | 6/20 | 0.3678 | 0.0217 | 3.7975 | 0.8625 |
| factorial | factorial n=10 p=3 o=3 m=50 g=moderate cv=10 a=50 d=30 | 20 | optimized | 0.0063 | [0.0, 0.035] | 1.0 | 0/20 | 0.0 | 0.0 | 2.9925 | 0.899 |
| factorial | factorial n=14 p=2 o=2 m=50 g=flat cv=0 a=80 d=30 | 20 | optimized | 0.0 | [0.0, 0.017] | 0.0 | 0/20 | 0.0 | 0.0 | 3.925 | 1.0 |
| factorial | factorial n=14 p=3 o=3 m=0 g=steep cv=30 a=80 d=90 | 20 | optimized | 0.0471 | [0.0412, 0.0595] | 3.0 | 14/20 | 0.2352 | -0.063 | 1.9025 | 0.8498 |
| factorial | factorial n=8 p=1 o=2 m=0 g=steep cv=30 a=80 d=30 | 20 | optimized | 0.0577 | [0.0237, 0.0906] | 1.0 | 1/20 | 0.1366 | 0.0 | 1.8925 | 1.0 |
| factorial | factorial n=6 p=1 o=1 m=50 g=moderate cv=30 a=50 d=60 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.013] | 0.0 | 0/14 | 0.0 | 0.0 | 1.9857 | 1.0 |
| factorial | factorial n=2 p=1 o=2 m=0 g=moderate cv=0 a=20 d=60 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0] | 0.0 | 0/5 | — | — | 0.0 | 1.0 |
| factorial | factorial n=12 p=1 o=3 m=0 g=steep cv=0 a=100 d=30 | 20 | optimized | 0.0331 | [0.0195, 0.0514] | 2.0 | 6/20 | 0.2405 | -0.0035 | 3.76 | 0.9799 |
| factorial | factorial n=10 p=2 o=2 m=0 g=moderate cv=10 a=100 d=90 | 20 | optimized | 0.0472 | [0.041, 0.0521] | 3.0 | 17/20 | 0.2381 | 0.0573 | 0.525 | 0.6738 |
| factorial | factorial n=4 p=2 o=2 m=50 g=moderate cv=10 a=100 d=90 | 20 | optimized | 0.0289 | [0.0139, 0.0482] | 1.0 | 2/20 | 0.2933 | 0.15 | 0.105 | 0.8864 |
| factorial | factorial n=12 p=1 o=2 m=50 g=flat cv=30 a=100 d=90 | 20 | optimized | 0.045 | [0.0351, 0.052] | 3.0 | 12/20 | 0.3014 | -0.4198 | 0.3775 | 0.8984 |
| factorial | factorial n=6 p=1 o=5 m=50 g=steep cv=10 a=20 d=90 | 20 | no_eligible_units/optimized | 0.0069 | [0.0, 0.0247] | 0.0 | 0/16 | 0.0 | 0.0 | 1.9906 | 0.5333 |
| factorial | factorial n=6 p=2 o=3 m=50 g=steep cv=30 a=80 d=30 | 20 | optimized | 0.0151 | [0.0, 0.0349] | 1.0 | 0/20 | 0.0 | 0.0133 | 1.915 | 1.0 |
| factorial | factorial n=4 p=2 o=5 m=50 g=flat cv=30 a=100 d=30 | 20 | optimized | 0.0014 | [0.0, 0.0143] | 0.5 | 0/20 | 0.0 | 0.0 | 0.9325 | 0.7462 |
| factorial | factorial n=14 p=3 o=2 m=0 g=flat cv=30 a=50 d=90 | 20 | optimized | 0.0327 | [0.0101, 0.04] | 1.0 | 6/20 | 0.3943 | -0.0377 | 3.6175 | 0.7763 |
| factorial | factorial n=6 p=1 o=2 m=50 g=flat cv=0 a=100 d=90 | 20 | optimized | 0.0 | [0.0, 0.0] | 0.0 | 0/20 | 0.0 | 0.2004 | 0.2975 | 0.7581 |
| factorial | factorial n=2 p=3 o=1 m=50 g=steep cv=10 a=100 d=60 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0] | 0.0 | 0/15 | 0.0 | 0.0 | 0.0 | 1.0 |
| factorial | factorial n=6 p=1 o=2 m=0 g=moderate cv=10 a=100 d=30 | 20 | optimized | 0.0175 | [0.0, 0.0362] | 1.0 | 0/20 | 0.0 | 0.0 | 1.9375 | 1.0 |
| factorial | factorial n=6 p=2 o=1 m=50 g=moderate cv=0 a=20 d=30 | 20 | no_eligible_units/optimized | 0.0 | [0.0, 0.0] | 0.0 | 0/2 | — | — | 2.0 | 1.0 |
| factorial | factorial n=2 p=1 o=5 m=50 g=steep cv=0 a=80 d=60 | 20 | optimized | 0.0 | [0.0, 0.0013] | 0.0 | 0/20 | 0.0 | 0.0 | 0.0 | 0.6667 |
| factorial | factorial n=8 p=2 o=5 m=0 g=flat cv=10 a=80 d=60 | 20 | optimized | 0.0268 | [0.0207, 0.0319] | 2.0 | 6/20 | 0.4021 | -0.0083 | 1.505 | 0.7161 |
| factorial | factorial n=12 p=2 o=3 m=50 g=moderate cv=30 a=80 d=90 | 20 | optimized | 0.0471 | [0.0353, 0.0568] | 3.0 | 14/20 | 0.3132 | -0.1259 | 2.28 | 0.8243 |
| null | null n=8 p=2 o=1 m=50 g=flat cv=0 a=100 d=100 | 20 | optimized | 0.0 | [0.0, 0.0] | 0.0 | 1/20 | 0.2 | 0.3 | 0.0 | 1.0 |
| mutualisation | mutualisation n=10 p=1 o=1 m=50 g=steep cv=0 a=100 d=100 | 20 | optimized | 0.0556 | [0.0398, 0.1358] | 1.0 | 2/20 | 0.2839 | -0.3273 | 0.0 | 1.0 |
| isolated | isolated n=8 p=2 o=2 m=50 g=moderate cv=0 a=50 d=30 | 20 | optimized | 0.0 | [0.0, 0.0025] | 0.0 | 1/20 | 0.1722 | 0.0 | 1.9825 | 1.0 |
| h2_violation | h2_violation n=8 p=2 o=2 m=50 g=flat cv=0 a=80 d=100 | 20 | capacity_model_violated | — | — | — | — | — | — | — | — |
| large | large n=16 p=2 o=1 m=50 g=moderate cv=0 a=80 d=100 | 20 | incomplete/optimized | 0.0247 | [0.02, 0.0304] | 3.0 | 9/16 | 0.0 | 0.4241 | 2.8531 | 1.0 |

### Décomposition des économies (sommes sur les instances, centimes)

> `residual_collective_negotiation` : résidu comptable, non identifiable causalement (plancher privé du palier collectif, avantage de négociation et artefact budgétaire de la stratégie historique mêlés).

| cellule | instances | v total | savings_offer_switch | savings_public_tier_pooling | residual_collective_negotiation | savings_individual_negotiation | identité exacte |
|---|---|---|---|---|---|---|---|
| factorial n=8 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | 490024 | -418370 | 637590 | 270804 | 5637503 | oui |
| factorial n=2 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 16 | 45006 | 0 | 58510 | -13504 | 1389695 | oui |
| factorial n=4 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | 134794 | -67315 | 183505 | 18604 | 3140206 | oui |
| factorial n=6 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | 259889 | -91580 | 351685 | -216 | 4071059 | oui |
| factorial n=10 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | 553278 | -335645 | 703500 | 185423 | 7076904 | oui |
| factorial n=12 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | 849087 | -224850 | 834365 | 239572 | 9602627 | oui |
| factorial n=14 p=2 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | 805585 | -80105 | 957250 | -71560 | 9893242 | oui |
| factorial n=8 p=1 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | 272199 | -88540 | 460985 | -100246 | 2505830 | oui |
| factorial n=8 p=3 o=2 m=50 g=moderate cv=0 a=80 d=60 | 20 | 451247 | -53190 | 328630 | 175807 | 7831343 | oui |
| factorial n=8 p=2 o=1 m=50 g=moderate cv=0 a=80 d=60 | 20 | 249135 | 0 | 310330 | -61195 | 4085469 | oui |
| factorial n=8 p=2 o=3 m=50 g=moderate cv=0 a=80 d=60 | 20 | 551054 | -228725 | 636700 | 143079 | 6322708 | oui |
| factorial n=8 p=2 o=5 m=50 g=moderate cv=0 a=80 d=60 | 20 | 436451 | -179620 | 683425 | -67354 | 7020201 | oui |
| factorial n=8 p=2 o=2 m=0 g=moderate cv=0 a=80 d=60 | 20 | 396602 | -119880 | 534060 | -17578 | 6048311 | oui |
| factorial n=8 p=2 o=2 m=50 g=flat cv=0 a=80 d=60 | 20 | 86392 | -376800 | 0 | 463192 | 5870605 | oui |
| factorial n=8 p=2 o=2 m=50 g=steep cv=0 a=80 d=60 | 20 | 441710 | -83415 | 1111200 | -586075 | 3788695 | oui |
| factorial n=8 p=2 o=2 m=50 g=moderate cv=10 a=80 d=60 | 20 | 660833 | 10 | 531615 | 129208 | 4565305 | oui |
| factorial n=8 p=2 o=2 m=50 g=moderate cv=30 a=80 d=60 | 20 | 810236 | -272605 | 544265 | 538576 | 4606428 | oui |
| factorial n=8 p=2 o=2 m=50 g=moderate cv=0 a=20 d=60 | 16 | 30730 | 86450 | 62195 | -117915 | 1552717 | oui |
| factorial n=8 p=2 o=2 m=50 g=moderate cv=0 a=50 d=60 | 20 | 177800 | 55985 | 235090 | -113275 | 3242776 | oui |
| factorial n=8 p=2 o=2 m=50 g=moderate cv=0 a=100 d=60 | 20 | 619835 | -130320 | 695065 | 55090 | 6979165 | oui |
| factorial n=8 p=2 o=2 m=50 g=moderate cv=0 a=80 d=30 | 20 | 168672 | -98960 | 191275 | 76357 | 3645189 | oui |
| factorial n=8 p=2 o=2 m=50 g=moderate cv=0 a=80 d=90 | 20 | 426386 | -175840 | 587815 | 14411 | 6603767 | oui |
| factorial n=4 p=3 o=2 m=50 g=steep cv=30 a=80 d=30 | 18 | 4956 | 0 | 0 | 4956 | 1438977 | oui |
| factorial n=14 p=3 o=3 m=50 g=steep cv=10 a=100 d=90 | 20 | 2496332 | 543215 | 1406910 | 546207 | 16189045 | oui |
| factorial n=2 p=1 o=2 m=50 g=moderate cv=30 a=50 d=90 | 15 | 10073 | -27600 | 31020 | 6653 | 306937 | oui |
| factorial n=14 p=1 o=3 m=0 g=steep cv=10 a=50 d=90 | 20 | 952197 | -200645 | 2441220 | -1288378 | 3263295 | oui |
| factorial n=4 p=1 o=5 m=50 g=flat cv=10 a=50 d=30 | 18 | 5695 | 6900 | 0 | -1205 | 972806 | oui |
| factorial n=4 p=2 o=3 m=50 g=flat cv=10 a=20 d=30 | 9 | 0 | 0 | 0 | 0 | 677175 | oui |
| factorial n=6 p=3 o=2 m=0 g=steep cv=10 a=50 d=90 | 20 | 232471 | 65870 | 74625 | 91976 | 3267776 | oui |
| factorial n=8 p=3 o=2 m=50 g=flat cv=30 a=80 d=60 | 20 | 1036875 | 81900 | 0 | 954975 | 8224878 | oui |
| factorial n=10 p=3 o=5 m=50 g=flat cv=0 a=100 d=90 | 20 | 66961 | 85000 | 0 | -18039 | 16827285 | oui |
| factorial n=6 p=1 o=3 m=0 g=moderate cv=0 a=100 d=30 | 20 | 115613 | -149075 | 202815 | 61873 | 2118921 | oui |
| factorial n=4 p=1 o=1 m=0 g=steep cv=10 a=50 d=90 | 17 | 96118 | 0 | 373455 | -277337 | 1000400 | oui |
| factorial n=14 p=2 o=1 m=0 g=moderate cv=0 a=100 d=90 | 20 | 1032217 | 0 | 1268375 | -236158 | 11652622 | oui |
| factorial n=2 p=3 o=3 m=0 g=steep cv=30 a=100 d=30 | 19 | 57198 | 19040 | 0 | 38158 | 1553931 | oui |
| factorial n=12 p=2 o=5 m=0 g=flat cv=30 a=50 d=30 | 20 | 201275 | -180000 | 0 | 381275 | 3397131 | oui |
| factorial n=14 p=1 o=5 m=0 g=moderate cv=30 a=80 d=90 | 20 | 1601516 | 115585 | 1453610 | 32321 | 5563280 | oui |
| factorial n=12 p=1 o=2 m=50 g=steep cv=0 a=100 d=90 | 20 | 1182689 | -780610 | 4586685 | -2623386 | 6029410 | oui |
| factorial n=8 p=3 o=3 m=50 g=moderate cv=0 a=50 d=90 | 20 | 93591 | -58280 | 109070 | 42801 | 5843576 | oui |
| factorial n=4 p=2 o=3 m=50 g=moderate cv=30 a=100 d=30 | 20 | 73671 | -47975 | 127480 | -5834 | 2055424 | oui |
| factorial n=12 p=1 o=1 m=0 g=moderate cv=10 a=100 d=90 | 20 | 1235706 | 0 | 1565980 | -330274 | 4942114 | oui |
| factorial n=8 p=1 o=1 m=50 g=moderate cv=30 a=100 d=30 | 18 | 82416 | 0 | 137200 | -54784 | 962277 | oui |
| factorial n=12 p=1 o=1 m=0 g=moderate cv=0 a=100 d=60 | 20 | 393247 | 0 | 497285 | -104038 | 3950692 | oui |
| factorial n=8 p=1 o=2 m=0 g=moderate cv=0 a=100 d=30 | 19 | 204549 | -106315 | 309625 | 1239 | 1848558 | oui |
| factorial n=14 p=2 o=1 m=0 g=steep cv=30 a=100 d=30 | 20 | 561517 | 0 | 1065705 | -504188 | 2487309 | oui |
| factorial n=6 p=2 o=2 m=0 g=moderate cv=0 a=50 d=30 | 16 | 41184 | 22140 | 54665 | -35621 | 1591298 | oui |
| factorial n=4 p=2 o=2 m=0 g=flat cv=10 a=100 d=90 | 20 | 446011 | 379400 | 0 | 66611 | 4763829 | oui |
| factorial n=12 p=1 o=2 m=50 g=moderate cv=30 a=100 d=30 | 20 | 607718 | -101820 | 805360 | -95822 | 2816924 | oui |
| factorial n=14 p=3 o=5 m=50 g=flat cv=0 a=50 d=90 | 20 | 68180 | -228400 | 0 | 296580 | 11734925 | oui |
| factorial n=10 p=3 o=1 m=0 g=flat cv=0 a=100 d=60 | 20 | 7 | 0 | 0 | 7 | 10715235 | oui |
| factorial n=14 p=3 o=2 m=50 g=steep cv=30 a=100 d=60 | 20 | 2543141 | 20385 | 1016370 | 1506386 | 11468186 | oui |
| factorial n=12 p=1 o=2 m=0 g=moderate cv=30 a=50 d=60 | 20 | 515847 | -69080 | 581770 | 3157 | 2235883 | oui |
| factorial n=6 p=3 o=5 m=50 g=steep cv=30 a=20 d=90 | 16 | 60980 | 24010 | 101250 | -64280 | 1499902 | oui |
| factorial n=10 p=2 o=5 m=50 g=flat cv=30 a=20 d=90 | 19 | 101785 | 154200 | 0 | -52415 | 2502467 | oui |
| factorial n=2 p=3 o=2 m=0 g=moderate cv=30 a=50 d=60 | 12 | 0 | 0 | 0 | 0 | 1074929 | oui |
| factorial n=4 p=1 o=5 m=0 g=moderate cv=10 a=80 d=30 | 20 | 89500 | -49440 | 192150 | -53210 | 1710190 | oui |
| factorial n=14 p=3 o=5 m=50 g=flat cv=10 a=80 d=90 | 20 | 2185752 | 1535000 | 0 | 650752 | 18937080 | oui |
| factorial n=6 p=2 o=5 m=50 g=moderate cv=30 a=50 d=90 | 20 | 344968 | -100530 | 288360 | 157138 | 3620421 | oui |
| factorial n=2 p=3 o=3 m=0 g=flat cv=10 a=80 d=90 | 20 | 154127 | 22100 | 0 | 132027 | 2900641 | oui |
| factorial n=6 p=3 o=2 m=0 g=flat cv=0 a=50 d=90 | 20 | 4 | 0 | 0 | 4 | 4483212 | oui |
| factorial n=12 p=1 o=3 m=50 g=steep cv=30 a=50 d=60 | 20 | 627914 | -152410 | 1937925 | -1157601 | 2164179 | oui |
| factorial n=10 p=3 o=3 m=50 g=moderate cv=10 a=50 d=30 | 20 | 288188 | 6750 | 55285 | 226153 | 4679746 | oui |
| factorial n=14 p=2 o=2 m=50 g=flat cv=0 a=80 d=30 | 20 | 194097 | -152200 | 0 | 346297 | 5952262 | oui |
| factorial n=14 p=3 o=3 m=0 g=steep cv=30 a=80 d=90 | 20 | 2476228 | 280890 | 1129500 | 1065838 | 12520121 | oui |
| factorial n=8 p=1 o=2 m=0 g=steep cv=30 a=80 d=30 | 20 | 570286 | -29230 | 1250175 | -650659 | 1364377 | oui |
| factorial n=6 p=1 o=1 m=50 g=moderate cv=30 a=50 d=60 | 14 | 40523 | 0 | 52595 | -12072 | 595361 | oui |
| factorial n=2 p=1 o=2 m=0 g=moderate cv=0 a=20 d=60 | 5 | 0 | 0 | 0 | 0 | 132757 | oui |
| factorial n=12 p=1 o=3 m=0 g=steep cv=0 a=100 d=30 | 20 | 518321 | -90800 | 2655510 | -2046389 | 4023520 | oui |
| factorial n=10 p=2 o=2 m=0 g=moderate cv=10 a=100 d=90 | 20 | 1595126 | -127880 | 1089730 | 633276 | 10698853 | oui |
| factorial n=4 p=2 o=2 m=50 g=moderate cv=10 a=100 d=90 | 20 | 377957 | -178570 | 309185 | 247342 | 3780280 | oui |
| factorial n=12 p=1 o=2 m=50 g=flat cv=30 a=100 d=90 | 20 | 1046184 | -34900 | 0 | 1081084 | 5567283 | oui |
| factorial n=6 p=1 o=5 m=50 g=steep cv=10 a=20 d=90 | 16 | 78277 | -39910 | 298365 | -180178 | 739455 | oui |
| factorial n=6 p=2 o=3 m=50 g=steep cv=30 a=80 d=30 | 20 | 339592 | -75055 | 586185 | -171538 | 1935340 | oui |
| factorial n=4 p=2 o=5 m=50 g=flat cv=30 a=100 d=30 | 20 | 122130 | 8100 | 0 | 114030 | 3089192 | oui |
| factorial n=14 p=3 o=2 m=0 g=flat cv=30 a=50 d=90 | 20 | 1377607 | -56800 | 0 | 1434407 | 8699037 | oui |
| factorial n=6 p=1 o=2 m=50 g=flat cv=0 a=100 d=90 | 20 | 36142 | 1800 | 0 | 34342 | 3005298 | oui |
| factorial n=2 p=3 o=1 m=50 g=steep cv=10 a=100 d=60 | 15 | 43745 | 0 | 23310 | 20435 | 1292974 | oui |
| factorial n=6 p=1 o=2 m=0 g=moderate cv=10 a=100 d=30 | 20 | 121683 | 18700 | 172070 | -69087 | 1363672 | oui |
| factorial n=6 p=2 o=1 m=50 g=moderate cv=0 a=20 d=30 | 2 | 0 | 0 | 0 | 0 | 199033 | oui |
| factorial n=2 p=1 o=5 m=50 g=steep cv=0 a=80 d=60 | 20 | 33270 | 18035 | 141180 | -125945 | 919866 | oui |
| factorial n=8 p=2 o=5 m=0 g=flat cv=10 a=80 d=60 | 20 | 575696 | -269000 | 0 | 844696 | 6535620 | oui |
| factorial n=12 p=2 o=3 m=50 g=moderate cv=30 a=80 d=90 | 20 | 1478718 | 37450 | 1096260 | 345008 | 8089550 | oui |
| null n=8 p=2 o=1 m=50 g=flat cv=0 a=100 d=100 | 20 | 16 | 0 | 0 | 16 | 8173868 | oui |
| mutualisation n=10 p=1 o=1 m=50 g=steep cv=0 a=100 d=100 | 20 | 770853 | 0 | 2862900 | -2092047 | 2278740 | oui |
| isolated n=8 p=2 o=2 m=50 g=moderate cv=0 a=50 d=30 | 20 | 82925 | -31350 | 115360 | -1085 | 1788784 | oui |
| large n=16 p=2 o=1 m=50 g=moderate cv=0 a=80 d=100 | 16 | 834525 | 0 | 1075125 | -240600 | 10038445 | oui |
