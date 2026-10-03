from pandas import DataFrame, concat
import talib.abstract as ta
from freqtrade.strategy import IStrategy, merge_informative_pair


class MoussaSmallCapBreadth(IStrategy):
    """Research-only breakout gated by cross-sectional altcoin breadth."""

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
        pairs = self.dp.current_whitelist()
        return [(pair, "4h") for pair in pairs]

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

        breadth_parts = []
        for pair in self.dp.current_whitelist():
            frame = self.dp.get_pair_dataframe(pair=pair, timeframe="4h").copy()
            if frame.empty:
                continue
            ema200 = ta.EMA(frame, timeperiod=200)
            frame = frame[["date"]].copy()
            frame[pair] = (
                self.dp.get_pair_dataframe(pair=pair, timeframe="4h")["close"].values > ema200.values
            ).astype(float)
            breadth_parts.append(frame.set_index("date")[pair])

        if breadth_parts:
            breadth = concat(breadth_parts, axis=1).mean(axis=1).rename("breadth")
            bdf = breadth.reset_index()
            dataframe = merge_informative_pair(
                dataframe, bdf, self.timeframe, "4h", ffill=True
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
            local_trend & breakout & acceleration
            & (dataframe["breadth_4h"] >= 0.55)
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[entry, ["enter_long", "enter_tag"]] = (1, "breadth_breakout")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        momentum_break = (
            (dataframe["close"] < dataframe["ema20"])
            & (dataframe["close"].shift(1) >= dataframe["ema20"].shift(1))
        )
        exit_signal = (
            momentum_break
            | (dataframe["ema20"] < dataframe["ema50"])
            | (dataframe["breadth_4h"] < 0.40)
            | (dataframe["rsi"] > 82)
        ) & (dataframe["volume"] > 0)
        dataframe.loc[exit_signal, ["exit_long", "exit_tag"]] = (1, "breadth_exit")
        return dataframe
