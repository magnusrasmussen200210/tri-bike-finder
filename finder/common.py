"""Shared helpers: HTTP session, price parsing, keyword checks."""
import re
import time
import random
from dataclasses import dataclass, field

import requests

MAX_PRICE = 4000

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

# Clear signs of disc brakes. These win over everything else.
STRONG_DISC_WORDS = [
    "scheibenbremse", "disc brake", "discbrake", "disc-brake", "hydraulische bremse",
    "hydraulic disc", "disc ", "disc,", "disc)", "disc/", "-disc", " disc",
]
# Weaker hints (thru axles and flat mount calipers only exist on disc bikes).
WEAK_DISC_WORDS = ["steckachse", "thru axle", "thru-axle", "flat mount", "flatmount"]
RIM_WORDS = ["felgenbremse", "rim brake", "rimbrake", "rim-brake", " rim ", "direct mount"]
# "Disc" next to these words is about a disc wheel, not brakes.
DISC_WHEEL_WORDS = ["disc wheel", "discrad", "disc-rad", "disc laufrad", "disc hinterrad",
                    "super-9 disc", "super 9 disc", "sub9 disc", "sub-9 disc", "disc rear"]

# Words that mean the ad is a part or accessory, not a bike or frame.
ACCESSORY_WORDS = [
    "schuh", "helm", "sattel", "lenker", "aufsatz", "aerobar", "extension",
    "laufrad", "laufräder", "felge", "reifen", "pedal", "trinksystem",
    "flaschenhalter", "anzug", "einteiler", "trisuit", "neopren", "wetsuit",
    "rollentrainer", "smart trainer", "tasche", "koffer", "bikebox", "bike box",
    "kurbel", "schaltwerk", "powermeter", "radcomputer", "sattelstütze", "vorbau",
    "trikot", "brille", "socken", "kassette", "scheibenrad", "bremssattel",
    "gabel ", "transporttasche", "fahrradträger",
]

# Bike models and words that only appear when the ad is a whole tri/TT bike.
BIKE_MODEL_WORDS = [
    "triathlonrad", "triathlon rad", "triathlon-rad", "triathlonfahrrad", "zeitfahrrad",
    "zeitfahrmaschine", "tt-rad", "tt rad", "tri-rad", "tri rad", "speedmax",
    "speed concept", "shiv", "trinity", "p-series", "prfive", "prfour", "pr five",
    "x-pr", "iax", "ia advanced", "e-117", "e117", "e-119", "e119", "aerodrive",
    "timemachine", "speedmachine", "plasma", "superslice", "tempus", "time warp",
    "aerorad", "alias tri", "propel advanced tri", "bolide",
]


@dataclass
class Listing:
    source: str            # "buycycle" or "kleinanzeigen"
    listing_id: str
    url: str
    title: str
    price: float | None
    location: str = ""
    description: str = ""
    brand: str = ""
    year: int | None = None
    is_frameset: bool = False
    brakes: str = "unknown"  # "disc", "rim" or "unknown"
    extra: dict = field(default_factory=dict)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    })
    return s


class Blocked(Exception):
    """The site refused us (captcha, 403, 429)."""


def fetch(session: requests.Session, url: str) -> str:
    time.sleep(random.uniform(1.5, 4.0))  # be polite, look human
    r = session.get(url, timeout=30)
    if r.status_code in (403, 429) or "captcha" in r.text[:5000].lower():
        raise Blocked(f"{url} -> HTTP {r.status_code}")
    r.raise_for_status()
    return r.text


def parse_price(text: str | None) -> float | None:
    """'3.999 € VB' -> 3999.0, '€ 2,870' -> 2870.0, 'Zu verschenken' -> 0."""
    if not text:
        return None
    t = text.strip().lower()
    if "verschenken" in t:
        return 0.0
    m = re.search(r"\d[\d.,\s]*", t)
    if not m:
        return None
    num = m.group(0).strip().replace(" ", "").replace("\u202f", "")
    num = re.sub(r"[.,]\d{1,2}$", "", num)  # drop cents: "1.299,00" -> "1.299"
    num = num.replace(".", "").replace(",", "")
    try:
        return float(num)
    except ValueError:
        return None


def _has_any(text: str, words) -> bool:
    return any(w in text for w in words)


def detect_brakes(text: str) -> str:
    t = f" {text.lower()} "
    for w in DISC_WHEEL_WORDS:
        t = t.replace(w, " ")
    if _has_any(t, STRONG_DISC_WORDS):
        return "disc"
    if _has_any(t, RIM_WORDS):
        return "rim"
    if _has_any(t, WEAK_DISC_WORDS):
        return "disc"
    return "unknown"


FRAME_RE = re.compile(r"\b(rahmen[- ]?set|rahmen|frame[- ]?set|frame only|nur rahmen)\b", re.I)


def detect_frameset(text: str) -> bool:
    return bool(FRAME_RE.search(text))


def looks_like_accessory(title: str) -> bool:
    """True when the title is clearly a part/accessory rather than a bike or frame."""
    t = f" {title.lower()} "
    if detect_frameset(t) or _has_any(t, BIKE_MODEL_WORDS):
        return False
    return _has_any(t, ACCESSORY_WORDS)


def is_wanted_ad(title: str) -> bool:
    """Kleinanzeigen 'Suche ...' ads are people looking to buy."""
    t = title.lower().strip()
    return t.startswith("suche") or t.startswith("gesucht") or " suche " in f" {t} "


def find_year(text: str) -> int | None:
    m = re.search(r"\b(20[0-3]\d)\b", text)
    return int(m.group(1)) if m else None


KNOWN_BRANDS = [
    "canyon", "cervelo", "cervélo", "trek", "specialized", "giant", "bmc", "felt",
    "quintana roo", "argon 18", "argon18", "cube", "scott", "ventum", "cannondale",
    "pinarello", "ridley", "merida", "orbea", "dimond", "boardman", "lapierre", "storck",
    "simplon", "ceepo", "kuota", "factor", "look", "colnago", "wilier", "bianchi",
    "rose", "radon", "vitus", "liv", "parlee", "diamondback", "fuji", "time", "elves",
    "airwolf", "de rosa", "basso", "focus", "stevens", "lightweight", "cipollini",
]


def find_brand(text: str) -> str:
    t = f" {text.lower()} "
    for b in KNOWN_BRANDS:
        if f" {b} " in t or t.startswith(f" {b}"):
            return {"cervélo": "cervelo", "argon18": "argon 18"}.get(b, b)
    return ""
