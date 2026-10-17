"""One-off export: every Kleinanzeigen tri bike/frame in a price range, with ad details, as JSON.

Usage: python -m finder.export MIN MAX OUT.json
"""
import json
import sys
from urllib.parse import quote

from bs4 import BeautifulSoup

from . import kleinanzeigen as ka
from .common import Blocked, fetch, make_session

MAX_PAGES = 5


def search_url(keyword: str, lo: int, hi: int, page: int) -> str:
    slug = quote(keyword.replace(" ", "-"))
    seite = f"/seite:{page}" if page > 1 else ""
    return f"{ka.BASE}/s-fahrraeder/anzeige:angebote/preis:{lo}:{hi}{seite}/{slug}/k0c217"


def ad_details(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    details = {}
    for li in soup.select(".addetailslist--detail"):
        val = li.select_one(".addetailslist--detail--value")
        if val is None:
            continue
        v = val.get_text(" ", strip=True)
        label = li.get_text(" ", strip=True).replace(v, "").strip()
        details[label] = v
    features = [el.get_text(" ", strip=True) for el in soup.select(".checktag")]
    return {"details": details, "features": features}


def main():
    lo, hi, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    s = make_session()
    found = {}
    for kw in ka.KEYWORDS:
        for page in range(1, MAX_PAGES + 1):
            items = ka.parse_search_page(fetch(s, search_url(kw, lo, hi, page)))
            new = [l for l in items if l.listing_id not in found]
            for l in new:
                if ka.is_candidate(l):
                    found[l.listing_id] = l
            print(f"{kw!r} page {page}: {len(items)} ads, {len(new)} new", flush=True)
            if len(items) < 20 or not new:
                break
    rows = []
    for l in found.values():
        if l.price is None or not lo < l.price < hi:
            continue
        try:
            html = fetch(s, l.url)
        except Blocked as e:
            print("blocked:", e, flush=True)
            break
        except Exception as e:  # ad removed meanwhile
            print("skip", l.url, e, flush=True)
            continue
        ka.parse_ad_page(html, l)
        rows.append({"id": l.listing_id, "url": l.url, "title": l.title, "price": l.price,
                     "location": l.location, "description": l.description,
                     "brand": l.brand, "year": l.year, "is_frameset": l.is_frameset,
                     "brakes": l.brakes, **ad_details(html)})
        print(f"{len(rows)}: {l.price:.0f} {l.brakes} {l.title}", flush=True)
    with open(out, "w") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print("saved", len(rows), "ads")


if __name__ == "__main__":
    main()
