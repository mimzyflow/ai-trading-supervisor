# Strategy V3 research — 6 October 2026

Simulation and research only. This revision cannot place broker orders, inject exchange credentials, fund an account, or switch Freqtrade out of dry-run.

## Control / challenger design

The deployed V2 Freqtrade strategy remains the control. V3 does not overwrite its history or silently replace it.

Three deterministic challengers are predeclared:

- `MoussaV3RegimeMomentum`: 1h trend/regime + breakout + ADX/RSI/ATR/volume filters.
- `MoussaV3TripleBarrier`: 1h breakout with stop-loss, take-profit, time limit and trailing stop.
- `MoussaV3SlowBreakout`: 4h lower-turnover trend/breakout control.

The research simulator implements the same exit concepts conservatively. Stop barriers are evaluated before profit barriers when the OHLC candle cannot reveal intrabar path.

## Portfolio and risk

Crypto challengers retain the 5% portfolio drawdown ceiling and add Freqtrade protections (cooldown, stop-loss guard, equity-based maximum drawdown; the triple-barrier variant also uses low-profit-pair locking).

The brokerless equity V2 portfolio remains unchanged as a control. Each V3 equity challenger receives its own new forward-only state file and therefore never replays the historical research sessions into prospective equity.

The V3 equity sizing layer applies:

- maximum gross exposure: 70%;
- maximum single position weight: 20%;
- rolling correlation refusal at 0.85 against existing positions;
- volatility scaling above a 2.5% daily target;
- 30% paper-cash reserve in the worker.
## Statistical promotion gate

No strategy is called good because of a few profitable trades. A deterministic challenger can only become `research_promising` if all gates pass:

- at least 30 closed trades;
- positive return and better than the selected benchmark;
- profit factor at least 1.20;
- maximum drawdown no more than 5%;
- deflated-Sharpe probability at least 0.90;
- PBO no more than 0.50 when estimable;
- Monte-Carlo loss probability no more than 35%;
- no negative independent chronological test window;
- no single asset contributing more than 65% of positive P/L.

Passing this gate means only eligibility for a new forward shadow experiment. It never means live eligibility.

## Native Freqtrade audits

`scripts/freqtrade_strategy_audit.py` builds bounded offline commands for:

- `lookahead-analysis`;
- `recursive-analysis`.

The commands use the existing digest-pinned Freqtrade 2026.9 image, `--network none`, dry-run=true, blank exchange keys and read-only data/config/strategy mounts. Only the three predeclared V3 strategies and EUR pairs are accepted.

Official rationale:
- Freqtrade lookahead analysis: https://docs.freqtrade.io/en/latest/lookahead-analysis/
- Freqtrade recursive analysis: https://docs.freqtrade.io/en/stable/recursive-analysis/
- Freqtrade protections: https://docs.freqtrade.io/en/2026.9/plugins/
## FreqAI LightGBM shadow

FreqAI is scaffolded but deliberately not activated yet.

`research_lab/freqai_shadow.py` requires a FreqAI Docker image reference containing an immutable `@sha256:<digest>`. A mutable tag such as `stable_freqai` is rejected. Once a compatible digest is independently pinned, the status becomes `ready_for_offline_backtest`, not live-ready.

The planned FreqAI research configuration uses:

- `LightGBMRegressor`;
- rolling 30-day train / 7-day backtest periods;
- 12-hour retrain interval for future dry-run research;
- 15m, 1h and 4h features;
- BTC/ETH correlation features;
- time-ordered 25% test split with shuffle disabled.

Official FreqAI references:
- https://docs.freqtrade.io/en/2026.9/freqai/
- https://docs.freqtrade.io/en/2026.9/freqai-running/
- https://docs.freqtrade.io/en/2026.9/freqai-configuration/

## Telemetry

The supervisor now emits a separate `v2` section with a fixed deployment boundary `2026-10-05T15:03:00+00:00`. V2 closed trades, wins/losses, realized P/L and profit factor are computed from trades closing after that boundary. The old eight-trade MoussaBaseline history is explicitly excluded from those V2 figures.

The autonomy report also exposes:
- V3 deterministic challenger state;
- FreqAI shadow readiness;
- up to three V3 equity forward-shadow summaries.

No secret is included in these reports.
## Deployment rules

Deployment must preserve:

- the existing Freqtrade dry-run SQLite database;
- the existing V2 paper state;
- all historical research evidence and consumed holdouts;
- `dry_run=true`;
- Kraken spot EUR only;
- empty exchange credentials in the active simulation environment.

The installer already backs up release files, validates the resolved private Compose configuration before activation, verifies both containers are healthy, validates dry-run/key absence after activation, and rolls code back without deleting runtime history on failure.

The V3 branch must pass the full test suite before deployment. The active Freqtrade strategy remains `MoussaBaseline`; V3 challengers are research/shadow artifacts only.

## What this revision does not claim

It does not claim V3 is profitable. It does not reinterpret the invalid 92.646 USD equity replay as prospective performance. It does not erase the old crypto baseline. It does not optimize parameters after seeing a holdout. It does not activate any broker or live exchange order path.
