VARIANTS: dict[str, list[dict[str, int | float]]] = {
    "TSMOM": [{"lookback": lb} for lb in (5, 7, 10, 14, 21, 30, 45, 63, 90, 126, 180, 252)],
    "MARegimeFilter": [{"ma_period": p} for p in (20, 30, 50, 75, 100, 150, 200)],
    "VolatilityBreakout": [
        {"atr_period": ap, "quantile": q}
        for ap in (7, 14, 21)
        for q in (0.6, 0.7, 0.8, 0.9)
    ],
    "ZScoreMeanReversion": [
        {"period": p, "entry_z": z}
        for p in (5, 10, 20, 40)
        for z in (-1.0, -1.5, -2.0, -2.5)
    ],
    "RegimeSwitching": [
        {"regime_period": rp, "trend_lookback": tl}
        for rp in (20, 50, 100, 200)
        for tl in (10, 14, 30, 60, 90)
    ],
}
