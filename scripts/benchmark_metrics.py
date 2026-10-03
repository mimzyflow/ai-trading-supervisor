def passive_net_return(price_return, fee_per_side=0.008, exposure=0.4):
    if not 0 <= exposure <= 1 or not 0 <= fee_per_side < 1 or price_return < -1:
        raise ValueError("invalid_benchmark_inputs")
    # Entry and exit fees; no rebalancing, slippage or return on idle cash.
    return exposure * ((1 + price_return) * (1 - fee_per_side) ** 2 - 1)
