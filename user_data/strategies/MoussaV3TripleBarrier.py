from datetime import timedelta
from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import IStrategy

class MoussaV3TripleBarrier(IStrategy):
    """Research-only breakout with stop/take-profit/time-limit/trailing barriers."""
    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "1h"
    startup_candle_count = 260
    process_only_new_candles = True
    minimal_roi = {"0": 0.065, "1440": 0.045, "2880": 0.025}
    stoploss = -0.03
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True
    use_exit_signal = True
    use_custom_exit = True

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 6},
            {"method": "StoplossGuard", "lookback_period_candles": 120,
             "trade_limit": 3, "stop_duration_candles": 36, "only_per_pair": False},
            {"method": "MaxDrawdown", "lookback_period_candles": 240,
             "trade_limit": 8, "stop_duration_candles": 36,
             "max_allowed_drawdown": 0.05, "calculation_mode": "equity"},
            {"method": "LowProfitPairs", "lookback_period_candles": 168,
             "trade_limit": 3, "stop_duration_candles": 48,
             "required_profit": 0.0, "only_per_pair": True},
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]
        dataframe["high48"] = dataframe["high"].rolling(48).max().shift(1)
        dataframe["vol_mean"] = dataframe["volume"].rolling(24).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        entry = (
            (dataframe["ema50"] > dataframe["ema200"])
            & (dataframe["close"] > dataframe["high48"])
            & (dataframe["adx"] > 22)
            & (dataframe["rsi"] > 55) & (dataframe["rsi"] < 76)
            & (dataframe["atr_pct"] > 0.01) & (dataframe["atr_pct"] < 0.09)
            & (dataframe["volume"] > dataframe["vol_mean"] * 1.3)
        )
        dataframe.loc[entry, ["enter_long", "enter_tag"]] = (1, "v3_triple_barrier")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_signal = ((dataframe["close"] < dataframe["ema50"]) | (dataframe["rsi"] > 84))
        dataframe.loc[exit_signal & (dataframe["volume"] > 0),
                      ["exit_long", "exit_tag"]] = (1, "v3_structure_exit")
        return dataframe

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if current_time >= trade.open_date_utc + timedelta(hours=72):
            return "time_limit_72h"
        return None
