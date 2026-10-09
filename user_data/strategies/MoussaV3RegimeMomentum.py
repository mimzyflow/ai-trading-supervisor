from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import IStrategy

class MoussaV3RegimeMomentum(IStrategy):
    """Research-only 1h trend/momentum challenger. Never auto-promoted live."""
    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "1h"
    startup_candle_count = 260
    process_only_new_candles = True
    minimal_roi = {"0": 0.07, "720": 0.045, "2160": 0.025, "4320": 0.0}
    stoploss = -0.035
    trailing_stop = True
    trailing_stop_positive = 0.018
    trailing_stop_positive_offset = 0.035
    trailing_only_offset_is_reached = True
    use_exit_signal = True

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 4},
            {"method": "StoplossGuard", "lookback_period_candles": 96,
             "trade_limit": 3, "stop_duration_candles": 24, "only_per_pair": False},
            {"method": "MaxDrawdown", "lookback_period_candles": 240,
             "trade_limit": 8, "stop_duration_candles": 24,
             "max_allowed_drawdown": 0.05, "calculation_mode": "equity"},
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]
        dataframe["vol_mean"] = dataframe["volume"].rolling(24).mean()
        dataframe["high24"] = dataframe["high"].rolling(24).max().shift(1)
        dataframe["ema200_slope"] = dataframe["ema200"] / dataframe["ema200"].shift(24) - 1
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        entry = (
            (dataframe["ema20"] > dataframe["ema50"])
            & (dataframe["ema50"] > dataframe["ema200"])
            & (dataframe["ema200_slope"] > 0)
            & (dataframe["close"] > dataframe["high24"])
            & (dataframe["rsi"] > 54) & (dataframe["rsi"] < 74)
            & (dataframe["adx"] > 20)
            & (dataframe["atr_pct"] > 0.008) & (dataframe["atr_pct"] < 0.08)
            & (dataframe["volume"] > dataframe["vol_mean"] * 1.2)
        )
        dataframe.loc[entry, ["enter_long", "enter_tag"]] = (1, "v3_regime_momentum")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_signal = (
            (dataframe["close"] < dataframe["ema20"])
            | (dataframe["ema20"] < dataframe["ema50"])
            | (dataframe["rsi"] > 82)
        ) & (dataframe["volume"] > 0)
        dataframe.loc[exit_signal, ["exit_long", "exit_tag"]] = (1, "v3_momentum_exit")
        return dataframe
