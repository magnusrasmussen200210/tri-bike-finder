"""Offline tests with small hand-made pages shaped like the real sites."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finder import buycycle, kleinanzeigen, main as finder_main  # noqa: E402
from finder.common import (Listing, detect_brakes, detect_frameset, looks_like_accessory,
                           parse_price)  # noqa: E402
from finder.db import DB  # noqa: E402

KA_SEARCH = """
<ul id="srchrslt-adtable">
<li class="ad-listitem"><article class="aditem" data-adid="3516130920"
  data-href="/s-anzeige/giant-trinity-advanced-pro-1/3516130920-217-4862">
 <div class="aditem-main--top--left"> 63571 Gelnhausen (12 km)</div>
 <h2 class="text-module-begin"><a class="ellipsis" href="/s-anzeige/giant-trinity-advanced-pro-1/3516130920-217-4862">Giant Trinity Advanced Pro 1 Disc - Carbon</a></h2>
 <p class="aditem-main--middle--description">Top Zustand, hydraulische Scheibenbremse, Gr. M</p>
 <p class="aditem-main--middle--price-shipping--price">3.250 € VB</p>
</article></li>
<li class="ad-listitem"><article class="aditem" data-adid="3522581623"
  data-href="/s-anzeige/sidi-wire-2/3522581623-217-8021">
 <h2><a class="ellipsis" href="/s-anzeige/sidi-wire-2/3522581623-217-8021">Sidi Wire 2 Carbon Rennradschuhe Triathlon</a></h2>
 <p class="aditem-main--middle--price-shipping--price">120 € VB</p>
</article></li>
<li class="ad-listitem"><article class="aditem" data-adid="3522627425"
  data-href="/s-anzeige/triathlonrad/3522627425-217-17417">
 <h2><a class="ellipsis" href="/s-anzeige/triathlonrad/3522627425-217-17417">Triathlonrad</a></h2>
 <p class="aditem-main--middle--description">Gebraucht, fährt gut</p>
 <p class="aditem-main--middle--price-shipping--price">700 € VB</p>
</article></li>
</ul>"""

KA_AD = """<h1 id="viewad-title">Triathlonrad</h1><h2 id="viewad-price">650 € VB</h2>
<p id="viewad-description-text">Cube Aerium 2019, Felgenbremsen, Shimano 105.</p>"""

BC_SEARCH = """
<a href="/en-de/product/speedmax-cf-8-disc-2021-93392"><img alt=""><p>Canyon</p>
 <p>Speedmax CF 8 Disc 2021</p><span>€2.870</span></a>
<a href="/en-de/product/speedmax-cf-8-disc-2021-93392">Canyon Speedmax CF 8 Disc 2021</a>
<a href="/en-de/product/iax-advanced-105-di2-2024-35314">Felt IAx Advanced 105 Di2 2024 €3.280</a>
<a href="/en-de/shop/main-types/bikes/is_frameset/1">Frames</a>
"""

BC_PRODUCT = """<html><head><title>Used Felt IAx Advanced 105 Di2 2024 – € 3,280 | buycycle</title>
<script type="application/ld+json">{"@type":"Product","name":"Felt IAx Advanced 105 Di2 2024",
"brand":{"name":"Felt"},"offers":{"price":"3280","priceCurrency":"EUR"}}</script></head>
<body><nav>All Framesets</nav><div>Frameset: No</div></body></html>"""


def test_parse_price():
    assert parse_price("3.250 € VB") == 3250
    assert parse_price("€2.870") == 2870
    assert parse_price("€ 3,999") == 3999
    assert parse_price("1.299,00 €") == 1299
    assert parse_price("Zu verschenken") == 0
    assert parse_price("VB") is None


def test_brakes_and_types():
    assert detect_brakes("Speedmax CF 7 Disc 2022") == "disc"
    assert detect_brakes("Cervelo P3 mit Zipp Super-9 Disc, Felgenbremse") == "rim"
    assert detect_brakes("Cervelo P3 2016") == "unknown"
    assert detect_frameset("Canyon Speedmax Rahmenset Gr. M")
    assert not detect_frameset("Rahmenhöhe 56 cm")
    assert looks_like_accessory("Selle Italia Watt Sattel Triathlon")
    assert not looks_like_accessory("Canyon Speedmax Rahmen mit Lenker")


def test_kleinanzeigen_search():
    ls = [l for l in kleinanzeigen.parse_search_page(KA_SEARCH) if kleinanzeigen.is_candidate(l)]
    assert [l.listing_id for l in ls] == ["3516130920", "3522627425"]
    trinity = ls[0]
    assert trinity.price == 3250 and trinity.brakes == "disc"
    assert trinity.url.startswith("https://www.kleinanzeigen.de/s-anzeige/")
    assert "Gelnhausen" in trinity.location
    assert ls[1].brakes == "unknown"
    detailed = kleinanzeigen.parse_ad_page(KA_AD, ls[1])
    assert detailed.brakes == "rim" and detailed.price == 650 and detailed.year == 2019


def test_kleinanzeigen_url():
    assert kleinanzeigen.search_url("speed concept") == (
        "https://www.kleinanzeigen.de/s-fahrraeder/anzeige:angebote/preis::4000/speed-concept/k0c217")


def test_buycycle():
    ls = buycycle.parse_search_page(BC_SEARCH)
    assert sorted(l.listing_id for l in ls) == ["35314", "93392"]
    felt = next(l for l in ls if l.listing_id == "35314")
    assert felt.price == 3280
    felt = buycycle.parse_product_page(BC_PRODUCT, felt)
    assert felt.brand == "felt" and felt.price == 3280 and not felt.is_frameset


class FakeTG:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)


class FakeSource:
    def __init__(self, listings):
        self.listings = listings

    def search(self, session):
        return [Listing(**vars(l)) for l in self.listings]

    def enrich(self, session, l):
        return l


def _l(i, price, brakes="disc"):
    return Listing("kleinanzeigen", str(i), f"https://x/{i}", f"Bike {i}", price, brakes=brakes)


def test_flow(tmp_path):
    db, tg = DB(str(tmp_path / "t.db")), FakeTG()
    src = FakeSource([_l(1, 2000)])
    finder_main.check_source("kleinanzeigen", src, db, tg, None)
    assert len(tg.sent) == 1 and "Now watching" in tg.sent[0]  # first run: summary only

    src.listings += [_l(2, 3000), _l(3, 3000, brakes="rim"), _l(4, 3500, brakes="unknown")]
    finder_main.check_source("kleinanzeigen", src, db, tg, None)
    assert len(tg.sent) == 2 and "Bike 2" in tg.sent[1]

    finder_main.check_source("kleinanzeigen", src, db, tg, None)
    assert len(tg.sent) == 2  # nothing repeated

    src.listings[1] = _l(2, 2500)
    finder_main.check_source("kleinanzeigen", src, db, tg, None)
    assert len(tg.sent) == 3 and "Price drop" in tg.sent[2] and "€2.500" in tg.sent[2]
    assert db.conn.execute("SELECT COUNT(*) FROM price_history WHERE listing_id='2'").fetchone()[0] == 2
