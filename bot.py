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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}

VACANCY_KEYWORDS = [
    "recruitment",
    "vacancy",
    "vacancies",
    "advertisement",
    "notification",
    "job",
    "appointment",
    "engagement",
    "career",
    "apply online",
    "application",
    "selection",
    "post",
    "posts",
    "recruitment notice",
    "employment"
]

IGNORE_KEYWORDS = [
    "tender",
    "procurement",
    "quotation",
    "auction",
    "corrigendum to tender",
    "press release",
    "meeting",
    "transfer",
    "promotion",
    "seniority",
    "result",
    "answer key",
    "admit card"
]

QUALIFICATIONS = [
    "10th pass",
    "10th passed",
    "matric",
    "matriculation",
    "12th pass",
    "12th passed",
    "higher secondary",
    "hs pass",
    "graduate",
    "graduation",
    "degree",
    "bachelor",
    "post graduate",
    "postgraduate",
    "master degree",
    "iti",
    "diploma"
]


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set(), False

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f)), True
    except Exception:
        return set(), False


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(
            sorted(seen),
            f,
            indent=2,
            ensure_ascii=False
        )


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
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def extract_last_date(text):
    patterns = [
        r"last date.{0,100}?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"last date.{0,100}?(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        r"closing date.{0,100}?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"closing date.{0,100}?(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        r"apply before.{0,100}?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"on or before.{0,100}?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return match.group(1)

    return "Not mentioned"


def extract_qualification(text):
    found = []

    text_lower = text.lower()

    for qualification in QUALIFICATIONS:
        if qualification in text_lower:
            found.append(qualification)

    unique = []

    for item in found:
        if item not in unique:
            unique.append(item)

    if unique:
        return ", ".join(unique[:5])

    return "Not mentioned"


def extract_pdf_text(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=40
        )

        response.raise_for_status()

        reader = PdfReader(
            BytesIO(response.content)
        )

        text = ""

        for page in reader.pages[:8]:
            try:
                text += page.extract_text() or ""
            except Exception:
                pass

        return text[:25000]

    except Exception as error:
        print(
            f"PDF ERROR: {url} -> {error}"
        )

        return ""


def is_vacancy(title, url, page_text=""):
    combined = (
        f"{title} {url} {page_text}"
    ).lower()

    has_vacancy_keyword = any(
        keyword in combined
        for keyword in VACANCY_KEYWORDS
    )

    has_ignore_keyword = any(
        keyword in combined
        for keyword in IGNORE_KEYWORDS
    )

    if not has_vacancy_keyword:
        return False

    if has_ignore_keyword:
        return False

    return True


def get_links(site):
    name = site["name"]
    category = site["category"]
    base_url = site["url"]

    print(f"Checking: {name}")

    response = requests.get(
        base_url,
        headers=HEADERS,
        timeout=40
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    results = []

    for link in soup.find_all(
        "a",
        href=True
    ):

        title = link.get_text(
            " ",
            strip=True
        )

        href = urljoin(
            base_url,
            link["href"]
        )

        if not title:
            continue

        # Ignore javascript / mail links
        if href.startswith(
            ("javascript:", "mailto:", "#")
        ):
            continue

        page_text = ""

        # PDF processing
        if href.lower().split("?")[0].endswith(".pdf"):

            page_text = extract_pdf_text(href)

        # Smart filtering
        if not is_vacancy(
            title,
            href,
            page_text
        ):
            continue

        last_date = extract_last_date(
            page_text
        )

        qualification = extract_qualification(
            page_text
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
                "last_date": last_date,
                "qualification": qualification
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
                f"{len(items)} vacancy item(s)"
            )

        except Exception as error:

            print(
                f"{site['name']}: "
                f"ERROR - {error}"
            )

    # First run = baseline
    if not has_baseline:

        initial_ids = {
            item["id"]
            for item in all_found
        }

        save_seen(initial_ids)

        print(
            f"Baseline created: "
            f"{len(initial_ids)} items"
        )

        print(
            "No Telegram alerts sent."
        )

        return

    # Find genuinely new items
    new_items = []

    for item in all_found:

        if item["id"] not in seen:

            new_items.append(item)

            seen.add(item["id"])

    print(
        f"New vacancy items: "
        f"{len(new_items)}"
    )

    # Telegram alerts
    for item in new_items[:10]:

        message = (
            "🚨 NEW GOVERNMENT VACANCY\n\n"
            f"📂 Category: {item['category']}\n"
            f"🏢 Organization: {item['source']}\n\n"
            f"📌 Notification:\n"
            f"{item['title']}\n\n"
            f"🎓 Qualification: "
            f"{item['qualification']}\n\n"
            f"📅 Last Date: "
            f"{item['last_date']}\n\n"
            f"🔗 Official Notification:\n"
            f"{item['url']}"
        )

        try:

            send_telegram(message)

            print(
                f"Telegram alert sent: "
                f"{item['title']}"
            )

        except Exception as error:

            print(
                f"Telegram ERROR: "
                f"{error}"
            )

    save_seen(seen)

    print(
        "Monitoring completed successfully."
    )


if __name__ == "__main__":
    main()
