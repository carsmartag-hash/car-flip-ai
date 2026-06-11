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


# ==========================================================
# CAR FLIP AI — CRAIGSLIST SLC 90-MILE SCANNER
# FULL MOBILE-SAFE STREAMLIT SCRIPT
# ==========================================================

st.set_page_config(
    page_title="Car Flip AI",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="collapsed"
)


# ==========================================================
# CSS
# ==========================================================

st.markdown(
    """
<style>
.block-container {
    padding-top: 1rem !important;
    padding-left: 0.85rem !important;
    padding-right: 0.85rem !important;
    max-width: 820px !important;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

h1 {
    font-size: 2.45rem !important;
    line-height: 1.05 !important;
    margin-bottom: 0.2rem !important;
}

.sub {
    color: #a7b0be;
    font-size: 1rem;
    margin-bottom: 1rem;
}

.top-box {
    background: #082f1b;
    border: 1px solid #22c55e;
    border-radius: 18px;
    padding: 14px 16px;
    margin-bottom: 18px;
    color: #c6f6d5;
    font-size: 1.02rem;
}

.car-card {
    border: 1px solid rgba(255,255,255,0.18);
    background: #111827;
    border-radius: 22px;
    padding: 18px;
    margin: 18px 0;
    box-shadow: 0 8px 20px rgba(0,0,0,0.20);
}

.car-title {
    font-size: 1.45rem;
    font-weight: 900;
    line-height: 1.15;
    margin-bottom: 12px;
    color: #f9fafb;
}

.metric-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 10px 0 12px 0;
}

.pill {
    background: #0b1220;
    border: 1px solid rgba(255,255,255,0.12);
    color: #e5e7eb;
    border-radius: 999px;
    padding: 7px 10px;
    font-size: 0.93rem;
    white-space: nowrap;
}

.buy {
    display: inline-block;
    background: #14532d;
    border: 1px solid #22c55e;
    color: #bbf7d0;
    font-weight: 900;
    border-radius: 999px;
    padding: 7px 13px;
    margin-top: 4px;
    margin-bottom: 10px;
}

.maybe {
    display: inline-block;
    background: #422006;
    border: 1px solid #f59e0b;
    color: #fde68a;
    font-weight: 900;
    border-radius: 999px;
    padding: 7px 13px;
    margin-top: 4px;
    margin-bottom: 10px;
}

.skip {
    display: inline-block;
    background: #450a0a;
    border: 1px solid #ef4444;
    color: #fecaca;
    font-weight: 900;
    border-radius: 999px;
    padding: 7px 13px;
    margin-top: 4px;
    margin-bottom: 10px;
}

.small {
    color: #d1d5db;
    font-size: 0.98rem;
    line-height: 1.55;
}

.good {
    color: #86efac;
    font-weight: 800;
}

.bad {
    color: #fca5a5;
    font-weight: 800;
}

.link-btn {
    display: block;
    text-align: center;
    background: #2563eb;
    color: white !important;
    padding: 12px 14px;
    border-radius: 14px;
    text-decoration: none !important;
    font-weight: 900;
    margin-top: 14px;
}

.link-btn:hover {
    background: #1d4ed8;
}

hr {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.12);
    margin: 12px 0;
}

.stButton > button {
    width: 100%;
    border-radius: 14px;
    font-weight: 900;
    padding: 0.75rem 1rem;
}

@media (max-width: 600px) {
    h1 {
        font-size: 2.15rem !important;
    }

    .car-card {
        padding: 15px;
        border-radius: 20px;
    }

    .car-title {
        font-size: 1.28rem;
    }

    .pill {
        font-size: 0.88rem;
        padding: 6px 9px;
    }

    .small {
        font-size: 0.94rem;
    }
}
</style>
""",
    unsafe_allow_html=True,
)


# ==========================================================
# SETTINGS
# ==========================================================

st.markdown("# 🚗 Car Flip AI")
st.markdown(
    '<div class="sub">Salt Lake Craigslist private-party scanner · 84107 · 90-mile radius</div>',
    unsafe_allow_html=True,
)

with st.expander("Scanner settings", expanded=False):
    col1, col2 = st.columns(2)

    with col1:
        zip_code = st.text_input("ZIP code", value="84107")
        radius = st.number_input("Radius miles", min_value=10, max_value=250, value=90, step=5)
        max_price = st.number_input("Max asking price", min_value=1000, max_value=50000, value=15000, step=500)

    with col2:
        min_profit = st.number_input("Minimum target profit", min_value=500, max_value=10000, value=2000, step=250)
        max_miles = st.number_input("Max mileage", min_value=50000, max_value=300000, value=190000, step=5000)
        max_results = st.number_input("Listings to scan", min_value=10, max_value=120, value=60, step=10)


