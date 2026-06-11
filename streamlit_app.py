import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from urllib.parse import quote_plus

# =========================
# MOBILE-FIRST PAGE SETUP
# =========================

st.set_page_config(
    page_title="Car Flip AI",
    page_icon="🚗",
    layout="centered"
)

# =========================
# MOBILE CSS
# =========================

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.2rem;
        padding-left: 1rem;
        padding-right: 1rem;
        max-width: 720px;
    }

    div[data-testid="stMetric"] {
        background-color: #111827;
        padding: 14px;
        border-radius: 14px;
        border: 1px solid #374151;
    }

    div.stButton > button {
        height: 3.3rem;
        font-size: 1.1rem;
        border-radius: 14px;
        font-weight: 700;
    }

    a {
        text-decoration: none;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# =========================
# MARKETS
# =========================

MARKETS = {
    "Salt Lake City Metro, UT": {
        "site": "saltlakecity",
        "postal": "84107"
    },
    "Ogden, UT": {
        "site": "ogden",
        "postal": "84401"
    },
    "Provo / Orem, UT": {
        "site": "provo",
        "postal": "84601"
    },
    "Las Vegas, NV": {
        "site": "lasvegas",
        "postal": "89101"
    },
    "Columbus, OH": {
        "site": "columbus",
        "postal": "43082"
    }
}

BAD_TITLE_WORDS = [
    "rv", "motorhome", "camper", "trailer", "semi", "tractor",
    "box truck", "food truck", "bus", "boat", "atv", "utv",
    "snowmobile", "forklift", "parts only", "part out",
    "motorcycle", "scooter"
]

GOOD_BRANDS = [
    "toyota", "honda", "lexus", "acura", "mazda", "subaru",
    "ford", "chevy", "chevrolet", "gmc", "nissan", "hyundai",
    "kia", "scion"
]

RISKY_BRANDS = [
    "bmw", "mercedes", "audi", "volkswagen", "vw", "mini",
    "land rover", "range rover", "jaguar", "porsche",
    "maserati", "volvo"
]

WARNING_WORDS = [
    "mechanic", "needs work", "not running", "doesn't run",
    "bad engine", "bad motor", "bad transmission", "transmission issue",
    "overheating", "salvage", "rebuilt", "project", "no title",
    "check engine", "blown head gasket"
]

# =========================
# FUNCTIONS
# =========================

def clean_price(text):
    if not text:
        return None

    text = text.replace(",", "")
    match = re.search(r"\$?\s*(\d{3,6})", text)

    if match:
        return int(match.group(1))

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
        r"(\d{2,3})\s?k\s*miles",
        r"(\d{2,3})\s?k\s*mi",
        r"(\d{5,6})\s*miles",
        r"(\d{5,6})\s*mi",
        r"odometer[:\s]+(\d{5,6})",
        r"mileage[:\s]+(\d{5,6})"
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            value = int(match.group(1))

            if value < 1000:
                return value * 1000

            return value

    return None


def has_bad_title(title):
    title = title.lower()
    return any(word in title for word in BAD_TITLE_WORDS)


def estimate_retail(title, year, mileage, ask):
    if not ask:
        return None

    title_lower = title.lower()
    current_year = datetime.now().year

    if year:
        age = current_year - year
    else:
        age = 12

    if ask <= 2500:
        retail = ask + 2500
    elif ask <= 5000:
        retail = ask + 3200
    elif ask <= 8000:
        retail = ask + 3500
    elif ask <= 12000:
        retail = ask + 3800
    else:
        retail = ask + 3000

    if any(brand in title_lower for brand in GOOD_BRANDS):
        retail += 900

    if any(brand in title_lower for brand in RISKY_BRANDS):
        retail -= 1200

    if mileage:
        if mileage <= 90000:
            retail += 1000
        elif mileage <= 130000:
            retail += 400
        elif mileage <= 170000:
            retail -= 600
        else:
            retail -= 1500

    if age <= 8:
        retail += 700
    elif age >= 17:
        retail -= 700

    return max(retail, ask)


def estimate_recon(title, mileage):
    title_lower = title.lower()

    recon = 900

    if mileage:
        if mileage > 130000:
            recon += 500
        if mileage > 170000:
            recon += 900

    if any(brand in title_lower for brand in RISKY_BRANDS):
        recon += 1200

    if any(word in title_lower for word in WARNING_WORDS):
        recon += 1800

    return recon


def score_listing(title, price, retail, recon, mileage, target_profit, max_mileage):
    if not price or not retail:
        return 0, "SKIP", 0

    profit = retail - price - recon
    title_lower = title.lower()

    score = 50

    if profit >= target_profit:
        score += 28
    elif profit >= target_profit * 0.70:
        score += 14
    else:
        score -= 18

    if mileage:
        if mileage <= max_mileage:
            score += 10
        else:
            score -= 18
    else:
        score -= 4

    if any(brand in title_lower for brand in GOOD_BRANDS):
        score += 10

    if any(brand in title_lower for brand in RISKY_BRANDS):
        score -= 15

    if any(word in title_lower for word in WARNING_WORDS):
        score -= 20

    if has_bad_title(title):
        score -= 50

    score = max(0, min(100, score))

    if score >= 80 and profit >= target_profit:
        decision = "BUY TARGET"
    elif score >= 65:
        decision = "WATCH / NEGOTIATE"
    elif score >= 50:
        decision = "CHECK MANUALLY"
    else:
        decision = "SKIP"

    return score, decision, profit


def build_url(market, radius, min_price, max_price, query):
    site = MARKETS[market]["site"]
    postal = MARKETS[market]["postal"]

    url = (
        f"https://{site}.craigslist.org/search/cto"
        f"?postal={postal}"
        f"&search_distance={radius}"
        f"&min_price={min_price}"
        f"&max_price={max_price}"
        f"&bundleDuplicates=1"
        f"&sort=date"
    )

    if query.strip():
        url += f"&query={quote_plus(query.strip())}"

    return url


def fetch_page(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive"
    }

    response = requests.get(url, headers=headers, timeout=25)
    return response.status_code, response.text


def parse_listings(html):
    soup = BeautifulSoup(html, "html.parser")
    listings = []

    # Craigslist current static layout
    rows = soup.select("li.cl-static-search-result")

    for row in rows:
        title_el = row.select_one(".title")
        price_el = row.select_one(".price")
        location_el = row.select_one(".location")
        link_el = row.select_one("a")

        title = title_el.get_text(" ", strip=True) if title_el else ""
        price = clean_price(price_el.get_text(" ", strip=True)) if price_el else None
        location = location_el.get_text(" ", strip=True) if location_el else ""
        url = link_el.get("href") if link_el else ""

        if title and url:
            listings.append({
                "title": title,
                "price": price,
                "location": location,
                "url": url
            })

    # Craigslist older layout fallback
    if not listings:
        rows = soup.select("li.result-row")

        for row in rows:
            title_el = row.select_one(".result-title")
            price_el = row.select_one(".result-price")
            location_el = row.select_one(".result-hood")

            title = title_el.get_text(" ", strip=True) if title_el else ""
            price = clean_price(price_el.get_text(" ", strip=True)) if price_el else None
            location = location_el.get_text(" ", strip=True) if location_el else ""
            url = title_el.get("href") if title_el else ""

            if title and url:
                listings.append({
                    "title": title,
                    "price": price,
                    "location": location,
                    "url": url
                })

    # Emergency fallback: pull listing cards from all links
    if not listings:
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(" ", strip=True)

            if "/cto/d/" in href and text:
                price = clean_price(text)
                title = re.sub(r"\$\s?\d[\d,]*", "", text).strip()

                if title:
                    listings.append({
                        "title": title,
                        "price": price,
                        "location": "",
                        "url": href
                    })

    # Remove duplicates
    clean = []
    seen = set()

    for item in listings:
        key = item["url"]

        if key not in seen:
            seen.add(key)
            clean.append(item)

    return clean


def analyze(item, target_profit, max_mileage):
    title = item["title"]
    price = item["price"]

    year = extract_year(title)
    mileage = extract_mileage(title)

    retail = estimate_retail(title, year, mileage, price)
    recon = estimate_recon(title, mileage)
    score, decision, profit = score_listing(
        title,
        price,
        retail,
        recon,
        mileage,
        target_profit,
        max_mileage
    )

    item["year"] = year
    item["mileage"] = mileage
    item["retail"] = retail
    item["recon"] = recon
    item["score"] = score
    item["decision"] = decision
    item["profit"] = profit

    return item


# =========================
# APP SCREEN
# =========================

st.title("Car Flip AI")
st.caption("Mobile Craigslist private-party scanner")

st.subheader("Settings")

market = st.selectbox(
    "Market",
    list(MARKETS.keys()),
    index=0
)

radius = st.slider(
    "Radius",
    min_value=10,
    max_value=200,
    value=85,
    step=5
)

target_profit = st.number_input(
    "Target Profit",
    min_value=500,
    max_value=10000,
    value=2000,
    step=250
)

max_mileage = st.number_input(
    "Max Mileage",
    min_value=50000,
    max_value=250000,
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

query = st.text_input(
    "Search Keyword",
    value=""
)

show_debug = st.checkbox(
    "Show debug info",
    value=True
)

search_url = build_url(
    market,
    radius,
    min_price,
    max_price,
    query
)

st.divider()

m1, m2 = st.columns(2)

with m1:
    st.metric("Market", market)

with m2:
    st.metric("Radius", f"{radius} mi")

m3, m4 = st.columns(2)

with m3:
    st.metric("Target Profit", f"${target_profit:,.0f}")

with m4:
    st.metric("Max Mileage", f"{max_mileage:,.0f}")

st.divider()

scan = st.button(
    "Scan Craigslist",
    type="primary",
    use_container_width=True
)

if scan:
    with st.spinner("Scanning Craigslist..."):
        try:
            status_code, html = fetch_page(search_url)

            if show_debug:
                st.info(f"Craigslist status code: {status_code}")
                st.write("Search URL:")
                st.code(search_url)

            if status_code != 200:
                st.error("Craigslist did not return a normal page.")
                st.write("Open this URL manually to test:")
                st.link_button("Open Craigslist Search", search_url)

                if show_debug:
                    st.write("Craigslist response preview:")
                    st.code(html[:1500])

                st.stop()

            raw = parse_listings(html)

            if not raw:
                st.warning("No listings parsed. This usually means Craigslist blocked Streamlit Cloud or changed the result layout.")

                st.write("Open this URL manually to check if Craigslist works in your browser:")
                st.link_button("Open Craigslist Search", search_url)

                if show_debug:
                    st.write("Craigslist response preview:")
                    st.code(html[:2000])

                st.stop()

            analyzed = []

            for item in raw:
                analyzed_item = analyze(item, target_profit, max_mileage)

                if analyzed_item["decision"] != "SKIP":
                    analyzed.append(analyzed_item)

            analyzed = sorted(
                analyzed,
                key=lambda x: (x["score"], x["profit"]),
                reverse=True
            )

            buy_targets = [x for x in analyzed if x["decision"] == "BUY TARGET"]
            watch_targets = [x for x in analyzed if x["decision"] == "WATCH / NEGOTIATE"]

            st.success(f"Parsed {len(raw)} listings. Showing {len(analyzed)} candidates.")

            c1, c2, c3 = st.columns(3)
            c1.metric("Buy", len(buy_targets))
            c2.metric("Watch", len(watch_targets))
            c3.metric("Parsed", len(raw))

            st.divider()

            if not analyzed:
                st.warning("Listings were found, but all were scored as SKIP. Raise mileage or lower target profit to see more.")
                st.stop()

            for item in analyzed[:60]:
                decision = item["decision"]

                if decision == "BUY TARGET":
                    icon = "🟢"
                elif decision == "WATCH / NEGOTIATE":
                    icon = "🟡"
                elif decision == "CHECK MANUALLY":
                    icon = "🟠"
                else:
                    icon = "🔴"

                with st.container(border=True):
                    st.subheader(f"{icon} {item['title']}")

                    a, b = st.columns(2)

                    with a:
                        st.metric(
                            "Ask",
                            f"${item['price']:,.0f}" if item["price"] else "N/A"
                        )

                        st.metric(
                            "Profit Est.",
                            f"${item['profit']:,.0f}"
                        )

                        st.metric(
                            "Score",
                            f"{item['score']}/100"
                        )

                    with b:
                        st.metric(
                            "Retail Est.",
                            f"${item['retail']:,.0f}" if item["retail"] else "N/A"
                        )

                        st.metric(
                            "Recon Est.",
                            f"${item['recon']:,.0f}"
                        )

                        st.metric(
                            "Mileage",
                            f"{item['mileage']:,.0f}" if item["mileage"] else "Unknown"
                        )

                    st.write(f"**Decision:** {item['decision']}")
                    st.write(f"**Location:** {item['location'] if item['location'] else 'Not shown'}")
                    st.write(f"**Year:** {item['year'] if item['year'] else 'Unknown'}")

                    st.link_button(
                        "Open Listing",
                        item["url"],
                        use_container_width=True
                    )

        except requests.exceptions.RequestException as e:
            st.error("Request failed. Craigslist may be blocking Streamlit Cloud.")
            st.code(str(e))

        except Exception as e:
            st.error("Unexpected app error.")
            st.code(str(e))

else:
    st.write("Press **Scan Craigslist** to start.")
    st.write("Current Craigslist search URL:")
    st.code(search_url)
