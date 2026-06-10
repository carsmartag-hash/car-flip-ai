import re
import time
import math
import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

# ==========================================================
# CAR FLIP AI - Craigslist Streamlit App
# Works on Streamlit Cloud / GitHub / iPhone
# ==========================================================

st.set_page_config(
    page_title="Car Flip AI",
    page_icon="🚗",
    layout="wide"
)

# -----------------------------
# SETTINGS
# -----------------------------

CRAIGSLIST_SITES = {
    "Salt Lake City": "saltlakecity",
    "Provo / Orem": "provo",
    "Ogden": "ogden",
    "Logan": "logan",
    "St George": "stgeorge",
    "Boise": "boise",
    "Las Vegas": "lasvegas",
    "Denver": "denver",
    "Columbus OH": "columbus",
}

GOOD_WORDS = [
    "clean title", "one owner", "no accidents", "runs great", "runs good",
    "must sell", "need gone", "priced to sell", "well maintained",
    "new tires", "new battery", "cold ac", "smog", "emissions",
    "low miles", "garage kept", "dealer maintained"
]

BAD_WORDS = [
    "salvage", "rebuilt", "branded title", "mechanic special", "parts only",
    "does not run", "not running", "blown", "bad engine", "bad transmission",
    "transmission slipping", "overheating", "head gasket", "no title",
    "lien", "flood", "totaled", "needs motor", "needs transmission"
]

HOT_BRANDS = [
    "toyota", "honda", "lexus", "acura", "subaru", "mazda",
    "ford", "chevy", "chevrolet", "gmc", "nissan", "hyundai", "kia"
]

RISKY_BRANDS_MODELS = [
    "bmw", "audi", "mercedes", "mini", "volkswagen", "vw",
    "range rover", "land rover", "jaguar", "maserati",
    "fiat", "chrysler 200", "dodge dart"
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    )
}


# -----------------------------
# HELPER FUNCTIONS
# -----------------------------

def safe_int(value):
    if value is None:
        return None
    value = str(value)
    value = re.sub(r"[^\d]", "", value)
    if value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def extract_year(text):
    match = re.search(r"\b(199[0-9]|20[0-2][0-9]|2030)\b", text)
    if match:
        return int(match.group(1))
    return None


def estimate_market_value(title, price, year):
    """
    Simple conservative market estimate.
    This is not KBB. It is a quick flipping estimate.
    """
    if not price:
        return None

    title_lower = title.lower()
    multiplier = 1.25

    if any(word in title_lower for word in ["toyota", "honda", "lexus"]):
        multiplier = 1.35
    elif any(word in title_lower for word in ["acura", "subaru", "mazda"]):
        multiplier = 1.30
    elif any(word in title_lower for word in ["ford", "chevy", "chevrolet", "gmc"]):
        multiplier = 1.22
    elif any(word in title_lower for word in ["bmw", "audi", "mercedes"]):
        multiplier = 1.18

    if year:
        age = 2026 - year
        if age <= 6:
            multiplier += 0.05
        elif age >= 18:
            multiplier -= 0.05

    market_value = int(price * multiplier)
    return market_value


def calculate_target_offer(price, market_value, min_profit):
    if not price or not market_value:
        return None

    recon_buffer = 800
    selling_cost_buffer = 300
    target_offer = market_value - min_profit - recon_buffer - selling_cost_buffer

    if target_offer < 500:
        target_offer = int(price * 0.60)

    return max(500, int(target_offer))


def calculate_profit(market_value, target_offer):
    if not market_value or not target_offer:
        return None

    recon_buffer = 800
    selling_cost_buffer = 300
    return int(market_value - target_offer - recon_buffer - selling_cost_buffer)


