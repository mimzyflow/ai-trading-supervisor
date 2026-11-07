# Research status and independent-review brief (2026-11-07)

**Status: suspended. No live execution.** This is an archived research
prototype, not a profitable, production-ready trading system. The production
Oracle jobs and simulation-only containers were disabled on 2026-11-07.
A private cold-state snapshot was retained outside this public repository.

## Last observed paper results

Figures below are from the Oracle latest.json report generated on
2026-11-07 at 00:43:11 UTC. These are *simulated*, not audited brokerage
results. Different paper portfolios must not be aggregated.

| Research stream | Observation |
|---|---|
| Crypto Freqtrade MoussaMarketRoom | 100 EUR initial, 77.8906 EUR remaining, -22.2718% total return, 138 closed trades, 9 wins, 129 losses, realized P&L -22.1106 EUR, unrealized -0.1612 EUR |
| Crypto friction | 20.8527 EUR fees paid over the observed experiment; profit factor 0.0314 |
| Crypto validation | No candidate passed development; all three V3 backtests rejected |
| Equity slow-trend SCHB paper account | 100 EUR initial funding; 97.2399 EUR approximate converted equity (-2.7601%); one open position, no closed trades |
| Other equity paper accounts | No closed trades; insufficient historical development data |
| TradingAgents market room | Advisory only; on 2026-11-06 both latest AI analyses had failed and were in fallback; no proof of added performance |

The crypto strategy uses high turnover relative to its small paper
portfolio, with severe net losses. A functioning simulation engine is
**not evidence of predictive edge**.

## Would 1,000 EUR improve the results?

This cannot be inferred from the observed 100 EUR simulation.
A larger balance may reduce the relative effect of **fixed** commissions,
minimum order sizes and integer share constraints, or allow more diversified
positions. It does **not** repair a losing signal. Under fully proportional
percentage-based fees and positions, scaling every trade and the starting
capital by 10 would leave percentage returns similar before capacity and
slippage effects. Conversely, keeping the original fixed 10 EUR order sizes
would increase idle cash and alter percentage returns without proving a
profitable approach. Only a matched, point-in-time reproducible simulation
with *identical dates/markets*, documented sizing and realistic costs can
evaluate this counterfactual.

## Contributions sought

1. Reproducible, cost-aware paper backtests with point-in-time data,
   no look-ahead or survivorship bias and a proper holdout.
2. Fair benchmarking against cash and a suitable passive benchmark in
   matching currencies, dates and costs.
3. Robust risk management with position and portfolio limits,
   scenario/stress and outage tests.
4. Evidence-led evaluation of 100 vs 1,000 EUR funding with fixed and
   proportional sizing, minimum order sizes and realistic exchange fees.
5. Simpler analysis replacing redundant agent orchestration, with
   quantified incremental impact of any AI signal.

## Safety and maintenance constraints

- Paper research only; do not add credentials or enable real-money orders.
- No auto-modification of risk limits or self-replicating live bots.
- Never commit account identifiers, balances, authentication material,
  runtime files, or private server data.
- Previously documented server paths, deployment methods and simulation
  settings are historical context. They are not current operational instructions.
- Reopening requires prospective evidence, independent tests and
  explicit owner authorization. Historical profits alone are insufficient.

See [CONTRIBUTING.md](../CONTRIBUTING.md).
