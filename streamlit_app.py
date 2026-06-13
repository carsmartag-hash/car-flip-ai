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
    padding-top: 1.1rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    max-width: 760px !important;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

h1 {
    font-size: 2.7rem !important;
    line-height: 1.05 !important;
    margin-bottom: 0.25rem !important;
}

.sub {
    color: #a1a1aa;
    font-size: 1rem;
    margin-bottom: 1.2rem;
}

.stButton > button {
    width: 100%;
    border-radius: 14px;
    font-weight: 800;
    padding: 0.75rem 1rem;
}

.car-card {
    border: 1px solid rgba(255,255,255,0.16);
    border-radius: 18px;
    padding: 16px;
    margin-bottom: 18px;
    background: rgba(255,255,255,0.045);
}

.car-title {
    font-size: 1.25rem;
    font-weight: 900;
    margin-bottom: 6px;
}

.price {
    font-size: 1.1rem;
    font-weight: 900;
}

.good {
    color: #22c55e;
    font-weight: 900;
}

.warn {
    color: #facc15;
    font-weight: 900;
}

.bad {
    color: #ef4444;
    font-weight: 900;
}

.small {
    color: #a1a1aa;
    font-size: 0.9rem;
}

.link-row a {
    display: inline-block;
    margin: 6px 6px 0 0;
    padding: 8px 10px;
    border-radius: 10px;
    background: rgba(255,255,255,0.10);
    color: white !important;
    text-decoration: none;
    font-weight: 800;
    font-size: 0.88rem;
}

.error-box {
    background: rgba(239, 68, 68, 0.20);
    border: 1px solid rgba(239, 68, 68, 0.35);
    color: #fecaca;
    padding: 14px;
    border-radius: 14px;
    margin: 16px 0;
}

.info-box {
    background: rgba(250, 204, 21, 0.16);
    border: 1px solid rgba(250, 204, 21, 0.28);
    color: #fef3c7;
    padding: 14px;
    border-radius: 14px;
    margin: 16px 0;
}

