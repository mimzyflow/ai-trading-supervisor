"""MoussaControlStops sans image Freqtrade : modules freqtrade/talib simulés.

Vérifie que l'arrêt portefeuille -5 % inclut le latent de TOUTES les positions
ouvertes, y compris dans confirm_trade_entry.
"""
import importlib
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


class FakeTrade:
    open_trades = []
    closed_trades = []

    def __init__(self, id, pair, open_rate, amount, fee=0.008, close_profit_abs=None, close_profit=None, close_date=None):
        self.id, self.pair, self.open_rate, self.amount, self.fee = id, pair, open_rate, amount, fee
        self.close_profit_abs, self.close_profit, self.close_date = close_profit_abs, close_profit, close_date

    def calc_profit(self, rate):
        return self.amount * (rate * (1 - self.fee) - self.open_rate * (1 + self.fee))

    @classmethod
    def get_trades_proxy(cls, is_open=None):
        return list(cls.open_trades if is_open else cls.closed_trades)


class FakeFrame:
    def __init__(self, close):
        self._close = close

    def __len__(self):
        return 1

    def __getitem__(self, key):
        value = self._close
        return types.SimpleNamespace(iloc={-1: value})


class FakeDP:
    def __init__(self, prices):
        self.prices = prices

    def get_analyzed_dataframe(self, pair, timeframe):
        if pair not in self.prices:
            return None, None
        return FakeFrame(self.prices[pair]), None


def load_strategy():
    stubs = {name: types.ModuleType(name) for name in [
        'talib', 'talib.abstract', 'freqtrade', 'freqtrade.strategy', 'freqtrade.vendor',
        'freqtrade.vendor.qtpylib', 'freqtrade.vendor.qtpylib.indicators', 'freqtrade.persistence']}
    stubs['freqtrade.strategy'].IStrategy = type('IStrategy', (), {'__init__': lambda self, config=None: setattr(self, 'config', config or {})})
    stubs['freqtrade.vendor.qtpylib'].indicators = stubs['freqtrade.vendor.qtpylib.indicators']
    stubs['freqtrade.persistence'].Trade = FakeTrade
    if 'pandas' not in sys.modules:
        try:
            importlib.import_module('pandas')
        except ImportError:
            stubs['pandas'] = types.ModuleType('pandas')
            stubs['pandas'].DataFrame = object
    paths = [str(ROOT / 'user_data/strategies'), str(ROOT / 'supervisor')]
    with patch.dict(sys.modules, stubs), patch.object(sys, 'path', paths + sys.path):
        for name in ['MoussaControlStops', 'MoussaBaseline', 'control_guards']:
            sys.modules.pop(name, None)
        module = importlib.import_module('MoussaControlStops')
        for name in ['MoussaControlStops', 'MoussaBaseline', 'control_guards']:
            sys.modules.pop(name, None)
    return module.MoussaControlStops


class ControlStrategyHaltTests(unittest.TestCase):
    def setUp(self):
        cls = load_strategy()
        self.strategy = cls({'dry_run': True, 'trading_mode': 'spot', 'dry_run_wallet': 100,
                             'exchange': {'key': '', 'secret': ''}})
        self.strategy.bot_start()
        FakeTrade.closed_trades = []
        FakeTrade.open_trades = [FakeTrade(1, 'XBT/EUR', 100, 0.1), FakeTrade(2, 'ETH/EUR', 10, 1),
                                 FakeTrade(3, 'SOL/EUR', 5, 2)]

    def entry(self, pair='LINK/EUR', rate=10):
        return self.strategy.confirm_trade_entry(pair, 'limit', 1, rate, 'GTC', NOW, None, 'long')

    def test_entry_blocked_by_unrealized_loss_of_other_positions(self):
        # -3.14 (XBT) -2.14 (ETH) -0.16 (SOL, sans prix -> frais) = -5.44 EUR < -5 % de 100 EUR.
        self.strategy.dp = FakeDP({'XBT/EUR': 70, 'ETH/EUR': 8})
        self.assertFalse(self.entry())

    def test_entry_allowed_when_total_loss_below_limit(self):
        self.strategy.dp = FakeDP({'XBT/EUR': 70, 'ETH/EUR': 10, 'SOL/EUR': 5})
        self.assertTrue(self.entry())

    def test_realized_plus_unrealized(self):
        FakeTrade.closed_trades = [FakeTrade(9, 'ADA/EUR', 1, 1, close_profit_abs=-3.0, close_profit=0.01,
                                             close_date=NOW)]
        self.strategy.dp = FakeDP({'XBT/EUR': 80, 'ETH/EUR': 10, 'SOL/EUR': 5})
        self.assertFalse(self.entry())

    def test_custom_exit_uses_all_positions(self):
        self.strategy.dp = FakeDP({'XBT/EUR': 70, 'ETH/EUR': 8, 'SOL/EUR': 5})
        trade = FakeTrade.open_trades[2]
        self.assertEqual(self.strategy.custom_exit('SOL/EUR', trade, NOW, 5, 0.0), 'control_portfolio_halt')
        self.strategy.dp = FakeDP({'XBT/EUR': 100, 'ETH/EUR': 10, 'SOL/EUR': 5})
        self.assertIsNone(self.strategy.custom_exit('SOL/EUR', trade, NOW, 5, 0.0))

    def test_current_rate_overrides_mark_for_its_pair(self):
        self.strategy.dp = FakeDP({'XBT/EUR': 100, 'ETH/EUR': 10, 'SOL/EUR': 5})
        self.assertTrue(self.entry('XBT/EUR', 100))
        self.assertFalse(self.entry('XBT/EUR', 45))

    def test_refuses_live(self):
        self.strategy.config['dry_run'] = False
        with self.assertRaises(ValueError):
            self.entry()


if __name__ == '__main__':
    unittest.main()
