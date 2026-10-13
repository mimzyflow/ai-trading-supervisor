# Compte témoin DRY-RUN avec stops (simulation uniquement)

Objectif : comparer, à frais, univers et capital identiques, l'expérience
actuelle sans stops (`MoussaMarketRoom`, politique `market-room-100eur-20261009`)
à une variante protégée. **Aucun ordre réel, aucune clé d'échange.**

| Élément | Expérience actuelle | Témoin |
|---|---|---|
| Stratégie | `MoussaMarketRoom` | `MoussaControlStops` (dérivée de `MoussaBaseline`) |
| Base | `trades-market-room-100eur-20261009.dryrun.sqlite` | `trades-control-stops-20261013.dryrun.sqlite` |
| Volume Docker | `ai-trading-freqtrade-runtime` | `ai-trading-freqtrade-control-runtime` |
| Journal Freqtrade | `/freqtrade/runtime/freqtrade.log` | `/freqtrade/runtime/control/freqtrade-control.log` |
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

## Déploiement Oracle manuel (après relecture de Manager)
```
docker compose -p ai-trading-control -f docker-compose.control.yml config  # vérifier DRY_RUN / clés vides
# Préparer le volume témoin (une fois ; idempotent) : répertoire du journal dédié, propriétaire ftuser
docker compose -p ai-trading-control -f docker-compose.control.yml run --rm --no-deps -T --user 0:0 --entrypoint sh freqtrade-control \
  -c 'mkdir -p /freqtrade/runtime/control && chown 1000:1000 /freqtrade/runtime && chown -R 1000:1000 /freqtrade/runtime/control'
docker compose -p ai-trading-control -f docker-compose.control.yml up -d
```

### Journal dédié (correctif boucle de redémarrage 2026-10-13)
Le témoin écrivait `--logfile /freqtrade/runtime/freqtrade.log`, même chemin
que le bot principal, et redémarrait en boucle avec
`PermissionError: /freqtrade/runtime/freqtrade.log` : le volume
`ai-trading-freqtrade-control-runtime` est d'abord créé vide (propriété root)
par le montage lecture seule du superviseur (`/app/control-runtime`), et
`ftuser` ne pouvait pas y écrire. Désormais :
- journal dédié `/freqtrade/runtime/control/freqtrade-control.log` ;
- `install_release.py::prepare_control_runtime` crée ce répertoire et attribue
  le volume témoin à `ftuser` (1000:1000) via un conteneur ponctuel avant `up`
  (volume témoin uniquement ; `ai-trading-freqtrade-runtime` jamais touché) ;
- `check_simulation.py` refuse un Compose témoin sans ce journal ou contenant
  le chemin du journal principal ; test `ControlLogfileTests`.
La base reste `/freqtrade/runtime/trades-control-stops-20261013.dryrun.sqlite`
(lue par le superviseur sous `/app/control-runtime`). Le bot principal, son
volume et son journal sont inchangés.
Non encore validé dans l'image Freqtrade : lancer d'abord
`freqtrade list-strategies` / un backtest court avec `MoussaControlStops`.
Le superviseur lit cette base via la PR #8 (« trading_status enrichi »,
variable `EXTRA_ACCOUNTS`, volume monté en lecture seule).

## Arrêt portefeuille -5 % : réalisé + latent de toutes les positions
`MoussaControlStops._halted` additionne la perte réalisée (trades clôturés)
et le P&L latent de **toutes** les positions ouvertes
(`control_guards.unrealized_pnl`), chacune valorisée à la dernière clôture
analysée de sa paire (ou au prix courant pour la paire évaluée ; à défaut de
prix, au prix d'entrée, ce qui compte les frais). Le même calcul est utilisé
dans `confirm_trade_entry` (aucune nouvelle entrée si l'arrêt est atteint) et
dans `custom_exit` (liquidation simulée des positions).

## Pause 3 pertes (témoin) ≠ critère 10 pertes (validation, PR #9)
| | Pause 3 pertes (ce compte) | Critère 10 pertes (VALIDATION_CRITERIA, #9) |
|---|---|---|
| Nature | protection **dans** la stratégie témoin | critère d'**évaluation** de l'expérience |
| Effet | bloque les nouvelles entrées 24 h, puis reprise automatique | arrête/invalide l'expérience ; décision humaine requise |
| Portée | `MoussaControlStops` uniquement | expérience suivie (`MoussaMarketRoom`) |
| Paramètre | `CONTROL_MAX_CONSECUTIVE_LOSSES` (défaut 3), `CONTROL_LOSS_PAUSE_HOURS` (24) | `config/validation-thresholds.json` → `stop.max_consecutive_losses` = 10 |

Les deux ne se substituent pas : la pause est temporaire et ne remet pas à
zéro le compteur du critère de validation.

## Coût net d'un stop -3 % avec frais 0,8 % par côté
Frais Kraken simulés : 0,8 % à l'entrée + 0,8 % à la sortie ≈ **1,6 %
aller-retour**. Un stop déclenché à -3 % de prix coûte donc environ
**-4,6 % de la mise nette** (≈ -0,46 EUR sur une mise de 10 EUR), hors
glissement. Il faut ~+1,6 % de hausse pour simplement couvrir les frais ;
le seuil de -5 % du portefeuille (5 EUR) correspond à environ 11 stops nets
sur 10 EUR, ou moins si plusieurs positions sont en perte latente.

## CI
`.github/workflows/ci.yml` exécute `scripts/check_simulation.py` (configs
statiques, sans base Oracle ni Docker) puis `pytest`. La stratégie témoin est
testée avec des modules Freqtrade simulés (`tests/test_control_strategy.py`).

## Déploiement
`scripts/install_release.py` vérifie aussi `docker-compose.control.yml`
(préflight : dry-run, clés vides, `--dry-run` en commande) **avant** toute
modification, puis démarre le témoin (`-p ai-trading-control`, service
`freqtrade-control` seulement) après que la release principale est saine.
Un échec du témoin est signalé (`"control"` dans la sortie JSON) sans
rollback ni effet sur `freqtrade`/`supervisor`.
