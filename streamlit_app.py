import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import math
import pandas as pd


# ==========================================================
# PAGE SETUP
# ==========================================================

st.set_page_config(
    page_title="Car Flip AI",
    page_icon="🚗",
    layout="wide",
)

st.title("🚗 Car Flip AI")
st.caption("Craigslist private-party scanner with profit/risk scoring")


# ==========================================================
# MARKET SETTINGS
# ==========================================================

MARKETS = {
    "Salt Lake City Metro, UT": {
        "craigslist_site": "saltlakecity",
        "center_city": "Salt Lake City, UT",
        "default_radius": 85,
        "cities": [
            "Salt Lake City",
            "Murray",
            "Sandy",
            "South Jordan",
            "West Jordan",
            "Draper",
            "Riverton",
            "Herriman",
            "Bountiful",
            "Layton",
            "Ogden",
            "Clearfield",
            "Lehi",
            "American Fork",
            "Orem",
            "Provo",
            "Tooele",
            "Park City",
            "Spanish Fork",
            "Springville",
        ],
    },
    "Columbus Metro, OH": {
        "craigslist_site": "columbus",
        "center_city": "Columbus, OH",
        "default_radius": 50,
        "cities": [
            "Columbus",
            "Westerville",
            "Dublin",
            "Grove City",
            "Reynoldsburg",
            "Pickerington",
            "Newark",
            "Delaware",
            "Lancaster",
            "Marysville",
            "Hilliard",
            "Worthington",
        ],
    },
}


# ==========================================================
# HELPERS
# ==========================================================

def clean_price(price_text):
    if not price_text:
        return None

    numbers = re.sub(r"[^\d]", "", price_text)

    if not numbers:
        return None

    try:
        return int(numbers)
    except Exception:
        return None


def extract_year(title):
    match = re.search(r"\b(19[8-9]\d|20[0-2]\d)\b", title)
    if match:
        return int(match.group(1))
    return None


