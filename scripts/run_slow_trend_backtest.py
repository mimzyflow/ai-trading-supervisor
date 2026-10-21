#!/usr/bin/env python3
"""Backtest rétrospectif de la rotation mensuelle lente. Simulation uniquement.

Entrées : fichiers JSON {bars:[{date,open,high,low,close,volume}], splits:[[date,ratio]]}
téléchargés depuis l'API publique Yahoo (aucune clé). Exemple :
  python3 scripts/run_slow_trend_backtest.py --btc BTC-EUR.bars.json --eth ETH-EUR.bars.json \
      --etf SCHB.bars.json --start 2022-01-01 --output research_results/slow-trend.json
"""
import argparse
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_lab.slow_trend import align, simulate, unadjust_splits

SCENARIOS = {'realistic': {'fee': 0.0025, 'slippage': 0.0010},
             'doubled': {'fee': 0.0050, 'slippage': 0.0020}}


def windows(start, end):
    out = [('full', start, end)]
    for year in range(int(start[:4]), int(end[:4]) + 1):
        left, right = max(start, f'{year}-01-01'), min(end, f'{year}-12-31')
        if left < right:
            out.append((str(year), left, right))
    return out


def compact(result):
    return {k: result[k] for k in ('start', 'end', 'final', 'return_pct', 'max_drawdown_pct', 'orders', 'round_trips')} | {
        'alerts_notify_only': len(result['alerts'])}


def run(btc, eth, etf, start, end=None):
    crypto = align({'BTC': btc, 'ETH': eth})
    end = end or crypto['BTC'][-1]['date']
    report = {'mode': 'SIMULATION_ONLY', 'real_money_eligible': False, 'rows': []}
    for label, left, right in windows(start, end):
        for cost_name, cost in SCENARIOS.items():
            rows = {
                'crypto_rotation': simulate(crypto, start_date=left, end_date=right, **cost),
                'crypto_buy_hold_btc': simulate({'BTC': crypto['BTC']}, start_date=left, end_date=right, rule='buy_hold', **cost),
                'crypto_buy_hold_eth': simulate({'ETH': crypto['ETH']}, start_date=left, end_date=right, rule='buy_hold', **cost),
            }
            if etf:
                rows['etf_trend'] = simulate(etf, start_date=left, end_date=right, whole_units=True, **cost)
                rows['etf_buy_hold'] = simulate(etf, start_date=left, end_date=right, whole_units=True, rule='buy_hold', **cost)
            for name, result in rows.items():
                report['rows'].append({'window': label, 'costs': cost_name, 'strategy': name, **compact(result)})
    return report


def load(path):
    data = json.loads(Path(path).read_text())
    bars = data['bars']
    if data.get('splits'):
        bars = unadjust_splits(bars, [tuple(x) for x in data['splits']])
    return bars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--btc', required=True)
    ap.add_argument('--eth', required=True)
    ap.add_argument('--etf')
    ap.add_argument('--etf-name', default='ETF')
    ap.add_argument('--start', default='2022-01-01')
    ap.add_argument('--end')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    etf = {args.etf_name: load(args.etf)} if args.etf else None
    report = run(load(args.btc), load(args.eth), etf, args.start, args.end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    for row in report['rows']:
        print(row['window'], row['costs'], row['strategy'], row['return_pct'], row['max_drawdown_pct'], row['orders'])


if __name__ == '__main__':
    main()
