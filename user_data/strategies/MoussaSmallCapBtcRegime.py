from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import IStrategy, merge_informative_pair


class MoussaSmallCapBtcRegime(IStrategy):
    """Research-only breakout gated by an independent BTC/EUR regime."""

    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "4h"
    startup_candle_count = 220
    process_only_new_candles = True

    minimal_roi = {"0": 0.12, "1440": 0.08, "4320": 0.04}
    stoploss = -0.07
    trailing_stop = True
    trailing_stop_positive = 0.03
    trailing_stop_positive_offset = 0.06
    trailing_only_offset_is_reached = True
    use_exit_signal = True

    def informative_pairs(self):
        return [("BTC/EUR", "4h")]

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

        btc = self.dp.get_pair_dataframe(pair="BTC/EUR", timeframe="4h")
        btc["btc_ema50"] = ta.EMA(btc, timeperiod=50)
        btc["btc_ema200"] = ta.EMA(btc, timeperiod=200)
        btc["btc_regime"] = (
            (btc["close"] > btc["btc_ema200"])
            & (btc["btc_ema50"] > btc["btc_ema200"])
            & (btc["btc_ema200"] > btc["btc_ema200"].shift(12))
        ).astype(int)
        dataframe = merge_informative_pair(
            dataframe,
            btc[["date", "btc_regime"]],
            self.timeframe,
            "4h",
            ffill=True,
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        breakout = (
            (dataframe["close"] > dataframe["high20"])
            & (dataframe["close"].shift(1) <= dataframe["high20"].shift(1))
        )
        local_trend = (
            (dataframe["ema20"] > dataframe["ema50"])
            & (dataframe["ema50"] > dataframe["ema200"])
        )
        acceleration = (
            (dataframe["volume"] > dataframe["vol_mean"] * 1.8)
            & (dataframe["adx"] > 22)
            & (dataframe["rsi"] > 55)
            & (dataframe["rsi"] < 76)
            & (dataframe["atr_pct"] > 0.015)
            & (dataframe["atr_pct"] < 0.12)
        )
        entry = (
            local_trend
            & breakout
            & acceleration
            & (dataframe["btc_regime_4h"] == 1)
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[entry, ["enter_long", "enter_tag"]] = (1, "btc_regime_breakout")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        momentum_break = (
            (dataframe["close"] < dataframe["ema20"])
            & (dataframe["close"].shift(1) >= dataframe["ema20"].shift(1))
        )
        exit_signal = (
            momentum_break
            | (dataframe["ema20"] < dataframe["ema50"])
            | (dataframe["btc_regime_4h"] == 0)
            | (dataframe["rsi"] > 82)
        ) & (dataframe["volume"] > 0)
        dataframe.loc[exit_signal, ["exit_long", "exit_tag"]] = (1, "btc_regime_exit")
        return dataframe
