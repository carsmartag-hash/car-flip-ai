import re
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
    color: #55aaff;
    border-radius: 14px;
    padding: 16px 18px;
    font-size: 1.05rem;
    line-height: 1.55;
    margin-bottom: 1.1rem;
}

.car-card {
    border: 1px solid rgba(250,250,250,0.16);
    border-radius: 18px;
    padding: 16px;
    margin-bottom: 14px;
    background: rgba(255,255,255,0.035);
}

.buy {
    border-left: 7px solid #22c55e;
}

.watch {
    border-left: 7px solid #facc15;
}

.reject {
    border-left: 7px solid #ef4444;
    opacity: 0.78;
}

.car-title {
    font-size: 1.15rem;
    font-weight: 800;
    margin-bottom: 6px;
}

.metric {
    font-size: 0.95rem;
    color: #d1d5db;
    margin-bottom: 4px;
}

.reason {
    font-size: 0.95rem;
    color: #a1a1aa;
    margin-top: 8px;
}

.badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    font-weight: 800;
    font-size: 0.82rem;
    margin-bottom: 8px;
}

.badge-buy {
    background: #14532d;
    color: #86efac;
}

.badge-watch {
    background: #713f12;
    color: #fde68a;
}

.badge-reject {
    background: #7f1d1d;
    color: #fecaca;
}

