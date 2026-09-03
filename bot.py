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
TELEGRAM_TIMEOUT = 30
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
    "recruitment notification",
    "vacancy",
    "vacancies",
    "advertisement",
    "job notification",
    "employment notification",
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
    "manpower",
    "staff recruitment",
    "direct recruitment",
    "contractual recruitment",
    "job",
    "jobs"
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
    "last date to apply",
    "closing date",
    "application deadline",
    "advt",
    "advertisement no",
    "recruitment notification",
    "number of posts",
    "no. of posts",
    "total posts"
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

QUALIFICATION_PATTERNS = [
    ("10th Pass", [
        "10th pass",
        "10th passed",
        "class 10",
        "class x",
        "matric",
        "matriculation",
        "high school"
    ]),
    ("12th Pass", [
        "12th pass",
        "12th passed",
        "class 12",
        "class xii",
        "higher secondary",
        "hs pass",
        "higher secondary pass"
    ]),
    ("ITI", [
        "iti",
        "industrial training institute"
    ]),
    ("Diploma", [
        "diploma"
    ]),
    ("Graduate", [
        "graduate",
        "graduation",
        "bachelor",
        "bachelor's degree",
        "degree"
    ]),
    ("Post Graduate", [
        "post graduate",
        "postgraduate",
        "master degree",
        "master's degree"
    ]),
    ("Engineering", [
        "b.tech",
        "btech",
        "b.e.",
        "b.e ",
        "engineering degree",
        "engineering"
    ]),
    ("MBBS", [
        "mbbs"
    ]),
    ("Nursing", [
        "gnm",
        "anm",
        "nursing"
    ]),
    ("PhD", [
        "phd",
        "doctorate"
    ])
]


# =========================================================
# LOAD SEEN
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


# =========================================================
# SAVE SEEN
# =========================================================

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
        timeout=TELEGRAM_TIMEOUT
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram API error: {result}"
        )


# =========================================================
# CLEAN TEXT
# =========================================================

def clean_text(text):

    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =========================================================
# NORMALIZE URL
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


# =========================================================
# UNIQUE ID
# =========================================================

def make_id(url, title):

    value = (
        f"{normalize_url(url)}|"
        f"{clean_text(title).lower()}"
    )

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


# =========================================================
# DATE EXTRACTION
# =========================================================

def extract_last_date(text):

    if not text:
        return "Not mentioned"

    text = clean_text(text)

    date_patterns = [

        # 30/09/2026
        r"(?:last date|closing date|apply before|on or before|deadline|last date to apply)"
        r".{0,80}?"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",

        # 30.09.2026
        r"(?:last date|closing date|apply before|on or before|deadline|last date to apply)"
        r".{0,80}?"
        r"(\d{1,2}\.\d{1,2}\.\d{2,4})",

        # 30 September 2026
        r"(?:last date|closing date|apply before|on or before|deadline|last date to apply)"
        r".{0,80}?"
        r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"(?:,)?\s+\d{4})",

        # September 30, 2026
        r"(?:last date|closing date|apply before|on or before|deadline|last date to apply)"
        r".{0,80}?"
        r"((?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2}(?:,)?\s+\d{4})",

        # 30-09-26
        r"(?:last date|closing date|deadline)"
        r".{0,80}?"
        r"(\d{1,2}-\d{1,2}-\d{2,4})"
    ]

    for pattern in date_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return clean_text(match.group(1))

    # Generic fallback
    fallback_patterns = [
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
        r"(\d{1,2}\.\d{1,2}\.\d{4})",
        r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})"
    ]

    for pattern in fallback_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return clean_text(match.group(1))

    return "Not mentioned"


# =========================================================
# QUALIFICATION EXTRACTION
# =========================================================

def extract_qualification(text):

    if not text:
        return "Not mentioned"

    text_lower = text.lower()

    found = []

    for label, patterns in QUALIFICATION_PATTERNS:

        for pattern in patterns:

            if pattern.lower() in text_lower:

                if label not in found:
                    found.append(label)

                break

    if not found:
        return "Not mentioned"

    return " / ".join(found[:6])


# =========================================================
# VACANCY / POSTS EXTRACTION
# =========================================================

def extract_vacancies(text):

    if not text:
        return "Not mentioned"

    text = clean_text(text)

    patterns = [

        # No. of Posts: 25
        r"(?:no\.?\s*of\s*posts|number\s*of\s*posts|total\s*posts|"
        r"no\.?\s*of\s*vacancies|number\s*of\s*vacancies|"
        r"total\s*vacancies)"
        r"\s*[:\-]?\s*(\d{1,5})",

        # 25 posts
        r"\b(\d{1,5})\s+(?:posts|post|vacancies|vacancy)\b",

        # 25 Nos.
        r"\b(\d{1,5})\s+(?:nos\.?|numbers)\b"
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
# AGE LIMIT EXTRACTION
# =========================================================

def extract_age_limit(text):

    if not text:
        return "Not mentioned"

    text = clean_text(text)

    patterns = [

        # Age Limit: 18-30 years
        r"(?:age\s*limit|age\s*criteria|age)"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}\s*(?:to|-)\s*\d{1,2}\s*years?)",

        # Minimum age 18 years
        r"(?:minimum|min\.?)\s*age"
        r"\s*[:\-]?\s*(\d{1,2}\s*years?)",

        # Maximum age 30 years
        r"(?:maximum|max\.?)\s*age"
        r"\s*[:\-]?\s*(\d{1,2}\s*years?)",

        # 18 years to 30 years
        r"(\d{1,2}\s*years?)\s*(?:to|-)\s*(\d{1,2}\s*years?)"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            if match.lastindex == 2:

                return (
                    f"{match.group(1)} to "
                    f"{match.group(2)}"
                )

            return clean_text(
                match.group(1)
            )

    return "Not mentioned"


