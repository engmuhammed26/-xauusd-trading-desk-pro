from typing import Any, Dict
import pandas as pd


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Standardise candle columns and ensure chronological order."""
    data = df.copy()
    data.columns = [str(c).lower() for c in data.columns]

    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in data.columns]
    if missing:
        raise ValueError(f"Missing candle columns: {missing}")

    for col in required:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    data = data.dropna(subset=required)

    if "datetime" in data.columns:
        data["datetime"] = pd.to_datetime(data["datetime"])
        data = data.sort_values("datetime")
    elif "time" in data.columns:
        data["time"] = pd.to_datetime(data["time"])
        data = data.sort_values("time")

    return data.reset_index(drop=True)


def analyze_market(h4: pd.DataFrame, m15: pd.DataFrame) -> Dict[str, Any]:
    """
    H4 liquidity sweep with M15 breakout confirmation.
    Returns LONG, SHORT, or NO TRADE with risk levels.
    Analysis only: never places orders.
    """
    result = {
        "signal": "NO TRADE",
        "entry": None,
        "stop_loss": None,
        "tp1": None,
        "tp2": None,
        "tp3": None,
        "reason": "Waiting for a confirmed H4 sweep and M15 confirmation.",
    }

    try:
        h4 = _prepare(h4)
        m15 = _prepare(m15)

        if len(h4) < 3 or len(m15) < 6:
            result["reason"] = "Not enough candle data."
            return result

        # Latest completed H4 candle and the two candles before it.
        sweep = h4.iloc[-1]
        previous = h4.iloc[-3:-1]
        prior_high = float(previous["high"].max())
        prior_low = float(previous["low"].min())

        # Latest completed M15 candle and preceding four-candle range.
        confirm = m15.iloc[-1]
        range_before = m15.iloc[-5:-1]
        m15_high = float(range_before["high"].max())
        m15_low = float(range_before["low"].min())

        entry = float(confirm["close"])
        signal = None
        stop = None

        # Sweep below prior lows, reclaim, then M15 bullish breakout.
        bullish_sweep = (
            float(sweep["low"]) < prior_low
            and float(sweep["close"]) > prior_low
        )
        bullish_confirm = entry > m15_high and entry > float(confirm["open"])

        # Sweep above prior highs, reject, then M15 bearish breakout.
        bearish_sweep = (
            float(sweep["high"]) > prior_high
            and float(sweep["close"]) < prior_high
        )
        bearish_confirm = entry < m15_low and entry < float(confirm["open"])

        if bullish_sweep and bullish_confirm:
            signal = "LONG"
            stop = float(sweep["low"])
        elif bearish_sweep and bearish_confirm:
            signal = "SHORT"
            stop = float(sweep["high"])
        else:
            result["reason"] = (
                "No valid H4 liquidity sweep with matching M15 confirmation."
            )
            return result

        risk = abs(entry - stop)
        if risk <= 0:
            result["reason"] = "Invalid stop-loss distance."
            return result

        if signal == "LONG":
            targets = [entry + risk, entry + 2 * risk, entry + 3 * risk]
        else:
            targets = [entry - risk, entry - 2 * risk, entry - 3 * risk]

        result.update({
            "signal": signal,
            "entry": round(entry, 2),
            "stop_loss": round(stop, 2),
            "tp1": round(targets[0], 2),
            "tp2": round(targets[1], 2),
            "tp3": round(targets[2], 2),
            "reason": "H4 liquidity sweep and M15 confirmation detected.",
        })
        return result

    except Exception as exc:
        result["reason"] = f"Analysis error: {exc}"
        return result
