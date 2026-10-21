"""Rotation mensuelle BTC/ETH en bougies quotidiennes. DRY-RUN / backtest uniquement.

Règle figée (identique à research_lab/slow_trend.py) : à la clôture de la première
bougie quotidienne de chaque mois, on retient l'actif au meilleur momentum 90 jours
parmi BTC/EUR et ETH/EUR, seulement si sa clôture est au-dessus de sa SMA200 ;
sinon cash. Entrée/sortie à l'ouverture suivante. Aucun stop forcé (règle du projet :
5 % et 10 % = alertes notify_only gérées par le superviseur), aucun ROI.
"""
from pandas import DataFrame
from freqtrade.strategy import IStrategy, merge_informative_pair

ROTATION_PAIRS = ("BTC/EUR", "ETH/EUR")


class MoussaMonthlyRotation(IStrategy):
    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "1d"
    startup_candle_count = 210
    process_only_new_candles = True
    minimal_roi = {"0": 100.0}
    # Le framework exige un stoploss numérique ; -100 % = aucune vente forcée.
    stoploss = -1.0
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False

    momentum_days = 90
    sma_days = 200

    def bot_start(self, **kwargs):
        if self.config.get("dry_run") is not True or self.config.get("trading_mode", "spot") != "spot":
            raise ValueError("monthly_rotation_strategy_is_simulation_only")

    def informative_pairs(self):
        return [(pair, self.timeframe) for pair in ROTATION_PAIRS]

    def _features(self, df: DataFrame) -> DataFrame:
        df["sma200"] = df["close"].rolling(self.sma_days).mean()
        df["mom90"] = df["close"] / df["close"].shift(self.momentum_days) - 1
        df["eligible"] = (df["close"] > df["sma200"]).astype(int)
        return df

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata["pair"]
        dataframe = self._features(dataframe)
        others = [p for p in ROTATION_PAIRS if p != pair]
        if pair not in ROTATION_PAIRS or not self.dp:
            dataframe["is_best"] = 0
            return dataframe
        other = others[0]
        inf = self.dp.get_pair_dataframe(pair=other, timeframe=self.timeframe)
        if inf is None or inf.empty:
            dataframe["is_best"] = 0
            return dataframe
        inf = self._features(inf.copy())[["date", "close", "sma200", "mom90", "eligible"]]
        dataframe = merge_informative_pair(dataframe, inf, self.timeframe, self.timeframe, ffill=True)
        suffix = "_" + self.timeframe
        other_ok = dataframe["eligible" + suffix] == 1
        better = (dataframe["mom90"] > dataframe["mom90" + suffix]) | ~other_ok
        dataframe["is_best"] = ((dataframe["eligible"] == 1) & better).astype(int)
        dataframe["month_start"] = (dataframe["date"].dt.month != dataframe["date"].shift(1).dt.month).astype(int)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if "month_start" not in dataframe:
            return dataframe
        entry = (dataframe["month_start"] == 1) & (dataframe["is_best"] == 1) & (dataframe["volume"] > 0)
        dataframe.loc[entry, ["enter_long", "enter_tag"]] = (1, "monthly_rotation")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if "month_start" not in dataframe:
            return dataframe
        exit_signal = (dataframe["month_start"] == 1) & (dataframe["is_best"] == 0) & (dataframe["volume"] > 0)
        dataframe.loc[exit_signal, ["exit_long", "exit_tag"]] = (1, "monthly_rotation_exit")
        return dataframe

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        return min(max_stake, 20.0, proposed_stake)
