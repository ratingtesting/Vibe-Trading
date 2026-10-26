#!/usr/bin/env bash
# jev_ask.sh — ask Jev one question, print the JSON decision.
#
# The arguments go through files because the request text carries dollar signs,
# apostrophes and percent signs that inline shell quoting mangles. Same pattern
# as the parent project's tmp/p1-ask.sh.
set -uo pipefail
REQ_FILE="$1"
CAND_FILE="$2"
exec ~/bin/jev-route --request "$(cat "$REQ_FILE")" --candidates "$(cat "$CAND_FILE")"
