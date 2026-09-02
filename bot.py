import os
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

message = """
🤖 NEJobPoint Vacancy Alert Bot

✅ Bot successfully connected!

Central Govt
Assam Govt
BTC Govt
Defence

🔔 Vacancy monitoring system is ready.
"""

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

response = requests.post(
    url,
    data={
        "chat_id": CHAT_ID,
        "text": message
    },
    timeout=30
)

response.raise_for_status()

print("Telegram test message sent successfully!")
