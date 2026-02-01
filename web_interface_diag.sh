#!/usr/bin/env bash
# web_interface_diag.sh
# Usage:
#   bash web_interface_diag.sh [BASE_URL]
# Example:
#   bash web_interface_diag.sh http://127.0.0.1:8081
#
# Writes all outputs into patches/web_interface_diag_YYYYmmdd_HHMMSS/

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8081}"

REPO_ROOT="$(pwd)"
PATCHES_DIR="${REPO_ROOT}/patches"
TS="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${PATCHES_DIR}/web_interface_diag_${TS}"

mkdir -p "${OUT_DIR}"

log() { printf '%s\n' "$*" | tee -a "${OUT_DIR}/_summary.txt" >/dev/null; }

log "BASE_URL=${BASE_URL}"
log "OUT_DIR=${OUT_DIR}"
log ""

# Helper: curl with sane defaults, capture body+headers separately where useful
curl_head() {
  local url="$1"
  curl -sS -D - -o /dev/null "${url}"
}

curl_body() {
  local url="$1"
  curl -sS "${url}"
}

curl_full() {
  local url="$1"
  curl -sS -D - "${url}"
}

# 0) Basic reachability
{
  log "== 0) Reachability =="
  curl_head "${BASE_URL}/" || true
} >"${OUT_DIR}/00_reachability_root_headers.txt" 2>&1

# 1) Fetch /ui/ index (first 200 lines)
{
  log "== 1) GET /ui/ (first 200 lines) =="
  curl_body "${BASE_URL}/ui/" | sed -n '1,200p'
} >"${OUT_DIR}/01_ui_index_first200.txt" 2>&1

# 2) Headers for key assets
for path in "/ui/assets/app.js" "/ui/assets/app.css"; do
  safe_name="${path#/}"
  safe_name="${safe_name//\//_}"
  {
    log "== 2) HEADERS ${path} =="
    curl_head "${BASE_URL}${path}" || true
  } >"${OUT_DIR}/02_headers_${safe_name}.txt" 2>&1
done

# 3) Detect if asset endpoints are returning HTML instead of JS/CSS
for path in "/ui/assets/app.js" "/ui/assets/app.css"; do
  safe_name="${path#/}"
  safe_name="${safe_name//\//_}"
  {
    log "== 3) BODY-SNIFF ${path} (first 40 lines) =="
    curl_body "${BASE_URL}${path}" | sed -n '1,40p'
  } >"${OUT_DIR}/03_body_sniff_${safe_name}.txt" 2>&1
done

# 4) Check for the known fatal syntax error ("async async function") in app.js
{
  log "== 4) app.js marker checks =="
  JS_TMP="${OUT_DIR}/app.js"
  curl_body "${BASE_URL}/ui/assets/app.js" >"${JS_TMP}" || true

  if [[ -s "${JS_TMP}" ]]; then
    if grep -nF "async async function" "${JS_TMP}" >/dev/null 2>&1; then
      log "FOUND: 'async async function' in app.js (fatal JS parse error)."
      grep -nF "async async function" "${JS_TMP}" | head -n 5
    else
      log "OK: no 'async async function' found in app.js."
    fi

    if grep -nF "async function renderRoute" "${JS_TMP}" >/dev/null 2>&1; then
      log "FOUND: 'async function renderRoute' marker present."
      grep -nF "async function renderRoute" "${JS_TMP}" | head -n 5
    else
      log "NOTE: 'async function renderRoute' marker NOT found (may be different build)."
    fi

    # Save a short top-of-file excerpt
    log ""
    log "-- app.js top (first 80 lines) --"
    sed -n '1,80p' "${JS_TMP}"
  else
    log "ERROR: Could not fetch app.js or it is empty."
  fi
} >"${OUT_DIR}/04_appjs_checks.txt" 2>&1

