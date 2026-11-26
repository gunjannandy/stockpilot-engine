#!/usr/bin/env bash
# Set one Pages secret from the VM's .env without the value ever touching a command line, a log or the screen.
#   scripts/cutover/set-secret.sh NAME [project] [production|preview]
# The value goes from .env to wrangler's stdin. Run it from the repo root on the VM.
set -euo pipefail
name="${1:?usage: set-secret.sh NAME [project] [production|preview]}"
project="${2:-stockpilotgn}"
envname="${3:-production}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
case "$name" in *[!A-Za-z0-9_]*|"") echo "bad name" >&2; exit 2 ;; esac
# Read the one line for NAME (not the whole file into the environment). Strip one pair of quotes.
value="$(grep -E "^(export )?${name}=" "${SP_ENV_FILE:-$root/.env}" | tail -1 | sed -E "s/^(export )?${name}=//; s/^\"(.*)\"\$/\1/; s/^'(.*)'\$/\1/")" || true
[ -n "$value" ] || { echo "$name is not in the .env file" >&2; exit 1; }
wr="${WRANGLER:-wrangler}"
printf '%s' "$value" | (cd "$root/web" && "$wr" pages secret put "$name" --project-name "$project" ${envname:+--env "$envname"} >/dev/null)
unset value
echo "$name set on $project ($envname)."
