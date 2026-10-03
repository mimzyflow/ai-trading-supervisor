"""Offline stock/ETF simulation; no account or broker order is contacted."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_lab.data import validate, canonical_hash
from research_lab.engine import simulate, TEMPLATES
from research_lab.research import costs, compact


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--template', type=int, choices=range(len(TEMPLATES)), default=0)
    args = parser.parse_args()
    if args.data.stat().st_size > 8_000_000:
        raise ValueError('equity_bundle_too_large')
    bundle = validate(json.loads(args.data.read_text()))
    if any(a['asset_class'] not in {'stock', 'etf'} for a in bundle['assets']):
        raise ValueError('equities_only')
    result = simulate(bundle, TEMPLATES[args.template], **costs(bundle))
    print(json.dumps({'data_sha256': canonical_hash(bundle), 'template': TEMPLATES[args.template], 'result': compact(result),
                      'scenario_costs': costs(bundle), 'broker_connected': False, 'real_money_eligible': False}, indent=2))


if __name__ == '__main__':
    main()
