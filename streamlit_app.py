import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from datetime import datetime


# =========================
# PAGE SETUP
# =========================
st.set_page_config(
    page_title="Car Flip AI",
    page_icon="🚗",
    layout="wide"
)

st.title("🚗 Car Flip AI")
st.caption("Private-party car flip scanner for Craigslist / future KSL / future Facebook Marketplace")


# =========================
# SIDEBAR SETTINGS
# =========================
st.sidebar.header("Search Settings")

city = st.sidebar.selectbox(
    "Market",
    [
        "Salt Lake City, UT",
        "Provo / Orem, UT",
        "Ogden, UT",
        "Logan, UT",
        "St George, UT",
        "Columbus, OH"
    ]
)

max_price = st.sidebar.slider(
    "Max asking price",
    min_value=1000,
    max_value=25000,
    value=12000,
    step=500
)

min_profit = st.sidebar.slider(
    "Minimum estimated profit",
    min_value=500,
    max_value=5000,
    value=2000,
    step=250
)

max_miles = st.sidebar.slider(
    "Max mileage",
    min_value=50000,
    max_value=250000,
    value=180000,
    step=5000
)

scan_limit = st.sidebar.slider(
    "Listings to scan",
    min_value=10,
    max_value=120,
    value=50,
    step=10
)

st.sidebar.markdown("---")
st.sidebar.subheader("Current Sources")
st.sidebar.success("Craigslist enabled")
st.sidebar.warning("KSL coming next")
st.sidebar.warning("Facebook Marketplace manual/import later")


# =========================
# CITY URL MAP
# =========================
CRAIGSLIST_URLS = {
    "Salt Lake City, UT": "https://saltlakecity.craigslist.org/search/cto",
    "Provo / Orem, UT": "https://provo.craigslist.org/search/cto",
    "Ogden, UT": "https://ogden.craigslist.org/search/cto",
    "Logan, UT": "https://logan.craigslist.org/search/cto",
    "St George, UT": "https://stgeorge.craigslist.org/search/cto",
    "Columbus, OH": "https://columbus.craigslist.org/search/cto"
}


# =========================
# BASIC VEHICLE RULES
# =========================
GOOD_FLIP_BRANDS = [
    "toyota", "honda", "lexus", "acura",
    "mazda", "subaru",
    "ford", "chevy", "chevrolet", "gmc",
    "hyundai", "kia",
    "nissan"
]

RISKY_WORDS = [
    "salvage", "rebuilt", "mechanic special", "needs engine",
    "needs transmission", "transmission bad", "does not run",
    "not running", "blown head gasket", "overheating",
    "no title", "parts only", "project", "tow away"
]

GOOD_WORDS = [
    "clean title", "runs great", "no issues", "cold ac",
    "new tires", "new brakes", "well maintained",
    "one owner", "smog", "emissions", "service records"
]

NON_CAR_WORDS = [
    "rv", "camper", "trailer", "motorhome", "boat",
    "semi", "box truck", "f650", "sprinter camper"
]


# =========================
# HELPER FUNCTIONS
# =========================
def extract_year(text):
    match = re.search(r"\b(1998|1999|20[0-2][0-9])\b", text)
    if match:
        return int(match.group(1))
    return None


