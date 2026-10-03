# Protocole de recherche et limites de validation

Toutes les stratégies existantes restent `research_only`. La validation technique
du pipeline ne valide jamais la rentabilité. Aucun passage en réel automatique.

## Coûts et versions

- Freqtrade Oracle figé à 2026.9 et au digest de l'image effectivement contrôlée.
- Les nouveaux trades simulés utilisent `fee=0.008` : 0,80 % **par côté**, soit
  environ 1,60 % aller-retour, avant spread et glissement. Stress : 0.012 par côté.
- Les anciens trades conservés peuvent utiliser un tarif différent. Ne pas
  réécrire leur historique ni assimiler un changement de frais à un gain.
- Le Mac Freqtrade 2026.6 reste un environnement de développement. Le runner
  utilise l'image Oracle figée pour comparer des résultats du même moteur.

## Expériences reproductibles

`scripts/research_run.py` accepte uniquement des backtests spot EUR, conserve
SHA-256 du code/config/données, dates, paires, image et frais par côté, active
les protections et désactive le cache. Il vérifie les bougies avant le backtest.
Les sorties restent dans `research_results/`, ignorées par Git.

Exemple sur Oracle, avec les données réellement disponibles :

```sh
python3 scripts/research_run.py --data backtests/q1-1h --strategy MoussaBaseline --timeframe 1h --timerange 20260201-20260401 --pairs BTC/EUR ETH/EUR
```

Le manifest reste `real_money_eligible=false`, même si le test réussit.
Un profit positif isolé n'est jamais une décision de promotion.

## Prochaine candidate

1. Définir une seule famille simple de règles et figer les seuils avant le test.
2. Allonger l'historique sur plusieurs régimes ; conserver assez de données
   avant chaque fenêtre pour initialiser les indicateurs sans amputer la fenêtre.
3. Réserver une période finale jamais utilisée dans la conception des variantes.
   T1/T2 2026 et juillet-octobre déjà étudiés deviennent exploratoires.
4. Reconstruire l'univers disponible à chaque date. Les données actuelles de
   capitalisation/volume/spread ne certifient pas une appartenance historique.
   Inclure les actifs disparus et documenter les périodes sans données.
5. Comparer cash, panier passif et stratégie avec frais et allocation comparables.
   Le benchmark 40 % + cash est une référence d'allocation, pas une égalisation
   exacte du risque ni une garantie de faisabilité avec les minimums d'ordres.
6. Contrôler stabilité, nombre de trades, concentration, retrait successif des
   meilleurs contributeurs, stress des coûts et perte maximale.
7. Vérifier lookahead-analysis et recursive-analysis, puis comparer backtest
   et plusieurs semaines de dry-run sans modifier les seuils sur les résultats.
8. Décision humaine explicite avant tout nouveau périmètre ou argent réel.

Les scripts enregistrent explicitement l'univers comme snapshot actuel non
historique. Les nouveaux téléchargements excluent la bougie Kraken inachevée.
Un historique OHLCV seul ne permet pas de recréer les spreads passés : conserver
des observations de carnet/spread pour les futures périodes et signaler cette
limite pour les anciennes. Ne pas inventer les données manquantes.

## Supervision

L'état moteur est lu via des GET bornés et allowlistés. API indisponible => état
inconnu ; base illisible => métriques indisponibles ; rapport >15 minutes => périmé.
Les archives horaires sont distinctes du heartbeat local toutes les 5 minutes.
Les erreurs de publication GitHub sont persistées et reprises avec backoff.
Sans jeton dédié, publication `not_configured`, jamais faux succès. Un rapport
GitHub horaire est un historique daté, pas un état en direct après 15 minutes.

Sources : documentation officielle Freqtrade backtesting, configuration,
lookahead-analysis et recursive-analysis ; Kraken API OHLC et barème de frais.
