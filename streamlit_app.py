import re
import math
import hashlib
from datetime import datetime
from urllib.parse import urlencode

import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup


# =========================================================
# CAR FLIP AI — MOBILE SAFE VERSION
# Salt Lake City / ZIP 84107 / 90 mile radius
# =========================================================

ZIP_CODE = "84107"
SEARCH_RADIUS_MILES = 90
CRAIGSLIST_SITE = "saltlakecity"
BASE_URL = f"https://{CRAIGSLIST_SITE}.craigslist.org"

MIN_YEAR = 2005
MAX_PRICE = 15000
MAX_MILES = 220000
TARGET_PROFIT = 2000

EXCLUDE_WORDS = [
    "rv", "camper", "motorhome", "trailer", "boat", "semi", "f650",
    "box truck", "bus", "atv", "utv", "parts only", "mechanic special",
    "salvage parts", "not running"
]

GOOD_MAKES = {
    "toyota": 1.18,
    "honda": 1.16,
    "lexus": 1.15,
    "acura": 1.10,
    "mazda": 1.07,
    "subaru": 1.04,
    "ford": 1.00,
    "chevrolet": 0.98,
    "chevy": 0.98,
    "gmc": 0.98,
    "hyundai": 0.97,
    "kia": 0.96,
    "nissan": 0.94,
    "volkswagen": 0.90,
    "vw": 0.90,
    "bmw": 0.82,
    "mercedes": 0.80,
    "audi": 0.79,
    "mini": 0.75,
    "chrysler": 0.78,
    "dodge": 0.80,
    "jeep": 0.85,
    "cadillac": 0.82,
    "buick": 0.88,
}

BODY_BONUS = {
    "camry": 800,
    "corolla": 900,
    "civic": 900,
    "accord": 800,
    "rav4": 1200,
    "cr-v": 1200,
    "crv": 1200,
    "highlander": 1300,
    "pilot": 1100,
    "tacoma": 2200,
    "tundra": 1800,
    "4runner": 2500,
    "sienna": 1000,
    "odyssey": 900,
    "prius": 900,
    "rx": 1200,
    "es": 800,
    "gx": 1800,
    "forester": 700,
    "outback": 650,
    "cx-5": 750,
    "mazda3": 500,
    "f-150": 1100,
    "f150": 1100,
    "silverado": 1000,
    "sierra": 1000,
}


# =========================================================
# PAGE SETUP
# =========================================================

