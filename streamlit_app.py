import re
import math
import hashlib
from datetime import datetime
from urllib.parse import urlencode, quote_plus

import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup


# =========================
# PAGE SETUP
# =========================

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
    padding-left: 0.8rem !important;
    padding-right: 0.8rem !important;
    max-width: 780px !important;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

h1 {
    font-size: 2.4rem !important;
    line-height: 1.05 !important;
    margin-bottom: 0.2rem !important;
}

.sub {
    color: #9ca3af;
    font-size: 0.95rem;
    margin-bottom: 1rem;
}

.car-card {
    border: 1px solid rgba(250,250,250,0.18);
    border-radius: 18px;
    padding: 15px;
    margin-bottom: 16px;
    background: rgba(255,255,255,0.035);
}

.car-title {
    font-size: 1.12rem;
    font-weight: 800;
    margin-bottom: 8px;
}

.price {
    font-size: 1.45rem;
    font-weight: 900;
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
    font-size: 0.88rem;
}

.metric-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 10px;
}

.metric-box {
    background: rgba(255,255,255,0.055);
    border-radius: 12px;
    padding: 9px;
}

.metric-label {
    color: #9ca3af;
    font-size: 0.78rem;
}

.metric-value {
    font-size: 1rem;
    font-weight: 800;
}

.link-row {
    display: grid;
    grid-template-columns: 1fr;
    gap: 8px;
    margin-top: 12px;
}

.link-row a {
    text-align: center;
    padding: 11px;
    border-radius: 13px;
    text-decoration: none !important;
    font-weight: 900;
    display: block;
    background: rgba(255,255,255,0.10);
    color: white !important;
    border: 1px solid rgba(255,255,255,0.14);
}

.link-row a:hover {
    background: rgba(255,255,255,0.18);
}

.decision {
    margin-top: 10px;
    padding: 10px;
    border-radius: 13px;
    font-weight: 900;
    text-align: center;
}

.buy {
    background: rgba(34,197,94,0.17);
    color: #4ade80;
    border: 1px solid rgba(34,197,94,0.35);
}

.maybe {
    background: rgba(245,158,11,0.16);
    color: #fbbf24;
    border: 1px solid rgba(245,158,11,0.35);
}

.skip {
    background: rgba(239,68,68,0.14);
    color: #f87171;
    border: 1px solid rgba(239,68,68,0.35);
}

