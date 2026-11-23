import os
import requests
import pandas as pd

API_URL = "https://api.twelvedata.com/time_series"


def get_candles(interval: str, outputsize: int = 100) -> pd.DataFrame:
    api_key = os.getenv("TWELVEDATA_API_KEY")

    if not api_key:
        raise RuntimeError("TWELVEDATA_API_KEY is not configured.")

    params = {
        "symbol": "XAU/USD",
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
        "format": "JSON",
        "timezone": "UTC",
    }

    response = requests.get(API_URL, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()

    if "values" not in data:
        message = data.get("message", data.get("code", "No candle data returned"))
        raise RuntimeError(f"Twelve Data error: {message}")

    df = pd.DataFrame(data["values"])

    for column in ["open", "high", "low", "close"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["datetime"] = pd.to_datetime(
        df["datetime"], errors="coerce", utc=True
    )

    df = df.dropna(
        subset=["datetime", "open", "high", "low", "close"]
    )

    df = df.sort_values("datetime").reset_index(drop=True)

    # Exclude candles that have not fully closed.
    now_utc = pd.Timestamp.now(tz="UTC")
    duration = (
        pd.Timedelta(hours=4)
        if interval == "4h"
        else pd.Timedelta(minutes=15)
    )

    df = df[
        df["datetime"] + duration <= now_utc
    ].reset_index(drop=True)

    if df.empty:
        raise RuntimeError("No completed candles available.")

    return df


def get_market_data():
    return {
        "h4": get_candles("4h"),
        "m15": get_candles("15min"),
    }
