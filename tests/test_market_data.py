import unittest
try:
    import pandas as pd
except ImportError:
    pd = None
from scripts.check_market_data import validate_frame


@unittest.skipIf(pd is None, 'pandas is available in the pinned Freqtrade image')
class MarketDataTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({'date': pd.date_range('2026-01-01', periods=3, freq='4h', tz='UTC'), 'open': [100., 100., 100.], 'high': [102., 102., 102.], 'low': [99., 99., 99.], 'close': [101., 101., 101.], 'volume': [1., 1., 1.]})

    def test_valid_data_has_no_gaps(self):
        self.assertEqual(validate_frame(self.frame(), '4h')['gap_count'], 0)

    def test_duplicate_and_future_candles_are_rejected(self):
        frame = self.frame()
        frame.loc[1, 'date'] = frame.loc[0, 'date']
        with self.assertRaises(ValueError): validate_frame(frame, '4h')
        with self.assertRaises(ValueError): validate_frame(self.frame(), '4h', pd.Timestamp('2026-01-01T09:00Z'))

    def test_invalid_high_low_and_infinite_price_are_rejected(self):
        for value in [98., float('inf')]:
            frame = self.frame()
            frame.loc[0, 'high'] = value
            with self.assertRaises(ValueError): validate_frame(frame, '4h')
