"""One-use, retrospective stock/ETF experiment. No account, order or promotion."""
import csv
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path

from .data import canonical_hash, stamp, subset, validate
from .engine import TEMPLATES, simulate
from .research import compact, costs, quality

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = ('research_lab/data.py', 'research_lab/engine.py',
                'research_lab/research.py', 'research_lab/equity_experiment.py',
                'scripts/run_equity_experiment.py')
WARMUP = 200
FIXED_CUTOFF = '2026-10-02'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def private_write(path, content):
    """Exclusive creation, including output files after an interrupted run."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(content if isinstance(content, bytes) else content.encode())
        stream.flush()
        os.fsync(stream.fileno())


def source_hashes():
    return {name: digest((ROOT / name).read_bytes()) for name in SOURCE_FILES}


def rules(data):
    return {'initial': 100, 'allocation_per_asset': 20, 'whole_lots_only': True,
            'warmup_sessions': WARMUP, 'templates': deepcopy(list(TEMPLATES)),
            'cost_scenarios': {'base': costs(data), 'stress': costs(data, True),
                               'zero_commission_hypothetical':
                               {'fee': 0, 'min_commission': 0, 'slippage': 0.001}},
            'strategy_risk_control': True, 'benchmark_risk_control': False,
            'close_at_end': True, 'minimum_trades_per_window': 5,
            'window_roles': {'2023': 'development_retrospective',
                             '2024': 'historical_test', '2025': 'historical_test',
                             '2026YTD': 'historical_test'},
            'data_cutoff': FIXED_CUTOFF,
            'liquidity': 'previous_session_volume_1pct_whole_lots',
            'first_session': 'volume_sentinel_1_never_traded',
            'selection': 'none', 'promotion_permitted': False}


def equity_data(bundle, now):
    data = validate(deepcopy(bundle), now)
    for asset in data['assets']:
        if asset['asset_class'] not in {'stock', 'etf'}:
            raise ValueError('equities_only')
        lot = float(asset.get('lot_size', 1))
        if not lot.is_integer() or lot < 1:
            raise ValueError('whole_equity_lots_required')
    flags = ('calendar_verified', 'corporate_actions_verified',
             'historical_universe_verified', 'future_membership_tracking')
    if any(key in data and type(data[key]) is not bool for key in flags):
        raise ValueError('invalid_quality_metadata')
    # Today's small, retrospective universe is not a verified historical universe.
    # Refuse claims this offline runner cannot establish instead of inventing proof.
    if (data.get('historical_universe_verified') is True
            or data.get('future_membership_tracking') is True
            or data.get('quality_verified') is True):
        raise ValueError('historical_quality_claim_requires_independent_review')
    return data


def causal_execution_bundle(data):
    execution = deepcopy(data)
    for original, asset in zip(data['assets'], execution['assets']):
        for index, bar in enumerate(asset['bars']):
            # The first bar has no known predecessor. Sentinel 1 cannot fill an
            # integer lot under the 1% cap; all runs also start after 200 warmup bars.
            bar['volume'] = original['bars'][index - 1]['volume'] if index else 1.0
    return execution


def windows(data):
    bars = data['assets'][0]['bars']
    dates = [stamp(bar['open_at']).date() for bar in bars]
    result = []
    for year in (2023, 2024, 2025, 2026):
        indices = [i for i, day in enumerate(dates) if day.year == year]
        if not indices or indices[0] < WARMUP:
            raise ValueError('insufficient_window_history_or_warmup')
        first, last = dates[indices[0]], dates[indices[-1]]
        if year == 2026 and (first.month != 1 or first.day > 10 or last.isoformat() != FIXED_CUTOFF):
            raise ValueError('fixed_2026_ytd_window_required')
        if year < 2026 and (len(indices) < 200 or first.month != 1 or first.day > 10
                            or last.month != 12 or last.day < 20
                            or {dates[i].month for i in indices} != set(range(1, 13))):
            raise ValueError('complete_annual_windows_required')
        result.append({'id': str(year) if year < 2026 else '2026YTD',
                       'role': 'development_retrospective' if year == 2023 else 'historical_test',
                       'first_session': first.isoformat(), 'last_session': last.isoformat(),
                       'start_index': indices[0], 'end_index': indices[-1] + 1,
                       'warmup_start_index': indices[0] - WARMUP,
                       'sessions': len(indices)})
    if dates[-1].isoformat() != FIXED_CUTOFF:
        raise ValueError('experiment_requires_2026_data_cutoff')
    return result


def prepare_experiment(bundle, output, *, now=None, source_bytes=None):
    """Write the complete preregistration before any engine call, in a new folder."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('timezone_required')
    data = equity_data(bundle, now)
    execution = causal_execution_bundle(data)
    period_plan = windows(data)
    raw = encoded(bundle) if source_bytes is None else source_bytes
    if canonical_hash(json.loads(raw)) != canonical_hash(bundle):
        raise ValueError('source_bytes_bundle_mismatch')
    code = source_hashes()
    fixed_rules = rules(data)
    plan = {'schema_version': 1, 'created_at': now.isoformat(),
            'experiment': 'offline_retrospective_equities', 'currency': data['currency'],
            'assets': [a['id'] for a in data['assets']],
            'source_hashes': code, 'source_code_sha256': canonical_hash(code),
            'bundle_file_sha256': digest(raw), 'original_bundle_sha256': canonical_hash(bundle),
            'validated_bundle_sha256': canonical_hash(data),
            'execution_bundle_sha256': canonical_hash(execution),
            'rules': fixed_rules, 'rules_sha256': canonical_hash(fixed_rules),
            'windows': period_plan, 'quality_via_research': quality(data),
            'quality_independently_verified': False, 'universe_policy': 'fixed_historical',
            'survivorship_bias': True, 'broker_connected': False,
            'real_money_eligible': False, 'promotion_permitted': False}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chmod(output, 0o700)
    private_write(output / 'bundle.json', raw)
    private_write(output / 'plan.json', encoded(plan))
    private_write(output / 'plan.sha256', canonical_hash(plan) + '\n')
    return plan


