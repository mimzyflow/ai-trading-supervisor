# Backtests et validation des stratégies

Dernière mise à jour : 2026-10-03.

## Principe

Ce dossier de recherche ne modifie jamais automatiquement la stratégie active.
Une stratégie candidate doit rester en laboratoire tant qu'elle n'a pas été
testée sur plusieurs fenêtres et avec des frais réalistes.

Le bot Oracle reste en `dry_run=true`.

## Frais retenus

Les tests prudents utilisent `--fee 0.008` (0,80 % par transaction),
correspondant au niveau taker de départ Kraken observé en octobre 2026.
Une sensibilité à 0,40 % est parfois calculée pour illustrer un scénario maker,
mais elle ne doit pas être interprétée comme un coût garanti.

## MoussaBaseline

Données publiques Kraken OHLCV récentes, BTC/EUR et ETH/EUR.

| Horizon | Fenêtre exploitable | Trades | Gagnants | Résultat |
|---|---:|---:|---:|---:|
| 15m | ~5 jours | 10 | 2 | -2,11 % |
| 1h | ~21 jours | 6 | 3 | -1,10 % |
| 4h | ~86 jours | 24 | 2 | -10,30 % |

Conclusion : la baseline sert de témoin mais ne satisfait pas les critères
minimaux pour envisager le réel.

## MoussaTrendGuard (candidate de laboratoire)

La candidate ajoute notamment une tendance EMA 200, ADX, filtre RSI/volume,
un rythme 1h et un trailing stop. Elle n'est pas déployée sur Oracle.

Résultats préliminaires :

| Horizon / frais | Trades | Gagnants | Résultat | Profit factor |
|---|---:|---:|---:|---:|
| 1h / 0,80 % | 4 | 2 | -0,08 % | 0,90 |
| 1h / 0,40 % | 4 | 2 | +0,57 % | 2,16 |
| 4h / 0,80 % | 13 | 4 | -3,31 % | 0,41 |

La fenêtre 1h est nettement meilleure que la baseline mais quatre trades sont
insuffisants pour conclure. Le 4h reste mauvais. Aucune promotion automatique.

## Validation suivante

1. Utiliser les archives OHLCVT officielles Kraken du T2 2026.
2. Tester baseline et candidate sur une période indépendante.
3. Comparer frais 0,80 % et 0,40 % comme analyse de sensibilité.
4. Lancer les contrôles lookahead / recursive lorsque la candidate est
   suffisamment robuste.
5. Ne modifier la stratégie dry-run Oracle qu'après résultats cohérents sur
   plusieurs fenêtres.
6. Le passage en réel exige toujours une décision explicite de Moussa.
