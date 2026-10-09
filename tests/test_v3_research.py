import unittest
from datetime import datetime, timedelta, timezone

from research_lab.engine import simulate
from research_lab.portfolio_risk import entry_budget
from research_lab.v3_challengers import evaluate

def make_bundle(count=650, assets=1, step=0.02):
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    items = []
    for asset_index in range(assets):
        bars = []
        price = 10 + asset_index
        for i in range(count):
            opened = start + timedelta(days=i)
            price *= 1 + step * (1.5 if i % 3 == 0 else 0.5)
            bars.append({
                "open_at": opened.isoformat(),
                "close_at": (opened + timedelta(hours=20)).isoformat(),
                "open": price * 0.995,
                "high": price * 1.08,
                "low": price * 0.99,
                "close": price,
                "volume": 100000 + i,
            })
        items.append({
            "id": "A" + str(asset_index), "currency": "USD",
            "asset_class": "stock", "price_basis": "raw",
            "lot_size": 1, "bars": bars,
        })
    return {
        "schema_version": 1, "currency": "USD",
        "calendar_verified": True, "corporate_actions_verified": True,
        "historical_universe_verified": True, "assets": items,
    }

class V3ResearchTests(unittest.TestCase):
    def test_triple_barrier_take_profit_is_available(self):
        data = make_bundle(count=30, step=0.12)
        data["assets"][0]["asset_class"] = "crypto"
        data["assets"][0]["lot_size"] = 0.00000001
        spec = {
            "family": "trend_breakout", "fast": 2, "slow": 3, "breakout": 2,
            "stop_loss": 0.05, "max_hold": 10, "take_profit": 0.03,
            "trailing_activation": 0.02, "trailing_distance": 0.01,
        }
        result = simulate(data, spec, fee=0, slippage=0, allocation=20)
        self.assertGreater(result["closed_trades"], 0)
        self.assertTrue(any(t["reason"] == "take_profit" for t in result["trades"]))

    def test_portfolio_risk_rejects_highly_correlated_duplicate(self):
        data = make_bundle(count=40, assets=2, step=0.01)
        state = {
            "cash": 80,
            "positions": {"A0": {"quantity": 1, "cost": 20}},
        }
        budget, reason = entry_budget(
            data, state, 39, data["assets"][1], equity=100,
            allocation=20, correlation_limit=0.80,
        )
        self.assertEqual(budget, 0)
        self.assertEqual(reason, "correlation_limit")

    def test_v3_matrix_never_authorizes_live(self):
        result = evaluate(make_bundle())
        self.assertIn(result["state"], {"all_rejected", "candidate_for_forward_shadow"})
        self.assertFalse(result["automatic_live_deployment"])
        self.assertFalse(result["real_money_eligible"])
        self.assertEqual(set(result["challengers"]), {
            "regime_momentum", "triple_barrier", "slow_breakout"
        })
        for value in result["challengers"].values():
            self.assertFalse(value["gate"]["automatic_live_deployment"])
            self.assertFalse(value["gate"]["real_money_eligible"])

if __name__ == "__main__":
    unittest.main()
