# Backtests et validation des stratégies

Dernière mise à jour : 2026-10-03.

## Règle de validation

Le bot Oracle reste en `dry_run=true`. Les stratégies de ce dépôt sont des
candidates de recherche tant qu'elles n'ont pas résisté à plusieurs fenêtres
indépendantes, aux frais, au lookahead-analysis et au recursive-analysis.

Aucune stratégie n'est promue automatiquement en réel.

## Données et frais

- Paires : BTC/EUR et ETH/EUR.
- Données récentes : API publique Kraken.
- Données indépendantes T1/T2 2026 : archives OHLCVT officielles Kraken.
- Test principal prudent : `--fee 0.008` (0,80 %).
- Sensibilité : `--fee 0.004` (0,40 %).

La sensibilité maker ne signifie pas que tous les ordres obtiendront ce tarif.

## MoussaBaseline — stratégie active de plomberie en dry-run

La baseline permet de valider le pipeline mais **n'est pas validée pour le réel**.

### Données récentes

| Horizon | Fenêtre exploitable | Trades | Gagnants | Résultat 0,80 % |
|---|---:|---:|---:|---:|
| 15m | ~5 jours | 10 | 2 | -2,11 % |
| 1h | ~21 jours | 6 | 3 | -1,10 % |
| 4h | ~86 jours | 24 | 2 | -10,30 % |

### Archives officielles 1h

| Période | Trades | Résultat 0,80 % | Résultat 0,40 % | Marché |
|---|---:|---:|---:|---:|
| T1 2026 | 32 | -8,71 % | -3,97 % | ~-27 % |
| T2 2026 | 49 | -16,88 % | -9,41 % | ~-21 % |

Conclusion : baseline rejetée comme candidate de trading réel.

## MoussaTrendGuard — candidate laboratoire 1h

Candidate plus restrictive avec EMA200, ADX, RSI/volume et trailing stop.

### Résultats

| Période | Trades | Résultat 0,80 % | Résultat 0,40 % |
|---|---:|---:|---:|
| récent ~21 j | 4 | -0,08 % | +0,57 % |
| T1 2026 | 15 | -4,04 % | -1,67 % |
| T2 2026 | 15 | -5,70 % | -3,47 % |

Conclusion : amélioration nette face à la baseline, mais échec sur deux fenêtres
indépendantes. Candidate rejetée.

## MoussaRegimeTrend — candidate laboratoire 4h

Approche faible fréquence : tendance EMA50/EMA200 haussière, EMA200 montante,
pullback/récupération, ADX et trailing stop.

### Résultats

| Période | Trades | Résultat 0,80 % | Résultat 0,40 % |
|---|---:|---:|---:|
| T1 2026 | 0 | 0,00 % | 0,00 % |
| T2 2026 | 3 | -1,92 % | -1,45 % |
| récent ~86 j | 14 | -5,70 % | -2,27 % |

Conclusion : protection correcte en marché baissier T1, mais capture de tendance
insuffisante au T2 et sur la période récente. Candidate rejetée.

## Small/mid-cap momentum — recherche du 3 octobre 2026

Univers construit dynamiquement à partir des paires Kraken/EUR croisées avec les
capitalisations CoinGecko : rangs environ 60 à 180, volume Kraken 24 h >= 200 kEUR
et spread <= 35 bps. 20 paires ont été retenues pour le premier test 4h.

### MoussaSmallCapMomentum — breakout 4h

| Fenêtre | Trades | Résultat 0,80 % | Profit factor | Drawdown |
|---|---:|---:|---:|---:|
| 12 juil. → 25 août | 6 | -1,54 % | 0,63 | 1,81 % |
| 25 août → 2 oct. | 24 | +8,60 % | 1,65 | 3,61 % |
| Ensemble ~83 j | 30 | +7,06 % | 1,41 | 3,66 % |

Le résultat global est positif, mais la stratégie échoue sur la première fenêtre.
Elle est donc **prometteuse mais non validée**.

### Benchmark buy-and-hold de l'univers

| Fenêtre | Buy-and-hold équipondéré |
|---|---:|
| 12 juil. → 25 août | +15,56 % |
| 25 août → 2 oct. | +44,29 % |
| Ensemble | +58,67 % |

La stratégie réduit fortement le drawdown et l'exposition, mais sous-performe
largement l'univers haussier. Elle doit donc démontrer une meilleure stabilité
et une vraie valeur ajoutée ajustée du risque avant toute promotion.

