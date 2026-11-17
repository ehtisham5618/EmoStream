#!/usr/bin/env bash
# Builds both browser clients with ONE build identifier, as the live worker serves them:
#   web/       product UI (Lovable design)        -> web/dist/client   served at /
#   frontend/  test and diagnostics client         -> frontend/dist     served at /diagnostics/
# The backend reports the identifier from web/dist/client/build.json; a page whose own
# identifier differs reloads itself once (stale-page protection).
#
#   bash scripts/build_frontends.sh            then   modal deploy modal/apps/serve.py
set -euo pipefail
cd "$(dirname "$0")/.."

export EMOSTREAM_BUILD="${EMOSTREAM_BUILD:-$(date -u +%Y%m%d%H%M%S)}"
echo "build id: $EMOSTREAM_BUILD"

(cd web && npm run build)
# MSYS2_ENV_CONV_EXCL: in Git Bash on Windows, "/diagnostics/" would otherwise be rewritten
# into a Windows path ("C:/Program Files/Git/diagnostics/") before Vite sees it.
(cd frontend && MSYS2_ENV_CONV_EXCL=EMOSTREAM_BASE EMOSTREAM_BASE=/diagnostics/ npm run build)
grep -q 'src="/diagnostics/assets/' frontend/dist/index.html || { echo "frontend/dist/index.html: assets not under /diagnostics/" >&2; exit 1; }

for f in web/dist/client/build.json frontend/dist/build.json; do
  grep -q "\"$EMOSTREAM_BUILD\"" "$f" || { echo "build id missing in $f" >&2; exit 1; }
done
echo "ok: web/dist/client and frontend/dist share build $EMOSTREAM_BUILD"