def calculate_risk(title, price, year):
    text = title.lower()
    risk_points = 0
    reasons = []

    if any(word in text for word in BAD_WORDS):
        risk_points += 40
        reasons.append("bad keyword")

    if any(word in text for word in RISKY_BRANDS_MODELS):
        risk_points += 25
        reasons.append("higher repair risk")

    if year:
        age = 2026 - year
        if age >= 18:
            risk_points += 15
            reasons.append("older vehicle")
        elif age <= 8:
            risk_points -= 5

    if price and price < 1500:
        risk_points += 20
        reasons.append("very cheap")
    elif price and price > 15000:
        risk_points += 10
        reasons.append("higher capital needed")

    if risk_points >= 45:
        return "High"
    elif risk_points >= 20:
        return "Medium"
    return "Low"


def calculate_flip_score(title, price, market_value, estimated_profit, risk):
    score = 0
    text = title.lower()

    if estimated_profit:
        score += min(50, estimated_profit / 100)

    if any(word in text for word in GOOD_WORDS):
        score += 15

    if any(word in text for word in HOT_BRANDS):
        score += 10

    if risk == "Low":
        score += 15
    elif risk == "Medium":
        score += 5
    else:
        score -= 20

    if price:
        if 1500 <= price <= 9000:
            score += 15
        elif price > 15000:
            score -= 10

    return int(max(0, min(100, score)))


def risk_badge(risk):
    if risk == "Low":
        return "🟢 Low"
    if risk == "Medium":
        return "🟡 Medium"
    return "🔴 High"


def craigslist_search(site_key, query, min_price, max_price, max_results):
    site = CRAIGSLIST_SITES[site_key]
    encoded_query = quote_plus(query)

    url = (
        f"https://{site}.craigslist.org/search/cta"
        f"?query={encoded_query}"
        f"&min_price={min_price}"
        f"&max_price={max_price}"
        f"&bundleDuplicates=1"
        f"&sort=date"
    )

    results = []

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        return results, f"Could not load Craigslist: {e}"

    soup = BeautifulSoup(response.text, "html.parser")

    listings = soup.select("li.cl-static-search-result")
    if not listings:
        listings = soup.select(".result-row")

    for item in listings[:max_results]:
        title = ""
        price = None
        link = ""

        title_tag = item.select_one(".title")
        price_tag = item.select_one(".price")
        link_tag = item.select_one("a")

        if title_tag:
            title = title_tag.get_text(" ", strip=True)

        if price_tag:
            price = safe_int(price_tag.get_text(" ", strip=True))

        if link_tag and link_tag.get("href"):
            link = link_tag.get("href")

        if not title or not price:
            continue

        year = extract_year(title)
        market_value = estimate_market_value(title, price, year)
        risk = calculate_risk(title, price, year)

        results.append({
            "Title": title,
            "Year": year,
            "Price": price,
            "Estimated Market": market_value,
            "Risk": risk,
            "Link": link,
            "Source": site_key
        })

    return results, None


def build_deal_rows(raw_results, min_profit):
    deals = []

    for item in raw_results:
        title = item["Title"]
        price = item["Price"]
        year = item["Year"]
        market_value = item["Estimated Market"]

        target_offer = calculate_target_offer(price, market_value, min_profit)
        estimated_profit = calculate_profit(market_value, target_offer)
        risk = item["Risk"]
        flip_score = calculate_flip_score(title, price, market_value, estimated_profit, risk)

        if estimated_profit is None:
            continue

        if estimated_profit < min_profit:
            continue

        deals.append({
            "Flip Score": flip_score,
            "Title": title,
            "Year": year if year else "",
            "Price": price,
            "Estimated Market": market_value,
            "Target Offer": target_offer,
            "Estimated Profit": estimated_profit,
            "Risk": risk,
            "Source": item["Source"],
            "Link": item["Link"]
        })

    deals = sorted(deals, key=lambda x: x["Flip Score"], reverse=True)
    return deals


# -----------------------------
# APP UI
# -----------------------------