@media (min-width: 650px) {
    .link-row {
        grid-template-columns: 1fr 1fr 1fr;
    }
}
</style>
""", unsafe_allow_html=True)


# =========================
# CONFIG
# =========================

CRAIGSLIST_SITE = "saltlakecity"
ZIP_CODE = "84107"
SEARCH_DISTANCE = 90

MIN_YEAR = 2006
MAX_PRICE_DEFAULT = 15000
MAX_MILES_DEFAULT = 190000
TARGET_PROFIT_DEFAULT = 2000

HEADERS = {
    "User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/124 Safari/537.36"
}


# =========================
# HELPERS
# =========================

def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def extract_price(text):
    if not text:
        return None

    match = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})", text)
    if not match:
        return None

    try:
        price = int(match.group(1).replace(",", ""))
        if 500 <= price <= 100000:
            return price
    except Exception:
        return None

    return None


def extract_year(text):
    if not text:
        return None

    match = re.search(r"\b(19[8-9][0-9]|20[0-2][0-9]|2030)\b", text)
    if match:
        year = int(match.group(1))
        if 1980 <= year <= 2030:
            return year

    return None


def extract_miles(text):
    if not text:
        return None

    patterns = [
        r"([0-9]{2,3},[0-9]{3})\s*(?:miles|mile|mi|k miles|kms)?",
        r"([0-9]{2,3})k\s*(?:miles|mile|mi)?",
        r"miles[:\s]+([0-9,]{5,7})",
        r"odometer[:\s]+([0-9,]{5,7})"
    ]

    lower = text.lower()

    for pattern in patterns:
        match = re.search(pattern, lower)
        if match:
            raw = match.group(1).replace(",", "")
            try:
                num = int(raw)
                if "k" in match.group(0) and num < 1000:
                    num *= 1000
                if 1000 <= num <= 400000:
                    return num
            except Exception:
                pass

    return None


def title_to_search(title):
    title = clean_text(title)
    title = re.sub(r"\$[0-9,]+", "", title)
    title = re.sub(r"\b[0-9]{5,6}\s*(miles|mile|mi)\b", "", title, flags=re.I)
    return clean_text(title)


def get_make_model_query(title):
    title = title_to_search(title)
    year = extract_year(title)

    cleaned = title
    if year:
        cleaned = cleaned.replace(str(year), "")

    cleaned = re.sub(r"[^A-Za-z0-9\s\-]", " ", cleaned)
    cleaned = clean_text(cleaned)

    words = cleaned.split()
    words = [w for w in words if w.lower() not in {
        "clean", "title", "excellent", "runs", "great", "loaded",
        "automatic", "manual", "awd", "fwd", "rwd", "sale", "private",
        "owner", "new", "nice", "good", "mechanic", "special"
    }]

    core = " ".join(words[:4]).strip()

    if year and core:
        return f"{year} {core}"

    return title


def compare_links(title, price=None, miles=None):
    query = get_make_model_query(title)
    encoded = quote_plus(query)

    cars_url = f"https://www.cars.com/shopping/results/?stock_type=used&makes[]=&models[]=&maximum_distance=100&zip={ZIP_CODE}&keyword={encoded}"

    cargurus_url = f"https://www.cargurus.com/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action?zip={ZIP_CODE}&distance=100&entitySelectingHelper.selectedEntity=&sourceContext=carGurusHomePage_false_0&searchText={encoded}"

    kbb_url = f"https://www.kbb.com/whats-my-car-worth/?intent=trade-in-sell&mileage={(miles or '')}&zip={ZIP_CODE}&vehicle={encoded}"

    return cars_url, kbb_url, cargurus_url


def rough_market_value(year, price, miles, title):
    """
    Conservative rough estimate only.
    Real compare buttons are provided for Cars.com, KBB, and CarGurus.
    """

    if not price:
        return None

    current_year = datetime.now().year
    age = current_year - year if year else 12

    base = price * 1.35

    if year:
        if age <= 5:
            base *= 1.12
        elif age <= 10:
            base *= 1.04
        elif age >= 17:
            base *= 0.88

    if miles:
        if miles < 80000:
            base *= 1.12
        elif miles < 120000:
            base *= 1.03
        elif miles > 190000:
            base *= 0.78
        elif miles > 160000:
            base *= 0.88

    lower_title = title.lower()

    premium_words = [
        "toyota", "honda", "lexus", "subaru", "tacoma", "4runner",
        "camry", "corolla", "civic", "accord", "rav4", "crv", "cr-v"
    ]

    risk_words = [
        "bmw", "audi", "mini", "mercedes", "land rover", "range rover",
        "jaguar", "volvo", "fiat"
    ]

    if any(w in lower_title for w in premium_words):
        base *= 1.10

    if any(w in lower_title for w in risk_words):
        base *= 0.90

    return int(round(base / 100) * 100)


def estimate_recon(title, price, miles, year):
    lower = title.lower()
    recon = 700

    if miles and miles > 170000:
        recon += 500
    elif miles and miles > 130000:
        recon += 300

    if year and year < 2010:
        recon += 400

    risk_words = [
        "needs", "mechanic", "project", "salvage", "rebuilt",
        "transmission", "engine", "overheating", "misfire",
        "check engine", "not running", "tow", "as is"
    ]

    if any(w in lower for w in risk_words):
        recon += 1200

    luxury_words = ["bmw", "audi", "mercedes", "mini", "land rover", "range rover", "volvo"]
    if any(w in lower for w in luxury_words):
        recon += 700

    return recon


def risk_level(title, miles, year):
    lower = title.lower()

    hard_risk = [
        "not running", "mechanic", "project", "transmission",
        "engine problem", "overheating", "salvage", "rebuilt"
    ]

    if any(w in lower for w in hard_risk):
        return "HIGH"

    if miles and miles > 190000:
        return "HIGH"

    if miles and miles > 150000:
        return "MEDIUM"

    if year and year < 2008:
        return "MEDIUM"

    risky_brands = ["bmw", "audi", "mini", "mercedes", "land rover", "range rover"]
    if any(w in lower for w in risky_brands):
        return "MEDIUM"

    return "LOW"


def flip_decision(profit, risk, target_profit):
    if profit is None:
        return "CHECK", "maybe"

    if profit >= target_profit and risk != "HIGH":
        return "BUY CANDIDATE", "buy"

    if profit >= target_profit * 0.65 and risk != "HIGH":
        return "NEGOTIATE / CHECK", "maybe"

    return "SKIP", "skip"


def craigslist_rss_url(max_price):
    params = {
        "format": "rss",
        "search_distance": SEARCH_DISTANCE,
        "postal": ZIP_CODE,
        "bundleDuplicates": 1,
        "purveyor": "owner",
        "auto_title_status": 1,
        "min_auto_year": MIN_YEAR,
        "max_price": max_price,
        "sort": "date"
    }

    return f"https://{CRAIGSLIST_SITE}.craigslist.org/search/cta?" + urlencode(params)


def fetch_craigslist(max_price):
    url = craigslist_rss_url(max_price)

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        st.error(f"Craigslist fetch failed: {e}")
        return []

    soup = BeautifulSoup(response.text, "xml")
    items = soup.find_all("item")

    listings = []

    for item in items:
        title = clean_text(item.title.text if item.title else "")
        link = clean_text(item.link.text if item.link else "")
        description = clean_text(item.description.text if item.description else "")

        combined = f"{title} {description}"

        price = extract_price(title) or extract_price(description)
        year = extract_year(title) or extract_year(description)
        miles = extract_miles(combined)

        if not title or not link or not price:
            continue

        bad_words = [
            "rv", "camper", "motorhome", "trailer", "boat",
            "parts only", "wheelchair", "semi", "f650", "box truck"
        ]

        if any(w in title.lower() for w in bad_words):
            continue

        listings.append({
            "id": hashlib.md5(link.encode()).hexdigest()[:10],
            "title": title,
            "price": price,
            "year": year,
            "miles": miles,
            "link": link,
            "description": description
        })

    return listings


# =========================
# APP UI
# =========================

st.title("🚗 Car Flip AI")
st.markdown('<div class="sub">Salt Lake City private-party scanner with KBB, Cars.com, and CarGurus comparison links.</div>', unsafe_allow_html=True)

with st.expander("Filters", expanded=False):
    max_price = st.slider("Max price", 3000, 25000, MAX_PRICE_DEFAULT, 500)
    max_miles = st.slider("Max miles", 80000, 250000, MAX_MILES_DEFAULT, 5000)
    target_profit = st.slider("Target profit", 500, 6000, TARGET_PROFIT_DEFAULT, 250)
    show_missing_miles = st.toggle("Show cars even if mileage is missing", value=True)

refresh = st.button("Scan Craigslist", use_container_width=True)

if "listings" not in st.session_state:
    st.session_state.listings = []

if refresh or not st.session_state.listings:
    with st.spinner("Scanning Salt Lake City Craigslist owner listings..."):
        st.session_state.listings = fetch_craigslist(max_price)

listings = st.session_state.listings

processed = []

for car in listings:
    price = car["price"]
    miles = car["miles"]
    year = car["year"]
    title = car["title"]

    if price and price > max_price:
        continue

    if miles and miles > max_miles:
        continue

    if not miles and not show_missing_miles:
        continue

    market = rough_market_value(year, price, miles, title)
    recon = estimate_recon(title, price, miles, year)
    profit = market - price - recon if market else None
    risk = risk_level(title, miles, year)
    decision, decision_class = flip_decision(profit, risk, target_profit)

    score = 0
    if profit:
        score += min(60, max(0, profit / target_profit * 45))
    if risk == "LOW":
        score += 30
    elif risk == "MEDIUM":
        score += 15
    if miles and miles < 130000:
        score += 10
    score = int(min(100, score))

    processed.append({
        **car,
        "market": market,
        "recon": recon,
        "profit": profit,
        "risk": risk,
        "decision": decision,
        "decision_class": decision_class,
        "score": score
    })

processed = sorted(processed, key=lambda x: (x["score"], x["profit"] or -9999), reverse=True)

st.markdown(f"**Found {len(processed)} possible cars**")

if not processed:
    st.warning("No cars found with your filters. Raise max price or allow missing mileage.")
else:
    for car in processed[:50]:
        cars_url, kbb_url, cargurus_url = compare_links(
            car["title"],
            car["price"],
            car["miles"]
        )

        risk_css = "good"
        if car["risk"] == "MEDIUM":
            risk_css = "warn"
        elif car["risk"] == "HIGH":
            risk_css = "bad"

        profit_display = "Unknown"
        if car["profit"] is not None:
            profit_display = f"${car['profit']:,}"

        market_display = "Check comps"
        if car["market"]:
            market_display = f"${car['market']:,}"

        miles_display = "Unknown"
        if car["miles"]:
            miles_display = f"{car['miles']:,}"

        year_display = car["year"] if car["year"] else "Unknown"

        st.markdown(f"""
