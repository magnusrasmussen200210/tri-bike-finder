"""Sending messages through a Telegram bot."""
import html

import requests

from .common import Listing


class Telegram:
    def __init__(self, token: str, chat_id: str, dry_run: bool = False):
        self.token, self.chat_id, self.dry_run = token, chat_id, dry_run

    def send(self, text: str) -> None:
        if self.dry_run or not self.token:
            print("--- TELEGRAM (not sent) ---\n" + text + "\n")
            return
        r = requests.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            data={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
            timeout=30)
        r.raise_for_status()


def find_chat_id(token: str) -> str | None:
    """The chat id of whoever last messaged the bot (used once during setup)."""
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30)
    r.raise_for_status()
    for upd in reversed(r.json().get("result", [])):
        msg = upd.get("message") or upd.get("edited_message")
        if msg:
            return str(msg["chat"]["id"])
    return None


SOURCE_NAMES = {"buycycle": "buycycle", "kleinanzeigen": "Kleinanzeigen"}


def euro(v: float | None) -> str:
    return "price not given" if v is None else f"€{v:,.0f}".replace(",", ".")


def format_listing(l: Listing, previous_price: float | None = None) -> str:
    kind = "frameset" if l.is_frameset else "tri bike"
    head = (f"📉 Price drop · {SOURCE_NAMES[l.source]}" if previous_price
            else f"🚲 New {kind} · {SOURCE_NAMES[l.source]}")
    lines = [f"<b>{html.escape(head)}</b>", html.escape(l.title)]
    if previous_price:
        lines.append(f"💶 <b>{euro(l.price)}</b> (was {euro(previous_price)})")
    else:
        lines.append(f"💶 <b>{euro(l.price)}</b>")
    details = []
    if l.brand:
        details.append(l.brand.title())
    if l.year:
        details.append(str(l.year))
    if l.is_frameset:
        details.append("frameset only")
    if l.location:
        details.append(l.location)
    if l.brakes == "unknown":
        details.append("brakes not stated, check the photos")
    if details:
        lines.append("ℹ️ " + html.escape(" · ".join(details)))
    lines.append("📈 Estimated profit: coming once the price model has enough data")
    lines.append(html.escape(l.url))
    return "\n".join(lines)
