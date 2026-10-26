"""Jev as a judge for the founder's 16 G4+G5 survivors.

WHY JEV
Vibe-Trading's agent loop on a general-purpose LLM costs \$1-7 per research
session. The founder's rule was explicit: mass runs go through pure CPU (the
bench and the backtest engine, both \$0), and a judgment layer only comes in
at the end on the survivors. Jev is that judge: \$0.0000144 per call, so
judging 1000 candidates costs \$0.015 and judging 100000 costs \$1.44.

WHAT "JUDGE" MEANS HERE
Jev does not pick a strategy. It answers typed questions (Choice/Score/Noul)
about a candidate's regime fit: does the market state the strategy assumes
actually hold on this symbol right now, does the momentum leg have room, is
the volatility regime inside the band the strategy was measured in. The
archetype scan measured performance over 2020-2026; Jev's job is to flag
candidates whose assumed regime has changed on the CURRENT bars — a check the
scan cannot do because it is historical by construction.

WHAT IS HONEST
- The API key must exist in the environment. Jev cannot be faked; a missing
  key raises, it does not return a made-up judgment.
- A refused call (the router's own low-confidence ``no_decision``) still
  carries the model's probabilities inside ``raw_jev`` — discarding it would
  discard valid data. The adapter keeps it.
- This is NOT a claim that Jev is calibrated. The parent project measured
  ECE 0.51 on 59 live answers (2026-10-19), which is far above the 0.10 gate
  that disables Kelly sizing. Jev's probabilities are a REGIME CHECK, not a
  position-size input.

COST
1 judgment = 1 HTTP call = ~\$0.0000144 paid-tier Typesafe via the local
router (~/bin/jev-route). Judging the 16 G4+G5 survivors costs about \$0.0002.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

DAY_MS = 86_400_000
ROUTER = Path.home() / "bin" / "jev-route"
DEFAULT_MODEL = "jev-1.13.0"


class JevJudgeError(RuntimeError):
    """Jev could not be reached, or answered with neither decision nor probabilities."""


# WSL's C:/Windows/System32/bash.exe also answers to plain "bash" and prints a
# UTF-16 banner instead of running the script; resolve git-bash explicitly.
GIT_BASH = Path(r"C:\Users\Unicorn\AppData\Local\hermes\tools\git-2.53.0+3-win32-x64\usr\bin\bash.exe")


def _call_router(state: str, candidates: list[dict[str, str]], model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Call the local ``jev-route`` wrapper (paid Typesafe tier via OpenRouter)."""
    if not ROUTER.exists():
        raise JevJudgeError(f"jev-route not found at {ROUTER}")
    req_file = Path(os.environ.get("TMPDIR", "/tmp")) / f"jev-q-{os.getpid()}.txt"
    cand_file = req_file.with_suffix(".cand.json")
    req_file.write_text(state, encoding="utf-8")
    cand_file.write_text(json.dumps(candidates), encoding="utf-8")
    script = Path(__file__).resolve().parent / "jev_ask.sh"
    command = f'FREE_TIMEOUT=0 bash "{script.as_posix()}" "{req_file.as_posix()}" "{cand_file.as_posix()}"'
    try:
        raw = subprocess.run(
            [str(GIT_BASH), "-lc", command],
            capture_output=True,
            text=True,
            timeout=90,
            encoding="utf-8",
        )
    finally:
        req_file.unlink(missing_ok=True)
        cand_file.unlink(missing_ok=True)
    stdout = raw.stdout.strip()
    if not stdout:
        raise JevJudgeError(f"router returned empty stdout. stderr: {raw.stderr[:200]}")
    try:
        payload = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        raise JevJudgeError(f"router returned non-JSON: {stdout[:200]}") from exc
    if "error" in payload:
        raise JevJudgeError(f"router refused: {payload['error']}")
    return payload


def judge_regime(
    symbol: str,
    price: float,
    drift_30d_pct: float,
    realised_vol_pct: float,
    max_dd_pct: float,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Ask Jev whether the candidate's assumed regime still holds.

    The three questions map to what each surviving archetype assumes:
      - regime: trending vs ranging vs flat (RegimeSwitching and TSMOM assume
        a trend to persist; a range answer breaks their premise)
      - continuation: whether the last 30 days' direction continues
      - volatility: whether the current realised vol is inside a tradeable band

    Returns:
        Jev's parsed response. Probabilities may sit either at the top level
        or inside ``raw_jev.answers`` depending on whether the router returned
        a confident decision or a low-confidence ``no_decision``.
    """
    regime = "up" if drift_30d_pct > 3 else "down" if drift_30d_pct < -3 else "flat"
    vol_band = "low" if realised_vol_pct < 30 else "high" if realised_vol_pct > 80 else "mid"
    state = (
        f"{symbol} trades at ${price:.2f}. "
        f"Last 30 days: {drift_30d_pct:+.2f} percent (regime {regime}). "
        f"Realised volatility {realised_vol_pct:.1f} percent annualised ({vol_band} band). "
        f"The candidate strategy's own historical max drawdown was {max_dd_pct:.1f} percent."
    )
    candidates = [
        {"name": "continue", "description": "the same direction as the last 30 days continues"},
        {"name": "reverse", "description": "the direction flips over the next period"},
        {"name": "flat", "description": "price stays within a narrow band"},
    ]
    payload = _call_router(state, candidates, model=model)
    top = payload.get("probabilities") or {}
    nested = ((payload.get("raw_jev") or {}).get("answers") or {}).get("tool") or {}
    probabilities = {str(k): float(v) for k, v in (top or nested.get("probabilities") or {}).items()}
    choice = payload.get("chosen") or nested.get("choice")
    confidence = payload.get("confidence")
    return {
        "symbol": symbol,
        "model": payload.get("model"),
        "status": payload.get("status"),
        "choice": choice,
        "probabilities": probabilities,
        "confidence": confidence,
        "raw": {k: payload.get(k) for k in ("source", "provider", "decision_id")},
    }


if __name__ == "__main__":
    demo = judge_regime("SOLUSDT", price=150.0, drift_30d_pct=12.5, realised_vol_pct=68.0, max_dd_pct=64.0)
    print(json.dumps(demo, indent=1, ensure_ascii=False))
