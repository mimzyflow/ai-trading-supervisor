from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import IStrategy


class MoussaSmallCapMomentum(IStrategy):
    """Research-only small/mid-cap momentum strategy for Kraken spot."""

    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "4h"
    startup_candle_count = 220
    process_only_new_candles = True

    minimal_roi = {
        "0": 0.12,
        "1440": 0.08,
        "4320": 0.04,
    }
    stoploss = -0.07
    trailing_stop = True
    trailing_stop_positive = 0.03
    trailing_stop_positive_offset = 0.06
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
        dataframe["high20"] = dataframe["high"].rolling(20).max().shift(1)
        dataframe["ema200_slope"] = dataframe["ema200"] / dataframe["ema200"].shift(12) - 1
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        breakout = (
            (dataframe["close"] > dataframe["high20"])
            & (dataframe["close"].shift(1) <= dataframe["high20"].shift(1))
        )
        regime = (
            (dataframe["ema20"] > dataframe["ema50"])
            & (dataframe["ema50"] > dataframe["ema200"])
            & (dataframe["ema200_slope"] > 0)
        )
        acceleration = (
            (dataframe["volume"] > dataframe["vol_mean"] * 1.8)
            & (dataframe["adx"] > 22)
            & (dataframe["rsi"] > 55)
            & (dataframe["rsi"] < 76)
            & (dataframe["atr_pct"] > 0.015)
            & (dataframe["atr_pct"] < 0.12)
        )
        entry = regime & breakout & acceleration & (dataframe["volume"] > 0)
        dataframe.loc[entry, ["enter_long", "enter_tag"]] = (
            1,
            "smallcap_breakout",
        )
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        momentum_break = (
            (dataframe["close"] < dataframe["ema20"])
            & (dataframe["close"].shift(1) >= dataframe["ema20"].shift(1))
        )
        structural_break = dataframe["ema20"] < dataframe["ema50"]
        exit_signal = (
            momentum_break
            | structural_break
            | (dataframe["rsi"] > 82)
        ) & (dataframe["volume"] > 0)
        dataframe.loc[exit_signal, ["exit_long", "exit_tag"]] = (
            1,
            "smallcap_exit",
        )
        return dataframe