st.title("🚗 Car Flip AI")
st.caption("Craigslist private-party deal scanner with target offer, estimated profit, risk, and flip score.")

with st.sidebar:
    st.header("Search Settings")

    selected_sites = st.multiselect(
        "Craigslist areas",
        list(CRAIGSLIST_SITES.keys()),
        default=["Salt Lake City", "Provo / Orem", "Ogden"]
    )

    search_query = st.text_input(
        "Search words",
        value="clean title"
    )

    col1, col2 = st.columns(2)

    with col1:
        min_price = st.number_input(
            "Min price",
            min_value=0,
            max_value=100000,
            value=1000,
            step=500
        )

    with col2:
        max_price = st.number_input(
            "Max price",
            min_value=1000,
            max_value=100000,
            value=12000,
            step=500
        )

    min_profit = st.number_input(
        "Minimum profit",
        min_value=500,
        max_value=10000,
        value=2000,
        step=250
    )

    max_results_per_city = st.slider(
        "Results per area",
        min_value=5,
        max_value=50,
        value=25
    )

    scan_button = st.button("Scan Craigslist", type="primary", use_container_width=True)


# -----------------------------
# RUN SCAN
# -----------------------------

if scan_button:
    if not selected_sites:
        st.warning("Choose at least one Craigslist area.")
        st.stop()

    all_raw_results = []
    errors = []

    progress = st.progress(0)
    status = st.empty()

    for index, site_key in enumerate(selected_sites):
        status.write(f"Scanning {site_key}...")
        city_results, error = craigslist_search(
            site_key=site_key,
            query=search_query,
            min_price=min_price,
            max_price=max_price,
            max_results=max_results_per_city
        )

        if error:
            errors.append(f"{site_key}: {error}")

        all_raw_results.extend(city_results)
        progress.progress((index + 1) / len(selected_sites))
        time.sleep(0.5)

    status.write("Scan complete.")

    deals = build_deal_rows(all_raw_results, min_profit)

    st.subheader("Results")

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Raw Listings Found", len(all_raw_results))
    col_b.metric("Deals Passing Filter", len(deals))
    col_c.metric("Minimum Profit", f"${min_profit:,.0f}")

    if errors:
        with st.expander("Errors / blocked searches"):
            for err in errors:
                st.write(err)

    if not deals:
        st.warning("No deals matched your profit filter. Lower minimum profit, raise max price, or try different search words.")
        st.stop()

    df = pd.DataFrame(deals)

    display_df = df.copy()
    for money_col in ["Price", "Estimated Market", "Target Offer", "Estimated Profit"]:
        display_df[money_col] = display_df[money_col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "")

    display_df["Risk"] = display_df["Risk"].apply(risk_badge)

    st.dataframe(
        display_df[
            [
                "Flip Score",
                "Title",
                "Year",
                "Price",
                "Estimated Market",
                "Target Offer",
                "Estimated Profit",
                "Risk",
                "Source"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Top Deals")

    for deal in deals:
        risk_text = risk_badge(deal["Risk"])

        with st.container(border=True):
            st.markdown(f"### {deal['Title']}")
            st.write(f"**Source:** {deal['Source']}")
            st.write(f"**Listed Price:** ${deal['Price']:,.0f}")
            st.write(f"**Estimated Market Value:** ${deal['Estimated Market']:,.0f}")
            st.write(f"**Target Offer:** ${deal['Target Offer']:,.0f}")
            st.write(f"**Estimated Profit:** ${deal['Estimated Profit']:,.0f}")
            st.write(f"**Risk:** {risk_text}")
            st.write(f"**Flip Score:** {deal['Flip Score']}/100")

            if deal["Link"]:
                st.link_button("Open Listing", deal["Link"])

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Results CSV",
        csv,
        "car_flip_ai_results.csv",
        "text/csv",
        use_container_width=True
    )

else:
    st.info("Choose your settings on the left, then tap **Scan Craigslist**.")
