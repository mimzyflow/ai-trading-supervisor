"""Paramétrable cost scenarios for simulation only. Not broker quotes.

Chaque scénario sépare explicitement les frais (par côté) et le glissement
(par côté). Le scénario historique 0,80 % est conservé comme cas dégradé
afin que les anciens résultats restent comparables.
"""
import math

SCENARIOS = {
    # Ordres limites passifs : hypothèse maker ~0,25 % par côté.
    'maker_realistic': {'fee': 0.0025, 'slippage': 0.0010, 'min_commission': 0.0},
    # Ordres agressifs : hypothèse taker ~0,40 % par côté.
    'taker': {'fee': 0.0040, 'slippage': 0.0015, 'min_commission': 0.0},
    # Ancien modèle du dépôt (0,80 % par côté), conservé comme scénario dégradé.
    'legacy_degraded': {'fee': 0.0080, 'slippage': 0.0010, 'min_commission': 0.0},
    # Stress identique à research.costs(stressed=True) pour la crypto.
    'stress': {'fee': 0.0120, 'slippage': 0.0025, 'min_commission': 0.0},
}
DEFAULT_SCENARIO = 'maker_realistic'
MAX_SIDE_COST = 0.02


def scenario(name=DEFAULT_SCENARIO, fee=None, slippage=None, min_commission=None):
    """Return engine kwargs; explicit overrides must stay within engine bounds."""
    if name not in SCENARIOS:
        raise ValueError('unknown_cost_scenario')
    out = dict(SCENARIOS[name])
    for key, value in (('fee', fee), ('slippage', slippage), ('min_commission', min_commission)):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('invalid_cost_override')
        out[key] = float(value)
    if out['fee'] > MAX_SIDE_COST or out['slippage'] > MAX_SIDE_COST:
        raise ValueError('cost_override_out_of_bounds')
    return out


def round_trip_pct(costs):
    """Approximate round-trip cost in percent (fees + slippage, both sides)."""
    return round(2 * (costs['fee'] + costs['slippage']) * 100, 6)


def freqtrade_fee(name=DEFAULT_SCENARIO):
    """Freqtrade --fee has no slippage term: fold slippage into the per-side fee."""
    costs = scenario(name)
    return round(costs['fee'] + costs['slippage'], 6)


def all_scenarios():
    return {name: dict(values, round_trip_pct=round_trip_pct(values)) for name, values in SCENARIOS.items()}