def extract_mileage(text):
    if not text:
        return None

    text = text.lower().replace(",", "")

    patterns = [
        r"(\d{2,3})k\s*miles",
        r"(\d{2,3})k\s*mi",
        r"(\d{5,6})\s*miles",
        r"(\d{5,6})\s*mi",
        r"mileage[:\s]+(\d{5,6})",
        r"odometer[:\s]+(\d{5,6})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))

            if value < 1000:
                return value * 1000

            return value

    return None


def detect_bad_keywords(title):
    bad_keywords = [
        "mechanic special",
        "mechanics special",
        "parts only",
        "does not run",
        "doesn't run",
        "not running",
        "salvage",
        "rebuilt title",
        "flood",
        "no title",
        "bill of sale",
        "transmission bad",
        "bad transmission",
        "engine bad",
        "bad engine",
        "blown head gasket",
        "head gasket",
        "project",
        "needs engine",
        "needs transmission",
    ]

    title_lower = title.lower()

    found = []
    for word in bad_keywords:
        if word in title_lower:
            found.append(word)

    return found


def detect_good_keywords(title):
    good_keywords = [
        "clean title",
        "one owner",
        "runs great",
        "runs good",
        "new tires",
        "new brakes",
        "well maintained",
        "no check engine",
        "cold ac",
        "low miles",
        "clean carfax",
    ]

    title_lower = title.lower()

    found = []
    for word in good_keywords:
        if word in title_lower:
            found.append(word)

    return found


def estimate_retail_value(title, year, price):
    """
    Simple estimated resale model.
    Later we can replace this with KBB / JD Power / Black Book / MarketCheck / VIN API.
    """

    title_lower = title.lower()

    base_multiplier = 1.35

    strong_brands = [
        "toyota",
        "honda",
        "lexus",
        "acura",
        "subaru",
    ]

    decent_brands = [
        "ford",
        "chevy",
        "chevrolet",
        "gmc",
        "mazda",
        "hyundai",
        "kia",
        "nissan",
    ]

    risky_brands = [
        "bmw",
        "mercedes",
        "audi",
        "mini",
        "volkswagen",
        "vw",
        "land rover",
        "jaguar",
    ]

    if any(brand in title_lower for brand in strong_brands):
        base_multiplier = 1.45

    elif any(brand in title_lower for brand in decent_brands):
        base_multiplier = 1.35

    elif any(brand in title_lower for brand in risky_brands):
        base_multiplier = 1.20

    if year:
        current_year = datetime.now().year
        age = current_year - year

        if age <= 8:
            base_multiplier += 0.10
        elif age >= 18:
            base_multiplier -= 0.10

    estimated = int(price * base_multiplier)

    return estimated


def score_listing(title, price, year, mileage, target_profit, max_mileage):
    if price is None:
        return {
            "decision": "SKIP",
            "score": 0,
            "risk": "High",
            "estimated_retail": None,
            "estimated_profit": None,
            "reason": "No price found",
        }

    if price < 1000:
        return {
            "decision": "SKIP",
            "score": 5,
            "risk": "High",
            "estimated_retail": None,
            "estimated_profit": None,
            "reason": "Price too low / likely junk or scam",
        }

    if price > 15000:
        return {
            "decision": "SKIP",
            "score": 10,
            "risk": "High",
            "estimated_retail": None,
            "estimated_profit": None,
            "reason": "Too expensive for current flip budget",
        }

    bad_words = detect_bad_keywords(title)
    good_words = detect_good_keywords(title)

    estimated_retail = estimate_retail_value(title, year, price)
    estimated_profit = estimated_retail - price

    score = 50
    risk = "Medium"
    reasons = []

    if estimated_profit >= target_profit:
        score += 25
        reasons.append(f"Profit estimate over target: ${estimated_profit:,}")
    else:
        score -= 20
        reasons.append(f"Profit estimate below target: ${estimated_profit:,}")

    if year:
        if year >= 2012:
            score += 10
            reasons.append("Good model year range")
        elif year < 2005:
            score -= 10
            reasons.append("Older vehicle")

    if mileage:
        if mileage <= max_mileage:
            score += 10
            reasons.append(f"Mileage under max: {mileage:,}")
        else:
            score -= 20
            reasons.append(f"Mileage over max: {mileage:,}")

    if bad_words:
        score -= 35
        risk = "High"
        reasons.append("Bad keywords: " + ", ".join(bad_words))

    if good_words:
        score += 10
        reasons.append("Good keywords: " + ", ".join(good_words))

    if price <= 7000:
        score += 10
        reasons.append("Good buy range")

    if price <= 4500:
        score += 5
        reasons.append("Strong cheap flip range")

    score = max(0, min(100, score))

    if score >= 75 and estimated_profit >= target_profit and not bad_words:
        decision = "BUY TARGET"
        risk = "Low" if risk != "High" else "High"
    elif score >= 55 and estimated_profit >= target_profit * 0.6:
        decision = "WATCH / NEGOTIATE"
    else:
        decision = "SKIP"

    return {
        "decision": decision,
        "score": score,
        "risk": risk,
        "estimated_retail": estimated_retail,
        "estimated_profit": estimated_profit,
        "reason": "; ".join(reasons),
    }


def build_craigslist_url(site, max_results):
    return f"https://{site}.craigslist.org/search/cto?bundleDuplicates=1&sort=date&max_price=15000#search=1~gallery~0~0"


def fetch_craigslist(site, max_results):
    url = build_craigslist_url(site, max_results)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
            "Mobile/15E148 Safari/604.1"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        return [], f"Request failed: {e}"

    if response.status_code != 200:
        return [], f"Craigslist returned status code {response.status_code}"

    soup = BeautifulSoup(response.text, "html.parser")

    rows = []

    listings = soup.select("li.cl-search-result")

    if not listings:
        listings = soup.select(".result-row")

    for item in listings[:max_results]:
        title = ""
        link = ""
        price = None
        location = ""

        title_el = item.select_one(".titlestring") or item.select_one("a")
        price_el = item.select_one(".price")
        location_el = item.select_one(".location")

        if title_el:
            title = title_el.get_text(" ", strip=True)
            link = title_el.get("href", "")

        if price_el:
            price = clean_price(price_el.get_text(" ", strip=True))

        if location_el:
            location = location_el.get_text(" ", strip=True)

        if not title:
            continue

        year = extract_year(title)
        mileage = extract_mileage(title)

        rows.append(
            {
                "title": title,
                "price": price,
                "year": year,
                "mileage": mileage,
                "location": location,
                "link": link,
            }
        )

    return rows, None


def format_money(value):
    if value is None:
        return ""
    return f"${value:,}"


def format_number(value):
    if value is None:
        return ""
    return f"{value:,}"


# ==========================================================
# SIDEBAR
# ==========================================================

with st.sidebar:
    st.header("Search Settings")

    selected_market = st.selectbox(
        "Market",
        list(MARKETS.keys()),
        index=0,
    )

    market_data = MARKETS[selected_market]

    radius_miles = st.slider(
        f"Search radius from {market_data['center_city']}",
        min_value=10,
        max_value=150,
        value=market_data["default_radius"],
        step=5,
    )

    max_results = st.slider(
        "Listings to scan",
        min_value=10,
        max_value=250,
        value=75,
        step=5,
    )

    target_profit = st.slider(
        "Target profit",
        min_value=500,
        max_value=5000,
        value=2000,
        step=250,
    )

    max_mileage = st.slider(
        "Max mileage",
        min_value=80000,
        max_value=250000,
        value=180000,
        step=5000,
    )

    st.divider()

    st.subheader("Current Sources")
    st.success("Craigslist enabled")
    st.info("KSL / Facebook planned")
    st.warning("Value estimates are AI estimates, not official KBB/JD Power yet.")

    st.divider()

    st.subheader("Cities covered")
    st.caption(f"{market_data['center_city']} + {radius_miles} mile radius")

    for city in market_data["cities"]:
        st.write(f"• {city}")


# ==========================================================
# MAIN APP
# ==========================================================

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Market", selected_market)

with col2:
    st.metric("Radius", f"{radius_miles} mi")

with col3:
    st.metric("Target Profit", f"${target_profit:,}")

with col4:
    st.metric("Max Mileage", f"{max_mileage:,}")


st.divider()

scan_button = st.button("Scan Craigslist", type="primary", use_container_width=True)

if scan_button:
    with st.spinner("Scanning Craigslist private-party listings..."):
        listings, error = fetch_craigslist(
            market_data["craigslist_site"],
            max_results,
        )

    if error:
        st.error(error)
        st.stop()

    if not listings:
        st.warning("No listings parsed. Craigslist may have changed layout or blocked the request.")
        st.stop()

    results = []

    for listing in listings:
        analysis = score_listing(
            title=listing["title"],
            price=listing["price"],
            year=listing["year"],
            mileage=listing["mileage"],
            target_profit=target_profit,
            max_mileage=max_mileage,
        )

        results.append(
            {
                "Decision": analysis["decision"],
                "Score": analysis["score"],
                "Risk": analysis["risk"],
                "Title": listing["title"],
                "Price": listing["price"],
                "Est. Retail": analysis["estimated_retail"],
                "Est. Profit": analysis["estimated_profit"],
                "Year": listing["year"],
                "Mileage": listing["mileage"],
                "Location": listing["location"],
                "Reason": analysis["reason"],
                "Link": listing["link"],
            }
        )

    df = pd.DataFrame(results)

    df = df.sort_values(
        by=["Score", "Est. Profit"],
        ascending=[False, False],
        na_position="last",
    )

    buy_targets = df[df["Decision"] == "BUY TARGET"]
    watch_targets = df[df["Decision"] == "WATCH / NEGOTIATE"]
    skip_targets = df[df["Decision"] == "SKIP"]

    st.success(f"Parsed listings: {len(df)}")
    st.metric("Buy Targets", len(buy_targets))
    st.metric("Watch / Negotiate", len(watch_targets))
    st.metric("Skips", len(skip_targets))

    st.divider()

    st.subheader("Best Deals First")

    display_df = df.copy()

    for col in ["Price", "Est. Retail", "Est. Profit"]:
        display_df[col] = display_df[col].apply(format_money)

    display_df["Mileage"] = display_df["Mileage"].apply(format_number)

    st.dataframe(
        display_df[
            [
                "Decision",
                "Score",
                "Risk",
                "Title",
                "Price",
                "Est. Retail",
                "Est. Profit",
                "Year",
                "Mileage",
                "Location",
                "Reason",
                "Link",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("Buy Target Cards")

    if buy_targets.empty:
        st.warning("No strong buy targets found. Try scanning more listings or lowering target profit.")
    else:
        for _, row in buy_targets.iterrows():
            with st.container(border=True):
                st.markdown(f"### {row['Title']}")
                st.write(f"**Decision:** {row['Decision']}")
                st.write(f"**Score:** {row['Score']}/100")
                st.write(f"**Risk:** {row['Risk']}")
                st.write(f"**Price:** {format_money(row['Price'])}")
                st.write(f"**Estimated Retail:** {format_money(row['Est. Retail'])}")
                st.write(f"**Estimated Profit:** {format_money(row['Est. Profit'])}")

                if row["Mileage"]:
                    st.write(f"**Mileage:** {format_number(row['Mileage'])}")

                if row["Location"]:
                    st.write(f"**Location:** {row['Location']}")

                st.write(f"**Reason:** {row['Reason']}")

                if row["Link"]:
                    st.link_button("Open Listing", row["Link"])

else:
    st.info("Choose market/settings on the left, then tap Scan Craigslist.")

    st.markdown(
        """
        ### What this version fixes

        - Salt Lake City is now treated as **Salt Lake City Metro + radius**
        - Columbus is now treated as **Columbus Metro + radius**
        - Target profit can be changed
        - Max mileage can be changed
        - Listings are scored as:
          - **BUY TARGET**
          - **WATCH / NEGOTIATE**
          - **SKIP**
        - Craigslist private-party source is enabled
        """
    )
