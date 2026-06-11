import re
import math
import html
import hashlib
from datetime import datetime
from urllib.parse import urlencode

import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup


# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="Car Flip AI",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.block-container {
    padding-top: 1.1rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    max-width: 760px !important;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

h1 {
    font-size: 2.4rem !important;
    line-height: 1.05 !important;
    margin-bottom: 0.25rem !important;
}

.sub {
    color: #9ca3af;
    font-size: 1rem;
    margin-bottom: 1.1rem;
}

.stButton > button {
    width: 100%;
    border-radius: 14px;
    font-weight: 800;
    padding: 0.75rem 1rem;
}

.car-card {
    border: 1px solid rgba(250,250,250,0.16);
    border-radius: 18px;
    padding: 15px 15px 13px 15px;
    margin-bottom: 14px;
    background: rgba(255,255,255,0.035);
}

.good {
    color: #22c55e;
    font-weight: 900;
}

.warn {
    color: #f59e0b;
    font-weight: 900;
}

.bad {
    color: #ef4444;
    font-weight: 900;
}

.small {
    color: #9ca3af;
    font-size: 0.9rem;
}

.debug-box {
    font-size: 0.88rem;
    color: #d1d5db;
    background: rgba(255,255,255,0.04);
    border-radius: 12px;
    padding: 12px;
    overflow-wrap: break-word;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# CONSTANTS
# ============================================================

ZIP_CODE = "84107"
RADIUS_MILES = 90
CRAIGSLIST_BASE = "https://saltlakecity.craigslist.org"

MAKES = [
    "toyota", "honda", "lexus", "acura", "mazda", "subaru",
    "ford", "chevy", "chevrolet", "gmc", "buick", "cadillac",
    "nissan", "infiniti", "hyundai", "kia",
    "bmw", "mercedes", "audi", "volkswagen", "vw",
    "jeep", "dodge", "ram", "chrysler",
    "mini", "volvo", "mitsubishi", "scion"
]

BAD_TITLE_WORDS = [
    "parts", "part out", "parting", "mechanic special",
    "does not run", "not running", "salvage only",
    "camper", "rv", "motorhome", "f650", "box truck",
    "semi", "trailer", "boat", "atv", "utv", "motorcycle"
]

HIGH_RISK_WORDS = [
    "rebuilt", "salvage", "branded", "mechanic", "needs",
    "transmission", "head gasket", "overheating", "no title",
    "lien", "tow", "project", "as is"
]


# ============================================================
# HELPERS
# ============================================================

def money(x):
    try:
        return f"${int(round(float(x))):,}"
    except Exception:
        return "$0"


def clean_text(value):
    if not value:
        return ""
    value = html.unescape(str(value))
    value = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def extract_price(text):
    if not text:
        return None

    patterns = [
        r"\$[\s]*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})",
        r"price[:\s]*\$?([0-9]{4,6})",
    ]

    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except Exception:
                pass

    return None


def extract_year(text):
    if not text:
        return None

    m = re.search(r"\b(19[8-9][0-9]|20[0-2][0-9])\b", text)
    if m:
        y = int(m.group(1))
        if 1980 <= y <= datetime.now().year + 1:
            return y

    return None


def extract_miles(text):
    if not text:
        return None

    text_l = text.lower()

    patterns = [
        r"([0-9]{1,3}(?:,[0-9]{3})+)\s*(?:miles|mi|mile)",
        r"([0-9]{2,3})k\s*(?:miles|mi|mile)?",
        r"mileage[:\s]*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{5,6})",
        r"odometer[:\s]*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{5,6})",
    ]

    for p in patterns:
        m = re.search(p, text_l)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                if "k" in m.group(0):
                    return int(float(raw) * 1000)
                return int(raw)
            except Exception:
                pass

    return None


def extract_make_model(title):
    t = title.lower()
    found_make = None

    for make in MAKES:
        if re.search(rf"\b{re.escape(make)}\b", t):
            found_make = make
            break

    return found_make


def is_probably_vehicle(title, body):
    text = f"{title} {body}".lower()

    if any(w in text for w in BAD_TITLE_WORDS):
        return False

    if extract_year(text) is None:
        return False

    if extract_make_model(title) is None and extract_make_model(body) is None:
        return False

    return True


def build_craigslist_rss_url(max_price):
    params = {
        "format": "rss",
        "postal": ZIP_CODE,
        "search_distance": RADIUS_MILES,
        "purveyor-input": "owner",
        "bundleDuplicates": "1",
        "sort": "date",
        "max_price": int(max_price),
        "auto_title_status": "1",
    }

    return f"{CRAIGSLIST_BASE}/search/cto?" + urlencode(params)


def build_craigslist_html_url(max_price):
    params = {
        "postal": ZIP_CODE,
        "search_distance": RADIUS_MILES,
        "purveyor-input": "owner",
        "bundleDuplicates": "1",
        "sort": "date",
        "max_price": int(max_price),
        "auto_title_status": "1",
    }

    return f"{CRAIGSLIST_BASE}/search/cto?" + urlencode(params)


def get_headers():
    return {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml, text/html, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://saltlakecity.craigslist.org/",
    }


def fetch_url(url):
    try:
        r = requests.get(
            url,
            headers=get_headers(),
            timeout=18,
            allow_redirects=True,
        )
        return {
            "ok": r.status_code == 200,
            "status": r.status_code,
            "url": url,
            "final_url": r.url,
            "text": r.text or "",
            "error": "",
        }
    except Exception as e:
        return {
            "ok": False,
            "status": "ERROR",
            "url": url,
            "final_url": url,
            "text": "",
            "error": str(e),
        }


def parse_rss(xml_text):
    listings = []

    soup = BeautifulSoup(xml_text, "xml")
    items = soup.find_all("item")

    if not items:
        soup = BeautifulSoup(xml_text, "html.parser")
        items = soup.find_all("item")

    for item in items:
        title = clean_text(item.title.get_text(" ", strip=True) if item.title else "")
        link = clean_text(item.link.get_text(" ", strip=True) if item.link else "")
        description = clean_text(item.description.get_text(" ", strip=True) if item.description else "")

        full_text = f"{title} {description}"

        price = extract_price(title) or extract_price(description)
        year = extract_year(full_text)
        miles = extract_miles(full_text)

        if not link:
            guid = item.find("guid")
            if guid:
                link = clean_text(guid.get_text(" ", strip=True))

        if title and link:
            listings.append({
                "title": title,
                "url": link,
                "price": price,
                "year": year,
                "miles": miles,
                "body": description,
            })

    return listings


def parse_html(html_text):
    listings = []

    soup = BeautifulSoup(html_text, "html.parser")

    rows = soup.select("li.cl-static-search-result, li.result-row, div.result-info, a.posting-title")

    for row in rows:
        text = clean_text(row.get_text(" ", strip=True))
        link = ""

        a = row.find("a", href=True)
        if a:
            link = a["href"]

        if not link and row.name == "a" and row.get("href"):
            link = row["href"]

        if link and link.startswith("/"):
            link = CRAIGSLIST_BASE + link

        title = text

        price = extract_price(text)
        year = extract_year(text)
        miles = extract_miles(text)

        if title and link:
            listings.append({
                "title": title,
                "url": link,
                "price": price,
                "year": year,
                "miles": miles,
                "body": text,
            })

    return listings


def dedupe_listings(listings):
    seen = set()
    clean = []

    for x in listings:
        key_source = x.get("url") or x.get("title", "")
        key = hashlib.md5(key_source.encode("utf-8", errors="ignore")).hexdigest()

        if key in seen:
            continue

        seen.add(key)
        clean.append(x)

    return clean


def estimate_retail_value(row):
    title = f"{row.get('title', '')} {row.get('body', '')}".lower()
    price = row.get("price")
    year = row.get("year")
    miles = row.get("miles")

    if not price:
        return None

    age = max(0, datetime.now().year - year) if year else 12

    base_markup = 1.35

    if price <= 3000:
        base_markup = 1.65
    elif price <= 5000:
        base_markup = 1.55
    elif price <= 8000:
        base_markup = 1.42
    elif price <= 12000:
        base_markup = 1.32
    else:
        base_markup = 1.22

    mileage_penalty = 0

    if miles:
        if miles > 220000:
            mileage_penalty = 0.25
        elif miles > 180000:
            mileage_penalty = 0.18
        elif miles > 150000:
            mileage_penalty = 0.11
        elif miles < 100000:
            mileage_penalty = -0.08

    age_penalty = 0

    if age > 18:
        age_penalty = 0.12
    elif age > 14:
        age_penalty = 0.07
    elif age < 9:
        age_penalty = -0.05

    brand_bonus = 0

    if any(b in title for b in ["toyota", "honda", "lexus", "acura"]):
        brand_bonus = 0.10
    elif any(b in title for b in ["mazda", "subaru"]):
        brand_bonus = 0.05
    elif any(b in title for b in ["bmw", "audi", "mercedes", "mini", "volkswagen", "vw"]):
        brand_bonus = -0.06

    risk_penalty = 0
    if any(w in title for w in HIGH_RISK_WORDS):
        risk_penalty = 0.12

    multiplier = base_markup + brand_bonus - mileage_penalty - age_penalty - risk_penalty
    multiplier = max(1.05, min(multiplier, 1.85))

    retail = price * multiplier

    return int(round(retail / 100) * 100)


def estimate_recon(row):
    title = f"{row.get('title', '')} {row.get('body', '')}".lower()
    miles = row.get("miles")
    price = row.get("price") or 0

    recon = 650

    if miles:
        if miles > 200000:
            recon += 1000
        elif miles > 160000:
            recon += 650
        elif miles > 120000:
            recon += 400
        else:
            recon += 250

    if any(w in title for w in ["needs", "mechanic", "check engine", "cel", "misfire"]):
        recon += 1200

    if any(w in title for w in ["transmission", "head gasket", "overheating"]):
        recon += 2500

    if any(w in title for w in ["rebuilt", "salvage", "branded"]):
        recon += 700

    if price < 3500:
        recon += 500

    return int(round(recon / 50) * 50)


def evaluate_listing(row, target_profit):
    price = row.get("price")
    title = row.get("title", "")
    body = row.get("body", "")

    if not price:
        row["decision"] = "SKIP"
        row["reason"] = "No price found"
        row["retail"] = None
        row["recon"] = None
        row["profit"] = None
        row["buy_target"] = None
        row["risk"] = "HIGH"
        row["score"] = 0
        return row

    retail = estimate_retail_value(row)
    recon = estimate_recon(row)

    profit = retail - price - recon if retail else None
    buy_target = retail - recon - target_profit if retail else None

    text = f"{title} {body}".lower()

    risk_points = 0

    if any(w in text for w in HIGH_RISK_WORDS):
        risk_points += 2

    miles = row.get("miles")
    year = row.get("year")

    if miles and miles > 180000:
        risk_points += 2
    elif miles and miles > 140000:
        risk_points += 1

    if year and year < 2006:
        risk_points += 1

    if price > 12000:
        risk_points += 1

    if risk_points >= 3:
        risk = "HIGH"
    elif risk_points == 2:
        risk = "MED"
    else:
        risk = "LOW"

    score = 0

    if profit is not None:
        score += min(50, max(0, profit / 100))

    if buy_target is not None and price <= buy_target:
        score += 25

    if risk == "LOW":
        score += 20
    elif risk == "MED":
        score += 8

    if any(b in text for b in ["toyota", "honda", "lexus", "acura"]):
        score += 10

    score = int(max(0, min(score, 100)))

    if not is_probably_vehicle(title, body):
        decision = "SKIP"
        reason = "Not a usable car listing"
    elif profit is None:
        decision = "SKIP"
        reason = "Missing numbers"
    elif profit >= target_profit and risk != "HIGH":
        decision = "BUY"
        reason = "Profit target met"
    elif profit >= target_profit and risk == "HIGH":
        decision = "CHECK"
        reason = "Profit possible but high risk"
    elif buy_target and price > buy_target:
        decision = "NEGOTIATE"
        reason = f"Needs lower buy price"
    else:
        decision = "SKIP"
        reason = "Profit target not met"

    row["decision"] = decision
    row["reason"] = reason
    row["retail"] = retail
    row["recon"] = recon
    row["profit"] = profit
    row["buy_target"] = buy_target
    row["risk"] = risk
    row["score"] = score

    return row


@st.cache_data(ttl=180, show_spinner=False)
def scan_craigslist(max_price, target_profit):
    debug = []

    rss_url = build_craigslist_rss_url(max_price)
    html_url = build_craigslist_html_url(max_price)

    debug.append(f"RSS URL: {rss_url}")
    rss_response = fetch_url(rss_url)
    debug.append(f"RSS status: {rss_response['status']}")
    debug.append(f"RSS final URL: {rss_response['final_url']}")
    if rss_response["error"]:
        debug.append(f"RSS error: {rss_response['error']}")

    listings = []

    if rss_response["ok"]:
        listings = parse_rss(rss_response["text"])
        debug.append(f"RSS parsed listings: {len(listings)}")
    else:
        debug.append("RSS failed or blocked.")

    if not listings:
        debug.append(f"HTML URL: {html_url}")
        html_response = fetch_url(html_url)
        debug.append(f"HTML status: {html_response['status']}")
        debug.append(f"HTML final URL: {html_response['final_url']}")
        if html_response["error"]:
            debug.append(f"HTML error: {html_response['error']}")

        if html_response["ok"]:
            listings = parse_html(html_response["text"])
            debug.append(f"HTML parsed listings: {len(listings)}")
        else:
            debug.append("HTML failed or blocked.")

    listings = dedupe_listings(listings)
    debug.append(f"Deduped listings: {len(listings)}")

    evaluated = []

    for item in listings:
        if not item.get("price"):
            item["price"] = extract_price(item.get("title", "")) or extract_price(item.get("body", ""))

        if item.get("price") and item["price"] > max_price:
            continue

        evaluated.append(evaluate_listing(item, target_profit))

    evaluated = sorted(
        evaluated,
        key=lambda x: (
            0 if x.get("decision") == "BUY" else
            1 if x.get("decision") == "CHECK" else
            2 if x.get("decision") == "NEGOTIATE" else
            3,
            -x.get("score", 0),
            -(x.get("profit") or -999999)
        )
    )

    return evaluated, debug, html_url


# ============================================================
# UI
# ============================================================

st.title("Car Flip AI")
st.markdown(
    "<div class='sub'>Salt Lake owner-only scanner — ZIP 84107, 90-mile radius</div>",
    unsafe_allow_html=True
)

target_profit = st.number_input(
    "Target profit",
    min_value=500,
    max_value=10000,
    value=2000,
    step=250,
)

max_price = st.number_input(
    "Max asking price",
    min_value=1000,
    max_value=50000,
    value=15000,
    step=500,
)

show_skipped = st.toggle("Show skipped cars too", value=False)

scan = st.button("Scan Salt Lake 90 Miles")

st.caption("Search: ZIP 84107, radius 90 miles, owner-only")

if scan:
    with st.spinner("Scanning Craigslist..."):
        rows, debug, manual_url = scan_craigslist(max_price, target_profit)

    with st.expander("Debug info"):
        st.markdown(
            "<div class='debug-box'>" + "<br>".join(debug) + "</div>",
            unsafe_allow_html=True
        )

    if not rows:
        st.error(
            "No listings loaded. Craigslist is blocking the request from Streamlit Cloud "
            "or returned no usable owner car listings."
        )

        st.info(
            "This is not a crash. Streamlit Cloud is being blocked by Craigslist. "
            "Use the button below to open the exact Craigslist search on your phone."
        )

        st.link_button("Open Craigslist Search", manual_url)

        st.stop()

    buy_count = len([x for x in rows if x["decision"] == "BUY"])
    check_count = len([x for x in rows if x["decision"] == "CHECK"])
    negotiate_count = len([x for x in rows if x["decision"] == "NEGOTIATE"])

    st.success(
        f"Loaded {len(rows)} listings. "
        f"BUY: {buy_count} | CHECK: {check_count} | NEGOTIATE: {negotiate_count}"
    )

    shown = 0

    for row in rows:
        if not show_skipped and row["decision"] == "SKIP":
            continue

        shown += 1

        decision = row["decision"]

        if decision == "BUY":
            decision_class = "good"
        elif decision in ["CHECK", "NEGOTIATE"]:
            decision_class = "warn"
        else:
            decision_class = "bad"

        title = row.get("title", "Untitled")
        price = row.get("price")
        year = row.get("year")
        miles = row.get("miles")
        retail = row.get("retail")
        recon = row.get("recon")
        profit = row.get("profit")
        buy_target = row.get("buy_target")
        risk = row.get("risk")
        score = row.get("score")
        url = row.get("url", "")

        miles_text = f"{miles:,} miles" if miles else "Miles unknown"
        year_text = str(year) if year else "Year unknown"

        st.markdown(f"""
        <div class="car-card">
            <div style="font-size:1.05rem;font-weight:900;">{html.escape(title)}</div>
            <div class="small">{year_text} • {miles_text}</div>
            <br>
            <div>Ask: <b>{money(price)}</b></div>
            <div>Estimated retail: <b>{money(retail)}</b></div>
            <div>Estimated recon: <b>{money(recon)}</b></div>
            <div>Estimated profit: <b>{money(profit)}</b></div>
            <div>Max buy target: <b>{money(buy_target)}</b></div>
            <br>
            <div>Risk: <b>{risk}</b> | Score: <b>{score}/100</b></div>
            <div class="{decision_class}">{decision} — {html.escape(row.get("reason", ""))}</div>
        </div>
        """, unsafe_allow_html=True)

        if url:
            st.link_button("Open Listing", url)

    if shown == 0:
        st.warning("Only skipped cars were found. Turn on 'Show skipped cars too' to see them.")

else:
    st.info("Tap **Scan Salt Lake 90 Miles** to start.")
