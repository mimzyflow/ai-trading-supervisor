"""Private offline experiment. Existing output directories are never reused."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_lab.equity_experiment import run_experiment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True,
                        help='New private directory, preferably below ignored research_results/')
    args = parser.parse_args()
    if args.data.stat().st_size > 8_000_000:
        raise ValueError('equity_bundle_too_large')
    raw = args.data.read_bytes()
    result = run_experiment(json.loads(raw), args.output, source_bytes=raw)
    print(json.dumps({'output': str(args.output), 'verdict': result['verdict'],
                      'runs_published': len(result['runs']), 'broker_connected': False,
                      'real_money_eligible': False, 'promotion_permitted': False}))


if __name__ == '__main__':
    main()