st.set_page_config(
    page_title="Car Flip AI",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
.block-container {
    padding-top: 1rem !important;
    padding-left: 0.85rem !important;
    padding-right: 0.85rem !important;
    max-width: 760px !important;
}
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

h1 {
    font-size: 2.35rem !important;
    line-height: 1.05 !important;
    margin-bottom: 0.2rem !important;
}

.sub {
    color: #9ca3af;
    font-size: 0.98rem;
    margin-bottom: 1rem;
}

.stButton > button {
    width: 100%;
    border-radius: 14px;
    font-weight: 800;
    padding: 0.8rem 1rem;
}

.car-card {
    border: 1px solid rgba(250,250,250,0.16);
    border-radius: 18px;
    padding: 15px;
    margin-bottom: 14px;
    background: rgba(255,255,255,0.035);
}

.buy {
    color: #22c55e;
    font-weight: 900;
}

.maybe {
    color: #f59e0b;
    font-weight: 900;
}

.skip {
    color: #ef4444;
    font-weight: 900;
}

.metric-line {
    font-size: 0.95rem;
    line-height: 1.45;
}

.small {
    color: #9ca3af;
    font-size: 0.85rem;
}
</style>
""", unsafe_allow_html=True)

st.title("Car Flip AI")
st.markdown(
    f"<div class='sub'>Salt Lake City private-party scan • ZIP {ZIP_CODE} • {SEARCH_RADIUS_MILES} mile radius</div>",
    unsafe_allow_html=True
)


# =========================================================
# HELPERS
# =========================================================

def money(n):
    try:
        return f"${int(round(float(n))):,}"
    except Exception:
        return "$0"


def clean_text(x):
    if not x:
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()


def extract_price(text):
    if not text:
        return None

    text = text.replace(",", "")
    patterns = [
        r"\$(\d{3,6})",
        r"\b(\d{4,6})\b"
    ]

    for p in patterns:
        m = re.search(p, text)
        if m:
            price = int(m.group(1))
            if 500 <= price <= 100000:
                return price
    return None


def extract_year(text):
    if not text:
        return None
    m = re.search(r"\b(19[8-9]\d|20[0-2]\d)\b", text)
    if m:
        y = int(m.group(1))
        if 1980 <= y <= datetime.now().year + 1:
            return y
    return None


def extract_miles(text):
    if not text:
        return None

    text_l = text.lower().replace(",", "")

    patterns = [
        r"(\d{2,3})\s?k\s?(?:mi|mile|miles)",
        r"(\d{5,6})\s?(?:mi|mile|miles|odometer)",
        r"miles?\s?:?\s?(\d{5,6})",
        r"odometer\s?:?\s?(\d{5,6})",
    ]

    for p in patterns:
        m = re.search(p, text_l)
        if m:
            val = int(m.group(1))
            if val < 1000:
                val *= 1000
            if 10_000 <= val <= 400_000:
                return val
    return None


def detect_make(title):
    t = title.lower()
    for make in GOOD_MAKES:
        if re.search(rf"\b{re.escape(make)}\b", t):
            return make
    return "unknown"


def detect_model_bonus(title):
    t = title.lower()
    bonus = 0
    matched = None

    for model, val in BODY_BONUS.items():
        if model in t:
            bonus = max(bonus, val)
            matched = model

    return bonus, matched


def is_bad_listing(title):
    t = title.lower()
    return any(word in t for word in EXCLUDE_WORDS)


def estimate_market_value(title, asking_price, year=None, miles=None):
    """
    This is not KBB. This is a local flip estimate formula so the app does not
    go blank when valuation sites are unavailable.
    """

    current_year = datetime.now().year
    make = detect_make(title)
    make_mult = GOOD_MAKES.get(make, 0.90)

    model_bonus, matched_model = detect_model_bonus(title)

    if year is None:
        year = extract_year(title)

    if miles is None:
        miles = extract_miles(title)

    if year:
        age = max(0, current_year - year)
    else:
        age = 13

    if miles:
        mileage_penalty = max(0, (miles - 100000) / 1000) * 35
        low_mile_bonus = max(0, (100000 - miles) / 1000) * 20
    else:
        mileage_penalty = 1200
        low_mile_bonus = 0

    base_value = 14500
    age_penalty = age * 650

    estimated = (
        base_value
        - age_penalty
        - mileage_penalty
        + low_mile_bonus
        + model_bonus
    ) * make_mult

    if asking_price:
        # Avoid crazy fantasy numbers. Keep market estimate realistic around ask.
        estimated = max(asking_price * 1.05, estimated)
        estimated = min(estimated, asking_price * 1.85)

    estimated = max(1200, estimated)

    return int(round(estimated / 100) * 100), make, matched_model


def estimate_recon(title, year=None, miles=None):
    t = title.lower()
    recon = 700

    if any(x in t for x in ["check engine", "cel", "misfire", "rough", "needs work"]):
        recon += 900
    if any(x in t for x in ["dent", "damage", "bumper", "fender"]):
        recon += 600
    if any(x in t for x in ["salvage", "rebuilt"]):
        recon += 1200
    if any(x in t for x in ["bmw", "audi", "mercedes", "mini", "volkswagen", "vw"]):
        recon += 700
    if miles and miles > 180000:
        recon += 500
    if year and year < 2010:
        recon += 400

    return int(recon)


def evaluate_listing(item):
    title = item.get("title", "")
    price = item.get("price")

    year = extract_year(title)
    miles = item.get("miles") or extract_miles(title)

    market_value, make, model = estimate_market_value(title, price, year, miles)
    recon = estimate_recon(title, year, miles)

    safe_offer = market_value - recon - TARGET_PROFIT

    if price:
        estimated_profit = market_value - price - recon
    else:
        estimated_profit = 0

    if not price:
        decision = "SKIP"
        reason = "No price shown"
    elif year and year < MIN_YEAR:
        decision = "SKIP"
        reason = f"Too old: {year}"
    elif miles and miles > MAX_MILES:
        decision = "SKIP"
        reason = f"Too many miles: {miles:,}"
    elif price > MAX_PRICE:
        decision = "SKIP"
        reason = f"Price over budget: {money(price)}"
    elif estimated_profit >= TARGET_PROFIT:
        decision = "BUY"
        reason = f"Estimated profit over {money(TARGET_PROFIT)}"
    elif estimated_profit >= 1000:
        decision = "MAYBE"
        reason = "Close deal if seller negotiates"
    else:
        decision = "SKIP"
        reason = "Not enough margin"

    score = 0
    score += min(40, max(0, estimated_profit / 100))
    score += 20 if make in ["toyota", "honda", "lexus", "acura"] else 0
    score += 10 if model else 0
    score += 10 if miles and miles < 140000 else 0
    score -= 20 if any(x in title.lower() for x in ["bmw", "audi", "mini", "mercedes"]) else 0
    score = int(max(0, min(100, score)))

    item.update({
        "year": year,
        "miles": miles,
        "make": make,
        "model": model,
        "market_value": market_value,
        "recon": recon,
        "safe_offer": max(500, int(round(safe_offer / 100) * 100)),
        "estimated_profit": int(round(estimated_profit / 100) * 100),
        "decision": decision,
        "reason": reason,
        "score": score,
    })

    return item


def dedupe_listings(items):
    seen = set()
    out = []

    for item in items:
        key_source = (
            clean_text(item.get("title", "")).lower()
            + str(item.get("price", ""))
            + clean_text(item.get("link", "")).lower()
        )
        key = hashlib.md5(key_source.encode("utf-8")).hexdigest()

        if key not in seen:
            seen.add(key)
            out.append(item)

    return out


# =========================================================
# CRAIGSLIST FETCH
# =========================================================

@st.cache_data(ttl=300, show_spinner=False)
def fetch_craigslist():
    params = {
        "postal": ZIP_CODE,
        "search_distance": SEARCH_RADIUS_MILES,
        "purveyor": "owner",
        "bundleDuplicates": 1,
        "sort": "date",
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    results = []
    errors = []

    # 1) RSS first
    rss_params = params.copy()
    rss_params["format"] = "rss"
    rss_url = f"{BASE_URL}/search/cta?" + urlencode(rss_params)

    try:
        r = requests.get(rss_url, headers=headers, timeout=15)
        if r.status_code == 200 and r.text.strip():
            soup = BeautifulSoup(r.text, "xml")
            items = soup.find_all("item")

            for it in items:
                title = clean_text(it.title.get_text() if it.title else "")
                link = clean_text(it.link.get_text() if it.link else "")
                desc = clean_text(it.description.get_text() if it.description else "")
                price = extract_price(title) or extract_price(desc)

                if title and not is_bad_listing(title):
                    results.append({
                        "title": title,
                        "price": price,
                        "link": link,
                        "source": "Craigslist RSS",
                    })
        else:
            errors.append(f"RSS returned status {r.status_code}")
    except Exception as e:
        errors.append(f"RSS error: {e}")

    # 2) HTML fallback
    if len(results) == 0:
        html_url = f"{BASE_URL}/search/cta?" + urlencode(params)

        try:
            r = requests.get(html_url, headers=headers, timeout=15)
            if r.status_code == 200 and r.text.strip():
                soup = BeautifulSoup(r.text, "html.parser")

                rows = soup.select("li.cl-search-result, li.result-row, div.cl-search-result")

                for row in rows:
                    title_el = (
                        row.select_one(".titlestring")
                        or row.select_one("a.posting-title")
                        or row.select_one("a.result-title")
                        or row.select_one("a")
                    )

                    price_el = (
                        row.select_one(".priceinfo")
                        or row.select_one(".result-price")
                        or row.select_one(".price")
                    )

                    if not title_el:
                        continue

                    title = clean_text(title_el.get_text(" "))
                    link = title_el.get("href", "")

                    if link.startswith("/"):
                        link = BASE_URL + link

                    price = extract_price(price_el.get_text(" ")) if price_el else extract_price(title)

                    if title and not is_bad_listing(title):
                        results.append({
                            "title": title,
                            "price": price,
                            "link": link,
                            "source": "Craigslist HTML",
                        })
            else:
                errors.append(f"HTML returned status {r.status_code}")
        except Exception as e:
            errors.append(f"HTML error: {e}")

    results = dedupe_listings(results)
    results = [evaluate_listing(x) for x in results]

    results = sorted(
        results,
        key=lambda x: (
            x.get("decision") != "BUY",
            x.get("decision") != "MAYBE",
            -x.get("estimated_profit", 0),
            -x.get("score", 0),
        )
    )

    return results, errors, rss_url


# =========================================================
# CONTROLS
# =========================================================

col1, col2 = st.columns(2)

with col1:
    min_profit = st.number_input(
        "Target profit",
        min_value=500,
        max_value=8000,
        value=TARGET_PROFIT,
        step=500
    )

with col2:
    max_price_ui = st.number_input(
        "Max asking price",
        min_value=3000,
        max_value=50000,
        value=MAX_PRICE,
        step=1000
    )

show_all = st.toggle("Show skipped cars too", value=False)

scan = st.button("Scan Salt Lake 90 Miles")


# =========================================================
# MAIN APP
# =========================================================

if scan:
    with st.spinner("Scanning private-party listings..."):
        listings, errors, used_url = fetch_craigslist()

    st.caption(f"Search: ZIP {ZIP_CODE}, radius {SEARCH_RADIUS_MILES} miles, owner-only")

    if errors:
        with st.expander("Debug info"):
            for e in errors:
                st.write(e)
            st.write("Craigslist URL:")
            st.code(used_url)

    if not listings:
        st.error("No listings loaded. The app is running, but Craigslist returned no usable cars or blocked the request.")
        st.info("Open the debug box above. If you see 403, Craigslist is blocking Streamlit Cloud. The app is not crashed.")
        st.stop()

    filtered = []

    for item in listings:
        if item.get("price") and item["price"] > max_price_ui:
            continue

        # Recalculate visible decision based on UI profit target
        visible_profit = item.get("estimated_profit", 0)

        if visible_profit >= min_profit:
            item["decision"] = "BUY"
            item["reason"] = f"Estimated profit over {money(min_profit)}"
        elif visible_profit >= 1000:
            item["decision"] = "MAYBE"
            item["reason"] = "Only works if seller negotiates"
        else:
            item["decision"] = "SKIP"
            item["reason"] = "Not enough margin"

        if not show_all and item["decision"] == "SKIP":
            continue

        filtered.append(item)

    buy_count = sum(1 for x in filtered if x["decision"] == "BUY")
    maybe_count = sum(1 for x in filtered if x["decision"] == "MAYBE")

    st.success(f"Found {len(filtered)} usable listings • BUY: {buy_count} • MAYBE: {maybe_count}")

    for item in filtered[:50]:
        decision = item["decision"]
        css_class = "buy" if decision == "BUY" else "maybe" if decision == "MAYBE" else "skip"

        title = item.get("title", "Unknown")
        link = item.get("link", "")
        price = item.get("price")
        year = item.get("year")
        miles = item.get("miles")
        market = item.get("market_value")
        recon = item.get("recon")
        safe_offer = item.get("safe_offer")
        profit = item.get("estimated_profit")
        score = item.get("score")
        reason = item.get("reason")
        source = item.get("source")

        st.markdown("<div class='car-card'>", unsafe_allow_html=True)

        st.markdown(f"### {title}")

        st.markdown(
            f"<div class='{css_class}'>{decision} • Score {score}/100</div>",
            unsafe_allow_html=True
        )

        st.markdown(
            f"""
<div class='metric-line'>
<b>Ask:</b> {money(price) if price else "Not listed"}<br>
<b>Estimated retail:</b> {money(market)}<br>
<b>Estimated recon:</b> {money(recon)}<br>
<b>Safe buy target:</b> {money(safe_offer)}<br>
<b>Estimated profit:</b> {money(profit)}<br>
<b>Year:</b> {year if year else "Unknown"}<br>
<b>Miles:</b> {f"{miles:,}" if miles else "Unknown"}<br>
<b>Reason:</b> {reason}
</div>
""",
            unsafe_allow_html=True
        )

        if link:
            st.link_button("Open Listing", link)

        st.markdown(f"<div class='small'>Source: {source}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

else:
    st.info("Tap Scan Salt Lake 90 Miles.")
    st.markdown("""
This version fixes the blank-screen problem by:

- forcing **84107 + 90 mile radius**
- owner-only Craigslist search
- RSS first, HTML fallback second
- duplicate removal
- no repeated same car cards
- visible debug box if Craigslist blocks Streamlit
- mobile-safe layout
- buy target, estimated retail, recon, and profit numbers
""")
