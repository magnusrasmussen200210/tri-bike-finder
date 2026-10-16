"""kleinanzeigen.de: keyword searches in "Fahrräder & Zubehör" (category 217)."""
import json
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from .common import (Listing, MAX_PRICE, fetch, parse_price, detect_brakes, detect_frameset,
                     find_brand, find_year, looks_like_accessory, is_wanted_ad)

BASE = "https://www.kleinanzeigen.de"
KEYWORDS = [
    "triathlon", "zeitfahrrad", "speedmax", "speed concept", "specialized shiv",
    "giant trinity", "cervelo p", "quintana roo", "triathlon rahmen",
]


def search_url(keyword: str) -> str:
    slug = quote(keyword.replace(" ", "-"))
    # Offers only (no "Suche" ads), price up to MAX_PRICE, newest first is the default.
    return f"{BASE}/s-fahrraeder/anzeige:angebote/preis::{MAX_PRICE}/{slug}/k0c217"


def _ld_json(art) -> dict:
    tag = art.find("script", type="application/ld+json")
    try:
        return json.loads(tag.string or "") if tag else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _price_text(art) -> str | None:
    # Old layout has a dedicated class; the 2026 layout is Tailwind, so take the first
    # paragraph with a euro sign that isn't the struck-through old price.
    el = art.select_one(".aditem-main--middle--price-shipping--price, "
                        ".aditem-main--middle--price")
    if el:
        return el.get_text(" ", strip=True)
    for p in art.find_all("p"):
        classes = " ".join(p.get("class", []))
        text = p.get_text(" ", strip=True)
        if "line-through" in classes:
            continue
        if "€" in text or "verschenken" in text.lower():
            return text
    return None


def _location_text(art) -> str:
    el = art.select_one(".aditem-main--top--left")
    if el is None:
        icon = art.find("svg", attrs={"data-title": "locationOutline"})
        el = icon.parent if icon is not None else None
    return " ".join(el.get_text(" ", strip=True).split()) if el is not None else ""


def parse_search_page(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for art in soup.select("article[data-adid]"):
        ad_id = art.get("data-adid")
        link = art.select_one("h2 a, h3 a, a.ellipsis")
        href = art.get("data-href") or (link.get("href") if link is not None else None)
        if not ad_id or not href:
            continue
        ld = _ld_json(art)
        title = (link.get_text(" ", strip=True) if link is not None else "") or ld.get("title", "")
        desc_el = art.select_one(".aditem-main--middle--description")
        desc = ld.get("description") or (desc_el.get_text(" ", strip=True) if desc_el else "")
        out.append(Listing(
            source="kleinanzeigen", listing_id=ad_id,
            url=href if href.startswith("http") else BASE + href,
            title=title,
            price=parse_price(_price_text(art)),
            location=_location_text(art),
            description=desc,
            brand=find_brand(title), year=find_year(f"{title} {desc}"),
            is_frameset=detect_frameset(title),
            brakes=detect_brakes(f"{title} {desc}"),
        ))
    return out


def parse_ad_page(html: str, listing: Listing) -> Listing:
    soup = BeautifulSoup(html, "html.parser")
    desc_el = soup.select_one("#viewad-description-text")
    if desc_el:
        listing.description = desc_el.get_text(" ", strip=True)[:4000]
    details = " ".join(el.get_text(" ", strip=True)
                       for el in soup.select("#viewad-details, .addetailslist"))
    price_el = soup.select_one("#viewad-price")
    if price_el:
        listing.price = parse_price(price_el.get_text(" ", strip=True)) or listing.price
    blob = f"{listing.title} {listing.description} {details}"
    listing.brakes = detect_brakes(blob)
    listing.year = listing.year or find_year(blob)
    listing.brand = listing.brand or find_brand(blob)
    return listing


def is_candidate(listing: Listing) -> bool:
    """Worth keeping at all: a bike or frame, not a part, not a 'wanted' ad."""
    return not looks_like_accessory(listing.title) and not is_wanted_ad(listing.title)


def search(session) -> list[Listing]:
    results: dict[str, Listing] = {}
    for kw in KEYWORDS:
        for l in parse_search_page(fetch(session, search_url(kw))):
            if is_candidate(l):
                results.setdefault(l.listing_id, l)
    return list(results.values())


def enrich(session, listing: Listing) -> Listing:
    return parse_ad_page(fetch(session, listing.url), listing)
