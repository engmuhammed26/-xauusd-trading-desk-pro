import os
import requests


def send_telegram_alert(signal: dict) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return False

    message = (
        "🟡 XAUUSD TRADING DESK PRO\n\n"
        f"Signal: {signal.get('signal', 'NO TRADE')}\n"
        f"Entry: {signal.get('entry', 'N/A')}\n"
        f"Stop Loss: {signal.get('stop_loss', 'N/A')}\n"
        f"TP1: {signal.get('tp1', 'N/A')}\n"
        f"TP2: {signal.get('tp2', 'N/A')}\n"
        f"TP3: {signal.get('tp3', 'N/A')}\n\n"
        f"Reason: {signal.get('reason', 'N/A')}\n\n"
        "Analysis alerts only. No automatic orders."
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": message},
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("ok", False)
    except requests.RequestException:
        return False
