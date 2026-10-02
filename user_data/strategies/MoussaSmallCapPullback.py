from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import IStrategy


class MoussaSmallCapPullback(IStrategy):
    """Research-only pullback strategy for liquid Kraken small/mid caps."""

    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "4h"
    startup_candle_count = 220
    process_only_new_candles = True

    minimal_roi = {
        "0": 0.09,
        "1440": 0.055,
        "4320": 0.025,
    }
    stoploss = -0.055
    trailing_stop = True
    trailing_stop_positive = 0.022
    trailing_stop_positive_offset = 0.045
    trailing_only_offset_is_reached = True
    use_exit_signal = True

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 2},
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 36,
                "trade_limit": 2,
                "stop_duration_candles": 12,
                "only_per_pair": False,
            },
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]
        dataframe["vol_mean"] = dataframe["volume"].rolling(20).mean()
        dataframe["ema200_slope"] = dataframe["ema200"] / dataframe["ema200"].shift(12) - 1
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        recovery = (
            (dataframe["close"] > dataframe["ema20"])
            & (dataframe["close"].shift(1) <= dataframe["ema20"].shift(1))
        )
        trend = (
            (dataframe["ema20"] > dataframe["ema50"])
            & (dataframe["ema50"] > dataframe["ema200"])
            & (dataframe["ema200_slope"] > 0)
        )
        quality = (
            (dataframe["rsi"] > 46)
            & (dataframe["rsi"] < 66)
            & (dataframe["adx"] > 17)
            & (dataframe["volume"] > dataframe["vol_mean"] * 0.75)
            & (dataframe["atr_pct"] > 0.012)
            & (dataframe["atr_pct"] < 0.10)
        )
        entry = trend & recovery & quality & (dataframe["volume"] > 0)
        dataframe.loc[entry, ["enter_long", "enter_tag"]] = (
            1,
            "smallcap_pullback",
        )
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        trend_break = (
            (dataframe["close"] < dataframe["ema50"])
            & (dataframe["close"].shift(1) >= dataframe["ema50"].shift(1))
        )
        exit_signal = (
            trend_break
            | (dataframe["ema20"] < dataframe["ema50"])
            | (dataframe["rsi"] > 78)
        ) & (dataframe["volume"] > 0)
        dataframe.loc[exit_signal, ["exit_long", "exit_tag"]] = (
            1,
            "smallcap_pullback_exit",
        )
        return dataframe
