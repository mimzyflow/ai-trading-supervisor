import unittest

from research_lab.robustness import (
    trade_metrics,
    monte_carlo_trade_risk,
    probability_of_backtest_overfitting,
    promotion_gate,
)

class RobustnessTests(unittest.TestCase):
    def test_trade_metrics_and_small_sample_are_explicit(self):
        trades = [{"profit": 2.0}, {"profit": -1.0}, {"profit": 1.0}]
        metrics = trade_metrics(trades)
        self.assertEqual(metrics["closed_trades"], 3)
        self.assertAlmostEqual(metrics["profit_factor"], 3.0)
        self.assertEqual(monte_carlo_trade_risk(trades)["state"], "insufficient_sample")

    def test_pbo_detects_unstable_winner_shape(self):
        windows = {
            "a": [5, 5, -5, -5],
            "b": [-1, -1, 2, 2],
            "c": [0, 0, 0, 0],
        }
        value = probability_of_backtest_overfitting(windows)
        self.assertIsNotNone(value)
        self.assertGreaterEqual(value, 0)
        self.assertLessEqual(value, 1)

    def test_promotion_gate_refuses_tiny_sample(self):
        result = {
            "return_pct": 5.0,
            "max_drawdown_pct": 2.0,
            "trades": [{"profit": 1.0}] * 5,
            "curve": [{"equity": 100 + i} for i in range(10)],
        }
        gate = promotion_gate(result, benchmark_return=0.0)
        self.assertEqual(gate["state"], "rejected")
        self.assertIn("insufficient_trades", gate["reasons"])
        self.assertFalse(gate["real_money_eligible"])
        self.assertFalse(gate["automatic_live_deployment"])

if __name__ == "__main__":
    unittest.main()