### MoussaSmallCapPullback — rejetée

| Fenêtre | Trades | Résultat 0,80 % | Profit factor |
|---|---:|---:|---:|
| 12 juil. → 25 août | 8 | -6,41 % | 0,08 |
| 25 août → 2 oct. | 42 | -16,06 % | 0,45 |
| Ensemble | 50 | -22,47 % | 0,38 |

Conclusion : le pullback classique est rejeté. La piste de recherche reste le
momentum/breakout avec filtre de régime, liquidité et contrôle du risque.

## Interprétation

Les essais montrent plusieurs choses distinctes :

1. L'infrastructure fonctionne et les stratégies génèrent bien des signaux.
2. Les règles de trading testées n'ont pas encore d'avantage robuste après frais.

Le projet ne doit donc pas passer en réel. Le zéro trade observé juste après le
redémarrage n'était pas une panne ; mais l'absence de panne ne signifie pas que
la stratégie est rentable.

## Étape de recherche suivante

Ne plus modifier manuellement quelques seuils jusqu'à obtenir un backtest positif.
La suite doit utiliser un protocole reproductible :

1. Construire un benchmark cash / buy-and-hold / stratégies.
2. Définir à l'avance une famille de règles simples à faible turnover.
3. Utiliser une période de développement et une période de validation séparées.
4. Évaluer résultat net de frais, drawdown, profit factor, nombre de trades et
   stabilité entre BTC et ETH.
5. Rejeter toute candidate dépendant fortement d'un seul trimestre ou d'un seul
   niveau de frais.
6. Exécuter lookahead-analysis et recursive-analysis avant toute promotion.
7. Si une candidate passe, la tester d'abord plusieurs jours en dry-run Oracle.
8. Toute activation réelle reste une décision explicite de Moussa.

## Robustesse par actif — cycle du 3 octobre 2026, 01 h

Le résultat global positif de `MoussaSmallCapMomentum` est trop concentré pour
constituer une validation. Sur les 30 trades du test complet, 15 des 20 paires
ont été tradées : 8 ont contribué positivement et 7 négativement.

Surtout, ARB/EUR apporte +6,003 EUR sur un profit total de +7,064 EUR, soit
environ 85 % du gain. Sans ARB/EUR, le résultat résiduel n'est plus que
+1,061 EUR avant toute nouvelle pénalisation de slippage.

Conclusion : **candidate non robuste à ce stade**. Le prochain test doit imposer
une stabilité cross-section : aucune paire ne doit expliquer une part dominante
du P/L, et les résultats doivent rester acceptables en retirant successivement
les meilleurs contributeurs (leave-one-pair-out).


### MoussaSmallCapRegime - filtre ex ante

Filtre local defini avant test : EMA20 > EMA50 > EMA200, pente EMA200 sur 12 bougies > 1 %, ecart EMA50/EMA200 > 3 %. Les autres regles et les frais de 0,80 % restent inchanges.

| Fenetre | Trades | Resultat | Profit factor | Drawdown |
|---|---:|---:|---:|---:|
| 12 juil. au 25 aout | 3 | -3,14 % | 0,08 | 3,42 % |
| 25 aout au 2 oct. | 20 | +6,42 % | 1,59 | 4,06 % |
| Ensemble | 23 | +3,28 % | 1,23 | 4,18 % |

Conclusion : **candidate rejetee**. Le filtre reduit les trades mais n'ameliore pas la stabilite inter-fenetres. Retoucher les seuils sur ces memes donnees augmenterait le risque d'overfit.

Prochaine experience : filtre de regime independant base sur BTC/EUR et/ou la breadth de l'univers, defini ex ante, puis walk-forward sur des fenetres non utilisees.


### Cycle 06 h — leave-one-pair-out ARB

Test de robustesse de `MoussaSmallCapMomentum` sans ARB/EUR, frais 0,80 %.

| Fenêtre | Trades | Résultat | Profit factor | Drawdown |
|---|---:|---:|---:|---:|
| 12 juil. → 25 août | 6 | -1,54 % | 0,63 | 1,81 % |
| 25 août → 2 oct. | 21 | +2,60 % | 1,20 | 4,41 % |
| Ensemble | 27 | +1,06 % | 1,06 | 4,47 % |

