import re
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import urlencode, quote_plus

st.set_page_config(
    page_title="Car Flip AI",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
.block-container {
    padding-top: 1rem !important;
    max-width: 850px !important;
}
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

SEARCH_ZIP = "84107"
SEARCH_RADIUS_MILES = 90

MIN_YEAR = 2008
MIN_PRICE = 1000
MAX_PRICE = 16000
MAX_MILES = 190000

MIN_TARGET_PROFIT = 2000
SAFETY_DISCOUNT = 1000
SELLING_COST_BUFFER = 500

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

BAD_WORDS = [
    "flat tow", "flat-tow", "dinghy tow", "dinghy", "toad",
    "tow behind", "rv tow", "motorhome tow",
    "mechanic special", "project car", "parts car", "parts only",
    "for parts", "not running", "does not run", "doesn't run",
    "wont run", "won't run", "no start", "bad engine", "needs engine",
    "blown engine", "bad transmission", "needs transmission",
    "bill of sale", "no title", "lost title", "title issue",
    "camper", "rv", "motorhome", "school bus", "box truck",
    "semi", "tractor", "trailer"
]

RISK_WORDS = [
    "salvage", "rebuilt", "branded", "hail", "water damage",
    "flood", "airbag", "frame damage", "check engine", "cel",
    "overheating", "misfire", "rough idle", "oil leak",
    "coolant leak", "needs work", "as is"
]

GOOD_MODELS = [
    "toyota camry", "toyota corolla", "toyota rav4", "toyota highlander",
    "toyota sienna", "honda accord", "honda civic", "honda cr-v",
    "honda crv", "honda pilot", "lexus rx", "lexus es",
    "mazda 3", "mazda cx-5", "subaru outback", "subaru forester",
    "hyundai elantra", "hyundai sonata", "kia optima", "kia forte",
    "ford f-150", "ford f150", "chevy silverado",
    "chevrolet silverado", "gmc sierra", "toyota tacoma", "toyota tundra"
]

BAD_MODELS = [
    "ford focus", "ford fiesta", "nissan altima", "nissan sentra",
    "nissan versa", "chevy cruze", "chevrolet cruze", "chevy sonic",
    "dodge dart", "mini cooper", "range rover", "land rover"
]


def money(value):
    if value is None:
        return "N/A"
    try:
        return "${:,.0f}".format(float(value))
    except Exception:
        return "N/A"


def clean_text(text):
    if not text:
        return ""
    text = BeautifulSoup(str(text), "html.parser").get_text(" ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_price(text):
    if not text:
        return None
    match = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})", text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def parse_year(text):
    if not text:
        return None
    match = re.search(r"\b(19[8-9][0-9]|20[0-2][0-9])\b", text)
    if not match:
        return None
    year = int(match.group(1))
    if 1980 <= year <= 2027:
        return year
    return None


def parse_miles(text):
    if not text:
        return None

    t = text.lower().replace(",", "")

    patterns = [
        r"\b([0-9]{2,3})\s*k\s*(mi|miles|mile)?\b",
        r"\b([0-9]{5,6})\s*(mi|miles|mile|odometer)\b",
        r"(miles|mile|odometer)\D{0,12}([0-9]{5,6})\b"
    ]

    for pattern in patterns:
        match = re.search(pattern, t)

        if match:
            nums = [g for g in match.groups() if g and g.isdigit()]
            if not nums:
                continue

            raw = int(nums[-1])

            if raw < 1000:
                raw = raw * 1000

            if 10000 <= raw <= 350000:
                return raw

    return None


def craigslist_rss_url():
    params = {
        "postal": SEARCH_ZIP,
        "search_distance": SEARCH_RADIUS_MILES,
        "min_price": MIN_PRICE,
        "max_price": MAX_PRICE,
        "auto_title_status": 1,
        "sort": "date",
        "format": "rss"
    }

    return "https://saltlakecity.craigslist.org/search/cto?" + urlencode(params)


def fetch_craigslist_rss():
    url = craigslist_rss_url()

    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        return [], "Craigslist RSS failed: " + str(e)

    soup = BeautifulSoup(r.text, "xml")
    items = soup.find_all("item")

    listings = []

    for item in items:
        title = clean_text(item.title.get_text(" ")) if item.title else ""
        link = clean_text(item.link.get_text(" ")) if item.link else ""
        desc = clean_text(item.description.get_text(" ")) if item.description else ""

        combined = title + " " + desc

        ask = parse_price(combined)
        year = parse_year(combined)
        miles = parse_miles(combined)

        if not title or ask is None:
            continue

        listings.append({
            "title": title,
            "ask": ask,
            "year": year,
            "miles": miles,
            "city": "Salt Lake City area",
            "url": link,
            "source": "Craigslist RSS",
            "raw_text": combined
        })

    return listings, None


