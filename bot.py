```python
import os
import json
import hashlib
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pypdf import PdfReader
from io import BytesIO
from datetime import datetime


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
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 40
MAX_PDF_PAGES = 10
MAX_TEXT_LENGTH = 30000
MAX_TELEGRAM_ALERTS = 10


# =========================================================
# VACANCY KEYWORDS
# =========================================================

VACANCY_KEYWORDS = [
    "recruitment",
    "recruitment notice",
    "recruitment advertisement",
    "vacancy",
    "vacancies",
    "advertisement",
    "job notification",
    "employment notification",
    "recruitment notification",
    "appointment",
    "engagement",
    "career",
    "apply online",
    "application invited",
    "applications are invited",
    "online application",
    "selection process",
    "walk-in interview",
    "walk in interview",
    "gds",
    "agniveer",
    "scholarship",
    "manpower",
    "staff recruitment",
    "direct recruitment",
    "contractual recruitment"
]


# =========================================================
# STRONG JOB INDICATORS
# =========================================================

STRONG_JOB_KEYWORDS = [
    "recruitment",
    "vacancy",
    "vacancies",
    "apply online",
    "applications are invited",
    "application invited",
    "online application",
    "post of",
    "posts of",
    "appointment",
    "engagement",
    "walk-in interview",
    "walk in interview",
    "selection process",
    "eligibility criteria",
    "last date",
    "closing date",
    "application deadline",
    "advt",
    "advertisement no",
    "recruitment notification"
]


# =========================================================
# IGNORE KEYWORDS
# =========================================================

IGNORE_KEYWORDS = [
    "tender",
    "tenders",
    "procurement",
    "quotation",
    "auction",
    "corrigendum to tender",
    "press release",
    "press note",
    "meeting notice",
    "transfer order",
    "transfer list",
    "promotion order",
    "seniority list",
    "answer key",
    "admit card",
    "hall ticket",
    "result",
    "results",
    "merit list",
    "selected candidates",
    "joining order",
    "retirement",
    "holiday notice",
    "calendar",
    "minutes of meeting"
]


# =========================================================
# QUALIFICATIONS
# =========================================================

QUALIFICATIONS = [
    "10th pass",
    "10th passed",
    "class 10",
    "class x",
    "matric",
    "matriculation",
    "high school",

    "12th pass",
    "12th passed",
    "class 12",
    "class xii",
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
    "nursing",
    "gnm",
    "anm",
    "phd"
]


# =========================================================
# LOAD SEEN
# =========================================================

def load_seen():

    if not os.path.exists(SEEN_FILE):
        return set(), False

    try:

        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if not isinstance(data, list):
            return set(), False

        return set(data), True

    except Exception as error:

        print(f"SEEN FILE ERROR: {error}")

        return set(), False


def save_seen(seen):

    try:

        with open(
            SEEN_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                sorted(seen),
                f,
                indent=2,
                ensure_ascii=False
            )

        print(
            f"Saved {len(seen)} notification IDs."
        )

    except Exception as error:

        print(
            f"SAVE SEEN ERROR: {error}"
        )


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(message):

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

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
# UNIQUE ID
# =========================================================

def normalize_url(url):

    url = url.strip()

    parsed = urlparse(url)

    clean = (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
        f"{parsed.path}"
    )

    return clean.rstrip("/")


def make_id(url, title):

    value = (
        f"{normalize_url(url)}|"
        f"{clean_text(title).lower()}"
    )

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


# =========================================================
# CLEAN TEXT
# =========================================================

def clean_text(text):

    if not text:
        return ""

    text = text.replace(
        "\xa0",
        " "
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# LAST DATE
# =========================================================

def extract_last_date(text):

    if not text:
        return "Not mentioned"

    text = clean_text(text)

    patterns = [

        # DD/MM/YYYY
        r"(?:last date|closing date|apply before|on or before|deadline)"
        r"\s*(?:for application)?\s*[:\-]?\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",

        # DD Month YYYY
        r"(?:last date|closing date|apply before|on or before|deadline)"
        r"\s*(?:for application)?\s*[:\-]?\s*"
        r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})",

        # Month DD, YYYY
        r"(?:last date|closing date|apply before|deadline)"
        r"\s*(?:for application)?\s*[:\-]?\s*"
        r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})",

        # Applications upto
        r"applications?.{0,100}?"
        r"(?:upto|up to)"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",

        r"applications?.{0,100}?"
        r"(?:upto|up to)"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return clean_text(
                match.group(1)
            )

    # Generic date search near "last date"
    match = re.search(
        r"last date.{0,120}?"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        text,
        re.IGNORECASE
    )

    if match:
        return match.group(1)

    return "Not mentioned"


# =========================================================
# QUALIFICATION
# =========================================================

def extract_qualification(text):

    if not text:
        return "Not mentioned"

    text_lower = text.lower()

    found = []

    for qualification in QUALIFICATIONS:

        if qualification.lower() in text_lower:

            if qualification not in found:
                found.append(
                    qualification
                )

    if not found:
        return "Not mentioned"

    # Remove duplicate / overlapping terms
    result = []

    for item in found:

        overlapping = False

        for existing in result:

            if item.lower() in existing.lower():
                overlapping = True
                break

        if not overlapping:
            result.append(item)

    return ", ".join(
        result[:6]
    )


# =========================================================
# PDF EXTRACTION
# =========================================================

def extract_pdf_text(url):

    try:

        print(
            f"Reading PDF: {url}"
        )

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

                page_text = (
                    page.extract_text()
                    or ""
                )

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

    title_clean = clean_text(
        title
    )

    combined = clean_text(
        f"{title} {url} {page_text}"
    ).lower()

    title_lower = title_clean.lower()

    # ---------------------------------------------
    # Reject clearly irrelevant titles
    # ---------------------------------------------

    for keyword in IGNORE_KEYWORDS:

        if keyword in title_lower:
            return False

    # ---------------------------------------------
    # Website-specific keywords
    # ---------------------------------------------

    custom_keywords = []

    if website_keywords:

        custom_keywords = [
            str(keyword).lower().strip()
            for keyword in website_keywords
            if str(keyword).strip()
        ]

    # ---------------------------------------------
    # Strong job indicator
    # ---------------------------------------------

    has_strong_indicator = any(
        keyword in combined
        for keyword in STRONG_JOB_KEYWORDS
    )

    # ---------------------------------------------
    # General/custom indicator
    # ---------------------------------------------

    all_keywords = list(
        dict.fromkeys(
            VACANCY_KEYWORDS
            + custom_keywords
        )
    )

    has_general_indicator = any(
        keyword in combined
        for keyword in all_keywords
    )

    if not has_general_indicator:
        return False

    # ---------------------------------------------
    # If page has strong indicator → accept
    # ---------------------------------------------

    if has_strong_indicator:
        return True

    # ---------------------------------------------
    # For weaker matches require application/
    # recruitment context.
    # ---------------------------------------------

    context_keywords = [
        "eligible",
        "eligibility",
        "qualification",
        "age limit",
        "salary",
        "pay scale",
        "application fee",
        "how to apply",
        "selection",
        "exam",
        "interview"
    ]

    context_count = sum(
        1
        for keyword in context_keywords
        if keyword in combined
    )

    return context_count >= 1


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

        if not title or not href:
            continue

        if href.startswith(
            (
                "javascript:",
                "mailto:",
                "tel:",
                "#"
            )
        ):
            continue

        # Ignore common file types that aren't useful
        # for vacancy detection.
        clean_href = (
            href.lower()
            .split("?")[0]
        )

        page_text = ""

        if clean_href.endswith(".pdf"):

            page_text = extract_pdf_text(
                href
            )

        if not is_vacancy(
            title,
            href,
            page_text,
            website_keywords
        ):
            continue

        source_text = clean_text(
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

        results.append(
            item
        )

    # Remove duplicates
    unique_results = {}

    for item in results:

        unique_results[
            item["id"]
        ] = item

    return list(
        unique_results.values()
    )


# =========================================================
# TELEGRAM MESSAGE
# =========================================================

def create_message(item):

    return (
        "🚨 NEW GOVERNMENT JOB ALERT\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        f"🏢 Organization\n"
        f"{item['source']}\n\n"

        f"📂 Category\n"
        f"{item['category']}\n\n"

        f"📌 Notification\n"
        f"{item['title']}\n\n"

        f"🎓 Qualification\n"
        f"{item['qualification']}\n\n"

        f"📅 Last Date\n"
        f"{item['last_date']}\n\n"

        "🔗 Official Notification\n"
        f"{item['url']}\n\n"

        "⚡ NEJobPoint Vacancy Alert"
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print("=" * 60)
    print("GOVERNMENT VACANCY MONITOR STARTED")
    print(
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )
    print("=" * 60)

    # ---------------------------------------------
    # Load websites
    # ---------------------------------------------

    try:

        with open(
            WEBSITES_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            websites = json.load(f)

        if not isinstance(
            websites,
            list
        ):
            raise ValueError(
                "websites.json must contain a list"
            )

    except Exception as error:

        print(
            f"WEBSITES FILE ERROR: {error}"
        )

        return

    print(
        f"Websites configured: "
        f"{len(websites)}"
    )

    # ---------------------------------------------
    # Load history
    # ---------------------------------------------

    seen, has_baseline = load_seen()

    print(
        f"Previously seen items: "
        f"{len(seen)}"
    )

    all_found = []

    # ---------------------------------------------
    # Check every website
    # ---------------------------------------------

    for site in websites:

        try:

            items = get_links(
                site
            )

            all_found.extend(
                items
            )

            print(
                f"{site.get('name', 'Unknown')}: "
                f"{len(items)} vacancy item(s)"
            )

        except Exception as error:

            print(
                f"{site.get('name', 'Unknown')}: "
                f"ERROR - {error}"
            )

    print("")
    print(
        f"Total vacancy items found: "
        f"{len(all_found)}"
    )

    # ---------------------------------------------
    # First run baseline
    # ---------------------------------------------

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

    # ---------------------------------------------
    # Find NEW notifications
    # ---------------------------------------------

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

    # ---------------------------------------------
    # Send alerts
    # ---------------------------------------------

    successfully_sent = 0

    for item in new_items[
        :MAX_TELEGRAM_ALERTS
    ]:

        message = create_message(
            item
        )

        try:

            send_telegram(
                message
            )

            successfully_sent += 1

            # Only mark as seen AFTER
            # successful Telegram delivery.
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

            # Failed alerts remain unseen
            # and will be retried next run.

    # ---------------------------------------------
    # Prevent unlimited history growth from
    # duplicate entries already present.
    # ---------------------------------------------

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
```
