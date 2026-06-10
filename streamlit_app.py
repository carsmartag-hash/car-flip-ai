import re
import time
import math
import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

# ==========================================
# CAR FLIP AI — Craigslist Streamlit App
# Works on Streamlit Cloud / GitHub / iPhone
# ==========================================

st.set_page_config(
    page_title="Car Flip AI",
    page_icon="🚗",
    layout="wide"
)

# -----------------------------
# SETTINGS
# -----------------------------

DEFAULT_MARKET = "Salt Lake City / Utah"
DEFAULT_MIN_PRICE = 500
DEFAULT_MAX_PRICE = 15000
DEFAULT_MIN_PROFIT = 2000

CRAIGSLIST_AREAS = {
    "Salt Lake City / Utah": [
        "saltlakecity",
        "provo",
        "ogden"
    ],
    "Columbus Ohio": [
        "columbus"
    ],
    "Denver Colorado": [
        "denver"
    ],
    "Las Vegas Nevada": [
        "lasvegas"
    ],
}

GOOD_WORDS = [
    "clean title",
    "clean",
    "title in hand",
    "runs great",
    "runs good",
    "no issues",
    "new tires",
    "new battery",
    "new brakes",
    "well maintained",
    "maintenance records",
    "smog",
    "emissions",
    "must sell",
    "need gone",
    "priced to sell",
    "moving",
    "cash only",
    "obo",
    "best offer",
    "firm but",
    "low miles",
    "one owner",
]

BAD_WORDS = [
    "salvage",
    "rebuilt",
    "branded title",
    "mechanic special",
    "parts only",
    "does not run",
    "doesn't run",
    "not running",
    "blown",
    "bad engine",
    "bad transmission",
    "transmission problem",
    "head gasket",
    "overheating",
    "needs engine",
    "needs transmission",
    "no title",
    "lien",
    "impound",
    "tow away",
    "project",
    "rust",
    "frame damage",
]

STRONG_FLIP_MAKES = [
    "toyota", "honda", "lexus", "acura",
    "mazda", "subaru",
    "ford", "chevy", "chevrolet", "gmc",
    "hyundai", "kia",
    "nissan",
]

HIGH_RISK_MAKES = [
    "bmw", "mercedes", "audi", "volkswagen", "vw",
    "mini", "land rover", "jaguar", "porsche",
    "maserati", "volvo"
]

BAD_BODY_WORDS = [
    "rv", "camper", "motorhome", "trailer", "boat",
    "atv", "utv", "motorcycle", "scooter",
    "semi", "tractor", "box truck", "bus"
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

def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def extract_price(text):
    if not text:
        return None
    match = re.search(r"\$[\s]*([0-9,]+)", text)
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except Exception:
        return None


def extract_year(text):
    if not text:
        return None
    match = re.search(r"\b(19[8-9][0-9]|20[0-2][0-9])\b", text)
    if match:
        year = int(match.group(1))
        if 1980 <= year <= 2026:
            return year
    return None


def extract_miles(text):
    if not text:
        return None

    text_low = text.lower()

    patterns = [
        r"([0-9]{2,3})[, ]?([0-9]{3})\s*(miles|mi|mile)",
        r"([0-9]{2,3})k\s*(miles|mi)?",
        r"miles[:\s]+([0-9,]+)",
        r"odometer[:\s]+([0-9,]+)",
    ]

    for p in patterns:
        m = re.search(p, text_low)
        if m:
            try:
                if "k" in p:
                    return int(m.group(1)) * 1000
                if len(m.groups()) >= 2 and m.group(2).isdigit():
                    return int(m.group(1) + m.group(2))
                return int(m.group(1).replace(",", ""))
            except Exception:
                pass

    return None


def get_make(title):
    title_low = title.lower()
    makes = [
        "toyota", "honda", "lexus", "acura", "mazda", "subaru",
        "ford", "chevy", "chevrolet", "gmc", "dodge", "ram",
        "jeep", "nissan", "infiniti", "hyundai", "kia",
        "bmw", "mercedes", "audi", "volkswagen", "vw",
        "mini", "land rover", "jaguar", "porsche",
        "volvo", "mitsubishi", "cadillac", "buick", "lincoln",
        "chrysler", "tesla"
    ]

    for make in makes:
        if re.search(rf"\b{re.escape(make)}\b", title_low):
            return make.title()

    return "Unknown"


def is_probably_car(title):
    title_low = title.lower()

    for bad in BAD_BODY_WORDS:
        if bad in title_low:
            return False

    has_year = extract_year(title_low) is not None
    has_make = get_make(title_low) != "Unknown"

    return has_year or has_make


def estimate_market_value(title, price, year=None, miles=None):
    """
    Simple flip estimate.
    This is not KBB/MMR. It is a practical private-party quick-sale estimate.
    """

    if not price:
        return None

    title_low = title.lower()
    make = get_make(title).lower()

    multiplier = 1.28

    if make in ["toyota", "honda", "lexus", "acura"]:
        multiplier += 0.17
    elif make in ["mazda", "subaru"]:
        multiplier += 0.10
    elif make in ["ford", "chevy", "chevrolet", "gmc"]:
        multiplier += 0.08
    elif make in ["hyundai", "kia", "nissan"]:
        multiplier += 0.05
    elif make in HIGH_RISK_MAKES:
        multiplier -= 0.10

    if year:
        age = 2026 - year
        if age <= 6:
            multiplier += 0.08
        elif age <= 12:
            multiplier