<div class="car-card">

    <div class="car-title">{car['title']}</div>

    <div class="price">${car['price']:,}</div>

    <div class="small">
        Year: {year_display} · Miles: {miles_display} · Score: {car['score']}/100
    </div>

    <div class="decision {car['decision_class']}">{car['decision']}</div>

    <div class="metric-row">
        <div class="metric-box">
            <div class="metric-label">Rough Market</div>
            <div class="metric-value">{market_display}</div>
        </div>

        <div class="metric-box">
            <div class="metric-label">Est. Recon</div>
            <div class="metric-value">${car['recon']:,}</div>
        </div>

        <div class="metric-box">
            <div class="metric-label">Potential Profit</div>
            <div class="metric-value">{profit_display}</div>
        </div>

        <div class="metric-box">
            <div class="metric-label">Risk</div>
            <div class="metric-value {risk_css}">{car['risk']}</div>
        </div>
    </div>

    <div class="link-row">
        <a href="{car['link']}" target="_blank">Open Listing</a>
        <a href="{kbb_url}" target="_blank">Check KBB</a>
        <a href="{cars_url}" target="_blank">Cars.com Comps</a>
        <a href="{cargurus_url}" target="_blank">CarGurus Comps</a>
    </div>

</div>
""", unsafe_allow_html=True)

st.caption("Values are rough estimates. Always verify VIN, title status, mileage, KBB, Cars.com, CarGurus, and mechanical condition before buying.")
