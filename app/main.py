
import os
import time
import threading
import logging
from datetime import datetime, timezone

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.data import get_market_data
from app.strategy import analyze_market
from app.alerts import send_telegram_alert

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="XAUUSD Trading Desk Pro")

LAST_SIGNAL = None
LAST_RESULT = None
LAST_ERROR = None
LAST_CHECK = None

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

telegram_offset = 0
worker_started = False


def get_session():
    hour = datetime.now(timezone.utc).hour

    if 0 <= hour < 8:
        return "Asian"
    if 8 <= hour < 13:
        return "London"
    if 13 <= hour < 22:
        return "New York"
    return "Market transition"


def telegram_send(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Telegram environment variables are missing.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            },
            timeout=15
        )
        response.raise_for_status()
        return response.json().get("ok", False)
    except Exception as exc:
        logger.error("Telegram send error: %s", exc)
        return False


def format_result(result):
    return (
        "🟡 XAUUSD TRADING DESK PRO\n\n"
        f"Signal: {result.get('signal', 'NO TRADE')}\n"
        f"Session: {result.get('session', get_session())}\n"
        f"Entry: {result.get('entry', 'N/A')}\n"
        f"Stop Loss: {result.get('stop_loss', 'N/A')}\n"
        f"TP1: {result.get('tp1', 'N/A')}\n"
        f"TP2: {result.get('tp2', 'N/A')}\n"
        f"TP3: {result.get('tp3', 'N/A')}\n\n"
        f"Reason: {result.get('reason', 'N/A')}\n\n"
        "Analysis alerts only. Manual lot sizing and "
        "manual trade execution. No automatic orders."
    )


def run_analysis():
    global LAST_SIGNAL, LAST_RESULT, LAST_ERROR, LAST_CHECK

    LAST_CHECK = datetime.now(timezone.utc).isoformat()

    try:
        market = get_market_data()
        result = analyze_market(market["h4"], market["m15"])

        result["session"] = get_session()
        result["checked_at_utc"] = LAST_CHECK

        if result["signal"] in ("LONG", "SHORT"):
            key = (
                result["signal"],
                result["entry"],
                result["stop_loss"]
            )

            if key != LAST_SIGNAL:
                if send_telegram_alert(result):
                    LAST_SIGNAL = key

        LAST_ERROR = None
        LAST_RESULT = result
        return result

    except Exception as exc:
        LAST_ERROR = str(exc)

        result = {
            "signal": "NO TRADE",
            "entry": None,
            "stop_loss": None,
            "tp1": None,
            "tp2": None,
            "tp3": None,
            "session": get_session(),
            "reason": f"Market data unavailable: {LAST_ERROR}",
            "checked_at_utc": LAST_CHECK
        }

        LAST_RESULT = result
        logger.exception("Market analysis failed")
        return result


def analysis_worker():
    while True:
        run_analysis()
        time.sleep(900)


def telegram_worker():
    global telegram_offset

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Telegram token or chat ID is missing.")
        return

    base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

    while True:
        try:
            response = requests.get(
                f"{base_url}/getUpdates",
                params={
                    "offset": telegram_offset,
                    "timeout": 25
                },
                timeout=35
            )

            response.raise_for_status()
            updates = response.json()

            if not updates.get("ok"):
                time.sleep(5)
                continue

            for update in updates.get("result", []):
                telegram_offset = update["update_id"] + 1

                message = update.get("message", {})
                chat = message.get("chat", {})
                text = message.get("text", "").strip().lower()

                chat_id = str(chat.get("id", ""))

                if chat_id != str(TELEGRAM_CHAT_ID):
                    continue

                if text.startswith("/start"):
                    telegram_send(
                        "Welcome to XAUUSD Trading Desk Pro!\n\n"
                        "I monitor XAUUSD using H4 liquidity sweeps "
                        "and M15 confirmation.\n\n"
                        "Commands:\n"
                        "/start - Start the bot\n"
                        "/help - Show commands\n"
                        "/status - Get latest market analysis\n\n"
                        "Alerts only. No automatic trading."
                    )

                elif text.startswith("/help"):
                    telegram_send(
                        "XAUUSD Trading Desk Pro Commands\n\n"
                        "/start - Welcome message\n"
                        "/help - Show commands\n"
                        "/status - Latest market analysis\n\n"
                        "LONG = Buy setup\n"
                        "SHORT = Sell setup\n"
                        "NO TRADE = No confirmed setup\n\n"
                        "You choose your own lot size and "
                        "execute trades manually."
                    )

                elif text.startswith("/status"):
                    result = run_analysis()
                    telegram_send(format_result(result))

        except Exception as exc:
            logger.error("Telegram polling error: %s", exc)
            time.sleep(5)


@app.on_event("startup")
def start_workers():
    global worker_started

    if worker_started:
        return

    worker_started = True

    threading.Thread(
        target=analysis_worker,
        daemon=True
    ).start()

    threading.Thread(
        target=telegram_worker,
        daemon=True
    ).start()


@app.get("/", response_class=HTMLResponse)
def dashboard():
    result = LAST_RESULT or run_analysis()

    def display(value):
        return "—" if value is None else str(value)

    signal = result.get("signal", "NO TRADE")

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
          margin: 0;
          padding: 20px;
          background: #101827;
          color: white;
          font-family: Arial, sans-serif;
        }}
        .card {{
          max-width: 600px;
          margin: 20px auto;
          padding: 24px;
          background: #1e293b;
          border-radius: 16px;
        }}
        h1 {{ color: #fbbf24; }}
        .signal {{
          font-size: 34px;
          font-weight: bold;
          color: {color};
        }}
        .item {{
          padding: 12px 0;
          border-bottom: 1px solid #334155;
        }}
        .note {{
          color: #cbd5e1;
          line-height: 1.6;
        }}
      </style>
    </head>
    <body>
      <div class="card">
        <h1>XAUUSD Trading Desk Pro</h1>
        <p>H4 Liquidity Sweep + M15 Confirmation</p>
        <p>Session: <b>{result.get("session", "Unknown")}</b></p>
        <p class="signal">{signal}</p>
        <div class="item">Entry: <b>{display(result.get("entry"))}</b></div>
        <div class="item">Stop Loss: <b>{display(result.get("stop_loss"))}</b></div>
        <div class="item">TP1: <b>{display(result.get("tp1"))}</b></div>
        <div class="item">TP2: <b>{display(result.get("tp2"))}</b></div>
        <div class="item">TP3: <b>{display(result.get("tp3"))}</b></div>
        <p class="note">Reason: {result.get("reason", "")}</p>
        <p class="note">Last check: {display(result.get("checked_at_utc"))}</p>
        <p class="note">Analysis runs every 15 minutes.</p>
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
