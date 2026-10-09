"""FreqAI LightGBM shadow readiness. Never starts a bot or downloads an image."""
import os
import re

IMAGE_RE = re.compile(r"^freqtradeorg/freqtrade:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")

def status(image=None):
    image = (image if image is not None else os.environ.get("FREQAI_SHADOW_IMAGE", "")).strip()
    if not image:
        return {
            "state": "blocked_unpinned_image",
            "model": "LightGBMRegressor",
            "reason": "immutable_freqai_image_required",
            "automatic_live_deployment": False,
            "real_money_eligible": False,
        }
    if not IMAGE_RE.fullmatch(image):
        return {
            "state": "blocked_mutable_or_invalid_image",
            "model": "LightGBMRegressor",
            "reason": "freqai_image_must_be_digest_pinned",
            "automatic_live_deployment": False,
            "real_money_eligible": False,
        }
    return {
        "state": "ready_for_offline_backtest",
        "model": "LightGBMRegressor",
        "image": image,
        "automatic_live_deployment": False,
        "real_money_eligible": False,
    }

def config(identifier="moussa-v3-freqai-shadow"):
    if not identifier or len(identifier) > 80:
        raise ValueError("invalid_freqai_identifier")
    return {
        "enabled": True,
        "purge_old_models": 2,
        "train_period_days": 30,
        "backtest_period_days": 7,
        "live_retrain_hours": 12,
        "identifier": identifier,
        "feature_parameters": {
            "include_timeframes": ["15m", "1h", "4h"],
            "include_corr_pairlist": ["XBT/EUR", "ETH/EUR"],
            "label_period_candles": 24,
            "include_shifted_candles": 2,
            "indicator_periods_candles": [10, 20, 50],
        },
        "data_split_parameters": {
            "test_size": 0.25,
            "shuffle": False,
        },
    }
