import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

WEBSITES_FILE = "websites.json"
SEEN_FILE = "seen.json"


def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False
        },
        timeout=30
    )

    response.raise_for_status()


def check_website(site, seen):
    name = site["name"]
    url = site["url"]
    keywords = [x.lower() for x in site.get("keywords", [])]

    try:
        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        found = []

        for link in soup.find_all("a", href=True):
            title = link.get_text(" ", strip=True)
            href = urljoin(url, link["href"])

            text = f"{title} {href}".lower()

            if title and any(keyword in text for keyword in keywords):
                found.append({
                    "title": title,
                    "url": href
                })

        new_items = []

        for item in found:
            item_id = item["url"]

            if item_id not in seen:
                seen.add(item_id)
                new_items.append(item)

        for item in new_items[:10]:
            message = (
                f"🚨 NEW GOVERNMENT UPDATE\n\n"
                f"🏢 Source: {name}\n"
                f"📌 {item['title']}\n\n"
                f"🔗 Official Link:\n{item['url']}"
            )

            send_telegram(message)

        print(f"{name}: {len(new_items)} new item(s)")

    except Exception as e:
        print(f"{name}: ERROR - {e}")


def main():
    websites = load_json(WEBSITES_FILE, [])
    seen_list = load_json(SEEN_FILE, [])
    seen = set(seen_list)

    for site in websites:
        check_website(site, seen)

    save_json(SEEN_FILE, list(seen))


if __name__ == "__main__":
    main()
