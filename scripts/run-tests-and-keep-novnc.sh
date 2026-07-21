#!/usr/bin/env bash
set -u -o pipefail

KEEP_NOVNC_OPEN="${KEEP_NOVNC_OPEN:-true}"
SIGNED_PDF="${SIGNED_PDF:-/app/reports/test_signed.pdf}"

pytest -m sign
test_status=$?

if [ "$test_status" -ne 0 ]; then
  exit "$test_status"
fi

case "$(printf '%s' "$KEEP_NOVNC_OPEN" | tr '[:upper:]' '[:lower:]')" in
  0|false|no)
    echo "Tests passed. KEEP_NOVNC_OPEN=false, exiting container."
    exit 0
    ;;
esac

if [ ! -f "$SIGNED_PDF" ]; then
  echo "Tests passed, but signed PDF was not found: $SIGNED_PDF" >&2
  exit 1
fi

export DISPLAY="${DISPLAY:-:99}"

review_profile_dir="$(mktemp -d /tmp/chromium-gost-review-XXXXXX)"
sleep_pid=""
browser_pid=""

cleanup() {
  if [ -n "$browser_pid" ]; then
    kill "$browser_pid" 2>/dev/null || true
  fi
  if [ -n "$sleep_pid" ]; then
    kill "$sleep_pid" 2>/dev/null || true
  fi
  rm -rf "$review_profile_dir"
  exit 0
}

trap cleanup INT TERM

chromium-gost \
  --no-sandbox \
  --disable-dev-shm-usage \
  --disable-gpu \
  --window-size=1920,1080 \
  --window-position=0,0 \
  --user-data-dir="$review_profile_dir" \
  "file://$SIGNED_PDF" &
browser_pid=$!

cat <<EOF
Tests passed. Signed PDF artifacts are available in reports/.
Chromium-Gost is left open in the noVNC session with:
  $SIGNED_PDF

Open noVNC from the host at the port mapped to container port 8081.
Stop the container manually when you are done reviewing the result.
Set KEEP_NOVNC_OPEN=false to exit immediately after successful tests.
EOF

sleep infinity &
sleep_pid=$!
wait "$sleep_pid"
