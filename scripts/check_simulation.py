"""Fail closed before deploying or running the simulation."""
import json
import math
from pathlib import Path


def validate(config):
    if config.get("dry_run") is not True or config.get("trading_mode") != "spot":
        raise ValueError("simulation_spot_required")
    if config.get("stake_currency") != "EUR" or config.get("exchange", {}).get("name") != "kraken":
        raise ValueError("kraken_eur_required")
    for key, cap in [("stake_amount", 20), ("dry_run_wallet", 100)]:
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 < value <= cap:
            raise ValueError("invalid_" + key)
    if config.get("max_open_trades") != -1:
        raise ValueError("position_count_must_be_unbounded_in_dry_run")
    if config.get("force_entry_enable"):
        raise ValueError("force_entry_forbidden")
    if any(config.get("exchange", {}).get(key) for key in ["key", "secret", "password"]):
        raise ValueError("exchange_credentials_not_needed_for_simulation")
    if config.get("add_config_files"):
        raise ValueError("unreviewed_config_overrides")
    return True


CONTROL_CONFIG = "user_data/config.control.dryrun.json"
CONTROL_COMPOSE = "docker-compose.control.yml"
CONTROL_LOGFILE = "/freqtrade/runtime/control/freqtrade-control.log"
MAIN_LOGFILE = "/freqtrade/runtime/freqtrade.log"


def validate_control(config, reference=None):
    """Control account (MoussaControlStops): same rules + identical market setup."""
    validate(config)
    if config.get("strategy") != "MoussaControlStops":
        raise ValueError("control_strategy_mismatch")
    if reference is not None:
        for key in ["fee", "dry_run_wallet", "stake_currency", "timeframe", "trading_mode"]:
            if config.get(key) != reference.get(key):
                raise ValueError("control_differs_from_experiment_" + key)
        if config.get("exchange", {}).get("pair_whitelist") != reference.get("exchange", {}).get("pair_whitelist"):
            raise ValueError("control_differs_from_experiment_pair_whitelist")
    return True


def validate_control_compose(text):
    """Static check of the control Compose file (no Docker, no Oracle DB needed)."""
    required = ['FREQTRADE__DRY_RUN: "true"', "--dry-run", 'FREQTRADE__EXCHANGE__KEY: ""',
                'FREQTRADE__EXCHANGE__SECRET: ""', "127.0.0.1:8081:8080"]
    for needle in required:
        if needle not in text:
            raise ValueError("control_compose_missing:" + needle)
    if "trades-market-room-100eur-20261009" in text:
        raise ValueError("control_compose_shares_experiment_db")
    # Journal dédié : le bot principal écrit MAIN_LOGFILE ; partager ce chemin a
    # provoqué une boucle de redémarrage (PermissionError) du témoin.
    if "--logfile " + CONTROL_LOGFILE not in text:
        raise ValueError("control_compose_missing_dedicated_logfile")
    if MAIN_LOGFILE in text:
        raise ValueError("control_compose_shares_experiment_logfile")
    return True


def main():
    root = Path(__file__).resolve().parents[1]
    reference = json.loads((root / "user_data/config.dryrun.json").read_text())
    validate(reference)
    if (root / CONTROL_CONFIG).exists():
        validate_control(json.loads((root / CONTROL_CONFIG).read_text()), reference)
        if (root / CONTROL_COMPOSE).exists():
            validate_control_compose((root / CONTROL_COMPOSE).read_text())
        print("Compte témoin MoussaControlStops validé : dry-run, mêmes frais/univers/capital, aucune clé.")
    print("Simulation Kraken spot EUR validée : portefeuille <=100 EUR, positions non plafonnées par nombre, stake <=20 EUR, aucune clé exchange.")


if __name__ == "__main__":
    main()
