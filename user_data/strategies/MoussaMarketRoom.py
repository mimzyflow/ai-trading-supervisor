"""100 EUR dry-run experiment, no loss stops, bounded desk advisory sizing."""
from pathlib import Path
from MoussaBaseline import MoussaBaseline
from paper_policy import read_policy, advice


class MoussaMarketRoom(MoussaBaseline):
    stoploss = -1.0
    trailing_stop = False

    def bot_start(self, **kwargs):
        self.paper_policy = read_policy()
        if self.config.get('dry_run') is not True or not self.paper_policy or self.config.get('trading_mode') != 'spot':
            raise ValueError('market_room_strategy_is_simulation_only')

    @property
    def protections(self):
        return [{'method': 'CooldownPeriod', 'stop_duration_candles': 2}]

    def room_advice(self, now):
        # Read a small mounted file; no network/model call inside trade callbacks.
        return advice(Path('/freqtrade/room-reports'), 'CRYPTO-EUR', now, self.paper_policy)

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        item = self.room_advice(current_time)
        return min(max_stake, 20.0, proposed_stake * item['stake_multiplier'])

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs):
        return self.config.get('dry_run') is True and self.room_advice(current_time)['allow_entry']

    def confirm_trade_exit(self, pair, trade, order_type, amount, rate, time_in_force,
                           exit_reason, current_time, **kwargs):
        if self.config.get('dry_run') is not True:
            raise ValueError('market_room_strategy_is_simulation_only')
        # The framework requires a numeric stoploss. At -100% and with these
        # dry-run-only vetoes, it never performs a loss-triggered sale.
        return exit_reason not in {'stop_loss', 'stoploss_on_exchange', 'trailing_stop_loss'}

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if self.room_advice(current_time)['exit']:
            return 'market_room_sell'
        return None
