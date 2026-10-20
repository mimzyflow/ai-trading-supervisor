# Coûts réalistes, tendance quotidienne et contrôles de biais — 21/10/2026

Simulation uniquement. Aucun ordre réel, aucune clé, aucun déploiement Oracle.
Branche de travail, non fusionnée ; à valider par Moussa.

## 1. Règle « 5 % = alerte seule » et `risk_halt_preserved`

- `research_lab/equity_paper.advance(..., halt_action='alert_only')` est le défaut.
  Un franchissement du seuil enregistre `halted=True`, `halt_reason`,
  `risk_halt_preserved=True` et une entrée `risk_alerts` (`action: notify_only`).
  Aucune position n'est vendue à cause du seuil ; les sorties normales de la
  stratégie continuent. L'état halt survit aux redémarrages et aux reprises.
- `halt_action='liquidate'` conserve l'ancien comportement, uniquement sur
  demande explicite (tests historiques conservés).
- Le worker Oracle appelait déjà le portefeuille papier avec `max_drawdown=None` ;
  il n'est pas modifié par cette branche. À vérifier : `research_lab/worker.py`
  applique `loss_limit=.05` **seulement si aucune politique n'est lue** (repli),
  ce qui peut conduire à l'arrêt vérifié du conteneur DRY-RUN. Non modifié ici ;
  décision à prendre par Moussa.
- Tests : `tests/test_risk_halt_preserved.py`.

## 2. Modèle de frais (`research_lab/cost_model.py`)

| Scénario | Frais/côté | Glissement/côté | Aller-retour |
|---|---:|---:|---:|
| maker_realistic (défaut recherche) | 0,25 % | 0,10 % | 0,70 % |
| taker | 0,40 % | 0,15 % | 1,10 % |
| legacy_degraded (ancien 0,8 %) | 0,80 % | 0,10 % | 1,80 % |
| stress | 1,20 % | 0,25 % | 2,90 % |

Hypothèses, pas des tarifs Kraken vérifiés. `freqtrade_fee()` replie le
glissement dans `--fee`. `research.costs()` (inclus dans l'empreinte des plans
gelés) n'est **pas** modifié, pour ne pas invalider les plans existants.

## 3. Stratégie `MoussaDailyTrend`

BTC/EUR et ETH/EUR, bougies quotidiennes. Entrée : clôture > SMA100 × 1,02 et
SMA100 montante sur 10 jours. Sortie : clôture < SMA100 × 0,98. Pas de stop
forcé, pas de ROI, 20 EUR max par position, `dry_run` exigé. Règles fixées
avant tout test, aucune optimisation. Config : `user_data/config.daily-trend.research.json`.

### Backtest exploratoire (box, Freqtrade 2026.9)

Données : API publique Kraken OHLC 1d (720 bougies, 30/10/2024 → 19/10/2026),
période testée 01/03/2025 → 19/10/2026 après chauffe. 100 EUR fictifs, 2 × 20 EUR.

| `--fee` (frais + glissement/côté) | Trades | Profit | PF | Marché BTC/ETH |
|---|---:|---:|---:|---:|
| 0,35 % (maker_realistic) | 8 | +4,93 % | 1,80 | −5,90 % |
| 0,90 % (legacy_degraded) | 8 | +3,13 % | 1,43 | −5,90 % |
| 1,45 % (stress) | 8 | +1,34 % | 1,16 | −5,90 % |

Sous-périodes à 0,35 % : 03→12/2025 : +4,83 % (5 trades, marché +3,93 %) ;
01→10/2026 : +0,09 % (3 trades, marché −9,69 %). Drawdown sur trades clôturés
3,70 % ; drawdown du solde marqué au marché 12,27 % (14,3 EUR).

Limites : 8 trades, source unique, période courte déjà vue, exposition maximale
40 %. **Non validée.** Étape suivante : dry-run prospectif.

### Biais

`scripts/run_bias_checks.py --strategy MoussaDailyTrend` (box, runner local) :
lookahead-analysis « no bias detected » (6 signaux) ; recursive-analysis : aucune
variance d'indicateur avec 120/240/400 bougies de chauffe. Les V3 sont listées
dans le script (runner `docker`, réseau coupé) mais n'ont pas été lancées faute
de données 1h/4h suffisantes sur la box.

## 4. Filtre V3 (`research_lab/v3_challengers.py`)

Nouveaux motifs de rejet : `stressed_costs_not_positive`,
`leave_one_pair_out_not_positive`, `net_pnl_concentration` (> 50 % du profit
net sur un actif) en plus de `positive_pnl_concentration` (> 65 %). Le résultat
publie aussi le scénario `legacy_degraded`. Paramètres des challengers inchangés.
L'empreinte V3 change : le cache quotidien sera recalculé au prochain cycle.
