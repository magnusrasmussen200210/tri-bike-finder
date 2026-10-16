# Tri bike finder

Checks buycycle and Kleinanzeigen every 15 minutes for triathlon bikes and framesets
with disc brakes priced up to €4,000, and sends each new one (and later price drops)
to Telegram. Every listing and price change is stored in `listings.db` (SQLite) to
train a price model later.

- `finder/main.py` one check of all sites (`--dry-run`, `--test`, `--only <site>`)
- `finder/buycycle.py`, `finder/kleinanzeigen.py` site readers
- `finder/db.py` storage: `listings`, `price_history`, `runs`
- `deploy/install.sh` one-command server install (systemd timer, auto `git pull` before each run)

Tests: `python -m pytest tests`

On the server: `journalctl -u tri-bike-finder -n 50` shows the last runs,
`sqlite3 /opt/tri-bike-finder/listings.db "select * from runs order by rowid desc limit 5"`.

## Running for free on GitHub Actions

`.github/workflows/check.yml` runs a check every 15 minutes. It needs the repository
secret `TELEGRAM_BOT_TOKEN`; the chat id is found automatically from the first message
sent to the bot (or set the `TELEGRAM_CHAT_ID` secret). The database is kept as a single
commit on the `data` branch. "Run workflow" with *dry_run* ticked tests without saving.
