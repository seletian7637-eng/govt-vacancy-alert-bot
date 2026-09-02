import os
import json
import hashlib
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pypdf import PdfReader
from io import BytesIO

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

WEBSITES_FILE = "websites.json"
SEEN_FILE = "seen.json"


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set(), False

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data), True
    except Exception:
        return set(), False


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2, ensure_ascii=False)


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


def make_id(url, title):
    value = f"{url}|{title}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def extract_last_date(text):
    patterns = [
        r"last date.{0,50}?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"last date.{0,50}?(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        r"closing date.{0,50}?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"closing date.{0,50}?(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        r"apply before.{0,50}?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return match.group(1)

    return "Not mentioned"


def extract_pdf_text(url):
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
                )
            },
            timeout=30
        )

        response.raise_for_status()

        reader = PdfReader(BytesIO(response.content))

        text = ""

        for page in reader.pages[:5]:
            try:
                text += page.extract_text() or ""
            except Exception:
                pass

        return text[:15000]

    except Exception as error:
        print(f"PDF ERROR: {url} -> {error}")
        return ""


def get_links(site):
    name = site["name"]
    category = site["category"]
    base_url = site["url"]

    keywords = [
        x.lower()
        for x in site.get("keywords", [])
    ]

    print(f"Checking: {name}")

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

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    results = []

    for link in soup.find_all("a", href=True):

        title = link.get_text(" ", strip=True)

        href = urljoin(
            base_url,
            link["href"]
        )

        if not title:
            continue

        combined = (
            f"{title} {href}"
        ).lower()

        if not any(
            keyword in combined
            for keyword in keywords
        ):
            continue

        last_date = "Not mentioned"

        if href.lower().endswith(".pdf"):

            pdf_text = extract_pdf_text(href)

            if pdf_text:
                last_date = extract_last_date(
                    pdf_text
                )

        results.append(
            {
                "id": make_id(
                    href,
                    title
                ),
                "title": title,
                "url": href,
                "category": category,
                "source": name,
                "last_date": last_date
            }
        )

    return results


def main():

    with open(
        WEBSITES_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        websites = json.load(f)

    seen, has_baseline = load_seen()

    all_found = []

    for site in websites:

        try:

            items = get_links(site)

            all_found.extend(items)

            print(
                f"{site['name']}: "
                f"{len(items)} matching item(s)"
            )

        except Exception as error:

            print(
                f"{site['name']}: "
                f"ERROR - {error}"
            )

    # FIRST RUN / BASELINE
    if not has_baseline:

        initial_ids = {
            item["id"]
            for item in all_found
        }

        save_seen(initial_ids)

        print(
            f"Baseline created: "
            f"{len(initial_ids)} existing items saved."
        )

        print(
            "No Telegram alerts sent during baseline."
        )

        return

    # FIND NEW ITEMS
    new_items = []

    for item in all_found:

        if item["id"] not in seen:

            new_items.append(item)

            seen.add(item["id"])

    print(
        f"New items detected: "
        f"{len(new_items)}"
    )

    # SEND TELEGRAM ALERTS
    for item in new_items[:10]:

        message = (
            "🚨 NEW GOVERNMENT VACANCY\n\n"
            f"📂 Category: {item['category']}\n"
            f"🏢 Organization: {item['source']}\n\n"
            f"📌 Notification:\n"
            f"{item['title']}\n\n"
            f"📅 Last Date: {item['last_date']}\n\n"
            f"🔗 Official Link:\n"
            f"{item['url']}"
        )

        try:

            send_telegram(message)

            print(
                f"Alert sent: "
                f"{item['title']}"
            )

        except Exception as error:

            print(
                f"Telegram ERROR: "
                f"{error}"
            )

    save_seen(seen)

    print(
        "Monitoring complete."
    )


if __name__ == "__main__":
    main()
