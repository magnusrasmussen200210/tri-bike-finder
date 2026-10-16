"""buycycle.com: triathlon category, filtered to disc brakes and max €4,000."""
import json
import re

from bs4 import BeautifulSoup

from .common import (Listing, MAX_PRICE, fetch, parse_price, detect_frameset,
                     find_brand, find_year)

BASE = "https://buycycle.com"
SEARCH_URL = (BASE + "/en-de/shop/main-types/bikes/types/road-gravel/categories/triathlon"
              f"/brake-types/disc/max-price/{MAX_PRICE}")
MAX_PAGES = 6
PRODUCT_RE = re.compile(r"/[a-z]{2}-[a-z]{2}/product/([a-z0-9-]*?-(\d+))(?:[/?#\"]|$)")


def _page_url(n: int) -> str:
    return SEARCH_URL if n == 1 else f"{SEARCH_URL}/page/{n}"


def clean_card_title(text: str) -> str:
    """'High demand 14 Orbea Custom 105 S • 2018 • Shimano' -> 'Orbea Custom 105 S'."""
    t = text.split("•")[0]
    t = re.sub(r"^\s*(high demand|new|neu|sale|reduced)\s+", "", t, flags=re.I)
    t = re.sub(r"^\s*\d+\s+", "", t)  # watch counter shown on the card
    return " ".join(t.split())


def parse_search_page(html: str) -> list[Listing]:
    """Product cards from a search page. Title/price are best-effort here."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, Listing] = {}
    for a in soup.find_all("a", href=True):
        m = PRODUCT_RE.search(a["href"] + "/")
        if not m:
            continue
        pid = m.group(2)
        text = " ".join(a.get_text(" ", strip=True).split())
        price = None
        pm = re.search(r"€\s?\d[\d.,]*", text) or re.search(r"\d[\d.,]*\s?€", text)
        if pm:
            price = parse_price(pm.group(0))
        title = clean_card_title(text.split("€")[0]) or m.group(1).replace("-", " ")
        url = f"{BASE}/en-de/product/{m.group(1)}"
        old = found.get(pid)
        if old is None or (price and not old.price) or len(title) > len(old.title):
            found[pid] = Listing(
                source="buycycle", listing_id=pid, url=url, title=title,
                price=price or (old.price if old else None), brakes="disc",
                brand=find_brand(title), year=find_year(title),
                is_frameset=detect_frameset(title),
            )
    return list(found.values())


def _json_ld_products(soup: BeautifulSoup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for it in items:
            if isinstance(it, dict) and it.get("@type") == "Product":
                yield it


def parse_product_page(html: str, listing: Listing) -> Listing:
    """Fill in reliable title, price, brand and frameset flag from the product page."""
    soup = BeautifulSoup(html, "html.parser")
    for prod in _json_ld_products(soup):
        listing.title = prod.get("name") or listing.title
        brand = prod.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")
        if brand:
            listing.brand = str(brand).lower()
        offers = prod.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if offers.get("price") and (offers.get("priceCurrency") in (None, "EUR")):
            listing.price = parse_price(str(offers["price"]))
        listing.description = (prod.get("description") or "")[:2000]
    title_tag = soup.find("title")
    page_title = title_tag.get_text(strip=True) if title_tag else ""
    # e.g. "Used Merida TIME WARP TRI 5000 – € 3,999 | buycycle"
    m = re.match(r"(?:Used|New|Gebraucht|Neu)?\s*(.*?)\s*[–-]\s*(€\s?[\d.,]+)", page_title)
    if m:
        if not listing.title or listing.title.isdigit():
            listing.title = m.group(1)
        listing.price = parse_price(m.group(2))
    body = soup.get_text(" ", strip=True)[:20000]
    # Only title/description and the spec row count: the menu always says "Framesets".
    listing.is_frameset = (
        listing.is_frameset
        or bool(re.search(r"\bframe ?set\b|\brahmenset\b",
                          f"{listing.title} {listing.description}", re.I))
        or bool(re.search(r"\b(?:frameset|rahmenset)\s*:?\s*(?:yes|ja)\b", body, re.I)))
    listing.brand = listing.brand or find_brand(listing.title)
    listing.year = listing.year or find_year(listing.title)
    return listing


def search(session) -> list[Listing]:
    results: dict[str, Listing] = {}
    for n in range(1, MAX_PAGES + 1):
        page = parse_search_page(fetch(session, _page_url(n)))
        new = [l for l in page if l.listing_id not in results]
        for l in new:
            results[l.listing_id] = l
        if not new:
            break
    return list(results.values())


def enrich(session, listing: Listing) -> Listing:
    return parse_product_page(fetch(session, listing.url), listing)