def benchmark_fills(data, scenario):
    """Describe the buy/hold model's first-open fills, including idle cash.

    This is the same whole-lot sizing rule as the engine, not equal risk exposure.
    Splits after entry may subsequently change the reported exit quantities.
    """
    fills = []
    for asset in data['assets']:
        bar = asset['bars'][WARMUP]
        price = bar['open'] * (1 + scenario['slippage'])
        lot = float(asset.get('lot_size', 1))
        quantity = math.floor(max(0, 20 - scenario['min_commission']) /
                              (price * (1 + scenario['fee'])) / lot) * lot
        quantity = min(quantity, math.floor(bar['volume'] * 0.01 / lot) * lot)
        notional = quantity * price
        cost = notional + max(scenario['min_commission'], notional * scenario['fee']) if quantity else 0
        if cost > 20 + 1e-8:
            quantity, notional, cost = 0, 0, 0
        fills.append({'asset': asset['id'], 'quantity': quantity,
                      'initial_notional': notional, 'initial_cash_spent': cost})
    return {'initial_fills': fills, 'initial_notional_exposure_pct': sum(f['initial_notional'] for f in fills),
            'initial_idle_cash': 100 - sum(f['initial_cash_spent'] for f in fills)}


def variant_verdict(rows):
    conservative = [r for r in rows if r['scenario'] in {'base', 'stress'}]
    if any(r['metrics']['profit'] < 0 or r['metrics']['halted'] for r in conservative):
        return {'verdict': 'rejet_experimental', 'reason': 'perte_ou_arret_risque_dans_une_fenetre'}
    if any(r['metrics']['closed_trades'] == 0 for r in conservative):
        return {'verdict': 'inconclusif', 'reason': 'au_moins_une_fenetre_sans_transaction'}
    if any(r['metrics']['closed_trades'] < 5 for r in conservative):
        return {'verdict': 'inconclusif', 'reason': 'transactions_trop_rares'}
    return {'verdict': 'inconclusif', 'reason': 'historique_exploratoire_sans_validation_future'}


