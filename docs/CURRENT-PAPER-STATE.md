# Current paper-trading state

Last verified: 2026-10-05 15:27 UTC.

## Crypto / Freqtrade

Oracle runs Freqtrade in DRY-RUN only. The V2 runtime uses `max_open_trades=-1`, a 10 EUR simulated stake, a 90% tradable-balance ratio, and the 12-pair EUR universe XBT, XRP, SUI, ETH, SOL, ADA, NEAR, ZEC, QNT, LTC, TAO and LINK. Position count is not a target: simulated capital, exchange minimums, liquidity, fees and portfolio risk remain the practical constraints.

The pre-V2 baseline history must not be attributed to V2: 8 closed trades, 8 losses, 100 EUR to 97.391 EUR (-2.609%). Forward V2 evidence starts after the V2 deployment.

## Equities / brokerless prospective paper

The equities engine now has a persistent brokerless paper portfolio on Oracle. It requires no brokerage account, credentials or order API and cannot place real orders.

Initial forward state after the initialization fix:
- 100 USD fictional initial cash
- 100 USD equity
- 0 positions
- 0 trades
- 0% drawdown
- `real_money_eligible=false`

Current universe: SOFI, U, PLUG, OPEN, FUBO, NIO, MARA and RIOT.

The public market-data collector runs before the research worker. It accepts only already-closed US regular sessions; historical bars are available to calculate indicators but are not replayed into the prospective portfolio. A first implementation incorrectly replayed 499 historical sessions and showed 92.646 USD / -7.354%; that result was rejected and the state was reset. Commit `b719b1d` fixes initialization so the portfolio starts after the latest known closed session.

The historical research gate currently has 499 common sessions versus its 600-session development requirement. This does not convert the forward paper portfolio into a broker or make it eligible for real money.

## Relevant V2 commits

- `6fcbb77` remove arbitrary research position cap
- `4ca8a92` enable unbounded Freqtrade dry-run slots
- `8362ae5` persistent brokerless equity paper portfolio
- `34be7f4` feed equity paper with closed public market data
- `b719b1d` start equity paper only from deployment forward

Deployment of `b719b1d` passed 128 tests with 4 optional skips. Both Oracle containers were healthy and the research timer was active at verification.

## Safety boundary

No real-money trading, funding, exchange/broker key installation or broker order activation is authorized by this state. Kraken classic-equity API compatibility for France/EEA remains unconfirmed; a brokerage integration is deliberately deferred until the strategy has useful paper evidence.
