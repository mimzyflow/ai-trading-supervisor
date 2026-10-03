"""Fail closed before deploying or running the simulation."""
import json
import math
from pathlib import Path


def validate(config):
    if config.get("dry_run") is not True or config.get("trading_mode") != "spot":
        raise ValueError("simulation_spot_required")
    if config.get("stake_currency") != "EUR" or config.get("exchange", {}).get("name") != "kraken":
        raise ValueError("kraken_eur_required")
    for key, cap in [("stake_amount", 20), ("max_open_trades", 2), ("dry_run_wallet", 100)]:
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 < value <= cap:
            raise ValueError("invalid_" + key)
    if config.get("force_entry_enable"):
        raise ValueError("force_entry_forbidden")
    if any(config.get("exchange", {}).get(key) for key in ["key", "secret", "password"]):
        raise ValueError("exchange_credentials_not_needed_for_simulation")
    if config.get("add_config_files"):
        raise ValueError("unreviewed_config_overrides")
    return True


def main():
    root = Path(__file__).resolve().parents[1]
    validate(json.loads((root / "user_data/config.dryrun.json").read_text()))
    print("Simulation Kraken spot EUR validée : portefeuille <=100 EUR, 2 positions <=20 EUR, aucune clé exchange.")


if __name__ == "__main__":
    main()
