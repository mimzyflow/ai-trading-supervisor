from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import IStrategy


class MoussaRegimeTrend(IStrategy):
    """Low-frequency long-only regime strategy for spot dry-run research."""

    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "4h"
    startup_candle_count = 220
    process_only_new_candles = True

    minimal_roi = {
        "0": 0.10,
        "1440": 0.07,
        "4320": 0.04,
    }
    stoploss = -0.06
    trailing_stop = True
    trailing_stop_positive = 0.025
    trailing_stop_positive_offset = 0.055
    trailing_only_offset_is_reached = True
    use_exit_signal = True

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 3},
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 42,
                "trade_limit": 2,
                "stop_duration_candles": 18,
                "only_per_pair": False,
            },
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["vol_mean"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pullback_recovery = (
            (dataframe["close"] > dataframe["ema20"])
            & (dataframe["close"].shift(1) <= dataframe["ema20"].shift(1))
        )
        regime = (
            (dataframe["ema50"] > dataframe["ema200"])
            & (dataframe["ema200"] > dataframe["ema200"].shift(12))
            & (dataframe["close"] > dataframe["ema200"] * 1.01)
        )
        entry = (
            regime
            & pullback_recovery
            & (dataframe["rsi"] > 50)
            & (dataframe["rsi"] < 67)
            & (dataframe["adx"] > 20)
            & (dataframe["volume"] > dataframe["vol_mean"] * 0.65)
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[entry, ["enter_long", "enter_tag"]] = (1, "bull_regime_pullback")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        regime_break = (
            (dataframe["close"] < dataframe["ema50"])
            & (dataframe["close"].shift(1) >= dataframe["ema50"].shift(1))
        )
        structural_break = dataframe["ema50"] < dataframe["ema200"]
        exit_signal = (
            regime_break | structural_break | (dataframe["rsi"] > 79)
        ) & (dataframe["volume"] > 0)
        dataframe.loc[exit_signal, ["exit_long", "exit_tag"]] = (1, "regime_exit")
        return dataframe
