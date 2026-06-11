import re
import math
import time
import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import urlencode, urljoin

# =========================
# APP SETTINGS
# =========================

ZIP_CODE = "84107"
SEARCH_RADIUS = 90
MIN_PRICE = 1000
MAX_PRICE = 16000
MIN_PROFIT = 2000
MAX_MILES = 220000

CRAIGSLIST_BASE = "https://saltlakecity.craigslist.org"
CRAIGSLIST_SEARCH = f"{CRAIGSLIST_BASE}/search/cto"

st.set_page_config(
    page_title="Car Flip AI",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# =========================
# MOBILE UI
# =========================

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
    border: 1px solid rgba(250,250,250,0.16);
    border-radius: 18px;
    padding: 16px;
    margin-bottom: 14px;
    background: rgba(255,255,255,0.035);
}

.buy-card {
    border: 1px solid rgba(50, 220, 140, 0.40);
    background: rgba(50, 220, 140, 0.08);
}

.reject-card {
    border: 1px solid rgba(255, 120, 120, 0.25);
    background: rgba(255, 120, 120, 0.045);
}

.small-muted {
    color: rgba(255,255,255,0.62);
    font-size: 0.92rem;
}

.big-number {
    font-size: 1.25rem;
    font-weight: 800;
}

.badge-buy {
   