# =========================================================
# SALARY / PAY EXTRACTION
# =========================================================

def extract_salary(text):

    if not text:
        return "Not mentioned"

    text = clean_text(text)

    patterns = [

        # ₹25,500 - ₹81,100
        r"(?:₹|rs\.?|inr)\s*"
        r"[\d,]+"
        r"\s*(?:-|to|–|—)\s*"
        r"(?:₹|rs\.?|inr)?\s*[\d,]+",

        # Pay Scale: 19900-63200
        r"(?:pay\s*scale|pay\s*level|salary|remuneration|"
        r"consolidated\s*pay)"
        r"\s*[:\-]?\s*"
        r"(?:₹|rs\.?|inr)?\s*[\d,]+"
        r"(?:\s*(?:-|to|–|—)\s*(?:₹|rs\.?|inr)?\s*[\d,]+)?",

        # ₹30,000 per month
        r"(?:₹|rs\.?|inr)\s*[\d,]+"
        r"(?:\s*per\s*month)?"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return clean_text(
                match.group(0)
            )

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

    title_clean = clean_text(title)

    title_lower = title_clean.lower()

    # Never allow obvious non-job titles
    for keyword in IGNORE_KEYWORDS:

        if keyword in title_lower:
            return False

    combined = clean_text(
        f"{title} {url} {page_text}"
    ).lower()

    custom_keywords = []

    if website_keywords:

        custom_keywords = [
            str(keyword).lower().strip()
            for keyword in website_keywords
            if str(keyword).strip()
        ]

    # Strong indicators
    strong_match = any(
        keyword in combined
        for keyword in STRONG_JOB_KEYWORDS
    )

    # General indicators
    all_keywords = list(
        dict.fromkeys(
            VACANCY_KEYWORDS
            + custom_keywords
        )
    )

    general_match = any(
        keyword in combined
        for keyword in all_keywords
    )

    if not general_match:
        return False

    if strong_match:
        return True

    context_keywords = [
        "eligible",
        "eligibility",
        "qualification",
        "age limit",
        "salary",
        "pay scale",
        "pay level",
        "application fee",
        "how to apply",
        "selection",
        "exam",
        "interview",
        "posts",
        "vacancies"
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

    if not base_url:
        return []

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

        clean_href = (
            href.lower()
            .split("?")[0]
        )

        # Ignore obviously useless links
        if clean_href.endswith(
            (
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".zip",
                ".doc",
                ".docx",
                ".xls",
                ".xlsx"
            )
        ):
            continue

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

        item = {
            "id": make_id(
                href,
                title
            ),
            "title": title,
            "url": href,
            "category": category,
            "source": name,
            "last_date": extract_last_date(
                source_text
            ),
            "qualification": extract_qualification(
                source_text
            ),
            "vacancies": extract_vacancies(
                source_text
            ),
            "age_limit": extract_age_limit(
                source_text
            ),
            "salary": extract_salary(
                source_text
            )
        }

        results.append(item)

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

        f"👥 Total Posts\n"
        f"{item['vacancies']}\n\n"

        f"🎓 Qualification\n"
        f"{item['qualification']}\n\n"

        f"🎂 Age Limit\n"
        f"{item['age_limit']}\n\n"

        f"💰 Salary / Pay\n"
        f"{item['salary']}\n\n"

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

    # -----------------------------------------------------
    # Load websites
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Load history
    # -----------------------------------------------------

    seen, has_baseline = load_seen()

    print(
        f"Previously seen items: "
        f"{len(seen)}"
    )

    # -----------------------------------------------------
    # Check every website
    # -----------------------------------------------------

    all_found = []

    for site in websites:

        try:

            items = get_links(site)

            all_found.extend(items)

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

    # -----------------------------------------------------
    # First run = baseline
    # -----------------------------------------------------

    if not has_baseline:

        initial_ids = {
            item["id"]
            for item in all_found
        }

        save_seen(initial_ids)

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

    # -----------------------------------------------------
    # Find new vacancies
    # -----------------------------------------------------

    new_items = []

    for item in all_found:

        if item["id"] in seen:
            continue

        new_items.append(item)

    print("")
    print(
        f"NEW vacancy items: "
        f"{len(new_items)}"
    )

    # -----------------------------------------------------
    # Send Telegram alerts
    # -----------------------------------------------------

    successfully_sent = 0

    for item in new_items[:MAX_TELEGRAM_ALERTS]:

        message = create_message(item)

        try:

            send_telegram(message)

            successfully_sent += 1

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

    # -----------------------------------------------------
    # IMPORTANT:
    # Only successfully sent notifications are added.
    # Failed Telegram messages will be retried next run.
    # -----------------------------------------------------

    save_seen(seen)

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
# START
# =========================================================

if __name__ == "__main__":
    main()
