"""Print what the sites send back, to diagnose parsing problems from GitHub logs."""
import re
import sys

from bs4 import BeautifulSoup

from .common import make_session

URLS = sys.argv[1:] or [
    "https://www.kleinanzeigen.de/s-fahrraeder/anzeige:angebote/preis::4000/triathlon/k0c217",
    "https://www.kleinanzeigen.de/s-fahrraeder/triathlon/k0c217",
    "https://www.kleinanzeigen.de/s-triathlon/k0",
]

s = make_session()
for url in URLS:
    r = s.get(url, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    print("=" * 80)
    print("URL     ", url)
    print("final   ", r.url, "status", r.status_code, "bytes", len(r.text))
    print("title   ", soup.title.get_text(strip=True) if soup.title else None)
    print("article.aditem", len(soup.select("article.aditem")),
          "| data-adid", len(re.findall(r"data-adid", r.text)),
          "| s-anzeige links", len(re.findall(r"/s-anzeige/", r.text)))
    first = soup.select_one("article.aditem") or soup.select_one("[data-adid]")
    if first is not None:
        print("first item html:\n", str(first)[:2500])
    else:
        body = soup.body.get_text(" ", strip=True) if soup.body else r.text
        print("body text:", body[:1500])
        print("classes:", sorted({c for t in soup.find_all(class_=True) for c in t["class"]})[:120])
