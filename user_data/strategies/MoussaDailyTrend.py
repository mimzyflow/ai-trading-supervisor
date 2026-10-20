"""BTC/ETH daily low-turnover trend filter. DRY-RUN / backtest research only.

Règles figées avant test (aucune optimisation sur résultats) :
- bougies quotidiennes ; entrée si clôture > SMA100 * (1 + 2 %) et SMA100 montante sur 10 jours ;
- sortie si clôture < SMA100 * (1 - 2 %) (bande d'hystérésis pour limiter les allers-retours) ;
- pas de stop-loss forcé (règle du projet : 5 % = alerte), pas de ROI fixe ;
- un ordre au plus par paire, 20 EUR maximum, Kraken spot EUR, jamais de clé.
"""
from pandas import DataFrame
from freqtrade.strategy import IStrategy

DAILY_TREND_PAIRS = ("BTC/EUR", "XBT/EUR", "ETH/EUR")


class MoussaDailyTrend(IStrategy):
    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "1d"
    startup_candle_count = 120
    process_only_new_candles = True
    minimal_roi = {"0": 100.0}
    # Le framework exige un stoploss numérique ; -100 % = aucune vente forcée.
    stoploss = -1.0
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False

    sma_period = 100
    slope_lookback = 10
    band = 0.02

    def bot_start(self, **kwargs):
        if self.config.get("dry_run") is not True or self.config.get("trading_mode", "spot") != "spot":
            raise ValueError("daily_trend_strategy_is_simulation_only")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma"] = dataframe["close"].rolling(self.sma_period).mean()
        dataframe["sma_slope"] = dataframe["sma"] - dataframe["sma"].shift(self.slope_lookback)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if metadata.get("pair") not in DAILY_TREND_PAIRS:
            return dataframe
        entry = (
            (dataframe["close"] > dataframe["sma"] * (1 + self.band))
            & (dataframe["sma_slope"] > 0)
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[entry, ["enter_long", "enter_tag"]] = (1, "daily_trend")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_signal = (dataframe["close"] < dataframe["sma"] * (1 - self.band)) & (dataframe["volume"] > 0)
        dataframe.loc[exit_signal, ["exit_long", "exit_tag"]] = (1, "daily_trend_exit")
        return dataframe

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        return min(max_stake, 20.0, proposed_stake)
