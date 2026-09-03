import os
import json
import hashlib
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pypdf import PdfReader
from io import BytesIO


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

WEBSITES_FILE = "websites.json"
SEEN_FILE = "seen.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 40
MAX_PDF_PAGES = 10
MAX_TEXT_LENGTH = 30000
MAX_TELEGRAM_ALERTS = 10


# =========================================================
# GENERAL VACANCY KEYWORDS
# =========================================================

VACANCY_KEYWORDS = [
    "recruitment",
    "recruitment notice",
    "recruitment advertisement",
    "vacancy",
    "vacancies",
    "advertisement",
    "notification",
    "notice",
    "job",
    "jobs",
    "appointment",
    "engagement",
    "career",
    "careers",
    "apply online",
    "application",
    "applications",
    "selection",
    "post",
    "posts",
    "employment",
    "joining",
    "walk-in",
    "walk in",
    "agniveer",
    "gds",
    "scholarship"
]


# =========================================================
# IGNORE KEYWORDS
# =========================================================

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
    "answer key",
    "admit card"
]


# =========================================================
# QUALIFICATION KEYWORDS
# =========================================================

QUALIFICATIONS = [
    "10th pass",
    "10th passed",
    "class 10",
    "matric",
    "matriculation",
    "high school",
    "12th pass",
    "12th passed",
    "class 12",
    "higher secondary",
    "hs pass",
    "higher secondary pass",
    "graduate",
    "graduation",
    "degree",
    "bachelor",
    "bachelor's",
    "post graduate",
    "postgraduate",
    "master degree",
    "master's degree",
    "iti",
    "diploma",
    "engineering",
    "b.tech",
    "b.e",
    "mbbs",
    "nursing"
]


# =========================================================
# LOAD SEEN DATA
# =========================================================

def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set(), False

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return set(), False

        return set(data), True

    except Exception as error:
        print(f"SEEN FILE ERROR: {error}")
        return set(), False


def save_seen(seen):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(
                sorted(seen),
                f,
                indent=2,
                ensure_ascii=False
            )

        print(f"Saved {len(seen)} notification IDs.")

    except Exception as error:
        print(f"SAVE SEEN ERROR: {error}")


# =========================================================
# TELEGRAM
# =========================================================

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

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram API error: {result}"
        )


# =========================================================
# CREATE UNIQUE ID
# =========================================================

def make_id(url, title):
    value = f"{url.strip()}|{title.strip()}"

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


# =========================================================
# CLEAN TEXT
# =========================================================

def clean_text(text):
    if not text:
        return ""

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# LAST DATE EXTRACTION
# =========================================================

def extract_last_date(text):
    if not text:
        return "Not mentioned"

    text = clean_text(text)

    patterns = [
        r"last date\s*(?:for application)?\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"last date\s*(?:for application)?\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})",

        r"closing date\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"closing date\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})",

        r"apply before\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"apply before\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})",

        r"on or before\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"on or before\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})",

        r"applications.*?upto\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"applications.*?upto\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})",

        r"application.*?deadline\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"application.*?deadline\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})"
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


# =========================================================
# QUALIFICATION EXTRACTION
# =========================================================

def extract_qualification(text):
    if not text:
        return "Not mentioned"

    text_lower = text.lower()

    found = []

    for qualification in QUALIFICATIONS:
        if qualification.lower() in text_lower:
            found.append(qualification)

    unique = []

    for item in found:
        if item not in unique:
            unique.append(item)

    if unique:
        return ", ".join(unique[:6])

    return "Not mentioned"


# =========================================================
# PDF TEXT EXTRACTION
# =========================================================

def extract_pdf_text(url):
    try:
        print(f"Reading PDF: {url}")

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        reader = PdfReader(
            BytesIO(response.content)
        )

        text = ""

        for page in reader.pages[:MAX_PDF_PAGES]:
            try:
                page_text = page.extract_text() or ""
                text += " " + page_text

            except Exception as error:
                print(
                    f"PDF PAGE ERROR: {error}"
                )

        return clean_text(
            text[:MAX_TEXT_LENGTH]
        )

    except Exception as error:
        print(
            f"PDF ERROR: {url} -> {error}"
        )

        return ""


# =========================================================
# VACANCY DETECTION
# =========================================================

def is_vacancy(
    title,
    url,
    page_text="",
    website_keywords=None
):

    combined = clean_text(
        f"{title} {url} {page_text}"
    ).lower()

    # Website-specific keywords
    custom_keywords = []

    if website_keywords:
        custom_keywords = [
            str(keyword).lower()
            for keyword in website_keywords
        ]

    all_keywords = list(
        dict.fromkeys(
            VACANCY_KEYWORDS + custom_keywords
        )
    )

    has_vacancy_keyword = any(
        keyword in combined
        for keyword in all_keywords
    )

    if not has_vacancy_keyword:
        return False

    # Ignore only when the title itself clearly
    # indicates a non-recruitment document.
    title_lower = title.lower()

    strong_ignore = [
        "tender",
        "procurement",
        "quotation",
        "auction",
        "corrigendum to tender"
    ]

    if any(
        keyword in title_lower
        for keyword in strong_ignore
    ):
        return False

    return True


