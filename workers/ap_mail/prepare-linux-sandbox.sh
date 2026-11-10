#!/usr/bin/env bash
# Install the sandbox from the pinned Playwright browser, never the runner's
# globally writable preinstalled Chrome directory. Only used on ephemeral CI.
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = 'true'

sandbox_source="$(node -e "const path=require('node:path');const {chromium}=require('./workers/ap_mail/node_modules/playwright');process.stdout.write(path.join(path.dirname(chromium.executablePath()),'chrome_sandbox'))")"
test -f "$sandbox_source"
test ! -L "$sandbox_source"

sandbox_directory=/usr/local/libexec/hwfc-ap-mail
sudo install -d -o root -g root -m 0755 "$sandbox_directory"
for directory in / /usr /usr/local /usr/local/libexec "$sandbox_directory"; do
  test ! -L "$directory"
  test "$(stat -c '%u' "$directory")" = '0'
  test "$((8#$(stat -c '%a' "$directory") & 0022))" = '0'
done
sudo install -o root -g root -m 4755 "$sandbox_source" "$sandbox_directory/chrome-sandbox"
test "$(stat -c '%u:%a' "$sandbox_directory/chrome-sandbox")" = '0:4755'
printf '%s\n' 'CHROME_DEVEL_SANDBOX=/usr/local/libexec/hwfc-ap-mail/chrome-sandbox' >> "$GITHUB_ENV"
