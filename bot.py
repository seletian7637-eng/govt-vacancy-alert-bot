import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

WEBSITES_FILE = "websites.json"
SEEN_FILE = "seen.json"


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f, indent=2)


def send_telegram(message):
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        api_url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False
        },
        timeout=30
    )

    response.raise_for_status()


def make_id(url, title):
    raw = f"{url}|{title}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def check_site(site, seen):
    name = site["name"]
    category = site["category"]
    base_url = site["url"]
    keywords = [x.lower() for x in site.get("keywords", [])]

    print(f"Checking: {name}")

    try:
        response = requests.get(
            base_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
                )
            },
            timeout=30
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        found = []

        for link in soup.find_all("a", href=True):
            title = link.get_text(" ", strip=True)
            href = urljoin(base_url, link["href"])

            if not title:
                continue

            combined = f"{title} {href}".lower()

            if any(keyword in combined for keyword in keywords):

                item_id = make_id(href, title)

                if item_id not in seen:
                    found.append({
                        "id": item_id,
                        "title": title,
                        "url": href,
                        "category": category,
                        "source": name
                    })

        for item in found[:10]:

            message = (
                "🚨 NEW GOVERNMENT UPDATE\n\n"
                f"📂 Category: {item['category']}\n"
                f"🏢 Organization: {item['source']}\n\n"
                f"📌 {item['title']}\n\n"
                f"🔗 Official Link:\n{item['url']}"
            )

            send_telegram(message)

            seen.add(item["id"])

        print(f"{name}: {len(found)} new item(s)")

    except Exception as error:
        print(f"{name}: ERROR - {error}")


def main():

    with open(WEBSITES_FILE, "r", encoding="utf-8") as f:
        websites = json.load(f)

    seen = load_seen()

    for site in websites:
        check_site(site, seen)

    save_seen(seen)

    print("Monitoring completed successfully.")


if __name__ == "__main__":
    main()
