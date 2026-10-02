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
