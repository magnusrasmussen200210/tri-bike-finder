"""One check of all sites. Run every 15 minutes by a systemd timer.

    python -m finder.main             normal run
    python -m finder.main --dry-run   print messages instead of sending them
    python -m finder.main --test      send a test message to Telegram
"""
import argparse
import os
import sys
import traceback
from pathlib import Path

from . import buycycle, kleinanzeigen
from .common import MAX_PRICE, Blocked, Listing, make_session
from .db import DB
from .telegram import Telegram, find_chat_id, format_listing

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {"buycycle": buycycle, "kleinanzeigen": kleinanzeigen}
MAX_DETAIL_FETCHES = 25      # per site per run, keeps each run short
MIN_PRICE = 150              # below this it's almost never a real bike
# Many sellers never mention brakes. Old rim-brake tri bikes are mostly cheap, so ads
# without brake info are still sent from this price, marked "brakes not stated".
UNKNOWN_BRAKES_MIN_PRICE = 1200
PRICE_DROP_ALERT = 0.05      # tell me when a sent bike drops 5% or more
BLOCKED_RUNS_BEFORE_WARNING = 4


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def qualifies(l: Listing) -> bool:
    if l.price is None or not MIN_PRICE <= l.price <= MAX_PRICE:
        return False
    if l.brakes == "disc":
        return True
    return l.brakes == "unknown" and l.price >= UNKNOWN_BRAKES_MIN_PRICE


def from_row(row) -> Listing:
    return Listing(source=row["source"], listing_id=row["listing_id"], url=row["url"],
                   title=row["title"] or "", price=row["price"], location=row["location"] or "",
                   description=row["description"] or "", brand=row["brand"] or "",
                   year=row["year"], is_frameset=bool(row["is_frameset"]),
                   brakes=row["brakes"] or "unknown")


def check_source(name: str, mod, db: DB, tg: Telegram, session) -> None:
    first_run = db.count(name) == 0
    try:
        listings = mod.search(session)
    except Blocked as e:
        db.log_run(name, "blocked", message=str(e))
        db.commit()
        recent = db.recent_statuses(name, BLOCKED_RUNS_BEFORE_WARNING + 1)
        if (recent[:BLOCKED_RUNS_BEFORE_WARNING] == ["blocked"] * BLOCKED_RUNS_BEFORE_WARNING
                and (len(recent) <= BLOCKED_RUNS_BEFORE_WARNING
                     or recent[BLOCKED_RUNS_BEFORE_WARNING] != "blocked")):
            tg.send(f"⚠️ {name} has blocked the bike finder for the last hour. "
                    "Tell Claude in the project so it can switch to the backup.")
        return

    if not listings:
        # A page change can make the parser find nothing; say so rather than go quiet.
        db.log_run(name, "empty")
        db.commit()
        if db.recent_statuses(name, 4) == ["empty"] * 4:
            tg.send(f"⚠️ The bike finder found 0 listings on {name} for an hour. "
                    "The site may have changed; tell Claude in the project.")
        return

    new_count, fetched = 0, 0
    for l in listings:
        is_new, prev_price = db.upsert(l)
        row = db.get(name, l.listing_id)
        if first_run:
            db.mark_alerted(l)  # don't flood the phone with everything already for sale
            continue
        if is_new:
            new_count += 1
        if not row["enriched"] and not row["alerted"] and fetched < MAX_DETAIL_FETCHES:
            try:
                l = mod.enrich(session, l)
                db.save_details(l)
                fetched += 1
            except Blocked:
                raise
            except Exception:
                traceback.print_exc()
                continue
        elif row["enriched"]:
            stored = from_row(db.get(name, l.listing_id))
            l = stored
        if not db.get(name, l.listing_id)["enriched"]:
            continue  # wait for details next run
        if not qualifies(l):
            continue
        if not row["alerted"]:
            tg.send(format_listing(l))
            db.mark_alerted(l)
        elif prev_price and l.price and l.price <= prev_price * (1 - PRICE_DROP_ALERT):
            tg.send(format_listing(l, previous_price=prev_price))
        db.commit()

    # Slowly fill in details for older listings too; the price model wants them.
    for row in db.conn.execute(
            "SELECT * FROM listings WHERE source=? AND enriched=0 ORDER BY last_seen DESC LIMIT ?",
            (name, max(0, 10 - fetched))).fetchall():
        try:
            db.save_details(mod.enrich(session, from_row(row)))
        except Blocked:
            raise
        except Exception:
            traceback.print_exc()

    db.log_run(name, "ok", found=len(listings), new=new_count)
    db.commit()
    if first_run:
        tg.send(f"✅ Now watching {name}: {len(listings)} matching listings are up right now. "
                "From here on you get a message for each new one.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--only", choices=list(SOURCES))
    args = ap.parse_args()

    load_env(ROOT / ".env")
    db = DB(os.environ.get("FINDER_DB", str(ROOT / "listings.db")))
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token and not args.dry_run:
        # Don't use up the "first run" before messages can actually be delivered.
        print("No TELEGRAM_BOT_TOKEN set yet; skipping this check.")
        db.log_run("all", "no_token")
        db.commit()
        return 0
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "") or db.setting("telegram_chat_id") or ""
    if token and not chat_id and not args.dry_run:
        # Whoever sent the bot a message is the person to notify.
        chat_id = find_chat_id(token) or ""
        if not chat_id:
            print("No Telegram chat yet: open your bot in Telegram and send it any message.")
            db.log_run("all", "no_chat")
            db.commit()
            return 1
        db.set_setting("telegram_chat_id", chat_id)
    tg = Telegram(token, chat_id, dry_run=args.dry_run)
    if args.test:
        tg.send("👋 Hi Magnus, the tri bike finder is connected and working.")
        return 0

    session = make_session()
    status = 0
    for name, mod in SOURCES.items():
        if args.only and name != args.only:
            continue
        try:
            check_source(name, mod, db, tg, session)
        except Blocked as e:
            db.log_run(name, "blocked", message=str(e))
            db.commit()
        except Exception as e:
            traceback.print_exc()
            db.log_run(name, "error", message=repr(e)[:500])
            db.commit()
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
