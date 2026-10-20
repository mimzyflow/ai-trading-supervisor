import unittest

from research_lab import cost_model
from research_lab.v3_challengers import (MAX_NET_PNL_ASSET_SHARE, _net_concentration,
                                         evaluate, leave_one_pair_out)
from research_lab.research import costs
from tests.test_v3_research import make_bundle


class CostModelTests(unittest.TestCase):
    def test_maker_default_and_legacy_kept_as_degraded(self):
        self.assertEqual(cost_model.DEFAULT_SCENARIO, 'maker_realistic')
        self.assertEqual(cost_model.scenario()['fee'], 0.0025)
        self.assertEqual(cost_model.scenario('legacy_degraded')['fee'], 0.008)
        self.assertGreater(cost_model.scenario()['slippage'], 0)

    def test_stress_matches_existing_research_stress(self):
        crypto = make_bundle(count=5)
        crypto['assets'][0]['asset_class'] = 'crypto'
        stressed = costs(crypto, stressed=True)
        self.assertEqual(cost_model.scenario('stress')['fee'], stressed['fee'])
        self.assertEqual(cost_model.scenario('stress')['slippage'], stressed['slippage'])

    def test_round_trip_and_freqtrade_fee(self):
        self.assertEqual(cost_model.round_trip_pct(cost_model.scenario()), 0.7)
        self.assertEqual(cost_model.freqtrade_fee('maker_realistic'), 0.0035)
        self.assertEqual(cost_model.freqtrade_fee('legacy_degraded'), 0.009)

    def test_overrides_are_bounded(self):
        self.assertEqual(cost_model.scenario(slippage=0.002)['slippage'], 0.002)
        for bad in (-0.1, float('nan'), True, 0.5):
            with self.assertRaises(ValueError):
                cost_model.scenario(fee=bad)
        with self.assertRaises(ValueError):
            cost_model.scenario('free_lunch')


class V3GateTests(unittest.TestCase):
    def test_net_concentration(self):
        trades = [{'asset': 'A', 'profit': 9}, {'asset': 'B', 'profit': 1}]
        self.assertAlmostEqual(_net_concentration(trades), 0.9)
        self.assertEqual(_net_concentration([{'asset': 'A', 'profit': -1}]), 0.0)
        self.assertLess(MAX_NET_PNL_ASSET_SHARE, 0.9)

    def test_leave_one_pair_out_single_asset_not_applicable(self):
        data = make_bundle(count=50)
        out = leave_one_pair_out(data, {'family': 'buy_hold'}, 10, costs(data))
        self.assertEqual(out['state'], 'not_applicable_single_asset')

    def test_evaluate_reports_stress_lopo_and_concentration(self):
        data = make_bundle(count=650, assets=2)
        result = evaluate(data)
        policy = result['selection_policy']
        self.assertTrue(policy['stressed_costs_must_be_positive'])
        self.assertTrue(policy['leave_one_pair_out_must_stay_positive'])
        self.assertEqual(policy['maximum_net_pnl_asset_share'], MAX_NET_PNL_ASSET_SHARE)
        for item in result['challengers'].values():
            self.assertIn('stressed_costs', item)
            self.assertIn('legacy_degraded_costs', item)
            self.assertEqual(item['leave_one_pair_out']['state'], 'computed')
            self.assertEqual(set(item['leave_one_pair_out']['runs']), {'A0', 'A1'})
            self.assertIn('net_pnl_top_asset_share', item)
        self.assertFalse(result['real_money_eligible'])


if __name__ == '__main__':
    unittest.main()