a {
    color: #60a5fa !important;
}
</style>
""", unsafe_allow_html=True)


# =========================
# CONFIG
# =========================

ZIP_CODE = "84107"
RADIUS_MILES = 90
MIN_PRICE = 1000
MAX_PRICE = 16000
MIN_PROFIT_TARGET = 2000
MAX_MILES_SOFT = 180000

CRAIGSLIST_BASE = "https://saltlakecity.craigslist.org/search/cto"

BAD_WORDS = [
    "rv", "motorhome", "camper", "trailer", "fifth wheel", "5th wheel",
    "boat", "atv", "utv", "side by side", "motorcycle", "scooter",
    "semi", "dump truck", "box truck", "bus", "parts only", "mechanic special",
    "salvage title only", "no title", "bill of sale"
]

GOOD_BRANDS = [
    "toyota", "honda", "lexus", "acura", "mazda", "subaru",
    "ford", "chevrolet", "gmc", "hyundai", "kia", "nissan"
]

RISKY_BRANDS = [
    "bmw", "mini", "mercedes", "audi", "volkswagen", "vw",
    "land rover", "range rover", "jaguar", "volvo", "fiat"
]


# =========================
# HELPERS
# =========================

def craigslist_search_url(format_rss=False):
    params = {
        "postal": ZIP_CODE,
        "search_distance": RADIUS_MILES,
        "min_price": MIN_PRICE,
        "max_price": MAX_PRICE,
        "auto_title_status": 1,
        "sort": "date"
    }
    if format_rss:
        params["format"] = "rss"
    return CRAIGSLIST_BASE + "?" + urlencode(params)


def clean_text(x):
    if not x:
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()


def parse_price(text):
    if not text:
        return None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})", text.replace(".", ""))
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except Exception:
        return None


def parse_year(text):
    m = re.search(r"\b(19[8-9][0-9]|20[0-2][0-9])\b", text or "")
    if not m:
        return None
    year = int(m.group(1))
    current_year = datetime.now().year
    if 1980 <= year <= current_year + 1:
        return year
    return None


def parse_miles(text):
    text = (text or "").lower().replace(",", "")
    patterns = [
        r"\b([0-9]{2,3})k\s*miles?\b",
        r"\b([0-9]{5,6})\s*miles?\b",
        r"\bmileage[:\s]+([0-9]{5,6})\b",
        r"\bodometer[:\s]+([0-9]{5,6})\b"
    ]

    for p in patterns:
        m = re.search(p, text)
        if m:
            val = int(m.group(1))
            if "k" in p:
                val *= 1000
            if 10000 <= val <= 350000:
                return val
    return None


def normalize_title_for_duplicate(title):
    title = (title or "").lower()
    title = re.sub(r"\$[0-9,]+", "", title)
    title = re.sub(r"[^a-z0-9 ]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def listing_key(item):
    title_key = normalize_title_for_duplicate(item.get("title", ""))
    price = item.get("price") or 0
    url = item.get("url", "")

    if url:
        url = url.split("?")[0].strip("/")
        post_id = url.split("/")[-1].replace(".html", "")
        if post_id.isdigit():
            return post_id

    raw = f"{title_key}|{price}"
    return hashlib.md5(raw.encode()).hexdigest()


def rough_market_value(title, year, miles):
    """
    Conservative estimator.
    This is NOT KBB. It is a flip-screening estimate.
    It intentionally avoids fake exact KBB numbers.
    """

    title_l = (title or "").lower()

    if not year:
        base = 6500
    else:
        age = max(datetime.now().year - year, 0)

        if age <= 5:
            base = 15500
        elif age <= 8:
            base = 12500
        elif age <= 11:
            base = 9500
        elif age <= 15:
            base = 7000
        else:
            base = 4500

    if any(b in title_l for b in GOOD_BRANDS):
        base += 1200

    if any(b in title_l for b in RISKY_BRANDS):
        base -= 1800

    if miles:
        if miles < 90000:
            base += 1200
        elif miles < 120000:
            base += 500
        elif miles < 160000:
            base -= 500
        elif miles < 200000:
            base -= 1600
        else:
            base -= 3200

    if "hybrid" in title_l:
        base -= 700

    if "clean title" in title_l:
        base += 400

    if "rebuilt" in title_l or "salvage" in title_l:
        base -= 2500

    return max(1500, int(round(base / 100) * 100))


def estimate_recon(title, year, miles, price):
    title_l = (title or "").lower()

    recon = 700

    if miles and miles > 150000:
        recon += 600

    if miles and miles > 190000:
        recon += 900

    if any(b in title_l for b in RISKY_BRANDS):
        recon += 1200

    if "needs" in title_l:
        recon += 1200

    if "check engine" in title_l or "cel" in title_l:
        recon += 1000

    if "transmission" in title_l:
        recon += 1800

    if "overheating" in title_l:
        recon += 1200

    if "rebuilt" in title_l or "salvage" in title_l:
        recon += 700

    return recon


def evaluate_listing(item):
    title = item.get("title", "")
    title_l = title.lower()
    price = item.get("price")
    year = item.get("year")
    miles = item.get("miles")

    reasons = []

    if any(w in title_l for w in BAD_WORDS):
        return {
            **item,
            "decision": "REJECT",
            "score": 0,
            "market_value": None,
            "recon": None,
            "target_buy": None,
            "estimated_profit": None,
            "risk": "HIGH",
            "reasons": "Not a normal private car listing / bad keyword."
        }

    if price is None:
        return {
            **item,
            "decision": "REJECT",
            "score": 0,
            "market_value": None,
            "recon": None,
            "target_buy": None,
            "estimated_profit": None,
            "risk": "HIGH",
            "reasons": "No price found."
        }

    if price < MIN_PRICE or price > MAX_PRICE:
        return {
            **item,
            "decision": "REJECT",
            "score": 0,
            "market_value": None,
            "recon": None,
            "target_buy": None,
            "estimated_profit": None,
            "risk": "HIGH",
            "reasons": "Outside price range."
        }

    market_value = rough_market_value(title, year, miles)
    recon = estimate_recon(title, year, miles, price)

    selling_cost = 350
    estimated_profit = market_value - price - recon - selling_cost
    target_buy = market_value - recon - selling_cost - MIN_PROFIT_TARGET

    score = 50

    if estimated_profit >= 3000:
        score += 30
        reasons.append("Strong estimated profit.")
    elif estimated_profit >= 2000:
        score += 20
        reasons.append("Meets profit target.")
    elif estimated_profit >= 1000:
        score += 5
        reasons.append("Possible deal but below target.")
    else:
        score -= 25
        reasons.append("Estimated profit too low.")

    if year and year >= 2011:
        score += 10
    elif year and year < 2006:
        score -= 10
        reasons.append("Older vehicle.")

    if miles:
        if miles <= 130000:
            score += 10
        elif miles <= MAX_MILES_SOFT:
            score -= 5
        else:
            score -= 20
            reasons.append("High mileage.")
    else:
        score -= 8
        reasons.append("Mileage unknown.")

    if any(b in title_l for b in GOOD_BRANDS):
        score += 8

    if any(b in title_l for b in RISKY_BRANDS):
        score -= 18
        reasons.append("Higher repair-risk brand.")

    if "rebuilt" in title_l or "salvage" in title_l:
        score -= 20
        reasons.append("Rebuilt/salvage title risk.")

    score = max(0, min(100, score))

    if estimated_profit >= MIN_PROFIT_TARGET and score >= 70:
        decision = "BUY"
    elif estimated_profit >= 1000 and score >= 50:
        decision = "WATCH"
    else:
        decision = "REJECT"

    if score >= 72:
        risk = "LOW/MED"
    elif score >= 52:
        risk = "MED"
    else:
        risk = "HIGH"

    return {
        **item,
        "decision": decision,
        "score": score,
        "market_value": market_value,
        "recon": recon,
        "target_buy": max(0, target_buy),
        "estimated_profit": estimated_profit,
        "risk": risk,
        "reasons": " ".join(reasons) if reasons else "Standard screening result."
    }


# =========================
# SCRAPING
# =========================

def request_page(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://saltlakecity.craigslist.org/"
    }

    session = requests.Session()
    r = session.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.text


@st.cache_data(ttl=300, show_spinner=False)
def fetch_craigslist():
    html_url = craigslist_search_url(format_rss=False)
    rss_url = craigslist_search_url(format_rss=True)

    errors = []

    # Try normal HTML first
    try:
        html = request_page(html_url)
        listings = parse_craigslist_html(html)
        if listings:
            return listings, html_url, None
    except Exception as e:
        errors.append(f"HTML failed: {e}")

    # Try RSS second
    try:
        rss = request_page(rss_url)
        listings = parse_craigslist_rss(rss)
        if listings:
            return listings, rss_url, None
    except Exception as e:
        errors.append(f"RSS failed: {e}")

    return [], html_url, "Craigslist blocked the Streamlit server. This is a Craigslist 403 block, not a Python crash."


def parse_craigslist_html(html):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    cards = soup.select("li.cl-search-result, li.result-row, div.result-info, ol li")

    for card in cards:
        text = clean_text(card.get_text(" ", strip=True))
        if not text:
            continue

        a = card.select_one("a[href]")
        if not a:
            continue

        url = a.get("href")
        if url and url.startswith("/"):
            url = "https://saltlakecity.craigslist.org" + url

        title = clean_text(a.get_text(" ", strip=True))
        if len(title) < 5:
            title = text[:100]

        price = None

        price_el = card.select_one(".price")
        if price_el:
            price = parse_price(price_el.get_text())

        if price is None:
            price = parse_price(text)

        year = parse_year(title)
        miles = parse_miles(text)

        if not price:
            continue

        results.append({
            "title": title,
            "price": price,
            "year": year,
            "miles": miles,
            "url": url,
            "source": "Craigslist"
        })

    return dedupe_listings(results)


def parse_craigslist_rss(xml_text):
    soup = BeautifulSoup(xml_text, "xml")
    results = []

    for item in soup.find_all("item"):
        title = clean_text(item.title.get_text()) if item.title else ""
        link = clean_text(item.link.get_text()) if item.link else ""
        desc = clean_text(item.description.get_text()) if item.description else ""

        full_text = f"{title} {desc}"
        price = parse_price(full_text)
        year = parse_year(full_text)
        miles = parse_miles(full_text)

        if not title or not price:
            continue

        results.append({
            "title": title,
            "price": price,
            "year": year,
            "miles": miles,
            "url": link,
            "source": "Craigslist RSS"
        })

    return dedupe_listings(results)


def dedupe_listings(items):
    seen = set()
    clean = []

    for item in items:
        key = listing_key(item)
        if key in seen:
            continue
        seen.add(key)
        clean.append(item)

    return clean


# =========================
# UI
# =========================

st.markdown("# 🚗 Car Flip AI")
st.markdown(
    f"<div class='sub'>ZIP {ZIP_CODE} · {RADIUS_MILES} mile radius · Craigslist owner listings</div>",
    unsafe_allow_html=True
)

st.markdown(
    "<div class='info-box'>App scans automatically. BUY cars show first. Rejected listings stay at the bottom.</div>",
    unsafe_allow_html=True
)

if st.button("Refresh Scan"):
    st.cache_data.clear()
    st.rerun()

with st.spinner("Scanning listings..."):
    raw_listings, search_url, error_message = fetch_craigslist()

if error_message:
    st.error(error_message)
    st.markdown(f"Open Craigslist search manually here: [Craigslist 84107 / 90 miles owner listings]({search_url})")
    st.stop()

if not raw_listings:
    st.warning("No listings found right now. Try Refresh Scan in a minute.")
    st.markdown(f"Manual search link: [Open Craigslist]({search_url})")
    st.stop()

evaluated = [evaluate_listing(x) for x in raw_listings]

buy = [x for x in evaluated if x["decision"] == "BUY"]
watch = [x for x in evaluated if x["decision"] == "WATCH"]
reject = [x for x in evaluated if x["decision"] == "REJECT"]

buy = sorted(buy, key=lambda x: (x["estimated_profit"] or -99999), reverse=True)
watch = sorted(watch, key=lambda x: (x["estimated_profit"] or -99999), reverse=True)
reject = sorted(reject, key=lambda x: (x["score"] or 0), reverse=True)

st.markdown(f"### Found {len(evaluated)} listings")
st.markdown(f"**BUY:** {len(buy)} · **WATCH:** {len(watch)} · **Rejected:** {len(reject)}")


def money(x):
    if x is None:
        return "Unknown"
    return f"${int(x):,}"


def miles_fmt(x):
    if x is None:
        return "Unknown"
    return f"{int(x):,}"


def render_card(car):
    decision = car["decision"]

    if decision == "BUY":
        cls = "car-card buy"
        badge = "badge badge-buy"
    elif decision == "WATCH":
        cls = "car-card watch"
        badge = "badge badge-watch"
    else:
        cls = "car-card reject"
        badge = "badge badge-reject"

    title = car.get("title") or "Untitled listing"
    url = car.get("url") or "#"

    st.markdown(f"""
    <div class="{cls}">
        <div class="{badge}">{decision} · SCORE {car.get("score", 0)}/100 · RISK {car.get("risk", "UNK")}</div>
        <div class="car-title"><a href="{url}" target="_blank">{title}</a></div>
        <div class="metric">Ask Price: <b>{money(car.get("price"))}</b></div>
        <div class="metric">Estimated Retail/Market: <b>{money(car.get("market_value"))}</b></div>
        <div class="metric">Estimated Recon: <b>{money(car.get("recon"))}</b></div>
        <div class="metric">Target Buy Price for $2,000 profit: <b>{money(car.get("target_buy"))}</b></div>
        <div class="metric">Estimated Profit at Ask: <b>{money(car.get("estimated_profit"))}</b></div>
        <div class="metric">Year: <b>{car.get("year") or "Unknown"}</b> · Miles: <b>{miles_fmt(car.get("miles"))}</b></div>
        <div class="reason">{car.get("reasons", "")}</div>
    </div>
    """, unsafe_allow_html=True)


if buy:
    st.markdown("## ✅ BUY")
    for car in buy:
        render_card(car)

if watch:
    st.markdown("## 👀 WATCH / NEGOTIATE")
    for car in watch:
        render_card(car)

with st.expander(f"Rejected listings ({len(reject)})"):
    for car in reject:
        render_card(car)

st.caption(f"Last scan: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