def normalize_title(title):
    title = title.lower()
    title = re.sub(r"\$[0-9,]+", " ", title)
    title = re.sub(r"\b(19[8-9][0-9]|20[0-2][0-9])\b", " ", title)
    title = re.sub(r"[^a-z0-9 ]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def dedupe(listings):
    seen = set()
    clean = []

    for car in listings:
        price_bucket = int(round(car["ask"] / 500) * 500)
        key = normalize_title(car["title"]) + "|" + str(price_bucket)

        if key in seen:
            continue

        seen.add(key)
        clean.append(car)

    return clean


def contains_any(text, words):
    text = text.lower()
    hits = []
    for word in words:
        if word in text:
            hits.append(word)
    return hits


def estimate_retail(car):
    title = car["title"].lower()
    year = car["year"] or 2012
    miles = car["miles"] or 150000
    ask = car["ask"]

    if any(m in title for m in GOOD_MODELS):
        base = 13500
    elif any(m in title for m in BAD_MODELS):
        base = 8200
    elif "truck" in title or "silverado" in title or "f150" in title or "f-150" in title or "sierra" in title or "tacoma" in title:
        base = 14500
    elif "suv" in title or "rav4" in title or "cr-v" in title or "pilot" in title or "highlander" in title:
        base = 13000
    else:
        base = 10500

    retail = base
    retail += (year - 2012) * 450
    retail -= max(0, miles - 100000) * 0.035

    max_markup = ask * 1.35 + 1800
    retail = min(retail, max_markup)
    retail = max(retail, ask * 1.05)
    retail = min(retail, 26000)

    return int(round(retail / 100) * 100)


def estimate_recon(car):
    title = car["title"].lower()
    year = car["year"] or 2012
    miles = car["miles"] or 150000

    recon = 700

    if miles > 130000:
        recon += 350

    if miles > 160000:
        recon += 450

    if year < 2012:
        recon += 300

    risk_hits = contains_any(title, RISK_WORDS)
    recon += len(risk_hits) * 300

    if any(m in title for m in BAD_MODELS):
        recon += 500

    if "bmw" in title or "audi" in title or "mercedes" in title or "mini" in title or "volkswagen" in title:
        recon += 700

    return int(round(recon / 50) * 50)


def max_buy(retail, recon):
    value = retail - recon - SAFETY_DISCOUNT - SELLING_COST_BUFFER - MIN_TARGET_PROFIT
    return int(round(value / 50) * 50)


def evaluate(car):
    title = car["title"]
    ask = car["ask"]
    year = car["year"]
    miles = car["miles"]

    bad_hits = contains_any(title, BAD_WORDS)

    if bad_hits:
        car["show"] = False
        car["reason"] = "Rejected: contains '" + bad_hits[0] + "'"
        return car

    if year is None:
        car["show"] = False
        car["reason"] = "Rejected: year unknown"
        return car

    if year < MIN_YEAR:
        car["show"] = False
        car["reason"] = "Rejected: older than " + str(MIN_YEAR)
        return car

    if miles is None:
        car["show"] = False
        car["reason"] = "Rejected: mileage unknown"
        return car

    if miles > MAX_MILES:
        car["show"] = False
        car["reason"] = "Rejected: mileage over " + str(MAX_MILES)
        return car

    retail = estimate_retail(car)
    recon = estimate_recon(car)
    buy = max_buy(retail, recon)
    profit = retail - ask - recon - SAFETY_DISCOUNT - SELLING_COST_BUFFER

    score = 50

    if ask <= buy:
        score += 25
    elif ask <= buy + 750:
        score += 10
    else:
        score -= 25

    if profit >= 3500:
        score += 20
    elif profit >= MIN_TARGET_PROFIT:
        score += 10
    else:
        score -= 20

    if miles <= 90000:
        score += 12
    elif miles <= 130000:
        score += 6
    elif miles > 160000:
        score -= 12

    if any(m in title.lower() for m in GOOD_MODELS):
        score += 10

    if any(m in title.lower() for m in BAD_MODELS):
        score -= 18

    score = max(0, min(100, score))

    if profit >= MIN_TARGET_PROFIT and score >= 60:
        car["show"] = True
        car["status"] = "BUY CHECK" if score >= 78 and ask <= buy else "WATCH"
    else:
        car["show"] = False
        car["status"] = "SKIP"

    car["score"] = score
    car["estimated_retail"] = retail
    car["estimated_recon"] = recon
    car["suggested_max_buy"] = buy
    car["estimated_profit"] = int(round(profit / 50) * 50)
    car["reason"] = "Evaluated with max-buy formula"

    return car


def links_for(car):
    query = quote_plus(car["title"])
    year = quote_plus(str(car["year"] or ""))

    return {
        "KBB Value": "https://www.kbb.com/whats-my-car-worth/",
        "KBB Comps": "https://www.kbb.com/cars-for-sale/cars/" + year + "/?searchText=" + query,
        "Cars.com": "https://www.cars.com/shopping/results/?keyword=" + query + "&maximum_distance=100&zip=" + SEARCH_ZIP,
        "CarGurus": "https://www.cargurus.com/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action?zip=" + SEARCH_ZIP + "&distance=" + str(SEARCH_RADIUS_MILES),
        "KSL": "https://cars.ksl.com/search/keyword/" + query
    }


st.title("🚗 Car Flip AI")
st.caption("ZIP " + SEARCH_ZIP + " · " + str(SEARCH_RADIUS_MILES) + " mile radius · Craigslist owner listings")

st.info("App is scanning automatically. If no BUY cars show, open rejected listings at the bottom.")

if st.button("Refresh Scan"):
    st.rerun()

raw, error = fetch_craigslist_rss()

if error:
    st.error(error)
    st.stop()

unique = dedupe(raw)

shown = []
skipped = []

for car in unique:
    checked = evaluate(car)

    if checked.get("show"):
        shown.append(checked)
    else:
        skipped.append(checked)

shown = sorted(
    shown,
    key=lambda x: (x.get("score", 0), x.get("estimated_profit", 0) or 0),
    reverse=True
)

st.write("### Scan Summary")
st.write("Raw listings found: **" + str(len(raw)) + "**")
st.write("After duplicate cleanup: **" + str(len(unique)) + "**")
st.write("Shown as possible deals: **" + str(len(shown)) + "**")
st.write("Rejected / skipped: **" + str(len(skipped)) + "**")

if len(raw) == 0:
    st.warning("Craigslist returned zero listings. This is a source issue, not your filter.")
    st.link_button("Open Craigslist Search", craigslist_rss_url().replace("&format=rss", ""))

if shown:
    st.write("## Possible Deals")

for i, car in enumerate(shown):
    st.divider()

    if car["status"] == "BUY CHECK":
        st.success(car["status"] + " — Score " + str(car["score"]) + "/100")
    else:
        st.warning(car["status"] + " — Score " + str(car["score"]) + "/100")

    st.subheader(car["title"])

    st.write("**Ask:** " + money(car["ask"]))
    st.write("**Year:** " + str(car["year"]))
    st.write("**Miles:** " + "{:,}".format(car["miles"]))
    st.write("**Estimated Retail:** " + money(car["estimated_retail"]))
    st.write("**Estimated Recon:** " + money(car["estimated_recon"]))
    st.write("**Estimated Profit at Ask:** " + money(car["estimated_profit"]))

    st.markdown("### Suggested Max Buy: " + money(car["suggested_max_buy"]))

    if car["url"]:
        st.link_button("Open Listing", car["url"])

    comp_links = links_for(car)

    c1, c2 = st.columns(2)

    with c1:
        st.link_button("KBB Value", comp_links["KBB Value"])
        st.link_button("Cars.com", comp_links["Cars.com"])
        st.link_button("KSL", comp_links["KSL"])

    with c2:
        st.link_button("KBB Comps", comp_links["KBB Comps"])
        st.link_button("CarGurus", comp_links["CarGurus"])

    with st.expander("Manual KBB adjustment"):
        kbb_value = st.number_input(
            "Paste KBB Private Party Value",
            min_value=0,
            max_value=100000,
            step=100,
            key="kbb_" + str(i)
        )

        if kbb_value > 0:
            kbb_max_buy = max_buy(kbb_value, car["estimated_recon"])
            kbb_profit = kbb_value - car["ask"] - car["estimated_recon"] - SAFETY_DISCOUNT - SELLING_COST_BUFFER

            st.write("**KBB-Based Max Buy:** " + money(kbb_max_buy))
            st.write("**KBB-Based Profit at Ask:** " + money(kbb_profit))

            if car["ask"] <= kbb_max_buy:
                st.success("KBB supports this deal.")
            else:
                st.error("Too expensive based on your KBB number.")

if not shown:
    st.warning("No cars passed the buy filter. Check rejected listings below to see exactly why.")

with st.expander("Rejected / skipped listings", expanded=True):
    if not skipped:
        st.write("No rejected listings.")
    else:
        for car in skipped[:150]:
            st.write(
                "**"
                + car.get("title", "Unknown")
                + "** — "
                + money(car.get("ask"))
                + " — "
                + car.get("reason", "")
            )