# 5) Verify /ui/ contains expected asset links (/ui/assets/app.js and /ui/assets/app.css)
{
  log "== 5) index.html asset link checks =="
  IDX_TMP="${OUT_DIR}/index.html"
  curl_body "${BASE_URL}/ui/" >"${IDX_TMP}" || true

  if [[ -s "${IDX_TMP}" ]]; then
    log "Searching for '/ui/assets/app.js' and '/ui/assets/app.css' references:"
    grep -nE "/ui/assets/app\.(js|css)" "${IDX_TMP}" || log "NOT FOUND: asset references missing in /ui/ HTML"

    log ""
    log "Searching for '#app' container:"
    grep -nE 'id=["'\'']app["'\'']' "${IDX_TMP}" || log "NOT FOUND: #app container missing in /ui/ HTML"
  else
    log "ERROR: Could not fetch /ui/ HTML or it is empty."
  fi
} >"${OUT_DIR}/05_index_asset_checks.txt" 2>&1

# 6) API sanity: verify /api routes return JSON and are not swallowed by SPA fallback
for path in "/api/ui/nav" "/api/ui/pages" "/api/am/config"; do
  safe_name="${path#/}"
  safe_name="${safe_name//\//_}"
  {
    log "== 6) API FULL RESPONSE ${path} (headers + first 200 lines of body) =="
    # Capture full response, but truncate body for readability
    curl_full "${BASE_URL}${path}" | awk '
      BEGIN { in_body=0; body_lines=0; }
      /^(\r)?$/ { in_body=1; print ""; next; }
      {
        if (!in_body) { print; }
        else {
          body_lines++;
          if (body_lines <= 200) print;
        }
      }
    '
  } >"${OUT_DIR}/06_api_${safe_name}.txt" 2>&1
done

# 7) SPA fallback check: these should return index.html (200) not 404/500
# (Adjust list if needed)
SPA_PATHS=(
  "/plugins"
  "/stage"
  "/wizards"
  "/config"
  "/logs"
  "/ui-config"
)
for path in "${SPA_PATHS[@]}"; do
  safe_name="${path#/}"
  safe_name="${safe_name//\//_}"
  {
    log "== 7) SPA FALLBACK ${path} (headers + first 40 lines) =="
    curl_full "${BASE_URL}${path}" | awk '
      BEGIN { in_body=0; body_lines=0; }
      /^(\r)?$/ { in_body=1; print ""; next; }
      {
        if (!in_body) { print; }
        else {
          body_lines++;
          if (body_lines <= 40) print;
        }
      }
    '
  } >"${OUT_DIR}/07_spa_${safe_name}.txt" 2>&1
done

# 8) Optional: show running process info (best-effort, no sudo)
{
  log "== 8) Process snapshot (best-effort) =="
  ps -ef | grep -E "plugins/web_interface/run\.py|uvicorn|fastapi|web_interface" | grep -v grep || true
} >"${OUT_DIR}/08_process_snapshot.txt" 2>&1

# 9) Summarize key outcomes in one place
{
  echo "BASE_URL=${BASE_URL}"
  echo "OUT_DIR=${OUT_DIR}"
  echo ""
  echo "Key quick reads:"
  echo " - 04_appjs_checks.txt"
  echo " - 05_index_asset_checks.txt"
  echo " - 02_headers_ui_assets_app.js.txt / 03_body_sniff_ui_assets_app.js.txt"
  echo " - 06_api_api_ui_nav.txt (and others)"
  echo ""
  echo "If app.js contains 'async async function' => fatal JS parse error => blank page."
  echo "If /ui/assets/app.js headers show Content-Type text/html or body starts with '<!doctype' => routing is swallowing assets."
  echo "If /api/* returns HTML instead of JSON => SPA fallback is swallowing API."
} >"${OUT_DIR}/_readme.txt"

log "DONE. Outputs written to: ${OUT_DIR}"
log "Open these first: ${OUT_DIR}/04_appjs_checks.txt and ${OUT_DIR}/03_body_sniff_ui_assets_app.js.txt"