# ==========================================================
# VEHICLE DATA
# ==========================================================

BAD_TITLE_WORDS = [
    "parts",
    "part out",
    "mechanic special",
    "does not run",
    "not running",
    "no title",
    "salvage only",
    "bill of sale",
    "camper",
    "rv",
    "motorhome",
    "trailer",
    "semi",
    "box truck",
    "f650",
    "f-650",
    "bus",
    "boat",
    "atv",
    "utv",
    "motorcycle",
    "scooter",
    "project",
]

GOOD_MAKES = {
    "toyota": 1.18,
    "lexus": 1.18,
    "honda": 1.15,
    "acura": 1.10,
    "mazda": 1.05,
    "subaru": 1.03,
    "ford": 1.00,
    "chevrolet": 0.98,
    "chevy": 0.98,
    "gmc": 0.98,
    "nissan": 0.95,
    "hyundai": 0.95,
    "kia": 0.93,
}

RISKY_MAKES = {
    "bmw": 0.78,
    "mercedes": 0.76,
    "audi": 0.76,
    "volkswagen": 0.82,
    "vw": 0.82,
    "mini": 0.70,
    "land rover": 0.60,
    "range rover": 0.60,
    "jaguar": 0.62,
    "fiat": 0.65,
    "chrysler": 0.82,
    "dodge": 0.84,
}

MAKE_ALIASES = [
    "toyota", "lexus", "honda", "acura", "mazda", "subaru",
    "ford", "chevrolet", "chevy", "gmc", "nissan", "hyundai",
    "kia", "bmw", "mercedes", "audi", "volkswagen", "vw",
    "mini", "land rover", "range rover", "jaguar", "fiat",
    "chrysler", "dodge", "jeep", "ram", "cadillac", "buick",
    "lincoln", "infiniti", "mitsubishi", "volvo",
]

MODEL_BONUS = {
    "camry": 1.12,
    "corolla": 1.12,
    "rav4": 1.15,
    "highlander": 1.16,
    "sienna": 1.15,
    "tacoma": 1.22,
    "tundra": 1.18,
    "4runner": 1.24,
    "civic": 1.12,
    "accord": 1.12,
    "cr-v": 1.14,
    "crv": 1.14,
    "pilot": 1.13,
    "odyssey": 1.10,
    "fit": 1.08,
    "rx": 1.16,
    "es": 1.12,
    "mdx": 1.08,
    "tsx": 1.04,
    "cx-5": 1.08,
    "cx5": 1.08,
    "outback": 1.08,
    "forester": 1.08,
    "f150": 1.08,
    "f-150": 1.08,
    "silverado": 1.08,
    "sierra": 1.08,
}


# ==========================================================
# HELPERS
# ==========================================================

def money(n):
    try:
        return "${:,.0f}".format(float(n))
    except Exception:
        return "$0"


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def extract_price(text):
    text = text or ""
    prices = re.findall(r"\$[\s]*([0-9][0-9,]{2,})", text)
    if not prices:
        return None

    nums = []
    for p in prices:
        try:
            nums.append(int(p.replace(",", "")))
        except Exception:
            pass

    nums = [x for x in nums if 500 <= x <= 80000]
    if not nums:
        return None

    return nums[0]


def extract_year(text):
    match = re.search(r"\b(19[8-9][0-9]|20[0-2][0-9])\b", text or "")
    if match:
        return int(match.group(1))
    return None


def extract_miles(text):
    t = (text or "").lower().replace(",", "")

    patterns = [
        r"\b([0-9]{2,3})\s?k\s?(?:miles|mi|mile)?\b",
        r"\b([0-9]{5,6})\s?(?:miles|mi|mile)\b",
        r"\bmiles[:\s]+([0-9]{5,6})\b",
        r"\bodometer[:\s]+([0-9]{5,6})\b",
    ]

    for p in patterns:
        m = re.search(p, t)
        if not m:
            continue

        val = int(m.group(1))

        if val < 1000 and "k" in m.group(0):
            val *= 1000

        if 20000 <= val <= 350000:
            return val

    return None


def detect_make(text):
    t = (text or "").lower()
    for make in MAKE_ALIASES:
        if re.search(rf"\b{re.escape(make)}\b", t):
            if make == "chevy":
                return "chevrolet"
            if make == "vw":
                return "volkswagen"
            return make
    return None


def detect_model_bonus(text):
    t = (text or "").lower()
    bonus = 1.0
    found = []
    for model, mult in MODEL_BONUS.items():
        if re.search(rf"\b{re.escape(model)}\b", t):
            bonus = max(bonus, mult)
            found.append(model)
    return bonus, found