def markdown_report(plan, results):
    currency = plan['currency']
    lines = ['# Expérience actions rétrospective', '',
             f"Verdict global : **{results['verdict']}**. Aucune sélection de gagnant ni promotion.", '',
             f'Budget fictif : 100 {currency}, allocation maximale de 20 {currency} par instrument, lots entiers.',
             'Chaque fenêtre repart de 100. Cash et buy/hold utilisent les mêmes dates, lots et coûts,',
             'sans arrêt de drawdown ; leur risque et leur exposition effective peuvent donc différer.', '',
             '2023 est le développement descriptif ; 2024, 2025 et 2026YTD sont des tests historiques.',
             'Toutes les périodes sont rétrospectives et exploratoires, sans holdout prospectif.',
             'Les quatre variantes préfixées et les trois scénarios sont publiés intégralement.', '',
             'Coûts par côté : base 0,1 %, minimum 1, glissement 0,1 % ; stress 0,1 %, minimum 1,',
             'glissement 0,25 %. Zéro commission : hypothèse séparée (frais/minimum 0, glissement 0,1 %).',
             'Ce sont des hypothèses de simulation, aucun tarif courtier vérifié. Fiscalité, change,',
             'garde et frais de financement ne sont pas modélisés.', '',
             'Univers fixe choisi rétrospectivement : biais de survivance. Qualité déclarée via',
             f"research.quality : {plan['quality_via_research']}, vérification indépendante : False.",
             'La couverture annuelle est contrôlée par nombre de séances et bornes janvier/décembre ;',
             'elle ne certifie pas les calendriers ni toutes les opérations sur titres.', '',
             'Signaux OHLC inchangés ; décisions sur les clôtures passées, achats à l’ouverture suivante.',
             'Le plafond de liquidité utilise exclusivement le volume de la séance précédente.',
             'La première séance sans antécédent ne peut pas être tradée ; 200 séances de préchauffage',
             'précèdent chaque fenêtre et ne portent aucune transaction. Les stops intrajournaliers',
             'utilisent low et min(stop, ouverture) : approximation sans séquence intraday ni spread réel.',
             'La clôture forcée de fin de fenêtre applique aussi les coûts. Aucun paper trading courtier,',
             'compte, ordre réel, validation réelle ou autorisation de production.', '',
             f"Empreinte du plan : `{canonical_hash(plan)}`.",
             f"Code : `{plan['source_code_sha256']}`.",
             f"Bundle original : `{plan['original_bundle_sha256']}`.",
             f"Bundle d’exécution (volume J-1) : `{plan['execution_bundle_sha256']}`."]
    lines += ['', 'Variantes préfixées (moyenne rapide / lente, fenêtre de breakout) :']
    for index, spec in enumerate(plan['rules']['templates']):
        lines.append(f"- template_{index} : {spec['fast']} / {spec['slow']} séances, breakout {spec['breakout']} séances ; "
                     f"stop {spec['stop_loss'] * 100:g} %, durée maximale {spec['max_hold']} séances.")
    for window in plan['windows']:
        lines += ['', f"## {window['id']} : {window['first_session']} au {window['last_session']}", '',
                  '| Variante | Coûts | Gain net | Rendement | Drawdown | Transactions | Verdict |',
                  '| --- | --- | ---: | ---: | ---: | ---: | --- |']
        for row in results['runs']:
            if row['window'] != window['id']:
                continue
            m = row['metrics']
            verdict = results['variant_verdicts'].get(row['variant'], {}).get('verdict', 'référence')
            lines.append(f"| {row['variant']} | {row['scenario']} | {m['profit']:.3f} {currency} | "
                         f"{m['return_pct']:.3f} % | {m['max_drawdown_pct']:.3f} % | {m['closed_trades']} | {verdict} |")
        lines += ['']
        for row in results['runs']:
            if row['window'] == window['id'] and row['variant'] == 'buy_hold':
                fills = row['benchmark_fills']
                quantities = ', '.join(f"{f['asset']} : {f['quantity']:g}" for f in fills['initial_fills'])
                lines.append(f"Référence buy/hold {row['scenario']} : exposition initiale "
                             f"{fills['initial_notional_exposure_pct']:.3f} %, cash "
                             f"{fills['initial_idle_cash']:.3f} {currency}, quantités ({quantities}).")
    lines += ['', 'Les transactions absentes et quantités nulles restent visibles dans les références.',
              'Courbes et transactions détaillées : curves.json/CSV et trades.json/CSV, fichiers privés.', '']
    return '\n'.join(lines)


