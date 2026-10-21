# Rotation lente mensuelle (21/10/2026) — SIMULATION UNIQUEMENT

Règle : 1re séance de chaque mois, décision à la clôture, exécution à l'ouverture suivante.
Parmi les actifs au-dessus de leur SMA200 quotidienne, on garde celui au meilleur momentum 90 j ; sinon cash.
- Crypto : BTC/EUR vs ETH/EUR. Recherche : `research_lab/slow_trend.py` ; Freqtrade : `MoussaMonthlyRotation` (nouvelle stratégie, dry-run, stake ≤ 20 EUR, stoploss −1 = aucun stop forcé).
- Actions papier : SCHB (marché US total, ~29,5 USD) contre cash, parts entières. SPY (~769), VT (~159), URTH (~208) ne sont pas achetables avec 100 USD.
- Alertes drawdown 5 % et 10 % : `notify_only`, aucune vente.

## Défaut de taille d'ordre papier (non corrigé dans le runtime)
`research_lab/worker.py` appelle `advance_equity_paper(..., allocation=10 * usd_per_eur)` (~11,6 USD) avec la commission minimale par défaut de 1 USD :
prix maximal achetable = (11,6 − 1)/1,001 ≈ 10,6 USD. Tout ETF large est donc bloqué.
Non modifié (runtime Oracle / budget hors périmètre). Correctifs possibles, à décider par Moussa : `min_commission=0` (frais proportionnels) et allocation ≥ prix d'une part.
Le nouveau simulateur utilise `min_commission=0`, 0,25 % + 0,10 % par côté.

## Reproduire
`python3 scripts/run_slow_trend_backtest.py --btc BTC-EUR.bars.json --eth ETH-EUR.bars.json --etf SCHB.bars.json --etf-name SCHB --start 2022-01-01 --output research_results/slow-trend.json`
(données Yahoo chart v8, quotidiennes ; prix SCHB dé-ajustés des splits 2:1 du 11/03/2022 et 3:1 du 11/10/2024).

## Limites
Source unique Yahoo (pas Kraken : seulement 720 bougies disponibles) ; dividendes ignorés ; biais du survivant (BTC/ETH, ETF US choisis a posteriori) ;
coûts supposés ; parts entières → cash résiduel important (ex. 1 part à 53 USD fin 2023) ; Freqtrade `lookahead-analysis` signale 1 entrée sur 10 (BTC 02/02/2023)
sans indicateur biaisé, alors qu'un test de troncature indépendant donne des signaux identiques : drapeau non résolu, à revoir ; `recursive-analysis` : aucune variance.
`run_bias_checks.py` marque « passed » sur les seuls codes de sortie.
