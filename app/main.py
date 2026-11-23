import os
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.data import get_market_data
from app.strategy import analyze_market
from app.alerts import send_telegram_alert

app = FastAPI(title="XAUUSD Trading Desk Pro")

LAST_SIGNAL = None
LAST_ERROR = None
LAST_CHECK = None


def get_session():
    hour = datetime.now(timezone.utc).hour

    if 0 <= hour < 8:
        return "Asian"
    if 8 <= hour < 13:
        return "London"
    if 13 <= hour < 22:
        return "New York"
    return "Market transition"


def run_analysis():
    global LAST_SIGNAL, LAST_ERROR, LAST_CHECK

    LAST_CHECK = datetime.now(timezone.utc).isoformat()

    try:
        market = get_market_data()
        result = analyze_market(market["h4"], market["m15"])

        result["session"] = get_session()
        result["checked_at_utc"] = LAST_CHECK

        # Alert only when a new LONG or SHORT signal appears.
        if result["signal"] in ("LONG", "SHORT"):
            key = (
                result["signal"],
                result["entry"],
                result["stop_loss"],
            )

            if key != LAST_SIGNAL:
                send_telegram_alert(result)
                LAST_SIGNAL = key

        LAST_ERROR = None
        return result

    except Exception as exc:
        LAST_ERROR = str(exc)
        return {
            "signal": "NO TRADE",
            "entry": None,
            "stop_loss": None,
            "tp1": None,
            "tp2": None,
            "tp3": None,
            "session": get_session(),
            "reason": f"Market data unavailable: {LAST_ERROR}",
            "checked_at_utc": LAST_CHECK,
        }


@app.get("/", response_class=HTMLResponse)
def dashboard():
    result = run_analysis()

    def display(value):
        return "—" if value is None else str(value)

    signal = result["signal"]

    color = (
        "#16a34a" if signal == "LONG"
        else "#dc2626" if signal == "SHORT"
        else "#64748b"
    )

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <meta http-equiv="refresh" content="300">
      <title>XAUUSD Trading Desk Pro</title>
      <style>
        body {{
          margin: 0; padding: 20px;
          background: #101827; color: white;
          font-family: Arial, sans-serif;
        }}
        .card {{
          max-width: 600px; margin: 20px auto;
          padding: 24px; background: #1e293b;
          border-radius: 16px;
        }}
        h1 {{ color: #fbbf24; }}
        .signal {{
          font-size: 34px; font-weight: bold;
          color: {color};
        }}
        .item {{
          padding: 12px 0;
          border-bottom: 1px solid #334155;
        }}
        .note {{ color: #cbd5e1; line-height: 1.6; }}
        a {{ color: #fbbf24; }}
      </style>
    </head>
    <body>
      <div class="card">
        <h1>🟡 XAUUSD Trading Desk Pro</h1>
        <p>H4 Liquidity Sweep + M15 Confirmation</p>
        <p>Session: <b>{result.get("session", "Unknown")}</b></p>
        <p class="signal">{signal}</p>
        <div class="item">Entry: <b>{display(result.get("entry"))}</b></div>
        <div class="item">Stop Loss: <b>{display(result.get("stop_loss"))}</b></div>
        <div class="item">TP1: <b>{display(result.get("tp1"))}</b></div>
        <div class="item">TP2: <b>{display(result.get("tp2"))}</b></div>
        <div class="item">TP3: <b>{display(result.get("tp3"))}</b></div>
        <p class="note">Reason: {result.get("reason", "")}</p>
        <p class="note">Last check: {display(result.get("checked_at_utc"))} UTC</p>
        <p class="note">Refreshes every 5 minutes.</p>
        <p class="note">
          Manual lot sizing and manual trade execution only.
          No automatic orders.
        </p>
      </div>
    </body>
    </html>
    """

    return HTMLResponse(html)


@app.get("/api/signal")
def api_signal():
    return run_analysis()


@app.get("/health")
def health():
    return {"status": "ok"}