def extract_miles(text):
    text = text.lower().replace(",", "")
    patterns = [
        r"(\d{2,3})k\s*miles",
        r"(\d{2,3})k\s*mi",
        r"(\d{5,6})\s*miles",
        r"(\d{5,6})\s*mi"
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            number = int(match.group(1))
            if "k" in pattern:
                return number * 1000
            return number

    return None


def estimate_market_value(title, price, year, miles):
    title_lower = title.lower()

    value = price

    if any(brand in title_lower for brand in ["toyota", "honda", "lexus", "acura"]):
        value += 2500
    elif any(brand in title_lower for brand in ["mazda", "subaru"]):
        value += 1800
    elif any(brand in title_lower for brand in ["ford", "chevy", "chevrolet", "gmc"]):
        value += 1500
    elif any(brand in title_lower for brand in ["hyundai", "kia", "nissan"]):
        value += 1200
    else:
        value += 700

    if year:
        if year >= 2015:
            value += 1800
        elif year >= 2010:
            value += 1000
        elif year >= 2005:
            value += 400
        else:
            value -= 500

    if miles:
        if miles < 100000:
            value += 1500
        elif miles < 140000:
            value += 800
        elif miles < 180000:
            value += 200
        else:
            value -= 1000

    return max(value, price)


def calculate_score(title, price, year, miles, description):
    score = 50
    full_text = f"{title} {description}".lower()

    if any(brand in full_text for brand in GOOD_FLIP_BRANDS):
        score += 15

    if any(word in full_text for word in GOOD_WORDS):
        score += 15

    if any(word in full_text for word in RISKY_WORDS):
        score -= 35

    if price <= 4000:
        score += 15
    elif price <= 8000:
        score += 10
    elif price <= 12000:
        score += 5
    else:
        score -= 5

    if year:
        if 2008 <= year <= 2018:
            score += 10
        elif year < 2005:
            score -= 10

    if miles:
        if miles <= 120000:
            score += 10
        elif miles <= 180000:
            score += 3
        else:
            score -= 15

    return max(0, min(score, 100))


def risk_level(score, description):
    description = description.lower()

    if any(word in description for word in RISKY_WORDS):
        return "High Risk"

    if score >= 75:
        return "Low Risk"
    elif score >= 55:
        return "Medium Risk"
    else:
        return "High Risk"


def buy_decision(score, estimated_profit, risk):
    if risk == "High Risk":
        return "SKIP"

    if score >= 75 and estimated_profit >= min_profit:
        return "BUY / CALL NOW"

    if score >= 60 and estimated_profit >= min_profit:
        return "CHECK / NEGOTIATE"

    return "SKIP"


def get_craigslist_listings(base_url, limit):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    params = {
        "max_price": max_price,
        "auto_title_status": 1
    }

    response = requests.get(base_url, headers=headers, params=params, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    listings = []

    cards = soup.select("li.cl-static-search-result")

    if not cards:
        cards = soup.select(".result-row")

    for card in cards[:limit]:
        title = ""
        price = None
        link = ""
        location = ""

        title_el = card.select_one(".title")
        price_el = card.select_one(".price")
        link_el = card.select_one("a")
        location_el = card.select_one(".location")

        if title_el:
            title = title_el.get_text(" ", strip=True)

        if price_el:
            price_text = price_el.get_text(strip=True)
            price_numbers = re.sub(r"[^\d]", "", price_text)
            if price_numbers:
                price = int(price_numbers)

        if link_el and link_el.get("href"):
            link = link_el.get("href")

        if location_el:
            location = location_el.get_text(" ", strip=True)

        if not title or not price:
            continue

        title_lower = title.lower()

        if any(word in title_lower for word in NON_CAR_WORDS):
            continue

        year = extract_year(title)
        miles = extract_miles(title)

        estimated_value = estimate_market_value(title, price, year, miles)
        estimated_profit = estimated_value - price

        score = calculate_score(title, price, year, miles, title)
        risk = risk_level(score, title)
        decision = buy_decision(score, estimated_profit, risk)

        listings.append({
            "Decision": decision,
            "Score": score,
            "Risk": risk,
            "Title": title,
            "Price": price,
            "Est. Value": estimated_value,
            "Est. Profit": estimated_profit,
            "Year": year,
            "Miles": miles,
            "Location": location,
            "Link": link
        })

    return listings


# =========================
# MAIN APP
# =========================
st.subheader("Scanner")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Market", city)

with col2:
    st.metric("Max Price", f"${max_price:,}")

with col3:
    st.metric("Min Profit", f"${min_profit:,}")

with col4:
    st.metric("Max Miles", f"{max_miles:,}")


if st.button("🚀 Scan Craigslist"):
    with st.spinner("Scanning private-party listings..."):
        try:
            base_url = CRAIGSLIST_URLS[city]
            results = get_craigslist_listings(base_url, scan_limit)

            if not results:
                st.warning("No listings found. Try raising max price or changing market.")
            else:
                df = pd.DataFrame(results)

                df = df[df["Price"] <= max_price]

                df = df[
                    (df["Miles"].isna()) |
                    (df["Miles"] <= max_miles)
                ]

                df = df.sort_values(
                    by=["Decision", "Est. Profit", "Score"],
                    ascending=[True, False, False]
                )

                buy_count = len(df[df["Decision"] == "BUY / CALL NOW"])
                check_count = len(df[df["Decision"] == "CHECK / NEGOTIATE"])
                skip_count = len(df[df["Decision"] == "SKIP"])

                c1, c2, c3 = st.columns(3)

                with c1:
                    st.metric("Buy Now", buy_count)

                with c2:
                    st.metric("Check / Negotiate", check_count)

                with c3:
                    st.metric("Skip", skip_count)

                st.markdown("---")

                for _, row in df.iterrows():
                    if row["Decision"] == "BUY / CALL NOW":
                        box = st.success
                    elif row["Decision"] == "CHECK / NEGOTIATE":
                        box = st.warning
                    else:
                        box = st.info

                    box(
                        f"""
                        **{row['Decision']}** — Score: **{row['Score']}** — Risk: **{row['Risk']}**

                        **{row['Title']}**

                        Asking Price: **${row['Price']:,}**  
                        Estimated Value: **${row['Est. Value']:,}**  
                        Estimated Profit: **${row['Est. Profit']:,}**

                        Year: **{row['Year']}**  
                        Miles: **{row['Miles']}**  
                        Location: **{row['Location']}**

                        [Open Listing]({row['Link']})
                        """
                    )

                st.markdown("---")
                st.subheader("Full Table")

                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )

                csv = df.to_csv(index=False).encode("utf-8")

                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"car_flip_ai_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )

        except Exception as e:
            st.error("Scanner error")
            st.code(str(e))


# =========================
# INSTRUCTIONS
# =========================
st.markdown("---")
st.subheader("Notes")

st.write(
    """
    This version scans Craigslist owner listings and gives a basic flip score.
    It is intentionally conservative. Use it to find leads, then verify:
    title status, VIN, mileage, engine/transmission condition, market comps,
    fees, transport, auction values, and repair cost.
    """
)

st.info("Next upgrade: KSL source, Telegram alerts, VIN decoder, and partner profiles.")