def has_bad_words(text):
    t = (text or "").lower()
    found = []
    for word in BAD_TITLE_WORDS:
        if word in t:
            found.append(word)
    return found


def craigslist_url(zip_code, radius, max_price):
    params = {
        "format": "rss",
        "postal": zip_code,
        "search_distance": int(radius),
        "max_price": int(max_price),
        "sort": "date",
        "bundleDuplicates": "1",
        "purveyor": "owner",
    }

    return "https://saltlakecity.craigslist.org/search/cto?" + urlencode(params)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_craigslist_rss(zip_code, radius, max_price):
    url = craigslist_url(zip_code, radius, max_price)

    headers = {
        "User-Agent": "Mozilla/5.0 CarFlipAI/1.0",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "xml")
    items = soup.find_all("item")

    rows = []

    for item in items:
        title = clean_text(item.title.text if item.title else "")
        link = clean_text(item.link.text if item.link else "")
        desc = clean_text(item.description.text if item.description else "")
        pub_date = clean_text(item.pubDate.text if item.pubDate else "")

        combined = f"{title} {desc}"

        price = extract_price(combined)
        year = extract_year(combined)
        miles = extract_miles(combined)
        make = detect_make(combined)

        if not title or not link:
            continue

        rows.append(
            {
                "title": title,
                "link": link,
                "description": desc,
                "pub_date": pub_date,
                "price": price,
                "year": year,
                "miles": miles,
                "make": make,
                "raw": combined,
            }
        )

    return rows


def estimate_vehicle(row):
    title = row.get("title", "")
    raw = row.get("raw", "")
    text = f"{title} {raw}".lower()

    ask = row.get("price")
    year = row.get("year")
    miles = row.get("miles")
    make = row.get("make")

    bad_flags = has_bad_words(text)

    if ask is None:
        return None

    if ask < 800 or ask > max_price:
        return None

    if year is None:
        year = 2010

    if miles is None:
        miles = 160000

    age = max(1, datetime.now().year - year)

    make_mult = 1.0
    if make in GOOD_MAKES:
        make_mult *= GOOD_MAKES[make]
    if make in RISKY_MAKES:
        make_mult *= RISKY_MAKES[make]

    model_mult, model_hits = detect_model_bonus(text)
    make_mult *= model_mult

    # Base resale model
    base = ask * 1.34

    # Year adjustment
    if year >= 2018:
        base *= 1.15
    elif year >= 2015:
        base *= 1.10
    elif year >= 2011:
        base *= 1.03
    elif year <= 2006:
        base *= 0.88

    # Mileage adjustment
    if miles <= 90000:
        base *= 1.17
    elif miles <= 120000:
        base *= 1.10
    elif miles <= 150000:
        base *= 1.02
    elif miles <= 180000:
        base *= 0.92
    elif miles <= 220000:
        base *= 0.78
    else:
        base *= 0.62

    base *= make_mult

    # Market ceiling for older high-mile cars
    if year <= 2010 and miles > 170000:
        base = min(base, 8500)

    if year <= 2007 and miles > 180000:
        base = min(base, 6500)

    est_resale = round(base / 100) * 100

    # Negotiation estimate
    if ask <= 3500:
        expected_buy = ask * 0.80
    elif ask <= 7000:
        expected_buy = ask * 0.86
    elif ask <= 11000:
        expected_buy = ask * 0.90
    else:
        expected_buy = ask * 0.93

    expected_buy = round(expected_buy / 100) * 100

    # Recon allowance
    recon = 900

    if miles > 170000:
        recon += 400
    if miles > 210000:
        recon += 500
    if year <= 2008:
        recon += 300
    if make in RISKY_MAKES:
        recon += 700
    if bad_flags:
        recon += 1000

    fees = 350

    estimated_profit = est_resale - expected_buy - recon - fees
    max_buy = est_resale - recon - fees - min_profit

    # Score
    score = 50

    if estimated_profit >= min_profit:
        score += 25
    elif estimated_profit >= 1000:
        score += 12
    else:
        score -= 15

    if make in GOOD_MAKES:
        score += 10
    if make in RISKY_MAKES:
        score -= 15

    if miles <= 130000:
        score += 10
    elif miles > max_miles:
        score -= 25

    if bad_flags:
        score -= 35

    if ask <= max_buy:
        score += 10

    score = max(0, min(100, int(score)))

    good_signs = []

    if make in GOOD_MAKES:
        good_signs.append(f"strong resale make: {make}")
    if model_hits:
        good_signs.append("desirable model")
    if miles <= 130000:
        good_signs.append("lower mileage")
    if estimated_profit >= min_profit:
        good_signs.append("profit target possible")

    risk_flags = []

    if bad_flags:
        risk_flags.extend(bad_flags)
    if make in RISKY_MAKES:
        risk_flags.append(f"higher repair-risk make: {make}")
    if miles > max_miles:
        risk_flags.append("mileage above your limit")
    if year <= 2007:
        risk_flags.append("older unit")
    if estimated_profit < min_profit:
        risk_flags.append("profit below target")

    if score >= 78 and estimated_profit >= min_profit and not bad_flags and miles <= max_miles:
        decision = "BUY CANDIDATE"
        decision_class = "buy"
    elif score >= 58 and estimated_profit >= 800 and not bad_flags:
        decision = "MAYBE / NEGOTIATE"
        decision_class = "maybe"
    else:
        decision = "SKIP"
        decision_class = "skip"

    return {
        "ask": ask,
        "year": year,
        "miles": miles,
        "make": make or "unknown",
        "est_resale": est_resale,
        "expected_buy": expected_buy,
        "recon": recon,
        "fees": fees,
        "profit": estimated_profit,
        "max_buy": max_buy,
        "score": score,
        "decision": decision,
        "decision_class": decision_class,
        "risk_flags": risk_flags,
        "good_signs": good_signs,
    }


