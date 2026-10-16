#!/usr/bin/env bash
# Installs the tri bike finder on a fresh Ubuntu/Debian server. Safe to run again.
#   curl -fsSL https://raw.githubusercontent.com/OWNER/tri-bike-finder/main/deploy/install.sh | sudo bash -s OWNER
set -euo pipefail

OWNER="${1:?usage: install.sh <github-username>}"
REPO="https://github.com/${OWNER}/tri-bike-finder.git"
DIR=/opt/tri-bike-finder

say() { printf '\n\033[1;32m%s\033[0m\n' "$*"; }

say "1/5  Installing what the program needs..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 python3-venv sqlite3 >/dev/null

id finder >/dev/null 2>&1 || useradd --system --home "$DIR" --shell /usr/sbin/nologin finder

say "2/5  Downloading the bike finder..."
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only --quiet
else
  git clone --quiet "$REPO" "$DIR"
fi
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --quiet --upgrade pip
"$DIR/.venv/bin/pip" install --quiet -r "$DIR/requirements.txt"
chown -R finder:finder "$DIR"
git config --system --add safe.directory "$DIR"

say "3/5  Connecting your Telegram bot..."
if [ ! -s "$DIR/.env" ]; then
  echo "Paste your bot token from BotFather and press Enter."
  echo "(Nothing will appear on screen while you paste. That is normal.)"
  read -rs TOKEN < /dev/tty
  echo
  TOKEN="$(echo "$TOKEN" | tr -d '[:space:]')"
  if ! curl -fsS "https://api.telegram.org/bot${TOKEN}/getMe" >/dev/null; then
    echo "That token didn't work. Run the same command again and paste it once more."
    exit 1
  fi
  echo "Now open Telegram, go to your new bot and send it any message, like: hi"
  CHAT=""
  for _ in $(seq 1 60); do
    CHAT="$(cd "$DIR" && TOKEN="$TOKEN" .venv/bin/python -c \
      'import os; from finder.telegram import find_chat_id; print(find_chat_id(os.environ["TOKEN"]) or "")' \
      2>/dev/null || true)"
    [ -n "$CHAT" ] && break
    sleep 5
  done
  if [ -z "$CHAT" ]; then
    echo "I didn't see your message to the bot. Run the same command again to retry."
    exit 1
  fi
  umask 077
  printf 'TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=%s\n' "$TOKEN" "$CHAT" > "$DIR/.env"
  chown finder:finder "$DIR/.env"
fi
(cd "$DIR" && runuser -u finder -- .venv/bin/python -m finder.main --test)

say "4/5  Setting it to check every 15 minutes..."
cp "$DIR/deploy/tri-bike-finder.service" "$DIR/deploy/tri-bike-finder.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tri-bike-finder.timer >/dev/null

say "5/5  Running the first check now (this takes a few minutes)..."
systemctl start tri-bike-finder.service || true
sqlite3 "$DIR/listings.db" "SELECT source, status, found, message FROM runs ORDER BY rowid DESC LIMIT 2" || true

say "All done! You should have messages in Telegram. You can close this window."
