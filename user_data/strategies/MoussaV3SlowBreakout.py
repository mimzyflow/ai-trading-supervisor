from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import IStrategy

class MoussaV3SlowBreakout(IStrategy):
    """Research-only 4h challenger intended to reduce noise and fee turnover."""
    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "4h"
    startup_candle_count = 240
    process_only_new_candles = True
    minimal_roi = {"0": 0.09, "2880": 0.06, "8640": 0.03}
    stoploss = -0.04
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.045
    trailing_only_offset_is_reached = True
    use_exit_signal = True

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 3},
            {"method": "StoplossGuard", "lookback_period_candles": 60,
             "trade_limit": 2, "stop_duration_candles": 12, "only_per_pair": False},
            {"method": "MaxDrawdown", "lookback_period_candles": 90,
             "trade_limit": 6, "stop_duration_candles": 18,
             "max_allowed_drawdown": 0.05, "calculation_mode": "equity"},
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["high20"] = dataframe["high"].rolling(20).max().shift(1)
        dataframe["vol_mean"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        entry = (
            (dataframe["ema20"] > dataframe["ema50"])
            & (dataframe["ema50"] > dataframe["ema200"])
            & (dataframe["close"] > dataframe["high20"])
            & (dataframe["adx"] > 20)
            & (dataframe["rsi"] > 52) & (dataframe["rsi"] < 75)
            & (dataframe["volume"] > dataframe["vol_mean"])
        )
        dataframe.loc[entry, ["enter_long", "enter_tag"]] = (1, "v3_slow_breakout")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_signal = (dataframe["close"] < dataframe["ema20"]) | (dataframe["ema20"] < dataframe["ema50"])
        dataframe.loc[exit_signal & (dataframe["volume"] > 0),
                      ["exit_long", "exit_tag"]] = (1, "v3_slow_exit")
        return dataframe