def run_prepared(output):
    """Verify preregistration, claim it once, then publish every fixed run."""
    output = Path(output)
    plan = json.loads((output / 'plan.json').read_bytes())
    if canonical_hash(plan) != (output / 'plan.sha256').read_text().strip():
        raise ValueError('preregistered_plan_changed')
    if source_hashes() != plan['source_hashes']:
        raise ValueError('preregistered_source_changed')
    raw = (output / 'bundle.json').read_bytes()
    if digest(raw) != plan['bundle_file_sha256']:
        raise ValueError('preregistered_bundle_changed')
    bundle = json.loads(raw)
    data = equity_data(bundle, stamp(plan['created_at']))
    execution = causal_execution_bundle(data)
    if (canonical_hash(bundle) != plan['original_bundle_sha256']
            or canonical_hash(data) != plan['validated_bundle_sha256']
            or canonical_hash(execution) != plan['execution_bundle_sha256']
            or rules(data) != plan['rules'] or canonical_hash(rules(data)) != plan['rules_sha256']
            or windows(data) != plan['windows']):
        raise ValueError('preregistered_inputs_or_rules_changed')
    if output.stat().st_mode & 0o077:
        raise ValueError('private_experiment_directory_required')
    private_write(output / 'started.json', encoded({'plan_sha256': canonical_hash(plan)}))
    runs, curves, trades = [], {}, {}
    for window in plan['windows']:
        sample = subset(execution, window['warmup_start_index'], window['end_index'])
        variants = [(f'template_{i}', spec, True) for i, spec in enumerate(plan['rules']['templates'])]
        variants += [('cash', {'family': 'cash'}, False), ('buy_hold', {'family': 'buy_hold'}, False)]
        for variant, spec, risk in variants:
            for scenario, scenario_costs in plan['rules']['cost_scenarios'].items():
                result = simulate(deepcopy(sample), spec, initial=100, allocation=20,
                                  start_index=WARMUP, risk_control=risk, close_at_end=True,
                                  **scenario_costs)
                key = f"{window['id']}/{variant}/{scenario}"
                row = {'window': window['id'], 'variant': variant, 'spec': spec,
                       'scenario': scenario, 'costs': scenario_costs, 'risk_control': risk,
                       'metrics': compact(result), 'series_key': key}
                if variant == 'buy_hold':
                    row['benchmark_fills'] = benchmark_fills(sample, scenario_costs)
                runs.append(row)
                curves[key], trades[key] = result['curve'], result['trades']
    verdicts = {f'template_{i}': variant_verdict([r for r in runs if r['variant'] == f'template_{i}'])
                for i in range(len(TEMPLATES))}
    results = {'schema_version': 1, 'plan_sha256': canonical_hash(plan),
               'verdict': 'rejet_experimental' if all(v['verdict'] == 'rejet_experimental' for v in verdicts.values()) else 'inconclusif',
               'variant_verdicts': verdicts, 'runs': runs, 'selection': None,
               'broker_connected': False, 'real_money_eligible': False,
               'promotion_permitted': False, 'quality_independently_verified': False}
    artifacts = {'results.json': encoded(results), 'curves.json': encoded(curves),
                 'trades.json': encoded(trades), 'report.md': markdown_report(plan, results).encode()}
    for name, series, fields in [('curves.csv', curves, ['date', 'equity']),
                                 ('trades.csv', trades, ['asset', 'entry_session', 'exit_session', 'reason', 'profit', 'quantity'])]:
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=['run', *fields]); writer.writeheader()
        for key, values in series.items():
            for value in values:
                writer.writerow({'run': key, **{field: value.get(field, '') for field in fields}})
        artifacts[name] = stream.getvalue().encode()
    for name, content in artifacts.items():
        private_write(output / name, content)
    private_write(output / 'outputs.sha256.json', encoded({name: digest(content) for name, content in artifacts.items()}))
    return results


def run_experiment(bundle, output, *, now=None, source_bytes=None):
    prepare_experiment(bundle, output, now=now, source_bytes=source_bytes)
    return run_prepared(output)
