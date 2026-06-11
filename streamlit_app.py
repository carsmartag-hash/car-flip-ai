import re
import time
import math
import hashlib
from datetime import datetime
from urllib.parse import urlencode

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
    padding-top: 1.1rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    max-width: 760px !important;
}
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

h1 {
    font-size: 2.8rem !important;
    line-height: 1.05 !important;
    margin-bottom: 0.2rem !important;
}

.sub {
    color: #9ca3af;
    font-size: 1rem;
    margin-bottom: 1.2rem;
}

.info-box {
    background: #132f4c;
    color: #cfe4ff;
    border: 1px solid #2d5d9f;
    border-radius: 18px;
    padding: 16px 18px;
    margin: 14px 0 18px 0;
    font-size: 0.98rem;
    line-height: 1.5;
}

.err-box {
    background: #3a171d;
    color: #ffd3d9;
    border: 1px solid #9b3945;
    border-radius: 18px;
    padding: 16px 18px;
    margin: 14px 0 18px 0;
    font-size: 0.98rem;
    line-height: 1.5;
}

.warn-box {
    background: #33270e;
    color: #ffe6a7;
    border: 1px solid #8a6b22;
    border-radius: 18px;
    padding: 16px 18px;
    margin: 14px 0 18px 0;
    font-size: 0.98rem;
    line-height: 1.5;
}

.good-box {
    background: #0d2f1f;
    color: #c9f7dc;
    border: 1px solid #2f8f5b;
    border-radius: 18px;
    padding: 16px 18px;
    margin: 14px 0 18px 0;
    font-size: 0.98rem;
    line-height: 1.5;
}

.car-card {
    border: 1px solid rgba(250,250,250,0.16);
    border-radius: 20px;
    padding: 16px;
    margin: 14px 0;
    background: rgba(255,255,255,0.035);
}

.car-title {
    font-size: 1.15rem;
    font-weight: 800;
    line-height: 1.25;
    margin-bottom: 8px;
}

.metric-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin: 8px 0 10px 0;
}

.pill {
    border: 1px solid rgba(255,255,255,0.18);
    border-radius: 999px;
    padding: 6px 10px;
    font-size: 0.86rem;
    color: #e5e7eb;
    background: rgba(255,255,255,0.05);
}

.buy {
    color: #86efac;
    font-weight: 900;
}

.maybe {
    color: #fde68a;
    font-weight: 900;
}

.skip {
    color: #fca5a5;
    font-weight: 900;
}

.small {
    color: #9ca3af;
    font-size: 0.88rem;
    line-height: 1.45;
}

