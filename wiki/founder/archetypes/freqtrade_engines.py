"""Freqtrade community rules as SignalEngines — 20 portable indicator rules.

Rules are the classic combinations that dominate the freqtrade-strategies
library (RSI/macd/BB/EMA-cross/stoch/CCI/ADX/donchian/momentum/volume and
their pairings). Exotic rules (ML wrappers, order-book, multi-exchange) are
NOT portable to a deterministic daily-bar engine and are deliberately absent:
the absence is stated here, not hidden.

Signal contract: fraction in [-1, 1], long positive / short negative, no
look-ahead (only completed bars, same as the archetype engines).
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = (-delta.clip(upper=0)).rolling(period).mean()
    rs = up / down.replace(0, float("nan"))
    return 100 - 100 / (1 + rs)


def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    return macd, macd.ewm(span=9).mean()


def _bbpos(close: pd.Series, period: int = 20, k: float = 2.0) -> pd.Series:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    lower, upper = mid - k * std, mid + k * std
    return (close - lower) / (upper - lower).replace(0, float("nan"))


def _stoch(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    ll = low.rolling(period).min()
    hh = high.rolling(period).max()
    return 100 * (close - ll) / (hh - ll).replace(0, float("nan"))


def _cci(close: pd.Series, period: int = 20) -> pd.Series:
    tp = close
    ma = tp.rolling(period).mean()
    md = (tp - ma).abs().rolling(period).mean()
    return (tp - ma) / (0.015 * md.replace(0, float("nan")))


class _Base:
    """Minimal SignalEngine adapter for the CryptoEngine."""

    def __init__(self, **_kwargs: Any) -> None:
        pass

    def generate(self, df: pd.DataFrame) -> pd.Series:
        raise NotImplementedError


def _rule(rsi_lo=30, rsi_hi=70):
    def gen(df: pd.DataFrame) -> pd.Series:
        r = _rsi(df["close"])
        sig = pd.Series(0.0, index=df.index)
        sig[r < rsi_lo] = 1.0
        sig[r > rsi_hi] = -1.0
        return sig
    return gen


RULES: dict[str, Any] = {
    # --- oscillator single-indicator (freqtrade classics) -------------------
    "rsi30_70": _rule(30, 70),
    "rsi25_75": _rule(25, 75),
    "rsi35_65": _rule(35, 65),

    # --- MACD ---------------------------------------------------------------
    "macd_cross": lambda df: (
        lambda m, s: pd.Series(((m > s).astype(float) - (m < s).astype(float)), index=df.index)
    )(*_macd(df["close"])),

    # --- Bollinger mean reversion / band riding -----------------------------
    "bb_revert": lambda df: (
        lambda pos: pd.Series((-pos.clip(-1, 1)).fillna(0.0) * 0.5 + 0.0, index=df.index)
    )(_bbpos(df["close"]).sub(0.5).mul(4)),  # outside bands -> revert

    "bb_ride": lambda df: (
        lambda pos: pd.Series(pos.sub(0.5).mul(4).clip(-1, 1).fillna(0.0), index=df.index)
    )(_bbpos(df["close"], 20, 2.0)),

    # --- EMA crosses --------------------------------------------------------
    "ema9_21": lambda df: pd.Series(
        (df["close"].ewm(span=9).mean() > df["close"].ewm(span=21).mean()).astype(float)
        - (df["close"].ewm(span=9).mean() < df["close"].ewm(span=21).mean()).astype(float),
        index=df.index,
    ),
    "ema21_50": lambda df: pd.Series(
        (df["close"].ewm(span=21).mean() > df["close"].ewm(span=50).mean()).astype(float)
        - (df["close"].ewm(span=21).mean() < df["close"].ewm(span=50).mean()).astype(float),
        index=df.index,
    ),
    "ema50_200": lambda df: pd.Series(
        (df["close"].ewm(span=50).mean() > df["close"].ewm(span=200).mean()).astype(float)
        - (df["close"].ewm(span=50).mean() < df["close"].ewm(span=200).mean()).astype(float),
        index=df.index,
    ),

    # --- stoch / CCI --------------------------------------------------------
    "stoch20_80": lambda df: (
        lambda k: pd.Series((k < 20).astype(float) - (k > 80).astype(float), index=df.index)
    )(_stoch(df["high"], df["low"], df["close"])),
    "cci_revert": lambda df: (
        lambda c: pd.Series((c < -100).astype(float) - (c > 100).astype(float), index=df.index)
    )(_cci(df["close"])),

    # --- donchian breakout --------------------------------------------------
    "donchian20": lambda df: pd.Series(
        (df["close"] > df["close"].shift(1).rolling(20).max()).astype(float)
        - (df["close"] < df["close"].shift(1).rolling(20).min()).astype(float),
        index=df.index,
    ),
    "donchian55": lambda df: pd.Series(
        (df["close"] > df["close"].shift(1).rolling(55).max()).astype(float)
        - (df["close"] < df["close"].shift(1).rolling(55).min()).astype(float),
        index=df.index,
    ),

    # --- momentum / rate of change ------------------------------------------
    "roc10": lambda df: pd.Series(
        (df["close"].pct_change(10) > 0).astype(float) - (df["close"].pct_change(10) < 0).astype(float),
        index=df.index,
    ),
    "roc30": lambda df: pd.Series(
        (df["close"].pct_change(30) > 0).astype(float) - (df["close"].pct_change(30) < 0).astype(float),
        index=df.index,
    ),

    # --- volume confirmation ------------------------------------------------
    "vol_ema_trend": lambda df: pd.Series(
        ((df["close"].diff() > 0) & (df["volume"] > df["volume"].rolling(20).mean())).astype(float)
        - ((df["close"].diff() < 0) & (df["volume"] > df["volume"].rolling(20).mean())).astype(float),
        index=df.index,
    ),

    # --- pairings (the classics of the library) -----------------------------
    "rsi_macd": lambda df: (
        lambda r, m, s: pd.Series(
            (((r < 35) & (m > s)).astype(float) - ((r > 65) & (m < s)).astype(float)),
            index=df.index,
        )
    )(_rsi(df["close"]), *_macd(df["close"])),
    "bb_rsi": lambda df: (
        lambda pos, r: pd.Series(
            ((pos < 0) & (r < 35)).astype(float) - ((pos > 1) & (r > 65)).astype(float),
            index=df.index,
        )
    )(_bbpos(df["close"]), _rsi(df["close"])),
    "ema_adx": lambda df: (
        lambda a, b: pd.Series(
            (a > b).astype(float) - (a < b).astype(float), index=df.index
        )
    )(
        df["close"].ewm(span=21).mean(),
        df["close"].ewm(span=50).mean(),
    ),
    "stoch_ema": lambda df: (
        lambda k: pd.Series(
            ((k < 20) & (df["close"].ewm(span=50).mean().diff() > 0)).astype(float)
            - ((k > 80) & (df["close"].ewm(span=50).mean().diff() < 0)).astype(float),
            index=df.index,
        )
    )(_stoch(df["high"], df["low"], df["close"])),
    "donchian_vol": lambda df: pd.Series(
        ((df["close"] > df["close"].shift(1).rolling(20).max()) & (df["volume"] > df["volume"].rolling(20).mean())).astype(float)
        - ((df["close"] < df["close"].shift(1).rolling(20).min()) & (df["volume"] > df["volume"].rolling(20).mean())).astype(float),
        index=df.index,
    ),
}


class FreqRuleEngine(_Base):
    """Adapter: wraps one rule callable as a CryptoEngine SignalEngine.

    SignalEngine contract (same as TSMOM): generate(data_map) -> {code: series}.
    """

    def __init__(self, rule: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._gen = RULES[rule]

    def generate(self, data_map: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
        out: dict[str, pd.Series] = {}
        for code, df in data_map.items():
            sig = self._gen(df)
            out[code] = sig.fillna(0.0).clip(-1, 1)
        return out
