import json
import tempfile
import unittest
from pathlib import Path

from research_lab.worker import replace_v3_marker


class V3ArchiveTests(unittest.TestCase):
    def test_recalculation_preserves_previous_result_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'last_v3_challengers.json'
            old = {'day': '2026-10-08', 'result': {'state': 'all_rejected', 'return_pct': -4.6}}
            new = {'day': '2026-10-08', 'implementation_sha256': 'a' * 64,
                   'result': {'state': 'all_rejected', 'return_pct': -5.2}}
            replace_v3_marker(path, old, new)
            archived = list((path.parent / 'archive').iterdir())
            self.assertEqual(len(archived), 1)
            self.assertEqual(json.loads(archived[0].read_text()), old)
            self.assertEqual(json.loads(path.read_text()), new)
            replace_v3_marker(path, old, new)
            self.assertEqual(len(list((path.parent / 'archive').iterdir())), 1)


if __name__ == '__main__':
    unittest.main()
