"""Native pinned-image check, with no network or operational state mounted."""
import subprocess

IMAGE='freqtradeorg/freqtrade:2026.9@sha256:9d67afb8eb5f4e1210f4fb067efcbd5e005bd4f1c27f6f3888b8b9fc7f9b5199'
CODE='''
import sys,json
from pathlib import Path
sys.path[:0]=['/candidate/user_data/strategies','/candidate/supervisor']
from freqtrade.enums import RunMode
from freqtrade.resolvers import StrategyResolver
config=json.loads(Path('/candidate/user_data/config.dryrun.json').read_text())
config.update(user_data_dir=Path('/candidate/user_data'),strategy_path='/candidate/user_data/strategies',runmode=RunMode.DRY_RUN)
strategy=StrategyResolver.load_strategy(config)
strategy.bot_start()
assert strategy.stoploss == -1.0
assert all(p['method'] != 'StoplossGuard' for p in strategy.protections)
from datetime import datetime,timezone
args=dict(pair='XBT/EUR',trade=None,order_type='limit',amount=1,rate=1,time_in_force='GTC',current_time=datetime.now(timezone.utc))
assert strategy.confirm_trade_exit(exit_reason='stop_loss',**args) is False
assert strategy.confirm_trade_exit(exit_reason='exit_signal',**args) is True
print(json.dumps({'native_strategy_verified':type(strategy).__name__,'stoploss':strategy.stoploss,'dry_run':config['dry_run'],'wallet':config['dry_run_wallet']}))
'''


def check(root):
    if not (root/'simulation-policy.json').exists():
        return
    result=subprocess.run(['docker','run','--rm','--network','none','--memory','512m','--cpus','1',
                           '--entrypoint','python','-e','SIMULATION_POLICY_FILE=/candidate/simulation-policy.json',
                           '-v',str(root)+':/candidate:ro',IMAGE,'-c',CODE],
                          check=True,capture_output=True,text=True,timeout=60)
    print(result.stdout.strip())
