import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import install_release


class RiskRegistryTests(unittest.TestCase):
    def test_missing_registry_warns_and_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertLogs('install_release', level='WARNING') as logs:
                self.assertIs(install_release.risk_halted(root), False)
        self.assertEqual(len(logs.records), 1)
        message = logs.records[0].getMessage()
        self.assertIn('risk_registry_absent', message)
        self.assertIn(str(root / 'research_state/registry.sqlite'), message)

    def test_existing_registry_behaviour_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'research_state').mkdir()
            db = root / 'research_state/registry.sqlite'
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE bots (id TEXT, status TEXT)')
                conn.execute("INSERT INTO bots VALUES ('root', 'paused_risk')")
            self.assertIs(install_release.risk_halted(root), True)
            with sqlite3.connect(db) as conn:
                conn.execute("UPDATE bots SET status='active' WHERE id='root'")
            self.assertIs(install_release.risk_halted(root), False)


if __name__ == '__main__':
    unittest.main()
