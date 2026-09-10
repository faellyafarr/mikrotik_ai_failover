import requests
import config

def send_telegram_alert(message):
    if not getattr(config, "ENABLE_TELEGRAM", False):
        return

    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[-] Failed to send Telegram notification: {e}")
