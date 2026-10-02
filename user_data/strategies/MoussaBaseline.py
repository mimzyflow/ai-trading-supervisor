from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import IStrategy
from freqtrade.vendor.qtpylib import indicators as qtpylib


class MoussaBaseline(IStrategy):
    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "15m"
    startup_candle_count = 200
    process_only_new_candles = True

    minimal_roi = {
        "0": 0.03,
        "60": 0.015,
        "180": 0.0,
    }
    stoploss = -0.04
    trailing_stop = False
    use_exit_signal = True

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 2},
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 48,
                "trade_limit": 2,
                "stop_duration_candles": 12,
                "only_per_pair": False,
            },
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["vol_mean"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        entry = (
            (dataframe["ema20"] > dataframe["ema50"])
            & qtpylib.crossed_above(dataframe["close"], dataframe["ema20"])
            & (dataframe["rsi"] > 50)
            & (dataframe["rsi"] < 68)
            & (dataframe["volume"] > dataframe["vol_mean"])
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[entry, ["enter_long", "enter_tag"]] = (1, "trend_pullback")
        return dataframe
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_signal = (
            qtpylib.crossed_below(dataframe["close"], dataframe["ema20"])
            | (dataframe["rsi"] > 75)
        ) & (dataframe["volume"] > 0)
        dataframe.loc[exit_signal, ["exit_long", "exit_tag"]] = (1, "trend_exit")
        return dataframe