a {
    color: #cfe4ff !important;
}
</style>
""", unsafe_allow_html=True)


# =========================
# DEFAULT SETTINGS
# =========================

DEFAULT_ZIP = "84107"
DEFAULT_RADIUS = 90
DEFAULT_MAX_PRICE = 15000
DEFAULT_MIN_YEAR = 2006
DEFAULT_MAX_MILES = 180000
DEFAULT_TARGET_PROFIT = 2000

CRAIGSLIST_BASE = "https://saltlakecity.craigslist.org"


# =========================
# VEHICLE VALUE LOGIC
# =========================

BRAND_SCORE = {
    "toyota": 1.18, "lexus": 1.18, "honda": 1.14, "acura": 1.10,
    "subaru": 1.04, "mazda": 1.04,
    "ford": 1.00, "chevrolet": 0.98, "chevy": 0.98, "gmc": 0.99,
    "nissan": 0.96, "hyundai": 0.98, "kia": 0.96,
    "bmw": 0.88, "audi": 0.87, "mercedes": 0.86, "mercedes-benz": 0.86,
    "volkswagen": 0.90, "vw": 0.90,
    "dodge": 0.90, "chrysler": 0.88, "jeep": 0.94,
    "mini": 0.80, "fiat": 0.75, "land rover": 0.70, "range rover": 0.70,
}

RISKY_TERMS = [
    "salvage", "rebuilt", "branded", "mechanic special", "mechanics special",
    "does not run", "doesn't run", "not running", "needs engine", "needs transmission",
    "bad transmission", "bad engine", "head gasket", "overheating", "blown",
    "no title", "parts only", "project", "tow", "towed"
]

GOOD_TERMS = [
    "clean title", "clean", "one owner", "new tires", "new battery",
    "runs great", "runs good", "well maintained", "maintenance", "service records",
    "no accidents"
]

MODEL_KEYWORDS = {
    "toyota": ["camry", "corolla", "rav4", "highlander", "tacoma", "4runner", "sienna", "avalon", "prius"],
    "honda": ["civic", "accord", "cr-v", "crv", "pilot", "odyssey", "fit", "ridgeline"],
    "lexus": ["rx", "es", "gs", "is", "gx", "ls"],
    "acura": ["mdx", "rdx", "tl", "tsx", "ilx"],
    "subaru": ["outback", "forester", "impreza", "legacy", "crosstrek"],
    "mazda": ["mazda3", "mazda6", "cx-5", "cx5", "cx-9", "cx9"],
    "ford": ["f150", "f-150", "escape", "explorer", "fusion", "focus", "edge", "mustang"],
    "chevrolet": ["silverado", "tahoe", "suburban", "malibu", "impala", "equinox", "traverse"],
    "chevy": ["silverado", "tahoe", "suburban", "malibu", "impala", "equinox", "traverse"],
    "gmc": ["sierra", "yukon", "terrain", "acadia"],
    "nissan": ["altima", "sentra", "maxima", "rogue", "murano", "frontier", "pathfinder"],
    "hyundai": ["elantra", "sonata", "santa fe", "tucson", "accent"],
    "kia": ["optima", "sorento", "sportage", "soul", "forte"],
    "bmw": ["x3", "x5", "328", "335", "528", "535", "3 series", "5 series"],
    "audi": ["a4", "a5", "a6", "q5", "q7"],
    "volkswagen": ["jetta", "passat", "tiguan", "golf", "beetle"],
    "vw": ["jetta", "passat", "tiguan", "golf", "beetle"],
    "dodge": ["charger", "challenger", "durango", "journey", "grand caravan"],
    "chrysler": ["300", "town", "pacifica"],
    "jeep": ["wrangler", "grand cherokee", "cherokee", "compass", "patriot"],
    "mini": ["cooper"],
}


# =========================
# HELPERS
# =========================

def clean_text(x):
    if not x:
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()


def money(n):
    try:
        return "${:,.0f}".format(float(n))
    except Exception:
        return "$0"


def parse_price(text):
    if not text:
        return None

    text = text.replace(",", "")
    patterns = [
        r"\$\s*([0-9]{3,6})",
        r"\bprice[:\s]*([0-9]{3,6})\b",
    ]

    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            try:
                val = int(m.group(1))
                if 500 <= val <= 100000:
                    return val
            except Exception:
                pass

    return None


def parse_year(text):
    if not text:
        return None

    years = re.findall(r"\b(19[8-9][0-9]|20[0-2][0-9])\b", text)
    if not years:
        return None

    years = [int(y) for y in years]
    years = [y for y in years if 1985 <= y <= datetime.now().year + 1]

    if not years:
        return None

    return max(years)


def parse_miles(text):
    if not text:
        return None

    t = text.lower().replace(",", "")

    patterns = [
        r"\b([0-9]{2,3})\s*k\s*(?:mi|miles|mile)?\b",
        r"\b([0-9]{4,6})\s*(?:mi|miles|mile|original miles|actual miles)\b",
        r"\bmiles[:\s]*([0-9]{4,6})\b",
        r"\bodometer[:\s]*([0-9]{4,6})\b",
    ]

    for p in patterns:
        m = re.search(p, t)
        if m:
            try:
                val = int(m.group(1))
                if "k" in p:
                    val *= 1000
                if 1000 <= val <= 400000:
                    return val
            except Exception:
                pass

    return None


def detect_make_model(title):
    t = title.lower()

    found_make = None
    found_model = None

    for make, models in MODEL_KEYWORDS.items():
        if re.search(r"\b" + re.escape(make) + r"\b", t):
            found_make = make
            for model in models:
                if model in t:
                    found_model = model
                    break
            break

    if not found_make:
        for make, models in MODEL_KEYWORDS.items():
            for model in models:
                if model in t:
                    found_make = make
                    found_model = model
                    break
            if found_make:
                break

    return found_make, found_model


def risk_flags(text):
    t = text.lower()
    return [term for term in RISKY_TERMS if term in t]


def good_flags(text):
    t = text.lower()
    return [term for term in GOOD_TERMS if term in t]


def estimate_market_value(title, price, year, miles, description=""):
    """
    This is not KBB/MMR. It is a conservative quick-flip estimator.
    It estimates likely private-party resale range from title/year/mileage/make.
    """

    make, model = detect_make_model(title)
    age = max(1, datetime.now().year - year) if year else 12
    miles = miles if miles else 150000

    base = 17000

    if year:
        if year >= 2020:
            base = 22000
        elif year >= 2017:
            base = 18500
        elif year >= 2014:
            base = 14500
        elif year >= 2011:
            base = 11000
        elif year >= 2008:
            base = 8500
        elif year >= 2005:
            base = 6500
        else:
            base = 4500

    mileage_penalty = 0

    if miles > 220000:
        mileage_penalty = 0.48
    elif miles > 190000:
        mileage_penalty = 0.38
    elif miles > 160000:
        mileage_penalty = 0.27
    elif miles > 130000:
        mileage_penalty = 0.17
    elif miles > 100000:
        mileage_penalty = 0.08
    elif miles < 80000:
        mileage_penalty = -0.10

    value = base * (1 - mileage_penalty)

    multiplier = BRAND_SCORE.get(make, 0.95)
    value *= multiplier

    text_all = f"{title} {description}".lower()
    risks = risk_flags(text_all)
    positives = good_flags(text_all)

    if risks:
        value *= 0.68

    if "rebuilt" in text_all or "salvage" in text_all:
        value *= 0.78

    if positives:
        value *= min(1.08, 1 + len(positives) * 0.015)

    if price:
        # Keep estimator anchored near asking price so it does not hallucinate crazy retail.
        value = max(value, price * 1.05)
        value = min(value, price * 1.75)

    value = round(value / 100) * 100
    return int(value)


def evaluate_listing(item, target_profit):
    title = item.get("title", "")
    desc = item.get("description", "")
    price = item.get("price")
    year = parse_year(title + " " + desc)
    miles = parse_miles(title + " " + desc)
    make, model = detect_make_model(title)

    full_text = f"{title} {desc}"
    risks = risk_flags(full_text)
    positives = good_flags(full_text)

    market_value = estimate_market_value(title, price, year, miles, desc)

    recon = 900
    if not miles:
        recon += 400
    if miles and miles > 170000:
        recon += 700
    if year and year < 2008:
        recon += 500
    if risks:
        recon += 1200
    if make in ["bmw", "audi", "mercedes", "mercedes-benz", "mini", "land rover", "range rover", "volkswagen", "vw"]:
        recon += 700

    fees = 350
    negotiation_discount = 0.12

    expected_buy = price * (1 - negotiation_discount) if price else 0
    expected_profit = market_value - expected_buy - recon - fees

    max_buy = market_value - recon - fees - target_profit
    max_buy = max(0, round(max_buy / 100) * 100)

    score = 50

    if expected_profit >= target_profit:
        score += 25
    elif expected_profit >= 1000:
        score += 12
    else:
        score -= 15

    if make in ["toyota", "honda", "lexus", "acura"]:
        score += 12
    elif make in ["bmw", "audi", "mercedes", "mercedes-benz", "mini", "land rover", "range rover"]:
        score -= 14

    if miles:
        if miles < 120000:
            score += 10
        elif miles > 180000:
            score -= 15

    if year:
        if year >= 2012:
            score += 8
        elif year < 2007:
            score -= 8

    if risks:
        score -= 25

    if positives:
        score += min(8, len(positives) * 2)

    score = max(0, min(100, int(score)))

    if risks:
        verdict = "SKIP / HIGH RISK"
        verdict_class = "skip"
    elif expected_profit >= target_profit and score >= 70:
        verdict = "BUY CANDIDATE"
        verdict_class = "buy"
    elif expected_profit >= 1000 and score >= 55:
        verdict = "MAYBE / NEGOTIATE"
        verdict_class = "maybe"
    else:
        verdict = "PASS UNLESS CHEAP"
        verdict_class = "skip"

    return {
        "year": year,
        "miles": miles,
        "make": make,
        "model": model,
        "market_value": market_value,
        "expected_buy": int(round(expected_buy / 100) * 100),
        "max_buy": int(max_buy),
        "recon": int(recon),
        "fees": int(fees),
        "expected_profit": int(round(expected_profit / 100) * 100),
        "score": score,
        "verdict": verdict,
        "verdict_class": verdict_class,
        "risks": risks,
        "positives": positives,
    }


def build_craigslist_url(zip_code, radius, max_price, fmt=None):
    params = {
        "postal": zip_code,
        "search_distance": radius,
        "bundleDuplicates": 1,
        "sort": "date",
        "max_price": max_price,
    }

    if fmt == "rss":
        params["format"] = "rss"

    # cto = cars/trucks by owner
    return f"{CRAIGSLIST_BASE}/search/cto?{urlencode(params)}"


def make_session():
    s = requests.Session()

    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.5 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
        "Referer": "https://saltlakecity.craigslist.org/",
    })

    return s


def fetch_url(url, timeout=20):
    s = make_session()

    last_error = None

    for attempt in range(3):
        try:
            r = s.get(url, timeout=timeout, allow_redirects=True)
            if r.status_code == 200 and r.text:
                return r.text
            last_error = f"{r.status_code} {r.reason}"
            time.sleep(1.2 + attempt)
        except Exception as e:
            last_error = str(e)
            time.sleep(1.2 + attempt)

    raise RuntimeError(last_error or "Unknown Craigslist request error")


def parse_rss(xml_text):
    soup = BeautifulSoup(xml_text, "xml")
    items = []

    for entry in soup.find_all(["item", "entry"]):
        title = clean_text(entry.title.get_text(" ", strip=True)) if entry.title else ""
        link = ""

        if entry.link:
            if entry.link.get("href"):
                link = entry.link.get("href")
            else:
                link = clean_text(entry.link.get_text(" ", strip=True))

        desc = ""
        for tag_name in ["description", "summary", "content"]:
            tag = entry.find(tag_name)
            if tag:
                desc = clean_text(BeautifulSoup(tag.get_text(" ", strip=True), "html.parser").get_text(" ", strip=True))
                break

        date_text = ""
        for tag_name in ["pubDate", "updated", "published", "dc:date"]:
            tag = entry.find(tag_name)
            if tag:
                date_text = clean_text(tag.get_text(" ", strip=True))
                break

        price = parse_price(title + " " + desc)

        if title and link:
            items.append({
                "title": title,
                "link": link,
                "description": desc,
                "date": date_text,
                "price": price,
            })

    return items


def parse_html(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    items = []

    rows = soup.select("li.cl-static-search-result, li.result-row, div.gallery-card, div.cl-search-result")

    for row in rows:
        title = ""

        title_tag = row.select_one(".title, .result-title, a.posting-title, a")
        if title_tag:
            title = clean_text(title_tag.get_text(" ", strip=True))

        link = ""
        a = row.select_one("a[href]")
        if a:
            link = a.get("href", "")
            if link.startswith("/"):
                link = CRAIGSLIST_BASE + link

        price = None
        price_tag = row.select_one(".price, .result-price")
        if price_tag:
            price = parse_price(price_tag.get_text(" ", strip=True))

        text = clean_text(row.get_text(" ", strip=True))
        if price is None:
            price = parse_price(text)

        if not title:
            title = text[:120]

        if title and link:
            items.append({
                "title": title,
                "link": link,
                "description": text,
                "date": "",
                "price": price,
            })

    return items


def dedupe_items(items):
    seen = set()
    clean = []

    for item in items:
        key_source = item.get("link") or item.get("title")
        key = hashlib.md5(key_source.encode("utf-8", errors="ignore")).hexdigest()

        if key in seen:
            continue

        seen.add(key)
        clean.append(item)

    return clean


def is_vehicle_listing(item):
    title = item.get("title", "").lower()
    desc = item.get("description", "").lower()
    text = f"{title} {desc}"

    bad = [
        "camper", "motorhome", "rv", "trailer", "boat", "atv", "utv",
        "motorcycle", "scooter", "semi", "f650", "box truck", "parts only"
    ]

    if any(x in text for x in bad):
        return False

    has_year = parse_year(text) is not None
    has_price = item.get("price") is not None

    vehicle_words = [
        "toyota", "honda", "lexus", "acura", "subaru", "mazda", "ford",
        "chevy", "chevrolet", "gmc", "nissan", "hyundai", "kia", "bmw",
        "audi", "mercedes", "volkswagen", "vw", "dodge", "chrysler",
        "jeep", "mini", "cadillac", "buick", "lincoln", "infiniti",
        "camry", "corolla", "civic", "accord", "crv", "cr-v", "rav4",
        "pilot", "odyssey", "tacoma", "4runner", "highlander", "f150",
        "silverado", "sierra", "escape", "explorer", "altima", "sentra"
    ]

    has_vehicle_word = any(w in text for w in vehicle_words)

    return has_price and (has_year or has_vehicle_word)


def scan_craigslist(zip_code, radius, max_price):
    rss_url = build_craigslist_url(zip_code, radius, max_price, fmt="rss")
    html_url = build_craigslist_url(zip_code, radius, max_price, fmt=None)

    errors = []

    try:
        xml_text = fetch_url(rss_url)
        items = parse_rss(xml_text)
        items = dedupe_items(items)

        if items:
            return items, rss_url, None

        errors.append("RSS loaded but returned zero parsed listings.")
    except Exception as e:
        errors.append(f"RSS failed: {e}")

    try:
        html_text = fetch_url(html_url)
        items = parse_html(html_text)
        items = dedupe_items(items)

        if items:
            return items, html_url, None

        errors.append("HTML search loaded but returned zero parsed listings.")
    except Exception as e:
        errors.append(f"HTML failed: {e}")

    return [], rss_url, " | ".join(errors)


def render_card(item, ev):
    title = item.get("title", "Untitled")
    link = item.get("link", "")
    price = item.get("price")

    miles_text = f"{ev['miles']:,} miles" if ev["miles"] else "Miles unknown"
    year_text = str(ev["year"]) if ev["year"] else "Year unknown"
    make_text = ev["make"].title() if ev["make"] else "Make unknown"

    risks_text = ", ".join(ev["risks"]) if ev["risks"] else "No major red flags detected from text"
    positives_text = ", ".join(ev["positives"]) if ev["positives"] else "No strong positive keywords detected"

    st.markdown(f"""
    <div class="car-card">
        <div class="car-title">{title}</div>

        <div class="metric-row">
            <span class="pill">Ask: <b>{money(price)}</b></span>
            <span class="pill">Est. resale: <b>{money(ev["market_value"])}</b></span>
            <span class="pill">Max buy: <b>{money(ev["max_buy"])}</b></span>
            <span class="pill">Est. profit: <b>{money(ev["expected_profit"])}</b></span>
            <span class="pill">Score: <b>{ev["score"]}/100</b></span>
        </div>

        <div class="{ev["verdict_class"]}">{ev["verdict"]}</div>

        <div class="small" style="margin-top:10px;">
            <b>Vehicle:</b> {year_text} · {make_text} · {miles_text}<br>
            <b>Expected negotiated buy:</b> {money(ev["expected_buy"])} · 
            <b>Recon allowance:</b> {money(ev["recon"])} · 
            <b>Fees:</b> {money(ev["fees"])}<br>
            <b>Risk flags:</b> {risks_text}<br>
            <b>Good signs:</b> {positives_text}
        </div>

        <div style="margin-top:12px;">
            <a href="{link}" target="_blank">Open Craigslist listing</a>
        </div>
    </div>
    """, unsafe_allow_html=True)


# =========================
# UI
# =========================

st.markdown("# Car Flip AI")
st.markdown(
    f'<div class="sub">Scanning Craigslist owner listings from ZIP <b>{DEFAULT_ZIP}</b> within <b>{DEFAULT_RADIUS} miles</b>.</div>',
    unsafe_allow_html=True
)

with st.expander("Filters"):
    zip_code = st.text_input("ZIP code", DEFAULT_ZIP)
    radius = st.slider("Search radius", 10, 120, DEFAULT_RADIUS, step=5)
    max_price = st.slider("Max price", 3000, 30000, DEFAULT_MAX_PRICE, step=500)
    min_year = st.slider("Minimum year", 1995, 2024, DEFAULT_MIN_YEAR, step=1)
    max_miles = st.slider("Max mileage", 80000, 300000, DEFAULT_MAX_MILES, step=5000)
    target_profit = st.slider("Target profit", 500, 6000, DEFAULT_TARGET_PROFIT, step=250)
    show_all = st.toggle("Show weak/pass listings too", value=False)

raw_url = build_craigslist_url(zip_code, radius, max_price, fmt="rss")

st.markdown(f"""
<div class="info-box">
<b>Source:</b> Craigslist owner listings only · ZIP {zip_code} · {radius}-mile radius · Max price {money(max_price)}<br>
<a href="{raw_url}" target="_blank">Open raw Craigslist RSS/search</a>
</div>
""", unsafe_allow_html=True)

scan = st.button("Scan Craigslist now", type="primary")

if scan:
    with st.spinner("Scanning Craigslist..."):
        items, used_url, error = scan_craigslist(zip_code, radius, max_price)

    if error:
        st.markdown(f"""
        <div class="err-box">
        <b>Craigslist blocked the app request.</b><br><br>
        Error detail: {error}<br><br>
        This usually means Craigslist blocked the Streamlit Cloud server IP. 
        The filters are correct. The app is now using owner-only <b>/search/cto</b>, real browser headers, RSS first, and HTML fallback.
        <br><br>
        Open the raw Craigslist link above. If that opens on your phone but the app still errors, Craigslist is blocking the cloud server, not your app code.
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    if not items:
        st.markdown("""
        <div class="warn-box">
        No listings returned. Craigslist may be temporarily blocking or there may be no matching listings for the filters.
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    parsed = []

    for item in items:
        if not item.get("price"):
            continue

        if item["price"] > max_price:
            continue

        if not is_vehicle_listing(item):
            continue

        ev = evaluate_listing(item, target_profit)

        if ev["year"] and ev["year"] < min_year:
            continue

        if ev["miles"] and ev["miles"] > max_miles:
            continue

        parsed.append((item, ev))

    parsed.sort(key=lambda x: (x[1]["score"], x[1]["expected_profit"]), reverse=True)

    if not parsed:
        st.markdown("""
        <div class="warn-box">
        Craigslist loaded, but no listings passed your filters. Try increasing mileage/year range or lowering target profit temporarily.
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    buy_count = sum(1 for _, ev in parsed if ev["verdict"] == "BUY CANDIDATE")
    maybe_count = sum(1 for _, ev in parsed if ev["verdict"] == "MAYBE / NEGOTIATE")

    st.markdown(f"""
    <div class="good-box">
    <b>Scan complete.</b><br>
    Parsed listings: {len(parsed)} · Buy candidates: {buy_count} · Maybe/negotiation candidates: {maybe_count}
    </div>
    """, unsafe_allow_html=True)

    rows = []

    for item, ev in parsed:
        if not show_all and ev["verdict"] not in ["BUY CANDIDATE", "MAYBE / NEGOTIATE"]:
            continue

        rows.append({
            "Verdict": ev["verdict"],
            "Score": ev["score"],
            "Title": item["title"],
            "Ask": item["price"],
            "Max Buy": ev["max_buy"],
            "Est Profit": ev["expected_profit"],
            "Est Resale": ev["market_value"],
            "Year": ev["year"],
            "Miles": ev["miles"],
            "Link": item["link"],
        })

        render_card(item, ev)

    if rows:
        df = pd.DataFrame(rows)
        st.download_button(
            "Download scan results CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"car_flip_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )
    else:
        st.markdown("""
        <div class="warn-box">
        No strong buy/maybe listings after scoring. Turn on “Show weak/pass listings too” inside Filters if you want to see everything.
        </div>
        """, unsafe_allow_html=True)

else:
    st.markdown("""
    <div class="small">
    Tap <b>Scan Craigslist now</b>. If Craigslist blocks Streamlit Cloud again, open the raw Craigslist link above to confirm the search itself still works.
    </div>
    """, unsafe_allow_html=True)