# =========================================================
# GET WEBSITE LINKS
# =========================================================

def get_links(site):

    name = site.get(
        "name",
        "Unknown Website"
    )

    category = site.get(
        "category",
        "Government"
    )

    base_url = site.get(
        "url",
        ""
    )

    website_keywords = site.get(
        "keywords",
        []
    )

    print("")
    print("=" * 60)
    print(f"Checking: {name}")
    print(f"URL: {base_url}")
    print("=" * 60)

    response = requests.get(
        base_url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    results = []

    links = soup.find_all(
        "a",
        href=True
    )

    print(
        f"Links found: {len(links)}"
    )

    for link in links:

        title = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

        href = urljoin(
            base_url,
            link.get("href", "")
        )

        if not title:
            continue

        if not href:
            continue

        # Ignore non-web links
        if href.startswith(
            (
                "javascript:",
                "mailto:",
                "tel:",
                "#"
            )
        ):
            continue

        page_text = ""

        # PDF
        clean_href = href.lower().split("?")[0]

        if clean_href.endswith(".pdf"):

            page_text = extract_pdf_text(
                href
            )

        # Vacancy filter
        if not is_vacancy(
            title,
            href,
            page_text,
            website_keywords
        ):
            continue

        # Extract information
        source_text = (
            f"{title} {page_text}"
        )

        last_date = extract_last_date(
            source_text
        )

        qualification = extract_qualification(
            source_text
        )

        item = {
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

        results.append(item)

    # Remove duplicates
    unique_results = {}

    for item in results:
        unique_results[item["id"]] = item

    return list(
        unique_results.values()
    )


# =========================================================
# TELEGRAM MESSAGE
# =========================================================

def create_message(item):

    return (
        "🚨 NEW GOVERNMENT VACANCY\n\n"
        f"📂 Category: {item['category']}\n"
        f"🏢 Organization: {item['source']}\n\n"
        f"📌 Notification:\n"
        f"{item['title']}\n\n"
        f"🎓 Qualification:\n"
        f"{item['qualification']}\n\n"
        f"📅 Last Date:\n"
        f"{item['last_date']}\n\n"
        f"🔗 Official Notification:\n"
        f"{item['url']}"
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print("=" * 60)
    print("GOVERNMENT VACANCY MONITOR STARTED")
    print("=" * 60)

    # Load websites
    try:

        with open(
            WEBSITES_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            websites = json.load(f)

    except Exception as error:

        print(
            f"WEBSITES FILE ERROR: {error}"
        )

        return

    print(
        f"Websites configured: "
        f"{len(websites)}"
    )

    # Load history
    seen, has_baseline = load_seen()

    print(
        f"Previously seen items: "
        f"{len(seen)}"
    )

    all_found = []

    # =====================================================
    # CHECK ALL WEBSITES
    # =====================================================

    for site in websites:

        try:

            items = get_links(site)

            all_found.extend(items)

            print(
                f"{site.get('name', 'Unknown')}: "
                f"{len(items)} vacancy item(s)"
            )

        except Exception as error:

            # Important:
            # One website failure must NOT stop
            # the entire monitoring system.

            print(
                f"{site.get('name', 'Unknown')}: "
                f"ERROR - {error}"
            )

    print("")
    print(
        f"Total vacancy items found: "
        f"{len(all_found)}"
    )

    # =====================================================
    # FIRST RUN BASELINE
    # =====================================================

    if not has_baseline:

        initial_ids = {
            item["id"]
            for item in all_found
        }

        save_seen(
            initial_ids
        )

        print("")
        print(
            f"Baseline created: "
            f"{len(initial_ids)} items"
        )

        print(
            "First run completed."
        )

        print(
            "No Telegram alerts sent."
        )

        return

    # =====================================================
    # FIND NEW ITEMS
    # =====================================================

    new_items = []

    for item in all_found:

        if item["id"] in seen:
            continue

        new_items.append(
            item
        )

    print("")
    print(
        f"NEW vacancy items: "
        f"{len(new_items)}"
    )

    # =====================================================
    # SEND TELEGRAM ALERTS
    # =====================================================

    successfully_sent = 0

    for item in new_items[:MAX_TELEGRAM_ALERTS]:

        message = create_message(
            item
        )

        try:

            send_telegram(
                message
            )

            successfully_sent += 1

            # IMPORTANT:
            # Only mark as seen AFTER
            # Telegram successfully sends.

            seen.add(
                item["id"]
            )

            print(
                f"Telegram alert sent: "
                f"{item['title']}"
            )

        except Exception as error:

            print(
                f"Telegram ERROR: "
                f"{item['title']} -> "
                f"{error}"
            )

            # DO NOT add failed notification
            # to seen.json.
            #
            # It will be retried on next run.

    # =====================================================
    # SAVE HISTORY
    # =====================================================

    save_seen(
        seen
    )

    print("")
    print("=" * 60)
    print(
        f"Alerts successfully sent: "
        f"{successfully_sent}"
    )

    print(
        "Monitoring completed successfully."
    )

    print("=" * 60)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
