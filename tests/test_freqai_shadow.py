import unittest

from research_lab.freqai_shadow import config, status

class FreqAIShadowTests(unittest.TestCase):
    def test_mutable_or_missing_image_is_blocked(self):
        self.assertEqual(status()["state"], "blocked_unpinned_image")
        self.assertEqual(
            status("freqtradeorg/freqtrade:stable_freqai")["state"],
            "blocked_mutable_or_invalid_image",
        )

    def test_digest_pinned_image_is_only_backtest_ready(self):
        image = "freqtradeorg/freqtrade:freqai@sha256:" + "a" * 64
        value = status(image)
        self.assertEqual(value["state"], "ready_for_offline_backtest")
        self.assertFalse(value["automatic_live_deployment"])
        self.assertFalse(value["real_money_eligible"])

    def test_config_keeps_time_ordered_split(self):
        value = config()
        self.assertTrue(value["enabled"])
        self.assertFalse(value["data_split_parameters"]["shuffle"])
        self.assertEqual(value["train_period_days"], 30)
        self.assertEqual(value["backtest_period_days"], 7)

if __name__ == "__main__":
    unittest.main()