def render_card(row, ev):
    title = html.escape(row.get("title", "Untitled"))
    link = html.escape(row.get("link", "#"))

    risk = ", ".join(ev["risk_flags"]) if ev["risk_flags"] else "No major red flags found from listing text"
    good = ", ".join(ev["good_signs"]) if ev["good_signs"] else "No strong positive signs found from listing text"

    risk = html.escape(risk)
    good = html.escape(good)

    vehicle_line = f'{ev["year"]} · {ev["make"].title()} · Miles {ev["miles"]:,}'

    card_html = f"""
<div class="car-card">
    <div class="car-title">{title}</div>

    <div class="metric-row">
        <span class="pill">Ask: <b>{money(ev["ask"])}</b></span>
        <span class="pill">Est. resale: <b>{money(ev["est_resale"])}</b></span>
        <span class="pill">Max buy: <b>{money(ev["max_buy"])}</b></span>
        <span class="pill">Est. profit: <b>{money(ev["profit"])}</b></span>
        <span class="pill">Score: <b>{ev["score"]}/100</b></span>
    </div>

    <div class="{ev["decision_class"]}">{ev["decision"]}</div>

    <div class="small">
        <b>Vehicle:</b> {html.escape(vehicle_line)}<br>
        <b>Expected negotiated buy:</b> {money(ev["expected_buy"])}<br>
        <b>Recon allowance:</b> {money(ev["recon"])}<br>
        <b>Fees:</b> {money(ev["fees"])}<br>
        <b>Risk flags:</b> {risk}<br>
        <b>Good signs:</b> {good}
    </div>

    <a class="link-btn" href="{link}" target="_blank">Open Craigslist Listing</a>
</div>
"""

    st.markdown(card_html, unsafe_allow_html=True)


# ==========================================================
# MAIN RUN
# ==========================================================

scan = st.button("Scan Craigslist Now")

if scan:
    with st.spinner("Scanning Craigslist owner listings..."):
        try:
            listings = fetch_craigslist_rss(zip_code, radius, max_price)
        except Exception as e:
            st.error(f"Craigslist scan failed: {e}")
            st.stop()

    seen = set()
    evaluated = []

    for row in listings:
        unique = hashlib.md5((row.get("title", "") + row.get("link", "")).encode()).hexdigest()
        if unique in seen:
            continue
        seen.add(unique)

        ev = estimate_vehicle(row)
        if ev is None:
            continue

        if ev["decision"] == "SKIP":
            continue

        evaluated.append((row, ev))

    evaluated = sorted(
        evaluated,
        key=lambda x: (x[1]["decision"] != "BUY CANDIDATE", -x[1]["score"], -x[1]["profit"]),
    )

    evaluated = evaluated[: int(max_results)]

    buy_count = sum(1 for _, ev in evaluated if ev["decision"] == "BUY CANDIDATE")
    maybe_count = sum(1 for _, ev in evaluated if ev["decision"] == "MAYBE / NEGOTIATE")

    st.markdown(
        f"""
<div class="top-box">
    Parsed listings: <b>{len(listings)}</b> · 
    Buy candidates: <b>{buy_count}</b> · 
    Maybe/negotiation candidates: <b>{maybe_count}</b>
</div>
""",
        unsafe_allow_html=True,
    )

    if not evaluated:
        st.warning("No strong candidates found right now. Try raising max price or mileage, or scan again later.")
    else:
        for row, ev in evaluated:
            render_card(row, ev)

else:
    st.info("Tap **Scan Craigslist Now** to run the 84107 / 90-mile private-party scan.")
