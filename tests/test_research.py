import tempfile
import unittest
from pathlib import Path
from scripts.research_run import command, digest
from scripts.benchmark_metrics import passive_net_return
from scripts.install_release import restore_files


class ResearchTests(unittest.TestCase):
    def test_rollback_restores_code_and_preserves_private_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root, backup = Path(folder) / 'root', Path(folder) / 'backup'
            root.mkdir(); backup.mkdir()
            (root / 'old.py').write_text('new release')
            (backup / 'old.py').write_text('previous release')
            (root / 'new.py').write_text('new file')
            (root / '.env').write_text('private local setting')
            (root / 'trades.sqlite').write_bytes(b'existing simulated history')
            restore_files(root, backup, [Path('old.py'), Path('new.py')], [Path('old.py')])
            self.assertEqual((root / 'old.py').read_text(), 'previous release')
            self.assertFalse((root / 'new.py').exists())
            self.assertEqual((root / '.env').read_text(), 'private local setting')
            self.assertEqual((root / 'trades.sqlite').read_bytes(), b'existing simulated history')

    def test_benchmark_includes_both_fees_and_idle_cash(self):
        self.assertAlmostEqual(passive_net_return(0), 0.4 * (0.992**2 - 1))
        self.assertAlmostEqual(passive_net_return(0.5, exposure=0), 0)
        self.assertAlmostEqual(passive_net_return(0.1, fee_per_side=0, exposure=0.4), 0.04)

    def test_benchmark_refuses_impossible_exposure(self):
        with self.assertRaises(ValueError):
            passive_net_return(0.1, exposure=2)
    def test_backtest_is_isolated_pinned_and_uses_per_side_fees(self):
        argv = command(Path('/project'), Path('/data'), Path('/result'), 'MoussaBaseline', '20260101-20260301', 0.008, ['BTC/EUR'], '15m')
        self.assertIn('backtesting', argv)
        self.assertNotIn('trade', argv)
        self.assertIn('--enable-protections', argv)
        self.assertIn('FREQTRADE__DRY_RUN=true', argv)
        self.assertEqual(argv[argv.index('--fee') + 1], '0.008')
        self.assertTrue(any('@sha256:' in a for a in argv))

    def test_invalid_arguments_do_not_reach_docker(self):
        for strategy, pairs, fee in [('Other;trade', ['BTC/EUR'], 0.008), ('MoussaBaseline', ['BTC/USDT'], 0.008), ('MoussaBaseline', ['BTC/EUR'], -1)]:
            with self.assertRaises(ValueError):
                command(Path('/project'), Path('/data'), Path('/result'), strategy, '20260101-', fee, pairs, '4h')

    def test_data_digest_changes_if_data_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'data'
            p.write_bytes(b'original')
            old = digest(p)
            p.write_bytes(b'changed')
            self.assertNotEqual(old, digest(p))
