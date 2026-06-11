import re
import math
import hashlib
from html import escape
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
    margin-bottom: 8px;
    line-height: 1.35;
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
    line-height: 1.4;
}

.badge {
    display: inline-block;
    padding: 5px 11px;
    border-radius: 999px;
    font-weight: 800;
    font-size: 0.82rem;
    margin-bottom: 9px;
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

.comp-links {
    margin-top: 12px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}

.comp-links a {
    text-decoration: none !important;
    background: rgba(96,165,250,0.14);
    border: 1px solid rgba(96,165,250,0.35);
    padding: 7px 10px;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 800;
    color: #93c5fd !important;
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

MAX_DETAIL_PAGES = 60

CRAIGSLIST_BASE = "https://saltlakecity.craigslist.org/search/cto"

BAD_WORDS = [
    "rv", "motorhome", "camper", "trailer", "fifth wheel", "5th wheel",
    "boat", "atv", "utv", "side by side", "motorcycle", "scooter",
    "semi", "dump truck", "box truck", "bus", "parts only", "mechanic special",
    "no title", "bill of sale"
]

GOOD_BRANDS = [
    "toyota", "honda", "lexus", "acura", "mazda", "subaru",
    "ford", "chevrolet", "gmc", "hyundai", "kia", "nissan"
]

RISKY_BRANDS = [
    "bmw", "mini", "mercedes", "audi", "volkswagen", "vw",
    "land rover", "range rover", "jaguar", "volvo", "fiat"
]

MAKE_LIST = [
    "acura", "audi", "bmw", "buick", "cadillac", "chevrolet", "chevy",
    "chrysler", "dodge", "ford", "gmc", "honda", "hyundai", "infiniti",
    "jaguar", "jeep", "kia", "land rover", "lexus", "lincoln", "mazda",
    "mercedes", "mercedes-benz", "mini", "mitsubishi", "nissan", "ram",
    "subaru", "toyota", "volkswagen", "vw", "volvo"
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

    raw = str(text)

    money_patterns = [
        r"\$\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})",
        r"price[:\s]*\$?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})",
        r"asking[:\s]*\$?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})",
    ]

    for pattern in money_patterns:
        m = re.search(pattern, raw, flags=re.I)
        if m:
            try:
                price = int(m.group(1).replace(",", ""))
                if 100 <= price <= 100000:
                    return price
            except Exception:
                pass

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
    """
    Strong mileage parser.
    Handles:
    - odometer: 211000
    - odometer 211,000
    - mileage: 211000
    - 211,000 miles
    - 211000 miles
    - 211k
    - 211k miles
    """

    if not text:
        return None

    raw = str(text).lower()
    raw = raw.replace("\xa0", " ")
    raw = raw.replace(",", "")

    patterns = [
        r"\bodometer[:\s#-]*([0-9]{5,6})\b",
        r"\bmileage[:\s#-]*([0-9]{5,6})\b",
        r"\bmiles[:\s#-]*([0-9]{5,6})\b",
        r"\b([0-9]{5,6})\s*(?:mi|mile|miles)\b",
        r"\b([0-9]{2,3})\s*k\s*(?:mi|mile|miles)?\b",
        r"\b([0-9]{2,3})k\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, raw)
        if not m:
            continue

        try:
            val = int(m.group(1))
            if "k" in pattern:
                val *= 1000

            if 10000 <= val <= 400000:
                return val
        except Exception:
            continue

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
        clean_url = url.split("?")[0].strip("/")
        post_id = clean_url.split("/")[-1].replace(".html", "")
        if post_id.isdigit():
            return post_id

    raw = f"{title_key}|{price}"
    return hashlib.md5(raw.encode()).hexdigest()


def extract_make_model(title):
    text = (title or "").lower()
    text_clean = re.sub(r"[^a-z0-9 ]", " ", text)
    text_clean = re.sub(r"\s+", " ", text_clean).strip()

    found_make = None

    for make in sorted(MAKE_LIST, key=len, reverse=True):
        pattern = r"\b" + re.escape(make) + r"\b"
        if re.search(pattern, text_clean):
            found_make = make
            break

    if not found_make:
        return None, None

    normalized_make = found_make

    if normalized_make == "chevy":
        normalized_make = "chevrolet"
    if normalized_make == "vw":
        normalized_make = "volkswagen"
    if normalized_make == "mercedes":
        normalized_make = "mercedes-benz"

    words = text_clean.split()
    make_words = found_make.split()

    model = None

    for i in range(len(words)):
        if words[i:i + len(make_words)] == make_words:
            after = words[i + len(make_words):i + len(make_words) + 3]
            after = [w for w in after if not re.match(r"^(awd|fwd|rwd|4x4|manual|auto|automatic|clean|title)$", w)]
            if after:
                model = " ".join(after[:2])
            break

    return normalized_make, model


def comparison_links(car):
    title = car.get("title") or ""
    year = car.get("year") or ""
    make, model = extract_make_model(title)

    search_text = f"{year} {title}".strip()
    q = quote_plus(search_text)

    if make and model and year:
        make_slug = quote_plus(make)
        model_slug = quote_plus(model)
        kbb = f"https://www.kbb.com/cars-for-sale/all/{year}/{make_slug}/{model_slug}/?zip={ZIP_CODE}"
        cars = f"https://www.cars.com/shopping/results/?stock_type=used&makes[]={make_slug}&models[]={make_slug}-{model_slug}&zip={ZIP_CODE}&maximum_distance=100"
    else:
        kbb = f"https://www.kbb.com/cars-for-sale/used/?zip={ZIP_CODE}&keyword={q}"
        cars = f"https://www.cars.com/shopping/results/?stock_type=used&keyword={q}&zip={ZIP_CODE}&maximum_distance=100"

    return {
        "KBB": kbb,
        "CarGurus": f"https://www.cargurus.com/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action?zip={ZIP_CODE}&distance=100#resultsPage=1&search={q}",
        "Cars.com": cars,
        "KSL": f"https://cars.ksl.com/search/zip/{ZIP_CODE}/miles/100/keyword/{q}",
        "Google": f"https://www.google.com/search?q={q}+for+sale+Utah+private+party",
    }


def rough_market_value(title, year, miles):
    """
    Conservative estimator.
    This is not KBB.
    It is only for quick flip screening before checking real comps.
    """

    title_l = (title or "").lower()

    if not year:
        base = 6000
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
        base += 1000

    if any(b in title_l for b in RISKY_BRANDS):
        base -= 1800

    if miles is None:
        base -= 800
    else:
        if miles < 90000:
            base += 1200
        elif miles < 120000:
            base += 500
        elif miles < 160000:
            base -= 600
        elif miles < 180000:
            base -= 1300
        elif miles < 200000:
            base -= 2200
        elif miles < 230000:
            base -= 3800
        else:
            base -= 5000

    if "hybrid" in title_l:
        base -= 700

    if "clean title" in title_l:
        base += 300

    if "rebuilt" in title_l or "salvage" in title_l:
        base -= 2500

    if "manual" in title_l:
        base -= 300

    return max(1500, int(round(base / 100) * 100))


def estimate_recon(title, year, miles, price):
    title_l = (title or "").lower()

    recon = 700

    if miles is None:
        recon += 400

    if miles and miles > 150000:
        recon += 600

    if miles and miles > 180000:
        recon += 600

    if miles and miles > 200000:
        recon += 700

    if any(b in title_l for b in RISKY_BRANDS):
        recon += 1200

    danger_words = {
        "needs": 1200,
        "check engine": 1000,
        "cel": 1000,
        "transmission": 1800,
        "overheating": 1400,
        "head gasket": 1800,
        "misfire": 900,
        "not running": 2500,
        "does not run": 2500,
        "won't start": 1800,
        "no reverse": 2200,
    }

    for word, add in danger_words.items():
        if word in title_l:
            recon += add

    if "rebuilt" in title_l or "salvage" in title_l:
        recon += 700

    return recon


def mileage_penalty(miles):
    if miles is None:
        return 18, "Mileage unknown."

    if miles >= 230000:
        return 42, "Very high mileage."
    if miles >= 200000:
        return 35, "Very high mileage."
    if miles >= 180000:
        return 28, "High mileage."
    if miles >= 150000:
        return 15, "Moderate/high mileage."
    if miles >= 120000:
        return 6, "Normal used-car mileage."

    return 0, "Good mileage."


def evaluate_listing(item):
    title = item.get("title", "")
    full_text = item.get("full_text", title)
    combined_l = f"{title} {full_text}".lower()

    price = item.get("price")
    year = item.get("year")
    miles = item.get("miles")

    reasons = []

    if any(w in combined_l for w in BAD_WORDS):
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
    recon = estimate_recon(combined_l, year, miles, price)

    selling_cost = 350
    estimated_profit = market_value - price - recon - selling_cost
    target_buy = market_value - recon - selling_cost - MIN_PROFIT_TARGET

    score = 50

    if estimated_profit >= 4000:
        score += 28
        reasons.append("Strong estimated profit.")
    elif estimated_profit >= 3000:
        score += 22
        reasons.append("Good estimated profit.")
    elif estimated_profit >= 2000:
        score += 14
        reasons.append("Meets profit target.")
    elif estimated_profit >= 1000:
        score += 3
        reasons.append("Possible deal but below target.")
    else:
        score -= 25
        reasons.append("Estimated profit too low.")

    if year and year >= 2011:
        score += 8
    elif year and year < 2006:
        score -= 10
        reasons.append("Older vehicle.")

    penalty, mile_note = mileage_penalty(miles)
    score -= penalty
    reasons.append(mile_note)

    if miles and miles <= 130000:
        score += 8

    if any(b in combined_l for b in GOOD_BRANDS):
        score += 7

    if any(b in combined_l for b in RISKY_BRANDS):
        score -= 18
        reasons.append("Higher repair-risk brand.")

    if "rebuilt" in combined_l or "salvage" in combined_l:
        score -= 20
        reasons.append("Rebuilt/salvage title risk.")

    if "clean title" in combined_l:
        score += 4

    score = max(0, min(100, score))

    # Hard safety rules
    if miles is None:
        if estimated_profit >= 2500 and score >= 55:
            decision = "WATCH"
            risk = "MED/HIGH"
            reasons.append("Do not buy until mileage is verified.")
        else:
            decision = "REJECT"
            risk = "HIGH"
            reasons.append("Mileage missing makes this unsafe.")
    elif miles >= 180000:
        if estimated_profit >= 3000 and price <= target_buy and score >= 45:
            decision = "WATCH"
            risk = "MED/HIGH"
            reasons.append("High-mileage car: inspect before buying.")
        else:
            decision = "REJECT"
            risk = "HIGH"
            reasons.append("Mileage too high for automatic buy.")
    else:
        if estimated_profit >= MIN_PROFIT_TARGET and score >= 70 and price <= target_buy:
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


@st.cache_data(ttl=600, show_spinner=False)
def fetch_detail_data(url):
    if not url or not str(url).startswith("http"):
        return {}

    try:
        html = request_page(url)
        soup = BeautifulSoup(html, "html.parser")

        body = clean_text(soup.get_text(" ", strip=True))

        attr_texts = []
        for attr in soup.select(".attrgroup span, .mapaddress, .postingtitletext, #postingbody"):
            attr_texts.append(clean_text(attr.get_text(" ", strip=True)))

        attr_text = clean_text(" ".join(attr_texts))
        full_text = clean_text(f"{attr_text} {body}")

        detail_price = parse_price(full_text)
        detail_year = parse_year(full_text)
        detail_miles = parse_miles(full_text)

        return {
            "detail_price": detail_price,
            "detail_year": detail_year,
            "detail_miles": detail_miles,
            "detail_text": full_text[:5000],
        }

    except Exception:
        return {}


def enrich_with_details(listings):
    enriched = []

    for idx, item in enumerate(listings):
        new_item = dict(item)

        if idx < MAX_DETAIL_PAGES and item.get("url"):
            detail = fetch_detail_data(item.get("url"))
            detail_text = detail.get("detail_text") or ""

            if new_item.get("miles") is None and detail.get("detail_miles"):
                new_item["miles"] = detail.get("detail_miles")

            if new_item.get("year") is None and detail.get("detail_year"):
                new_item["year"] = detail.get("detail_year")

            if new_item.get("price") is None and detail.get("detail_price"):
                new_item["price"] = detail.get("detail_price")

            new_item["full_text"] = clean_text(
                f"{new_item.get('title', '')} {new_item.get('raw_text', '')} {detail_text}"
            )
        else:
            new_item["full_text"] = clean_text(
                f"{new_item.get('title', '')} {new_item.get('raw_text', '')}"
            )

        if new_item.get("miles") is None:
            new_item["miles"] = parse_miles(new_item.get("full_text", ""))

        enriched.append(new_item)

    return enriched


@st.cache_data(ttl=300, show_spinner=False)
def fetch_craigslist():
    html_url = craigslist_search_url(format_rss=False)
    rss_url = craigslist_search_url(format_rss=True)

    errors = []

    try:
        html = request_page(html_url)
        listings = parse_craigslist_html(html)
        if listings:
            listings = enrich_with_details(listings)
            return listings, html_url, None
    except Exception as e:
        errors.append(f"HTML failed: {e}")

    try:
        rss = request_page(rss_url)
        listings = parse_craigslist_rss(rss)
        if listings:
            listings = enrich_with_details(listings)
            return listings, rss_url, None
    except Exception as e:
        errors.append(f"RSS failed: {e}")

    return [], html_url, "Craigslist blocked the Streamlit server. This is usually a Craigslist 403 block, not a Python crash."


def parse_craigslist_html(html):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    cards = soup.select("li.cl-search-result, li.result-row, div.result-info, ol li")

    for card in cards:
        raw_text = clean_text(card.get_text(" ", strip=True))
        if not raw_text:
            continue

        a = card.select_one("a[href]")
        if not a:
            continue

        url = a.get("href")
        if url and url.startswith("/"):
            url = "https://saltlakecity.craigslist.org" + url

        title = clean_text(a.get_text(" ", strip=True))
        if len(title) < 5:
            title = raw_text[:100]

        price = None
        price_el = card.select_one(".price")

        if price_el:
            price = parse_price(price_el.get_text())

        if price is None:
            price = parse_price(raw_text)

        year = parse_year(title) or parse_year(raw_text)
        miles = parse_miles(raw_text)

        if not price:
            continue

        results.append({
            "title": title,
            "price": price,
            "year": year,
            "miles": miles,
            "url": url,
            "source": "Craigslist",
            "raw_text": raw_text,
        })

    return dedupe_listings(results)


def parse_craigslist_rss(xml_text):
    soup = BeautifulSoup(xml_text, "xml")
    results = []

    for item in soup.find_all("item"):
        title = clean_text(item.title.get_text()) if item.title else ""
        link = clean_text(item.link.get_text()) if item.link else ""
        desc = clean_text(item.description.get_text()) if item.description else ""

        full_text = clean_text(f"{title} {desc}")
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
            "source": "Craigslist RSS",
            "raw_text": full_text,
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
    "<div class='info-box'>App scans automatically. BUY cars show first. High-mileage cars are forced to WATCH or REJECT until checked.</div>",
    unsafe_allow_html=True
)

if st.button("Refresh Scan"):
    st.cache_data.clear()
    st.rerun()

with st.spinner("Scanning listings and checking detail pages..."):
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

    try:
        return f"${int(x):,}"
    except Exception:
        return "Unknown"


def miles_fmt(x):
    if x is None:
        return "Unknown"

    try:
        return f"{int(x):,}"
    except Exception:
        return "Unknown"


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

    title = escape(car.get("title") or "Untitled listing")
    url = escape(car.get("url") or "#")
    reasons = escape(car.get("reasons", ""))

    links = comparison_links(car)

    comp_html = ""
    for name, link in links.items():
        comp_html += f'<a href="{escape(link)}" target="_blank">{escape(name)}</a>'

    st.markdown(f"""
    <div class="{cls}">
        <div class="{badge}">{decision} · SCORE {car.get("score", 0)}/100 · RISK {escape(car.get("risk", "UNK"))}</div>
        <div class="car-title"><a href="{url}" target="_blank">{title}</a></div>

        <div class="metric">Ask Price: <b>{money(car.get("price"))}</b></div>
        <div class="metric">Estimated Retail/Market: <b>{money(car.get("market_value"))}</b></div>
        <div class="metric">Estimated Recon: <b>{money(car.get("recon"))}</b></div>
        <div class="metric">Target Buy Price for $2,000 profit: <b>{money(car.get("target_buy"))}</b></div>
        <div class="metric">Estimated Profit at Ask: <b>{money(car.get("estimated_profit"))}</b></div>
        <div class="metric">Year: <b>{car.get("year") or "Unknown"}</b> · Miles: <b>{miles_fmt(car.get("miles"))}</b></div>

        <div class="reason">{reasons}</div>

        <div class="comp-links">
            {comp_html}
        </div>
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
