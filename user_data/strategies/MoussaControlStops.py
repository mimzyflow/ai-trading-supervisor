"""Compte témoin DRY-RUN : MoussaBaseline + stops et protections.

Simulation uniquement. Comparateur de l'expérience sans stops
(MoussaMarketRoom), avec les mêmes frais, univers et capital (100 EUR).
- stop par position (défaut -3 %) ;
- arrêt portefeuille persistant à -5 % du capital initial (+ MaxDrawdown) ;
- pause après N pertes consécutives (défaut 3, CONTROL_MAX_CONSECUTIVE_LOSSES).
"""
from datetime import timezone

from freqtrade.persistence import Trade

from MoussaBaseline import MoussaBaseline
from control_guards import (consecutive_loss_pause, portfolio_halt,
                            require_simulation, settings, unrealized_pnl)

_SETTINGS = settings()


class MoussaControlStops(MoussaBaseline):
    stoploss = _SETTINGS['position_stop']
    trailing_stop = False
    use_custom_stoploss = False

    @property
    def protections(self):
        n = _SETTINGS['max_consecutive_losses']
        return [
            {'method': 'CooldownPeriod', 'stop_duration_candles': 2},
            # Coupure native après N sorties sur stop dans la fenêtre.
            {'method': 'StoplossGuard', 'lookback_period_candles': 96,
             'trade_limit': n, 'stop_duration_candles': 96, 'only_per_pair': False},
            # Verrou temporaire si la baisse sur la fenêtre dépasse le seuil.
            {'method': 'MaxDrawdown', 'lookback_period_candles': 96 * 7, 'trade_limit': 1,
             'stop_duration_candles': 96, 'max_allowed_drawdown': _SETTINGS['portfolio_loss_limit_pct'] / 100.0},
        ]

    def bot_start(self, **kwargs):
        require_simulation(self.config)
        self.control = settings()

    def _initial(self):
        return float(self.config.get('dry_run_wallet', 100) or 100)

    def _mark_price(self, pair):
        """Dernière clôture analysée de la paire (données publiques, dry-run)."""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe is not None and len(dataframe):
                return float(dataframe['close'].iloc[-1])
        except Exception:
            return None
        return None

    def _halted(self, current_time, current_rate=None, current_pair=None):
        """Perte réalisée + latente de TOUTES les positions ouvertes >= limite."""
        closed = Trade.get_trades_proxy(is_open=False)
        realized = sum(float(t.close_profit_abs or 0) for t in closed)

        def price_for(trade):
            if current_rate and current_pair is not None and trade.pair == current_pair:
                return current_rate
            return self._mark_price(trade.pair)

        unrealized, _ = unrealized_pnl(Trade.get_trades_proxy(is_open=True), price_for)
        return portfolio_halt(self._initial(), realized, unrealized, self.control['portfolio_loss_limit_pct'])

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs):
        if self.config.get('dry_run') is not True:
            raise ValueError('control_strategy_is_simulation_only')
        if self._halted(current_time, rate, pair):
            return False
        closed = [(t.close_date.replace(tzinfo=timezone.utc) if t.close_date and t.close_date.tzinfo is None else t.close_date,
                   t.close_profit) for t in Trade.get_trades_proxy(is_open=False)]
        blocked, _ = consecutive_loss_pause(closed, current_time, self.control['max_consecutive_losses'],
                                            self.control['loss_pause_hours'])
        return not blocked

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        # Liquidation simulée des positions ouvertes une fois l'arrêt portefeuille atteint.
        if self._halted(current_time, current_rate, pair):
            return 'control_portfolio_halt'
        return None
