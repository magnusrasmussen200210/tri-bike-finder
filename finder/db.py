"""SQLite storage: every listing ever seen plus its price history (for the later price model)."""
import json
import sqlite3
from datetime import datetime, timezone

from .common import Listing

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    source       TEXT NOT NULL,
    listing_id   TEXT NOT NULL,
    url          TEXT NOT NULL,
    title        TEXT,
    brand        TEXT,
    year         INTEGER,
    is_frameset  INTEGER,
    brakes       TEXT,
    location     TEXT,
    description  TEXT,
    price        REAL,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    enriched     INTEGER DEFAULT 0,
    alerted      INTEGER DEFAULT 0,
    extra        TEXT,
    PRIMARY KEY (source, listing_id)
);
CREATE TABLE IF NOT EXISTS price_history (
    source      TEXT NOT NULL,
    listing_id  TEXT NOT NULL,
    price       REAL,
    seen_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    started_at  TEXT NOT NULL,
    source      TEXT NOT NULL,
    status      TEXT NOT NULL,
    found       INTEGER,
    new         INTEGER,
    message     TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def count(self, source: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM listings WHERE source=?", (source,)).fetchone()[0]

    def get(self, source: str, listing_id: str):
        return self.conn.execute(
            "SELECT * FROM listings WHERE source=? AND listing_id=?",
            (source, listing_id)).fetchone()

    def upsert(self, l: Listing, enriched: bool = False) -> tuple[bool, float | None]:
        """Save a listing. Returns (is_new, previous_price)."""
        ts = now()
        row = self.get(l.source, l.listing_id)
        if row is None:
            self.conn.execute(
                "INSERT INTO listings (source, listing_id, url, title, brand, year, is_frameset,"
                " brakes, location, description, price, first_seen, last_seen, enriched, extra)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (l.source, l.listing_id, l.url, l.title, l.brand, l.year, int(l.is_frameset),
                 l.brakes, l.location, l.description, l.price, ts, ts, int(enriched),
                 json.dumps(l.extra)))
            self._price(l, ts)
            return True, None
        prev = row["price"]
        self.conn.execute(
            "UPDATE listings SET last_seen=?, price=COALESCE(?, price),"
            " title=COALESCE(NULLIF(?, ''), title) WHERE source=? AND listing_id=?",
            (ts, l.price, l.title, l.source, l.listing_id))
        if l.price is not None and l.price != prev:
            self._price(l, ts)
        return False, prev

    def save_details(self, l: Listing):
        self.conn.execute(
            "UPDATE listings SET title=?, brand=?, year=?, is_frameset=?, brakes=?, location=?,"
            " description=?, price=COALESCE(?, price), enriched=1"
            " WHERE source=? AND listing_id=?",
            (l.title, l.brand, l.year, int(l.is_frameset), l.brakes, l.location,
             l.description, l.price, l.source, l.listing_id))

    def mark_alerted(self, l: Listing):
        self.conn.execute("UPDATE listings SET alerted=1 WHERE source=? AND listing_id=?",
                          (l.source, l.listing_id))

    def log_run(self, source, status, found=0, new=0, message=""):
        self.conn.execute("INSERT INTO runs VALUES (?,?,?,?,?,?)",
                          (now(), source, status, found, new, message))

    def recent_statuses(self, source: str, n: int) -> list[str]:
        return [r[0] for r in self.conn.execute(
            "SELECT status FROM runs WHERE source=? ORDER BY rowid DESC LIMIT ?", (source, n))]

    def _price(self, l: Listing, ts: str):
        self.conn.execute("INSERT INTO price_history VALUES (?,?,?,?)",
                          (l.source, l.listing_id, l.price, ts))

    def commit(self):
        self.conn.commit()
