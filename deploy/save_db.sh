#!/usr/bin/env bash
# Save listings.db as the single commit on the "data" branch.
set -euo pipefail
[ -f listings.db ] || exit 0
tmp=$(mktemp -d)
cp listings.db "$tmp/"
cd "$tmp"
git init -q -b data
git add listings.db
git -c user.name="bike-finder" -c user.email="bike-finder@users.noreply.github.com" \
  commit -q -m "Listing database"
git push -q -f "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}" data
rm -rf "$tmp"
