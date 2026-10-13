# Compte témoin DRY-RUN avec stops (simulation uniquement)

Objectif : comparer, à frais, univers et capital identiques, l'expérience
actuelle sans stops (`MoussaMarketRoom`, politique `market-room-100eur-20261009`)
à une variante protégée. **Aucun ordre réel, aucune clé d'échange.**

| Élément | Expérience actuelle | Témoin |
|---|---|---|
| Stratégie | `MoussaMarketRoom` | `MoussaControlStops` (dérivée de `MoussaBaseline`) |
| Base | `trades-market-room-100eur-20261009.dryrun.sqlite` | `trades-control-stops-20261013.dryrun.sqlite` |
| Volume Docker | `ai-trading-freqtrade-runtime` | `ai-trading-freqtrade-control-runtime` |
| Port API local | 8080 | 8081 |
| policy_id | `market-room-100eur-20261009` | `control-stops-20261013` |
| Capital / frais | 100 EUR / 0,8 % par côté | 100 EUR / 0,8 % par côté |
| Stop par position | aucun (-100 %) | -3 % (`CONTROL_POSITION_STOP`) |
| Arrêt portefeuille | aucun | persistant à -5 % du capital initial + `MaxDrawdown` |
| Pertes consécutives | aucune coupure | pause 24 h après N pertes (défaut 3, `CONTROL_MAX_CONSECUTIVE_LOSSES`) + `StoplossGuard` |

Différence assumée : le témoin n'utilise pas l'avis de la salle des marchés
(mise fixe 10 EUR), afin d'isoler l'effet des stops sur la stratégie de base.

## Ce qui n'est pas modifié
`docker-compose.yml`, le service `freqtrade`, `MoussaMarketRoom`,
`supervisor/paper_policy.py` (`read_policy`) et `simulation-policy.json`.
Le témoin est dans `docker-compose.control.yml`, projet Compose séparé.

## Garde-fous de simulation
- `--dry-run` en ligne de commande, `FREQTRADE__DRY_RUN=true`, clés vides.
- `bot_start` refuse de démarrer hors dry-run/spot ou avec une clé
  (`supervisor/control_guards.py::require_simulation`).
- L'arrêt portefeuille est recalculé depuis la base : il survit au redémarrage.

## Déploiement Oracle (manuel, après relecture de Manager)
```
docker compose -p ai-trading-control -f docker-compose.control.yml config  # vérifier DRY_RUN / clés vides
docker compose -p ai-trading-control -f docker-compose.control.yml up -d
```
Non encore validé dans l'image Freqtrade : lancer d'abord
`freqtrade list-strategies` / un backtest court avec `MoussaControlStops`.
Le superviseur ne lit pas encore cette base : voir la PR « trading_status enrichi »
(variable `EXTRA_ACCOUNTS`).
