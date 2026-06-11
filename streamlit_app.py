import re
import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import urlencode

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
    font-size: 2.9rem !important;
    line-height: 1.05 !important;
    margin-bottom: 0.2rem !important;
}

.stButton > button {
    width: 100%;
    border-radius: 14px;
    font-weight: 800;
    padding: 0.75rem 1rem;
}

.car-card {
    border: 1px solid rgba(250,250,250,0.18);
    border-radius: 18px;
    padding: 16px;
    margin-bottom: 14px;
    background: rgba(255,255,255,0.045);
}

.good { color: #2ecc71; font-weight: 900; }
.mid { color: #f1c40f; font-weight: 900; }
.bad { color: #ff6b6b; font-weight: 900; }
.small-muted { color: rgba(250,250,250,0.65); font-size: 0.92rem; }

@media (max-width: 480px) {
    h1 { font-size: 2.55rem !important; }
    .block-container {
        padding-left: 0.85rem !important;
        padding-right: 0.85rem !important;
    }
}
</style>
""", unsafe_allow_html=True)

MARKETS = {
    "Salt Lake City Metro, UT": {
        "site": "saltlakecity",
        "postal": "84101",
        "distance": 85
    },
    "Ogden, UT": {
        "site": "ogden",
        "postal": "84401",
        "distance": 55
    },
    "Provo / Orem, UT": {
        "site": "provo",
        "postal": "84601",
        "distance": 55
    },
    "Columbus, OH": {
        "site": "columbus",
        "postal": "43082",
        "distance": 50
    }
}

BAD_KEYWORDS = [
    "parts only", "mechanic special", "does not run", "not running",
    "no title", "salvage parts", "blown", "bad transmission",
    "bad engine", "needs engine", "needs transmission", "project car",
    "camper", "rv", "motorhome", "box truck", "semi", "trailer"
]

GOOD_KEYWORDS = [
    "clean title", "new tires", "new brakes", "runs good", "runs great",
    "no issues", "cold ac", "one owner", "well maintained"
]

BRAND_RISK = {
    "toyota": 1, "honda": 1, "lexus": 1, "acura": 1,
    "mazda": 2,
    "subaru": 3, "ford": 3, "chevy": 3, "chevrolet": 3,
    "gmc": 3, "hyundai": 3, "kia": 3,
    "nissan": 4, "infiniti": 4, "cadillac": 4, "volvo": 4,
    "bmw": 5, "mercedes": 5, "audi": 5, "volkswagen": 5,
    "vw": 5, "mini": 5, "chrysler": 5, "dodge": 5,
    "jeep": 5, "fiat": 5, "land rover": 5, "jaguar": 5
}

def clean_text(x):
    if not x:
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()

def money(x):
    try:
        return f"${int(x):,}"
    except Exception:
        return "$0"

def extract_year(title):
    match = re.search(r"\b(19[8-9]\d|20[0-2]\d)\b", title)
    return int(match.group(1)) if match else None

def guess_make(title):
    text = title.lower()
    for make in BRAND_RISK.keys():
        if make in text:
            return make
    return "unknown"

def brand_risk_score(title):
    return BRAND_RISK.get(guess_make(title), 3)

def estimate_retail_value(title, price, miles):
    year = extract_year(title)
    risk = brand_risk_score(title)

    if not price:
        return 0

    markup = 1.28

    if risk == 1:
        markup += 0.13
    elif risk == 2:
        markup += 0.08
    elif risk == 4:
        markup -= 0.08
    elif risk == 5:
        markup -= 0.15

    if miles:
        if miles < 80000:
            markup += 0.13
        elif miles < 120000:
            markup += 0.06
        elif miles > 170000:
            markup -= 0.20
        elif miles > 140000:
            markup -= 0.10

    if year:
        if year >= 2016:
            markup += 0.08
        elif year <= 2007:
            markup -= 0.10

    retail = int(price * markup)

    if risk <= 2:
        retail += 700
    elif risk >= 5:
        retail -= 500

    return max(retail, price)

def estimate_recon(title, miles):
    text = title.lower()
    recon = 700

    if miles and miles > 150000:
        recon += 500
    elif miles and miles > 120000:
        recon += 300

    if any(word in text for word in ["bmw", "mercedes", "audi", "mini", "volkswagen", "vw"]):
        recon += 700

    if any(word in text for word in ["needs", "check engine", "abs", "misfire", "overheating", "leak"]):
        recon += 900

    if any(word in text for word in ["new tires", "new brakes", "serviced", "maintenance"]):
        recon -= 200

    return max(recon, 400)

def deal_score(title, price, miles, target_profit):
    retail = estimate_retail_value(title, price, miles)
    recon = estimate_recon(title, miles)
    fees = 350
    profit = retail - price - recon - fees
    risk = brand_risk_score(title)
    text = title.lower()

    penalty = 0
    if any(k in text for k in BAD_KEYWORDS):
        penalty += 35
    if miles and miles > 160000:
        penalty += 15
    if risk >= 5:
        penalty += 15

    bonus = 0
    if any(k in text for k in GOOD_KEYWORDS):
        bonus += 8
    if profit >= target_profit:
        bonus += 25
    if profit >= target_profit + 1500:
        bonus += 15

    score = max(0, min(100, 50 + bonus - penalty))

    if profit < 500:
        score -= 25
    elif profit < target_profit:
        score -= 12

    score = max(0, min(100, score))

    if score >= 75 and profit >= target_profit:
        verdict = "BUY"
    elif score >= 58 and profit >= 1000:
        verdict = "MAYBE"
    else:
        verdict = "SKIP"

    if risk <= 2:
        risk_label = "Low"
    elif risk == 3:
        risk_label = "Medium"
    else:
        risk_label = "High"

    return {
        "retail": retail,
        "recon": recon,
        "fees": fees,
        "profit": profit,
        "score": score,
        "verdict": verdict,
        "risk": risk_label
    }

def craigslist_url(site, postal, distance, min_price, max_price, max_miles):
    params = {
        "min_price": int(min_price),
        "max_price": int(max_price),
        "search_distance": int(distance),
        "postal": postal,
        "bundleDuplicates": 1,
        "sort": "date"
    }

    if max_miles:
        params["max_auto_miles"] = int(max_miles)

    return f"https://{site}.craigslist.org/search/cto?" + urlencode(params)

def parse_price(text):
    if not text:
        return None
    match = re.search(r"\$?([\d,]+)", text)
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except Exception:
        return None

def parse_miles_from_text(text):
    if not text:
        return None

    text = text.lower().replace(",", "")

    patterns = [
        r"\b(\d{2,3})k\s*miles\b",
        r"\b(\d{2,3})k\s*mi\b",
        r"\b(\d{5,6})\s*miles\b",
        r"\b(\d{5,6})\s*mi\b"
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            miles = int(match.group(1))
            if "k" in pattern:
                miles *= 1000
            return miles

    return None

@st.cache_data(ttl=300, show_spinner=False)
def fetch_craigslist(site, postal, distance, min_price, max_price, max_miles):
    url = craigslist_url(site, postal, distance, min_price, max_price, max_miles)

    headers = {
        "User-Agent": "Mozilla/5.0 AppleWebKit/605.1.15 Mobile Safari/604.1"
    }

    response = requests.get(url, headers=headers, timeout=18)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    items = soup.select("li.cl-search-result, li.result-row, .cl-static-search-result")

    rows = []

    for item in items:
        title_el = item.select_one(".titlestring") or item.select_one(".label") or item.select_one("a")
        price_el = item.select_one(".priceinfo") or item.select_one(".result-price") or item.select_one(".price")
        link_el = item.select_one("a")
        location_el = item.select_one(".location")

        title = clean_text(title_el.get_text(" ")) if title_el else ""
        price_text = clean_text(price_el.get_text(" ")) if price_el else ""
        price = parse_price(price_text)

        link = ""
        if link_el and link_el.get("href"):
            link = link_el.get("href")
            if link.startswith("/"):
                link = f"https://{site}.craigslist.org{link}"

        location = clean_text(location_el.get_text(" ")) if location_el else ""
        full_text = clean_text(item.get_text(" "))
        miles = parse_miles_from_text(full_text)

        if not title or not price:
            continue

        if any(k in title.lower() for k in BAD_KEYWORDS):
            continue

        rows.append({
            "title": title,
            "price": price,
            "miles": miles,
            "location": location,
            "link": link
        })

    return rows, url

def value_research_links(title):
    q = title.replace(" ", "+")
    return {
        "KBB": f"https://www.kbb.com/cars-for-sale/all/{q}/",
        "Cars.com": f"https://www.cars.com/shopping/results/?keyword={q}",
        "CarGurus": f"https://www.cargurus.com/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action?search={q}"
    }

st.title("Car Flip AI")
st.caption("Mobile Craigslist private-party scanner")

st.subheader("Settings")

market_name = st.selectbox(
    "Market",
    list(MARKETS.keys()),
    index=0
)

market = MARKETS[market_name]

max_miles = st.number_input(
    "Max Mileage",
    min_value=30000,
    max_value=300000,
    value=130000,
    step=5000
)

min_price = st.number_input(
    "Min Price",
    min_value=0,
    max_value=50000,
    value=1000,
    step=500
)

max_price = st.number_input(
    "Max Price",
    min_value=1000,
    max_value=50000,
    value=12000,
    step=500
)

target_profit = st.number_input(
    "Target Profit",
    min_value=500,
    max_value=10000,
    value=2000,
    step=500
)

st.caption(
    f"Current search: {market_name} | {market['distance']} miles from ZIP {market['postal']} | owner-only Craigslist"
)

scan = st.button("Scan Craigslist")

if scan:
    if min_price >= max_price:
        st.error("Min Price must be lower than Max Price.")
        st.stop()

    with st.spinner("Scanning Craigslist owner listings..."):
        try:
            listings, source_url = fetch_craigslist(
                market["site"],
                market["postal"],
                market["distance"],
                min_price,
                max_price,
                max_miles
            )
        except Exception as e:
            st.error("Craigslist scan failed.")
            st.code(str(e))
            st.stop()

    st.success(f"Found {len(listings)} owner listings")
    st.markdown(f"[Open Craigslist search]({source_url})")

    if not listings:
        st.warning("No listings found with these filters. Raise max price or mileage.")
        st.stop()

    scored = []

    for car in listings:
        result = deal_score(
            car["title"],
            car["price"],
            car.get("miles"),
            target_profit
        )
        scored.append({**car, **result})

    df = pd.DataFrame(scored)

    verdict_rank = {"BUY": 0, "MAYBE": 1, "SKIP": 2}
    df["rank"] = df["verdict"].map(verdict_rank)
    df = df.sort_values(by=["rank", "profit", "score"], ascending=[True, False, False])

    buy_count = int((df["verdict"] == "BUY").sum())
    maybe_count = int((df["verdict"] == "MAYBE").sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("BUY", buy_count)
    c2.metric("MAYBE", maybe_count)
    c3.metric("Listings", len(df))

    st.subheader("Best Deals")

    for _, row in df.head(40).iterrows():
        verdict = row["verdict"]
        css = "good" if verdict == "BUY" else "mid" if verdict == "MAYBE" else "bad"
        miles_text = "Unknown" if pd.isna(row["miles"]) else f"{int(row['miles']):,}"

        st.markdown(
            f"""
            <div class="car-card">
                <div class="{css}" style="font-size:1.35rem;">{verdict} — Score {int(row['score'])}/100</div>
                <h3 style="margin-bottom:0.25rem;">{row['title']}</h3>
                <div class="small-muted">{row.get('location', '')}</div>
                <br>
                <b>Ask:</b> {money(row['price'])}<br>
                <b>Miles:</b> {miles_text}<br>
                <b>Estimated Retail:</b> {money(row['retail'])}<br>
                <b>Estimated Recon:</b> {money(row['recon'])}<br>
                <b>Estimated Profit:</b> {money(row['profit'])}<br>
                <b>Risk:</b> {row['risk']}<br>
            </div>
            """,
            unsafe_allow_html=True
        )

        if row["link"]:
            st.markdown(f"[Open Listing]({row['link']})")

        links = value_research_links(row["title"])
        st.markdown(
            f"[KBB research]({links['KBB']}) | [Cars.com comps]({links['Cars.com']}) | [CarGurus comps]({links['CarGurus']})"
        )

        st.divider()

else:
    st.info("Set filters, then tap **Scan Craigslist**.")
