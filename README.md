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