.success-box {
    background: rgba(34, 197, 94, 0.14);
    border: 1px solid rgba(34, 197, 94, 0.28);
    color: #bbf7d0;
    padding: 14px;
    border-radius: 14px;
    margin: 16px 0;
}
</style>
""", unsafe_allow_html=True)


# =========================
# HELPERS
# =========================

def clean_text(x):
    if not x:
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()


def money(n):
    try:
        return f"${int(n):,}"
    except Exception:
        return "$0"


def extract_price(text):
    if not text:
        return None
    m = re.search(r"\$[\s]*([0-9,]+)", text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except Exception:
        return None


def extract_year(text):
    if not text:
        return None
    m = re.search(r"\b(200[6-9]|201[0-9]|202[0-6])\b", text)
    if not m:
        return None
    return int(m.group(1))


def extract_mileage(text):
    if not text:
        return None

    text_l = text.lower()

    patterns = [
        r"([0-9]{2,3})\s*k\s*(?:miles|mi)?",
        r"([0-9]{2,3},[0-9]{3})\s*(?:miles|mi)",
        r"([0-9]{5,6})\s*(?:miles|mi)",
        r"mileage[:\s]+([0-9,]{5,6})",
        r"odometer[:\s]+([0-9,]{5,6})",
    ]

    for p in patterns:
        m = re.search(p, text_l)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                val = int(raw)
                if val < 1000:
                    val *= 1000
                if 20_000 <= val <= 350_000:
                    return val
            except Exception:
                pass

    return None


def make_search_query(title):
    title = clean_text(title)
    title = re.sub(r"\$[0-9,]+", "", title)
    title = re.sub(r"\bfor sale\b", "", title, flags=re.I)
    return clean_text(title)


def kbb_link(title):
    q = quote_plus(make_search_query(title))
    return f"https://www.kbb.com/cars-for-sale/all/?searchText={q}"


def cars_com_link(title):
    q = quote_plus(make_search_query(title))
    return f"https://www.cars.com/shopping/results/?keyword={q}&maximum_distance=100&zip=84107"


def cargurus_link(title):
    q = quote_plus(make_search_query(title))
    return f"https://www.cargurus.com/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action?zip=84107&distance=100&entitySelectingHelper.selectedEntity=d&sourceContext=carGurusHomePage_false_0&newUsed=3&searchChanged=true&keywords={q}"


def craigslist_manual_link(max_price, min_year, distance, postal, owner_only=True):
    params = {
        "search_distance": distance,
        "postal": postal,
        "auto_title_status": 1,
        "min_auto_year": min_year,
        "max_price": max_price,
        "sort": "date",
    }

    if owner_only:
        params["purveyor"] = "owner"

    return "https://saltlakecity.craigslist.org/search/cta?" + urlencode(params)


def craigslist_rss_link(max_price, min_year, distance, postal, owner_only=True):
    params = {
        "format": "rss",
        "search_distance": distance,
        "postal": postal,
        "auto_title_status": 1,
        "min_auto_year": min_year,
        "max_price": max_price,
        "sort": "date",
    }

    if owner_only:
        params["purveyor"] = "owner"

    return "https://saltlakecity.craigslist.org/search/cta?" + urlencode(params)


def estimate_market_value(year, price, mileage, title):
    """
    Rough internal estimate only.
    Real comparison buttons are included for KBB, Cars.com, and CarGurus.
    """

    if not year or not price:
        return None

    age = max(1, datetime.now().year - year)

    base = 19000 - (age * 900)

    if mileage:
        if mileage < 80_000:
            base += 1800
        elif mileage < 120_000:
            base += 500
        elif mileage < 160_000:
            base -= 700
        elif mileage < 210_000:
            base -= 1800
        else:
            base -= 3200
    else:
        base -= 900

    title_l = title.lower()

    premium_words = [
        "toyota", "lexus", "honda", "acura", "tacoma", "4runner",
        "rav4", "camry", "accord", "civic", "cr-v", "crv", "pilot",
        "highlander", "subaru", "wrangler", "tundra", "sequoia"
    ]

    risk_words = [
        "bmw", "audi", "mini", "mercedes", "volkswagen", "vw",
        "range rover", "land rover", "jaguar", "turbo", "mechanic",
        "needs", "salvage", "rebuilt", "not running", "transmission",
        "engine problem"
    ]

    for w in premium_words:
        if w in title_l:
            base += 1200
            break

    for w in risk_words:
        if w in title_l:
            base -= 1600
            break

    return max(1500, int(base))


def flip_score(price, market, mileage, title):
    if not price or not market:
        return 0, "Bad"

    profit = market - price

    score = 50

    if profit >= 3500:
        score += 30
    elif profit >= 2500:
        score += 22
    elif profit >= 1800:
        score += 12
    elif profit >= 1000:
        score += 5
    else:
        score -= 20

    if mileage:
        if mileage <= 120_000:
            score += 10
        elif mileage <= 170_000:
            score += 2
        elif mileage > 210_000:
            score -= 18
    else:
        score -= 7

    risky = ["salvage", "rebuilt", "not running", "mechanic", "transmission", "engine problem", "overheating"]
    if any(w in title.lower() for w in risky):
        score -= 25

    score = max(0, min(100, score))

    if score >= 78:
        label = "Strong Buy"
    elif score >= 63:
        label = "Possible Buy"
    elif score >= 48:
        label = "Check Carefully"
    else:
        label = "Skip"

    return score, label


def fetch_craigslist_rss(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml, text/html,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://saltlakecity.craigslist.org/",
    }

    r = requests.get(url, headers=headers, timeout=18)

    if r.status_code == 403:
        raise PermissionError("Craigslist blocked Streamlit Cloud with 403 Forbidden.")

    r.raise_for_status()
    return r.text


def parse_rss(xml_text):
    soup = BeautifulSoup(xml_text, "xml")
    items = soup.find_all("item")

    rows = []

    for item in items:
        title = clean_text(item.title.get_text() if item.title else "")
        link = clean_text(item.link.get_text() if item.link else "")
        desc = clean_text(item.description.get_text(" ") if item.description else "")

        price = extract_price(title) or extract_price(desc)
        year = extract_year(title) or extract_year(desc)
        mileage = extract_mileage(title + " " + desc)

        if not title or not link:
            continue

        rows.append({
            "title": title,
            "link": link,
            "price": price,
            "year": year,
            "mileage": mileage,
            "description": desc,
        })

    return rows


def dedupe(rows):
    seen = set()
    out = []

    for r in rows:
        key = hashlib.md5((r.get("title", "") + r.get("link", "")).encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)

    return out


# =========================
# UI
# =========================

st.markdown("# 🚗 Car Flip AI")
st.markdown(
    '<div class="sub">Salt Lake City private-party scanner with KBB, Cars.com, and CarGurus comparison links.</div>',
    unsafe_allow_html=True
)

with st.expander("Filters", expanded=False):
    postal = st.text_input("ZIP", value="84107")
    distance = st.slider("Search radius", 10, 120, 90, 5)
    max_price = st.slider("Max price", 1000, 30000, 15000, 500)
    min_year = st.slider("Minimum year", 1998, 2026, 2006, 1)
    min_profit = st.slider("Minimum estimated profit", 500, 6000, 2000, 250)
    max_mileage = st.slider("Max mileage", 50000, 300000, 210000, 5000)
    allow_missing_mileage = st.checkbox("Allow listings with missing mileage", value=True)
    owner_only = st.checkbox("Private-party / owner only", value=True)

scan = st.button("Scan Craigslist")

manual_url = craigslist_manual_link(max_price, min_year, distance, postal, owner_only)
rss_url = craigslist_rss_link(max_price, min_year, distance, postal, owner_only)

st.markdown(
    f"""
    <div class="link-row">
        <a href="{manual_url}" target="_blank">Open Craigslist Search</a>
    </div>
    """,
    unsafe_allow_html=True
)

if scan:
    rows = []

    try:
        xml = fetch_craigslist_rss(rss_url)
        rows = parse_rss(xml)
        rows = dedupe(rows)

        st.markdown(
            '<div class="success-box">Craigslist scan completed.</div>',
            unsafe_allow_html=True
        )

    except PermissionError as e:
        st.markdown(
            f"""
            <div class="error-box">
                <b>Craigslist blocked the cloud scanner.</b><br><br>
                This happens because the app is running on Streamlit Cloud, not directly from your phone.
                Craigslist returns <b>403 Forbidden</b> to many hosted/cloud servers.<br><br>
                Use the <b>Open Craigslist Search</b> button above for now. The comparison buttons below still work
                when listings are loaded.
            </div>
            """,
            unsafe_allow_html=True
        )

    except Exception as e:
        st.markdown(
            f"""
            <div class="error-box">
                Craigslist fetch failed:<br>
                {clean_text(str(e))}
            </div>
            """,
            unsafe_allow_html=True
        )

    filtered = []

    for r in rows:
        price = r.get("price")
        year = r.get("year")
        mileage = r.get("mileage")
        title = r.get("title", "")

        if not price:
            continue

        if price > max_price:
            continue

        if year and year < min_year:
            continue

        if mileage:
            if mileage > max_mileage:
                continue
        else:
            if not allow_missing_mileage:
                continue

        market = estimate_market_value(year, price, mileage, title)
        if not market:
            continue

        profit = market - price

        if profit < min_profit:
            continue

        score, label = flip_score(price, market, mileage, title)

        r["market"] = market
        r["profit"] = profit
        r["score"] = score
        r["label"] = label

        filtered.append(r)

    filtered = sorted(filtered, key=lambda x: (x["score"], x["profit"]), reverse=True)

    st.markdown(f"### Found {len(filtered)} possible cars")

    if not filtered:
        st.markdown(
            """
            <div class="info-box">
                No cars found with your filters. If Craigslist is showing 403, the problem is not your filters.
                It means Craigslist blocked the Streamlit Cloud server.
            </div>
            """,
            unsafe_allow_html=True
        )

    for r in filtered:
        title = r["title"]
        link = r["link"]
        price = r["price"]
        year = r["year"] or "Unknown"
        mileage = r["mileage"]
        market = r["market"]
        profit = r["profit"]
        score = r["score"]
        label = r["label"]

        if label == "Strong Buy":
            cls = "good"
        elif label in ["Possible Buy", "Check Carefully"]:
            cls = "warn"
        else:
            cls = "bad"

        mileage_text = f"{mileage:,} miles" if mileage else "Mileage missing"

        st.markdown(
            f"""
            <div class="car-card">
                <div class="car-title">{title}</div>
                <div class="price">Ask: {money(price)}</div>
                <div>Year: <b>{year}</b></div>
                <div>Mileage: <b>{mileage_text}</b></div>
                <div>Estimated market: <b>{money(market)}</b></div>
                <div>Estimated profit: <b>{money(profit)}</b></div>
                <div>Flip score: <span class="{cls}">{score}/100 — {label}</span></div>

                <div class="link-row">
                    <a href="{link}" target="_blank">Craigslist</a>
                    <a href="{kbb_link(title)}" target="_blank">KBB</a>
                    <a href="{cars_com_link(title)}" target="_blank">Cars.com</a>
                    <a href="{cargurus_link(title)}" target="_blank">CarGurus</a>
                </div>

                <div class="small">
                    Verify VIN, title, mileage, KBB, Cars.com, CarGurus, emissions, and mechanical condition before buying.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

st.markdown(
    """
    <div class="small">
        Values are rough estimates. Always verify VIN, title status, mileage, KBB, Cars.com, CarGurus,
        and mechanical condition before buying.
    </div>
    """,
    unsafe_allow_html=True
)