Le benchmark buy-and-hold équipondéré des 19 actifs hors ARB reste à +56,67 %
sur l'ensemble. La candidate est donc **rejetée** : elle reste négative en
développement et son avantage global devient quasi nul quand son meilleur
contributeur est retiré.

Prochaine expérience préparée : régime indépendant BTC/EUR, sans modifier les
seuils de la candidate sur les données de validation. Cette variante ne doit pas
être considérée testée avant injection propre des données BTC informatives.


### Cycle 08 h — breadth altcoins indépendante

Nouvelle candidate `MoussaSmallCapBreadth` : breakout small/mid-cap 4h inchangé,
mais entrée autorisée seulement lorsque >=55 % de l'univers est au-dessus de son
EMA200 ; sortie de régime sous 40 %. Seuils définis avant test, frais 0,80 %.

| Fenêtre | Trades | Résultat | Profit factor | Drawdown |
|---|---:|---:|---:|---:|
| 12 juil. → 25 août | 4 | -1,53 % | 0,55 | 1,80 % |
| 25 août → 2 oct. | 24 | +8,60 % | 1,65 | 3,61 % |
| Ensemble | 28 | +7,07 % | 1,43 | 3,66 % |

Le filtre breadth élimine deux trades de la première fenêtre mais ne corrige pas
son résultat négatif ; la validation reste identique au momentum initial. Le gain
reste en outre dominé par ARB/EUR (+6,003 EUR sur +7,074 EUR, ~85 %).

Conclusion : **candidate rejetée**. Le filtre breadth tel que défini n'apporte pas
la stabilité inter-fenêtres ni la diversification exigées. Aucun ajustement du
seuil 55 % ne sera fait sur ces mêmes données afin d'éviter l'overfit.

Prochaine expérience : abandonner les variantes de filtre sur ce même échantillon.
Étendre l'historique small/mid-cap sur plusieurs régimes indépendants, puis tester
une règle figée en walk-forward avec coûts 0,8–1,2 %, leave-one-pair-out et
critère de concentration du P/L avant toute nouvelle qualification.

### Cycle 12 h 22 — validation historique indépendante T1/T2 2026

La règle `MoussaSmallCapMomentum` a été figée sans réoptimisation puis testée sur 12 paires EUR présentes dans les archives OHLCVT officielles Kraken T1/T2 2026 : ALGO, ARB, ATOM, CRV, FET, INJ, KAS, OP, POL, RENDER, XDC et ZRO. Les 220 premières bougies 4h servent uniquement au warm-up des indicateurs.

| Fenêtre indépendante | Frais | Trades | Résultat | Profit factor | Drawdown | Cash | Buy-and-hold équipondéré |
|---|---:|---:|---:|---:|---:|---:|---:|
| 6 fév. → 31 mars 2026 | 0,80 % | 4 | -1,58 % | 0,60 | 2,79 % | 0,00 % | -2,60 % |
| 7 mai → 30 juin 2026 | 0,80 % | 11 | -2,29 % | 0,71 | 6,71 % | 0,00 % | -21,02 % |
| 6 fév. → 31 mars 2026 | 1,20 % | 4 | -2,03 % | 0,54 | 3,10 % | 0,00 % | -2,60 % |
| 7 mai → 30 juin 2026 | 1,20 % | 11 | -3,22 % | 0,63 | 7,60 % | 0,00 % | -21,02 % |

Conclusion : **MoussaSmallCapMomentum est rejetée** dans sa forme actuelle. Elle limite les pertes face au buy-and-hold au T2 baissier, mais perd contre le cash sur les deux fenêtres historiques et PF reste < 1. Les coûts renforcés dégradent encore le résultat. Le +7 % récent ne constitue donc pas une validation robuste.

La variante `MoussaSmallCapPullback` reste également rejetée : T1 = -0,22 %, 9 trades, PF 0,95, DD 2,85 % ; T2 = -4,96 %, 13 trades, PF 0,48, DD 6,63 % avec frais 0,80 %.

Prochaine expérience : ne pas retoucher ces seuils. Construire une nouvelle famille simple de tendance relative/cross-section définie ex ante, avec sélection de liquidité/spread au moment de chaque fenêtre pour réduire le biais de survivance, puis walk-forward T1 → T2 → période récente. Exiger PF > 1 sur plusieurs fenêtres, résultat supérieur au cash sur plusieurs régimes et P/L non dominé par un seul actif avant de parler seulement de candidate dry-run.
