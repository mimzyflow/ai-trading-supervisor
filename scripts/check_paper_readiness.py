"""Explicit read-only paper account check; no credential files are searched."""
import argparse
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_lab.paper_readiness import check


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols', nargs='+', default=[])
    parser.add_argument('--initial-usd', type=float, default=100)
    args = parser.parse_args()
    result = check(os.environ.get('ALPACA_PAPER_KEY_ID'), os.environ.get('ALPACA_PAPER_SECRET_KEY'),
                   args.symbols, args.initial_usd)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result['initial_setup_ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
