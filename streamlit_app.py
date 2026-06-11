import re
import math
import html
import hashlib
from datetime import datetime
from urllib.parse import urlencode, quote_plus

import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup


# ============================================================
# CAR FLIP AI — FULL STREAMLIT SCRIPT
# Location: ZIP 84107, radius 90 miles
# Source: Craigslist owner listings RSS
# ============================================================


# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="Car Flip AI",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
<style>
.block-container {
    padding-top: 1.1rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    max-width: 820px !important;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

h1 {
    font-size: 2.7rem !important;
    line-height: 1.05 !important;
    margin-bottom: 0.15rem !important;
}

.sub {
    color: #9ca3af;
    font-size: 1rem;
    margin-bottom: 1rem;
}

.info-box {
    background: rgba(37, 99, 235, 0.14);
    color: #bfdbfe;
    border: 1px solid rgba(96, 165, 250, 0.35);
    border-radius: 16px;
    padding: 13px 15px;
    margin: 10px 0 15px 0;
    font-size: 0.95rem;
}

.warn-box {
    background: rgba(245, 158, 11, 0.14);
    color: #fde68a;
    border: 1px solid rgba(245, 158, 11, 0.35);
    border-radius: 16px;
    padding: 13px 15px;
    margin: 10px 0 15px 0;
    font-size: 0.95rem;
}

.bad-box {
    background: rgba(239, 68, 68, 0.13);
    color: #fecaca;
    border: 1px solid rgba(248, 113, 113, 0.35);
    border-radius: 16px;
    padding: 13px 15px;
    margin: 10px 0 15px 0;
    font-size: 0.95rem;
}

.stButton > button {
    width: 100%;
    border-radius: 15px;
    font-weight: 900;
    padding: 0.8rem 1rem;
}

.car-card {
    border: 1px solid rgba(250,250,250,0.14);
    border-radius: 20px;
    padding: 16px;
    margin: 20px 0;
    background: #111827;
    box-shadow: 0 10px 28px rgba(0,0,0,0.25);
}

.car-card-buy {
    border-left: 10px solid #22c55e;
}

.car-card-watch {
    border-left: 10px solid #f59e0b;
}

.car-card-skip {
    border-left: 10px solid #ef4444;
}

.badge {
    display: inline-block;
    padding: 8px 16px;
    border-radius: 999px;
    font-weight: 950;
    margin-bottom: 14px;
    font-size: 0.92rem;
    letter-spacing: 0.2px;
}

.badge-buy {
    background: #14532d;
    color: #bbf7d0;
}

.badge-watch {
    background: #78350f;
    color: #fde68a;
}

.badge-skip {
    background: #7f1d1d;
    color: #fecaca;
}

.title {
    display: block;
    color: #60a5fa !important;
    font-size: 1.5rem;
    font-weight: 950;
    line-height: 1.25;
    margin-bottom: 14px;
    text-decoration: underline;
}

.metric {
    font-size: 1rem;
    margin: 7px 0;
    color: #e5e7eb;
}

.metric b {
    color: #ffffff;
}

.reason {
    margin-top: 14px;
    padding: 12px;
    border-radius: 13px;
    background: rgba(255,255,255,0.065);
    color: #d1d5db;
    line-height: 1.45;
}

.comp-links {
    margin-top: 13px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}

.comp-links a {
    color: #bfdbfe !important;
    background: rgba(37, 99, 235, 0.16);
    border: 1px solid rgba(96, 165, 250, 0.35);
    padding: 7px 10px;
    border-radius: 999px;
    font-size: 0.9rem;
    text-decoration: none !important;
    font-weight: 800;
}

.small-muted {
    color: #9ca3af;
    font-size: 0.88rem;
    margin-top: 6px;
}

.dataframe {
    font-size: 0.85rem !important;
}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# CONSTANTS
# ============================================================

ZIP_CODE = "84107"
RADIUS_MILES = 90
CRAIGSLIST_SITE = "saltlakecity"
CL_BASE = f"https://{CRAIGSLIST_SITE}.craigslist.org"

DEFAULT_MIN_PROFIT = 2000
DEFAULT_MAX_PRICE = 15000
DEFAULT_MAX_MILES = 170000
DEFAULT_MIN_YEAR = 2004

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

BAD_TITLE_WORDS = [
    "camper",
    "rv",
    "motorhome",
    "motor home",
    "trailer",
    "boat",
    "semi",
    "dump truck",
    "box truck",
    "bus",
    "school bus",
    "tow truck",
    "forklift",
    "tractor",
    "atv",
    "utv",
    "side by side",
    "motorcycle",
    "scooter",
    "dirt bike",
    "parts only",
    "mechanic special",
    "shell",
    "project",
    "does not run",
    "not running",
    "no title",
    "salvage only",
    "bill of sale",
]

HIGH_RISK_WORDS = [
    "salvage",
    "rebuilt",
    "branded",
    "lemon",
    "flood",
    "hail",
    "transmission",
    "engine knock",
    "knocking",
    "overheating",
    "head gasket",
    "blown",
    "misfire",
    "no reverse",
    "needs engine",
    "needs transmission",
    "mechanic special",
    "does not run",
    "not running",
    "no title",
]

GOOD_WORDS = [
    "clean title",
    "clean",
    "runs great",
    "runs good",
    "well maintained",
    "new tires",
    "new battery",
    "cold ac",
    "no issues",
    "reliable",
    "one owner",
    "service records",
]

BRANDS_RELIABLE = [
    "toyota",
    "honda",
    "lexus",
    "acura",
    "mazda",
    "subaru",
    "scion",
]

BRANDS_DECENT = [
    "ford",
    "chevrolet",
    "chevy",
    "gmc",
    "buick",
    "hyundai",
    "kia",
    "nissan",
    "infiniti",
]

BRANDS_RISKY = [
    "bmw",
    "audi",
    "mercedes",
    "mini",
    "volkswagen",
    "vw",
    "jaguar",
    "land rover",
    "range rover",
    "volvo",
    "chrysler",
]


# ============================================================
# HELPERS
# ============================================================

def money(n):
    try:
        if n is None or pd.isna(n):
            return "Unknown"
        return f"${int(round(float(n))):,}"
    except Exception:
        return "Unknown"


def miles_fmt(n):
    try:
        if n is None or pd.isna(n):
            return "Unknown"
        return f"{int(round(float(n))):,}"
    except Exception:
        return "Unknown"


def safe_text(value):
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def clean_spaces(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def parse_price(text):
    if not text:
        return None

    text = str(text)

    patterns = [
        r"\$\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,6})",
        r"price[:\s]+\$?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,6})",
    ]

    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            try:
                value = int(m.group(1).replace(",", ""))
                if 500 <= value <= 100000:
                    return value
            except Exception:
                pass

    return None


def parse_year(text):
    if not text:
        return None

    years = re.findall(r"\b(19[8-9][0-9]|20[0-2][0-9])\b", str(text))
    valid = []
    current_year = datetime.now().year

    for y in years:
        yi = int(y)
        if 1980 <= yi <= current_year + 1:
            valid.append(yi)

    if not valid:
        return None

    return valid[0]


def parse_mileage(text):
    if not text:
        return None

    t = str(text).lower().replace(",", "")

    patterns = [
        r"\b([0-9]{2,3})\s*k\s*(?:mi|miles|mile)?\b",
        r"\b([0-9]{4,6})\s*(?:mi|miles|mile)\b",
        r"\b(?:odometer|mileage|miles)[:\s]+([0-9]{4,6})\b",
    ]

    for p in patterns:
        m = re.search(p, t)
        if m:
            val = int(m.group(1))
            if "k" in p:
                val *= 1000
            if 10000 <= val <= 350000:
                return val

    all_nums = re.findall(r"\b([0-9]{5,6})\b", t)
    for n in all_nums:
        val = int(n)
        if 10000 <= val <= 350000:
            return val

    return None


def detect_make(title):
    t = f" {title.lower()} "

    make_aliases = {
        "chevrolet": ["chevrolet", "chevy"],
        "ford": ["ford"],
        "toyota": ["toyota"],
        "honda": ["honda"],
        "lexus": ["lexus"],
        "acura": ["acura"],
        "mazda": ["mazda"],
        "subaru": ["subaru"],
        "nissan": ["nissan"],
        "infiniti": ["infiniti"],
        "hyundai": ["hyundai"],
        "kia": ["kia"],
        "gmc": ["gmc"],
        "buick": ["buick"],
        "cadillac": ["cadillac"],
        "jeep": ["jeep"],
        "ram": ["ram"],
        "dodge": ["dodge"],
        "chrysler": ["chrysler"],
        "bmw": ["bmw"],
        "mercedes": ["mercedes", "benz"],
        "audi": ["audi"],
        "volkswagen": ["volkswagen", " vw "],
        "mini": ["mini cooper", " mini "],
        "volvo": ["volvo"],
    }

    for make, aliases in make_aliases.items():
        for a in aliases:
            if a in t:
                return make

    return None


def normalize_title(title):
    title = clean_spaces(title)
    title = re.sub(r"\s+\$[0-9,]+.*$", "", title)
    title = re.sub(r"\s+-\s+cars\s*&\s*trucks.*$", "", title, flags=re.I)
    return title.strip()


def dedupe_key(title, price, url):
    base = f"{title.lower()}|{price}|{url.split('?')[0]}"
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def is_bad_listing(title, desc):
    t = f"{title} {desc}".lower()

    for word in BAD_TITLE_WORDS:
        if word in t:
            return True, f"Filtered out because listing contains: {word}"

    return False, ""


def risk_words_found(title, desc):
    t = f"{title} {desc}".lower()
    found = []
    for word in HIGH_RISK_WORDS:
        if word in t:
            found.append(word)
    return found


def good_words_found(title, desc):
    t = f"{title} {desc}".lower()
    found = []
    for word in GOOD_WORDS:
        if word in t:
            found.append(word)
    return found


def craigslist_rss_url(max_price):
    params = {
        "format": "rss",
        "postal": ZIP_CODE,
        "search_distance": RADIUS_MILES,
        "purveyor": "owner",
        "bundleDuplicates": 1,
        "sort": "date",
        "max_price": int(max_price),
    }

    return f"{CL_BASE}/search/cta?{urlencode(params)}"


def make_comp_links(title, year, miles, zip_code=ZIP_CODE):
    q = quote_plus(clean_spaces(title))

    kbb = f"https://www.kbb.com/cars-for-sale/all/{q}/?zip={zip_code}"
    cargurus = f"https://www.cargurus.com/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action?zip={zip_code}&distance=100&searchChanged=true&entitySelectingHelper.selectedEntity=dummy&sourceContext=carGurusHomePageModel"
    cars = f"https://www.cars.com/shopping/results/?stock_type=used&maximum_distance=100&zip={zip_code}&keyword={q}"
    google = f"https://www.google.com/search?q={q}+for+sale+Utah+KBB+Cars.com+CarGurus"

    return {
        "KBB": kbb,
        "CarGurus": cargurus,
        "Cars.com": cars,
        "Google comps": google,
    }


# ============================================================
# VALUATION ENGINE
# ============================================================

def estimate_market_value(title, price, year, miles, desc):
    """
    This is a conservative flip-estimate engine.
    It does NOT pretend to be exact KBB/MMR.
    It estimates likely retail/private-party range based on year, mileage, make, price, and risk.
    """

    make = detect_make(title)
    current_year = datetime.now().year

    if price is None:
        return None

    if year is None:
        age = 14
    else:
        age = max(1, current_year - year)

    if miles is None:
        miles = 150000

    # Base multiplier by asking price bracket.
    if price <= 2500:
        multiplier = 1.85
    elif price <= 4500:
        multiplier = 1.60
    elif price <= 7000:
        multiplier = 1.42
    elif price <= 10000:
        multiplier = 1.30
    else:
        multiplier = 1.22

    # Age adjustment.
    if year is not None:
        if year >= 2018:
            multiplier += 0.10
        elif year >= 2014:
            multiplier += 0.06
        elif year >= 2010:
            multiplier += 0.02
        elif year < 2004:
            multiplier -= 0.25

    # Mileage adjustment.
    if miles <= 80000:
        multiplier += 0.14
    elif miles <= 120000:
        multiplier += 0.08
    elif miles <= 160000:
        multiplier += 0.00
    elif miles <= 200000:
        multiplier -= 0.12
    else:
        multiplier -= 0.25

    # Make adjustment.
    if make in BRANDS_RELIABLE:
        multiplier += 0.12
    elif make in BRANDS_DECENT:
        multiplier += 0.04
    elif make in BRANDS_RISKY:
        multiplier -= 0.15

    # Risk text adjustment.
    risk_hits = risk_words_found(title, desc)
    if risk_hits:
        multiplier -= min(0.30, 0.08 * len(risk_hits))

    good_hits = good_words_found(title, desc)
    if good_hits:
        multiplier += min(0.15, 0.04 * len(good_hits))

    multiplier = max(0.95, min(multiplier, 2.05))

    estimated = price * multiplier

    # Conservative cap/floor by age/mileage.
    if year is not None and year < 2004:
        estimated = min(estimated, price * 1.18)

    if miles and miles > 200000:
        estimated = min(estimated, price * 1.18)

    return int(round(estimated / 100) * 100)


def estimate_recon(title, desc, year, miles, price):
    t = f"{title} {desc}".lower()

    recon = 700

    if price is not None and price < 3500:
        recon += 400

    if miles is None:
        recon += 500
    elif miles > 200000:
        recon += 900
    elif miles > 170000:
        recon += 600
    elif miles > 140000:
        recon += 350

    if year is None:
        recon += 400
    elif year < 2006:
        recon += 700
    elif year < 2010:
        recon += 350

    risk_hits = risk_words_found(title, desc)
    recon += len(risk_hits) * 550

    if any(w in t for w in ["tires", "brakes", "battery", "windshield"]):
        recon += 250

    if any(w in t for w in ["transmission", "engine", "head gasket", "overheating", "knock"]):
        recon += 1500

    return int(round(recon / 50) * 50)


def calculate_score(title, desc, price, year, miles, market, recon, min_profit, max_miles, min_year):
    score = 50
    reasons = []

    make = detect_make(title)
    risk_hits = risk_words_found(title, desc)
    good_hits = good_words_found(title, desc)

    if price is None:
        score -= 35
        reasons.append("No clear price found.")
    else:
        if price <= 4500:
            score += 12
            reasons.append("Low asking price creates negotiation room.")
        elif price <= 8000:
            score += 7
            reasons.append("Asking price is within a workable flip range.")
        elif price > 15000:
            score -= 12
            reasons.append("Higher cash requirement for a flip.")

    if year is None:
        score -= 10
        reasons.append("Year not clearly detected.")
    else:
        if year < min_year:
            score -= 30
            reasons.append(f"Older than your minimum year filter ({min_year}).")
        elif year >= 2012:
            score += 10
            reasons.append("Year is modern enough for normal resale demand.")
        elif year >= 2008:
            score += 5
            reasons.append("Year is acceptable but needs careful inspection.")

    if miles is None:
        score -= 10
        reasons.append("Mileage not clearly detected.")
    else:
        if miles > max_miles:
            score -= 25
            reasons.append(f"Mileage is above your max mileage filter ({max_miles:,}).")
        elif miles <= 120000:
            score += 12
            reasons.append("Mileage is attractive.")
        elif miles <= 160000:
            score += 5
            reasons.append("Mileage is still workable.")
        elif miles > 190000:
            score -= 12
            reasons.append("Very high mileage increases resale and repair risk.")

    if make in BRANDS_RELIABLE:
        score += 12
        reasons.append(f"{make.title()} has strong resale demand.")
    elif make in BRANDS_DECENT:
        score += 5
        reasons.append(f"{make.title()} is usually marketable if condition is good.")
    elif make in BRANDS_RISKY:
        score -= 10
        reasons.append(f"{make.title()} can carry higher repair risk.")

    if risk_hits:
        score -= min(35, len(risk_hits) * 10)
        reasons.append("Risk keywords found: " + ", ".join(risk_hits[:5]) + ".")

    if good_hits:
        score += min(12, len(good_hits) * 4)
        reasons.append("Positive seller words found: " + ", ".join(good_hits[:4]) + ".")

    profit_at_ask = None
    target_buy = None

    if market is not None and price is not None and recon is not None:
        profit_at_ask = market - price - recon
        target_buy = market - recon - min_profit

        if profit_at_ask >= min_profit:
            score += 20
            reasons.append(f"Estimated profit at ask is above target profit.")
        elif profit_at_ask >= 1000:
            score += 8
            reasons.append("Could work only with negotiation.")
        else:
            score -= 15
            reasons.append("Profit at asking price is weak.")

    score = max(0, min(100, score))

    return score, reasons, profit_at_ask, target_buy


def decide(score, profit_at_ask, price, target_buy, year, miles, min_year, max_miles):
    if year is not None and year < min_year:
        return "SKIP", "HIGH"

    if miles is not None and miles > max_miles:
        return "SKIP", "HIGH"

    if profit_at_ask is None:
        if score >= 70:
            return "WATCH", "MED"
        return "SKIP", "MED/HIGH"

    if score >= 78 and profit_at_ask >= DEFAULT_MIN_PROFIT:
        return "BUY", "LOW/MED"

    if score >= 68 and target_buy is not None:
        return "WATCH", "MED"

    if score >= 58:
        return "WATCH", "MED/HIGH"

    return "SKIP", "HIGH"


# ============================================================
# SCRAPER
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def fetch_craigslist(max_price):
    url = craigslist_rss_url(max_price)

    try:
        r = requests.get(url, headers=REQUEST_HEADERS, timeout=18)
        r.raise_for_status()
    except Exception as e:
        return [], url, f"Craigslist request failed: {e}"

    try:
        soup = BeautifulSoup(r.text, "xml")
        items = soup.find_all("item")
    except Exception as e:
        return [], url, f"RSS parse failed: {e}"

    listings = []
    seen = set()

    for item in items:
        title = clean_spaces(item.title.get_text(" ", strip=True) if item.title else "")
        link = clean_spaces(item.link.get_text(" ", strip=True) if item.link else "")
        desc = item.description.get_text(" ", strip=True) if item.description else ""

        title = normalize_title(title)

        full_text = f"{title} {desc}"

        price = parse_price(full_text)
        year = parse_year(full_text)
        miles = parse_mileage(full_text)

        if not title or not link:
            continue

        bad, bad_reason = is_bad_listing(title, desc)
        if bad:
            continue

        key = dedupe_key(title, price, link)
        if key in seen:
            continue
        seen.add(key)

        listings.append(
            {
                "title": title,
                "url": link,
                "desc": clean_spaces(BeautifulSoup(desc, "html.parser").get_text(" ", strip=True)),
                "price": price,
                "year": year,
                "miles": miles,
            }
        )

    return listings, url, None


# ============================================================
# UI HEADER
# ============================================================

st.markdown("# Car Flip AI")
st.markdown(
    f"""
<div class="sub">
Scanning Craigslist owner listings from ZIP <b>{ZIP_CODE}</b> within <b>{RADIUS_MILES} miles</b>.
</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# CONTROLS
# ============================================================

with st.expander("Filters", expanded=False):
    max_price = st.number_input(
        "Max asking price",
        min_value=1000,
        max_value=50000,
        value=DEFAULT_MAX_PRICE,
        step=500,
    )

    max_miles = st.number_input(
        "Max mileage",
        min_value=50000,
        max_value=300000,
        value=DEFAULT_MAX_MILES,
        step=5000,
    )

    min_year = st.number_input(
        "Minimum year",
        min_value=1980,
        max_value=datetime.now().year + 1,
        value=DEFAULT_MIN_YEAR,
        step=1,
    )

    min_profit = st.number_input(
        "Target minimum profit",
        min_value=500,
        max_value=10000,
        value=DEFAULT_MIN_PROFIT,
        step=250,
    )

    show_skip = st.toggle("Show SKIP cars too", value=False)
    show_debug = st.toggle("Show debug table", value=False)


if st.button("Scan Craigslist now"):
    st.cache_data.clear()
    st.rerun()


# ============================================================
# FETCH DATA
# ============================================================

with st.spinner("Scanning listings..."):
    raw_listings, source_url, error = fetch_craigslist(max_price)


st.markdown(
    f"""
<div class="info-box">
<b>Source:</b> Craigslist owner listings only · ZIP {ZIP_CODE} · {RADIUS_MILES}-mile radius · Max price {money(max_price)}
<br>
<a href="{safe_text(source_url)}" target="_blank" style="color:#bfdbfe;">Open raw Craigslist RSS/search</a>
</div>
""",
    unsafe_allow_html=True,
)


if error:
    st.markdown(
        f"""
<div class="bad-box">
<b>Error:</b> {safe_text(error)}
</div>
""",
        unsafe_allow_html=True,
    )
    st.stop()


if not raw_listings:
    st.markdown(
        """
<div class="warn-box">
No listings found. Craigslist may be blocking temporarily, RSS may be empty, or filters may be too tight.
</div>
""",
        unsafe_allow_html=True,
    )
    st.stop()


# ============================================================
# EVALUATE LISTINGS
# ============================================================

evaluated = []

for car in raw_listings:
    title = car["title"]
    desc = car["desc"]
    price = car["price"]
    year = car["year"]
    miles = car["miles"]

    if price is None:
        continue

    market = estimate_market_value(title, price, year, miles, desc)
    recon = estimate_recon(title, desc, year, miles, price)

    score, reasons, profit_at_ask, target_buy = calculate_score(
        title=title,
        desc=desc,
        price=price,
        year=year,
        miles=miles,
        market=market,
        recon=recon,
        min_profit=min_profit,
        max_miles=max_miles,
        min_year=min_year,
    )

    decision, risk = decide(
        score=score,
        profit_at_ask=profit_at_ask,
        price=price,
        target_buy=target_buy,
        year=year,
        miles=miles,
        min_year=min_year,
        max_miles=max_miles,
    )

    evaluated.append(
        {
            **car,
            "market": market,
            "recon": recon,
            "score": score,
            "profit_at_ask": profit_at_ask,
            "target_buy": target_buy,
            "decision": decision,
            "risk": risk,
            "reason": " ".join(reasons[:5]),
        }
    )


df = pd.DataFrame(evaluated)

if df.empty:
    st.markdown(
        """
<div class="warn-box">
Listings were found, but nothing had a usable price/year/mileage combination.
</div>
""",
        unsafe_allow_html=True,
    )
    st.stop()


decision_rank = {"BUY": 0, "WATCH": 1, "SKIP": 2}
df["decision_rank"] = df["decision"].map(decision_rank).fillna(9)
df = df.sort_values(
    by=["decision_rank", "score", "profit_at_ask"],
    ascending=[True, False, False],
).reset_index(drop=True)


# ============================================================
# SUMMARY
# ============================================================

buy_count = int((df["decision"] == "BUY").sum())
watch_count = int((df["decision"] == "WATCH").sum())
skip_count = int((df["decision"] == "SKIP").sum())

st.markdown(
    f"""
<div class="info-box">
<b>Parsed listings:</b> {len(raw_listings)} · 
<b>Evaluated:</b> {len(df)} · 
<b>BUY:</b> {buy_count} · 
<b>WATCH:</b> {watch_count} · 
<b>SKIP:</b> {skip_count}
</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# DEBUG TABLE
# ============================================================

if show_debug:
    debug_cols = [
        "decision",
        "score",
        "risk",
        "title",
        "price",
        "market",
        "recon",
        "profit_at_ask",
        "target_buy",
        "year",
        "miles",
        "url",
    ]
    st.dataframe(df[debug_cols], use_container_width=True)


# ============================================================
# DISPLAY CAR CARDS — FIXED HTML RENDERING
# ============================================================

display_df = df.copy()

if not show_skip:
    display_df = display_df[display_df["decision"] != "SKIP"]


if display_df.empty:
    st.markdown(
        """
<div class="warn-box">
No BUY/WATCH cars after your filters. Turn on “Show SKIP cars too” if you want to inspect rejected listings.
</div>
""",
        unsafe_allow_html=True,
    )
    st.stop()


for _, row in display_df.iterrows():
    decision = row["decision"]
    score = int(row["score"])
    risk = row["risk"]

    if decision == "BUY":
        card_class = "car-card car-card-buy"
        badge_class = "badge badge-buy"
    elif decision == "WATCH":
        card_class = "car-card car-card-watch"
        badge_class = "badge badge-watch"
    else:
        card_class = "car-card car-card-skip"
        badge_class = "badge badge-skip"

    title = safe_text(row["title"])
    url = safe_text(row["url"])
    price = money(row["price"])
    market = money(row["market"])
    recon = money(row["recon"])
    profit = money(row["profit_at_ask"])
    target_buy = money(row["target_buy"])
    year = safe_text(row["year"] if pd.notna(row["year"]) else "Unknown")
    miles = miles_fmt(row["miles"])
    reason = safe_text(row["reason"])

    comp_links = make_comp_links(
        title=row["title"],
        year=row["year"],
        miles=row["miles"],
        zip_code=ZIP_CODE,
    )

    links_html = ""
    for name, link in comp_links.items():
        links_html += f'<a href="{safe_text(link)}" target="_blank">{safe_text(name)}</a>'

    card_html = f"""
<div class="{card_class}">
    <div class="{badge_class}">{safe_text(decision)} · SCORE {score}/100 · RISK {safe_text(risk)}</div>

    <a class="title" href="{url}" target="_blank">
        {title}
    </a>

    <div class="metric">Ask Price: <b>{price}</b></div>
    <div class="metric">Estimated Retail/Market: <b>{market}</b></div>
    <div class="metric">Estimated Recon: <b>{recon}</b></div>
    <div class="metric">Target Buy Price for {money(min_profit)} Profit: <b>{target_buy}</b></div>
    <div class="metric">Estimated Profit at Ask: <b>{profit}</b></div>
    <div class="metric">Year: <b>{year}</b> · Mileage: <b>{miles}</b></div>

    <div class="reason">{reason}</div>

    <div class="comp-links">
        {links_html}
    </div>

    <div class="small-muted">
        Numbers are conservative estimates. Verify VIN, title, condition, comps, and mechanical issues before buying.
    </div>
</div>
"""

    st.markdown(card_html, unsafe_allow_html=True)


# ============================================================
# FOOTER
# ============================================================

st.markdown(
    f"""
<div class="small-muted">
Last scan: {datetime.now().strftime("%Y-%m-%d %I:%M %p")}
</div>
""",
    unsafe_allow_html=True,
)
